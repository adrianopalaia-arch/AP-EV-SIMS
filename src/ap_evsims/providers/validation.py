"""Bounded, authenticated provider validation and immutable safe response capture."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from .security import load_credentials, redact, safe_quota
from .live import http_get
from ..integrity import digest, utc
from ..research_store import ResearchStore
from .quota import QuotaLedger

SPORTS = {'CFB':'americanfootball_ncaaf','NFL':'americanfootball_nfl',
          'NHL':'icehockey_nhl','MLB':'baseball_mlb','NBA':'basketball_nba'}

class ProviderValidator:
    def __init__(self, store, transport=http_get, max_odds_credits=120):
        self.store, self.transport = store, transport
        self.records = []
        self.credit_budget = max_odds_credits
        self.credits_used = 0
        self.remaining = None
        self.ledger = QuotaLedger(store.root/'quota.sqlite')
        self.remaining = self.ledger.summary()['requests_remaining']

    def request(self, provider, endpoint, parameters=None, *, historical=False, credit_cost=0):
        parameters = dict(parameters or {})
        if any(k.lower() in ('apikey','api_key','authorization') for k in parameters):
            raise ValueError('SECRET_IN_METADATA')
        key_name = 'CFBD_API_KEY' if provider == 'cfbd' else 'THE_ODDS_API_KEY'
        key = os.environ.get(key_name, '').strip()
        record = dict(provider=provider, endpoint=endpoint, parameters=parameters,
                      credential_present=bool(key), status='MISSING_CREDENTIAL', quota={},
                      snapshot_id=None, rows=0, historical=historical)
        if not key:
            self.records.append(record)
            return record, None
        if historical:
            cached = self.ledger.cached(provider,endpoint,parameters,datetime.now(timezone.utc).isoformat())
            if cached:
                manifest = self.store.manifest(cached)
                payload = self.store.payload(manifest)
                record.update(status=200,snapshot_id=cached,cached=True,
                    provider_snapshot_time=manifest['observed_at'],checked_at=manifest['fetched_at'])
                record['rows'] = len(payload.get('data',[]))
                self.records.append(record)
                return record,payload
        if provider == 'odds' and (self.credits_used + credit_cost > self.credit_budget or
                (self.remaining is not None and self.remaining < credit_cost)):
            record['status'] = 'QUOTA_BUDGET_LIMIT'
            self.records.append(record)
            return record, None
        if provider == 'cfbd':
            base = 'https://api.collegefootballdata.com/'
            headers = {'Authorization':'Bearer '+key}
            query = parameters
        elif provider == 'odds':
            base = 'https://api.the-odds-api.com/v4/'
            headers = {}
            query = dict(parameters, apiKey=key)
        else:
            raise ValueError('UNSUPPORTED_PROVIDER')
        # Only controlled endpoint paths; no authenticated URL is persisted.
        if not endpoint or '?' in endpoint or ':' in endpoint or '..' in endpoint:
            raise ValueError('INVALID_ENDPOINT')
        response = self.transport(base+endpoint+'?'+urlencode(query), headers)
        record['status'] = response.status
        record['checked_at'] = response.fetched_at
        record['quota'] = safe_quota(response.quota)
        if provider == 'odds':
            self.credits_used += record['quota'].get('x-requests-last', credit_cost)
            self.remaining = record['quota'].get('x-requests-remaining', self.remaining)
        try:
            decoded = response.body.decode('utf-8')
            sanitized = redact(decoded)
            payload = json.loads(sanitized)
        except (ValueError, UnicodeError):
            payload = None
            sanitized = json.dumps({'status':response.status,'body':'NON_JSON_RESPONSE_OMITTED'})
        if response.status == 200 and (payload is None or sanitized != decoded):
            record['status'] = 'INVALID_OR_SECRET_BEARING_RESPONSE'
            payload = None
        if response.status == 200 and isinstance(payload,dict) and 'error_code' in payload:
            record['status'] = 'PROVIDER_ERROR_PAYLOAD'
            payload = None
        observed = response.fetched_at
        basis = 'recorded_response'
        if historical and response.status == 200 and isinstance(payload, dict) and 'timestamp' in payload:
            observed = payload['timestamp']
            if utc(observed) > utc(parameters['date']):
                record['status'] = 'LOOKAHEAD_RISK'
                payload = None
                observed = response.fetched_at
            else:
                basis = 'historical_odds_snapshot'
                record['provider_snapshot_time'] = observed
        if response.body:
            # Error payloads are explicitly sanitized. Successful payload bytes are exact.
            body = response.body if response.status == 200 and payload is not None else sanitized.encode()
            manifest = self.store.archive(provider=provider, endpoint=endpoint,
                parameters={**parameters,'endpoint_status':record['status'],
                            'error_payload_sanitized':response.status != 200}, body=body,
                fetched_at=response.fetched_at, observed_at=observed, available_at=observed,
                availability_basis=basis)
            record['snapshot_id'] = manifest['snapshot_id']
        if isinstance(payload, list): record['rows'] = len(payload)
        elif isinstance(payload, dict) and isinstance(payload.get('data'), list): record['rows'] = len(payload['data'])
        if record['status'] != 200: payload = None
        self.records.append(record)
        self.ledger.record(record,immutable=historical and record['status']==200)
        return record, payload

    def run(self, historical_at='2025-10-04T16:00:00Z'):
        _, games = self.request('cfbd','games',{'year':2025,'week':6,'seasonType':'regular'})
        self.request('cfbd','plays',{'year':2025,'week':6,'team':'Alabama','seasonType':'regular'})
        self.request('cfbd','teams',{})
        self.request('cfbd','venues',{})
        self.request('cfbd','stats/game/advanced',{'year':2025,'week':6})
        self.request('cfbd','ratings/elo',{'year':2025,'week':5})
        self.request('cfbd','lines',{'year':2025,'week':6})
        if isinstance(games,list) and games:
            game_id = games[0].get('id')
            if game_id: self.request('cfbd','live/plays',{'gameId':game_id})
        self.request('odds','sports',{'all':'true'})
        current = {}
        for sport, key in SPORTS.items():
            record,payload = self.request('odds',f'sports/{key}/odds',
                {'regions':'us','markets':'h2h,spreads,totals','oddsFormat':'american'}, credit_cost=3)
            books = sorted({b['key'] for event in payload or [] for b in event.get('bookmakers',[])}) if isinstance(payload,list) else []
            record['draftkings_returned'] = 'draftkings' in books
            record['fanduel_returned'] = 'fanduel' in books
            current[sport] = record['status'] == 200
        params = {'regions':'us','markets':'h2h,spreads,totals','oddsFormat':'american','date':historical_at}
        history, payload = self.request('odds','historical/sports/americanfootball_ncaaf/odds',params,historical=True,credit_cost=30)
        success = history['status'] == 200 and isinstance(payload,dict) and isinstance(payload.get('data'),list)
        historical_dates = [history['provider_snapshot_time']] if success and payload['data'] else []
        if success:
            # One bounded early-season probe; a sampled boundary is not exhaustive coverage.
            early, early_payload = self.request('odds','historical/sports/americanfootball_ncaaf/odds',
                {**params,'date':'2020-09-05T16:00:00Z'},historical=True,credit_cost=30)
            if early['status']==200 and isinstance(early_payload,dict) and early_payload.get('data'):
                historical_dates.append(early['provider_snapshot_time'])
            event = next((e for e in payload['data'] if e.get('id')),None)
            if event:
                event_path='historical/sports/americanfootball_ncaaf/events/'+event['id']
                self.request('odds',event_path+'/markets',{'date':historical_at},historical=True,credit_cost=1)
                self.request('odds',event_path+'/odds',{'date':historical_at,'regions':'us',
                    'markets':'player_pass_yds','oddsFormat':'american'},historical=True,credit_cost=10)
        cfbd=[r for r in self.records if r['provider']=='cfbd']
        seasons = sorted({g.get('season') for g in games or [] if g.get('season') is not None}) if isinstance(games,list) else []
        return dict(generated_at=datetime.now(timezone.utc).isoformat(),
            credential_present={'cfbd':bool(os.environ.get('CFBD_API_KEY','')), 'odds_api':bool(os.environ.get('THE_ODDS_API_KEY',''))},
            cfbd_authentication='OK' if any(r['status']==200 for r in cfbd) else 'FAILED',
            cfbd_seasons_access_verified=seasons,
            cfbd_historical_feature_availability='HISTORICAL_AVAILABILITY_UNVERIFIED',
            CURRENT_ODDS_ACCESS='YES' if current.get('CFB') else 'NO',
            current_sports_access=current,
            HISTORICAL_ODDS_ACCESS='YES' if success else 'NO',
            historical_status=history['status'],
            blocker=None if success else 'BLOCKED_BY_HISTORICAL_ODDS_ACCESS',
            earliest_usable_historical_date=min(historical_dates) if historical_dates else None,
            coverage_scope='sampled endpoints only; not an exhaustive date coverage claim',
            odds_credits_consumed_this_run=self.credits_used,odds_credits_remaining=self.remaining,
            persistent_quota=self.ledger.summary(),
            endpoints=self.records)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--store',type=Path,default=Path('data'))
    parser.add_argument('--env-file',type=Path)
    parser.add_argument('--historical-at',default='2025-10-04T16:00:00Z')
    args=parser.parse_args()
    load_credentials(args.env_file)
    store=ResearchStore(args.store)
    report=ProviderValidator(store).run(args.historical_at)
    body=json.dumps(report,indent=2,allow_nan=False)
    if redact(body)!=body: raise ValueError('SECRET_IN_REPORT')
    store._immutable(store.root/'evaluations'/('provider-validation-'+digest(report)+'.json'),body.encode())
    (store.root/'evaluations'/'provider-validation-latest.json').write_text(body,encoding='utf-8')
    print(body)

if __name__=='__main__': main()

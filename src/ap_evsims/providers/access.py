"""Explicit, bounded access check; never infer historical entitlement from current odds."""
from datetime import datetime,timezone
from pathlib import Path
from .security import load_credentials
from .validation import ProviderValidator
from .live import http_get
from ..research_store import ResearchStore
from ..operations import import_local_archive
from ..warehouse import Warehouse
from ..publication import atomic_json
from ..product import card_lock,read_json


def verify_access(repo, *, transport=http_get):
    repo=Path(repo).resolve();store=ResearchStore(repo/'data');present=load_credentials(repo/'.env')
    with card_lock(store.root):
        validator=ProviderValidator(store,transport=transport,max_odds_credits=13)
        cfbd,games=validator.request('cfbd','games',{'year':2026,'week':7,'seasonType':'regular'})
        sports,_=validator.request('odds','sports',{'all':'true'})
        current,payload=validator.request('odds','sports/americanfootball_ncaaf/odds',
            {'regions':'us','markets':'h2h,spreads,totals','oddsFormat':'american'},credit_cost=3)
        books=sorted({b['key'] for e in payload or [] for b in e.get('bookmakers',[])}) if isinstance(payload,list) else []
        current.update(draftkings_returned='draftkings' in books,fanduel_returned='fanduel' in books)
        history,historical=validator.request('odds','historical/sports/americanfootball_ncaaf/odds',
            {'date':'2025-10-04T16:00:00Z','regions':'us','markets':'h2h','oddsFormat':'american'},historical=True,credit_cost=10)
        ok=history['status']==200 and isinstance(historical,dict) and isinstance(historical.get('data'),list)
        old=read_json(store.root/'evaluations/provider-validation-latest.json',{})
        report=dict(old,generated_at=datetime.now(timezone.utc).isoformat(),
            credential_present={'cfbd':present['CFBD_API_KEY'],'odds_api':present['THE_ODDS_API_KEY']},
            CURRENT_ODDS_ACCESS='YES' if current['status']==200 else 'NO',HISTORICAL_ODDS_ACCESS='YES' if ok else 'NO',
            historical_status=history['status'],blocker=None if ok else 'BLOCKED_BY_HISTORICAL_ODDS_ACCESS',
            earliest_usable_historical_date=history.get('provider_snapshot_time') if ok and historical.get('data') else None,
            coverage_scope='Only the requested historical timestamp was probed; earliest accessible provider date is not established.',
            cfbd_seasons_access_verified=sorted({g['season'] for g in games or [] if g.get('season')}) if isinstance(games,list) else [],
            cfbd_historical_feature_availability='HISTORICAL_AVAILABILITY_UNVERIFIED',
            verification_updates=old.get('verification_updates',[])+validator.records)
        atomic_json(store.root/'evaluations/provider-validation-latest.json',report)
        providers=read_json(repo/'outputs/provider_status.json',{})
        for name,r in (('cfbd',cfbd),('odds_api',current)):
            providers[name]=dict(credential_present=r['credential_present'],authentication_status='OK' if r['status']==200 else 'UNAVAILABLE',
                checked_at=r.get('checked_at'),endpoint_status=r['status'],quota_metadata=r['quota'])
        providers['odds_api'].update(historical_access=ok,historical_endpoint_status=history['status'],
            historical_checked_at=history.get('checked_at'),historical_quota=history.get('quota',{}),
            earliest_usable_historical_date=report['earliest_usable_historical_date'],coverage_scope=report['coverage_scope'],
            draftkings_returned='draftkings' in books,fanduel_returned='fanduel' in books,sports_endpoint_status=sports['status'])
        # Do not replace a feed member behind its generation manifest. daily_card
        # publishes this local access report with the next complete generation.
        atomic_json(store.root/'evaluations/application-provider-status.json',providers)
        imported=import_local_archive(store,Warehouse(store.root))
        return dict(CURRENT_ODDS_ACCESS=report['CURRENT_ODDS_ACCESS'],HISTORICAL_ODDS_ACCESS=report['HISTORICAL_ODDS_ACCESS'],
            providers=providers,import_failures=imported['failures'],blocker=report['blocker'])

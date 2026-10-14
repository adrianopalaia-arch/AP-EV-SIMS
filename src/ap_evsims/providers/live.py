"""Small real HTTP adapters. No retry loop, implicit spend sweep, or secret logging."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
import urllib.request
import urllib.error
import urllib.parse
from ..integrity import utc
from .security import safe_quota

@dataclass(frozen=True)
class HTTPResponse:
    status: int | str
    body: bytes
    fetched_at: str
    quota: dict = field(default_factory=dict)

def http_get(url, headers):
    try:
        with urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=20) as r:
            return HTTPResponse(r.status,r.read(),datetime.now(timezone.utc).isoformat(),safe_quota(r.headers))
    except urllib.error.HTTPError as e:
        return HTTPResponse(e.code,e.read(),datetime.now(timezone.utc).isoformat(),safe_quota(e.headers))
    except Exception:
        # Never stringify transport exceptions: request URLs can contain API keys.
        return HTTPResponse('NETWORK_ERROR',b'',datetime.now(timezone.utc).isoformat())

class ProviderAccessError(ValueError):
    def __init__(self, reason, status):
        self.reason,self.status=reason,status
        super().__init__(f'{reason}: endpoint_status={status}')

class CFBDClient:
    def __init__(self, store, transport=http_get): self.store,self.transport=store,transport
    def fetch(self, endpoint, **parameters):
        if endpoint not in ('games','plays','ratings/elo','ratings/core','stats/game/advanced','teams','venues','lines'):
            raise ValueError('unsupported CFBD endpoint')
        key=os.environ.get('CFBD_API_KEY','').strip()
        if not key: raise ProviderAccessError('MISSING_CFBD_CREDENTIAL',None)
        url='https://api.collegefootballdata.com/'+endpoint+'?'+urllib.parse.urlencode(parameters)
        r=self.transport(url,{'Authorization':'Bearer '+key})
        if r.status!=200: raise ProviderAccessError('CFBD_ACCESS_ERROR',r.status)
        if key.encode() in r.body: raise ValueError('SECRET_IN_PAYLOAD')
        json.loads(r.body)
        # Today's reconstruction is not a historical publication timestamp.
        return self.store.archive(provider='cfbd',endpoint=endpoint,parameters=parameters,body=r.body,
            fetched_at=r.fetched_at,observed_at=r.fetched_at,available_at=r.fetched_at,availability_basis='recorded_response')

    def games(self, year, **kw): return self.fetch('games',year=year,**kw)
    def plays(self, year, week, **kw): return self.fetch('plays',year=year,week=week,**kw)
    def elo(self, year, week): return self.fetch('ratings/elo',year=year,week=week)

class OddsAPIClient:
    SPORT='americanfootball_ncaaf'
    def __init__(self,store,transport=http_get): self.store,self.transport=store,transport
    def fetch(self, *, historical_at=None):
        key=os.environ.get('THE_ODDS_API_KEY','').strip()
        if not key: raise ProviderAccessError('BLOCKED_BY_HISTORICAL_ODDS_ACCESS' if historical_at else 'MISSING_ODDS_CREDENTIAL',None)
        endpoint=('historical/' if historical_at else '')+'sports/'+self.SPORT+'/odds'
        parameters=dict(regions='us',markets='h2h,spreads,totals',oddsFormat='american')
        if historical_at: parameters['date']=utc(historical_at).isoformat()
        url='https://api.the-odds-api.com/v4/'+endpoint+'?'+urllib.parse.urlencode({**parameters,'apiKey':key})
        r=self.transport(url,{})
        if r.status!=200:
            reason='BLOCKED_BY_HISTORICAL_ODDS_ACCESS' if historical_at and r.status in (401,403,422) else 'ODDS_ACCESS_ERROR'
            raise ProviderAccessError(reason,r.status)
        if key.encode() in r.body: raise ValueError('SECRET_IN_PAYLOAD')
        payload=json.loads(r.body)
        if isinstance(payload,dict) and ('error_code' in payload or 'message' in payload):
            raise ProviderAccessError('BLOCKED_BY_HISTORICAL_ODDS_ACCESS' if historical_at else 'ODDS_ACCESS_ERROR',r.status)
        observed=payload['timestamp'] if historical_at else r.fetched_at
        if historical_at and utc(observed)>utc(historical_at): raise ValueError('LOOKAHEAD_RISK')
        return self.store.archive(provider='odds',endpoint=endpoint,parameters=parameters,body=r.body,
            fetched_at=r.fetched_at,observed_at=observed,available_at=observed,
            availability_basis='historical_odds_snapshot' if historical_at else 'recorded_response')

class WeatherClient:
    def __init__(self,store,transport=http_get): self.store,self.transport=store,transport
    def points(self,latitude,longitude):
        if not -90<=latitude<=90 or not -180<=longitude<=180: raise ValueError('invalid coordinates')
        endpoint=f'points/{latitude},{longitude}'
        r=self.transport('https://api.weather.gov/'+endpoint,{'User-Agent':'AP-EV-SIMS/3.0 research','Accept':'application/geo+json'})
        if r.status!=200: raise ProviderAccessError('WEATHER_ACCESS_ERROR',r.status)
        return self.store.archive(provider='weather',endpoint=endpoint,parameters={},body=r.body,fetched_at=r.fetched_at,
            observed_at=r.fetched_at,available_at=r.fetched_at,availability_basis='recorded_response')

    def forecast(self,url):
        parsed=urllib.parse.urlparse(url)
        if parsed.scheme!='https' or parsed.netloc!='api.weather.gov' or parsed.query or parsed.fragment:
            raise ValueError('unsupported forecast URL')
        r=self.transport(url,{'User-Agent':'AP-EV-SIMS/3.0 research','Accept':'application/geo+json'})
        if r.status!=200: raise ProviderAccessError('WEATHER_ACCESS_ERROR',r.status)
        return self.store.archive(provider='weather',endpoint=parsed.path,parameters={},body=r.body,fetched_at=r.fetched_at,
            observed_at=r.fetched_at,available_at=r.fetched_at,availability_basis='recorded_response')

def probe_access(store, *, historical_at='2025-10-04T16:00:00Z', transport=http_get):
    """Probe even absent credentials; expose only status, presence, reachability and coverage."""
    def probe(url,headers,provider,endpoint,parameters):
        r=transport(url,headers)
        # Save safe raw probe payloads too; an HTTP error is never normalized
        # as sporting data. URLs/authorization headers are not persisted.
        if r.body and not any(key and key.encode() in r.body for key in (os.environ.get('CFBD_API_KEY',''),os.environ.get('THE_ODDS_API_KEY',''))):
            store.archive(provider=provider,endpoint=endpoint,parameters={**parameters,'endpoint_status':r.status},body=r.body,
                fetched_at=r.fetched_at,observed_at=r.fetched_at,available_at=r.fetched_at,availability_basis='recorded_response')
        return r.status
    cfbd=os.environ.get('CFBD_API_KEY','').strip(); odds=os.environ.get('THE_ODDS_API_KEY','').strip()
    cfbd_status=probe('https://api.collegefootballdata.com/games?year=2025&seasonType=regular',{'Authorization':'Bearer '+cfbd} if cfbd else {},'cfbd','games',{'year':2025,'seasonType':'regular'})
    params=dict(regions='us',markets='h2h',oddsFormat='american')
    if odds: params['apiKey']=odds
    safe={k:v for k,v in params.items() if k!='apiKey'}
    current_status=probe('https://api.the-odds-api.com/v4/sports/americanfootball_ncaaf/odds?'+urllib.parse.urlencode(params),{},'odds','sports/americanfootball_ncaaf/odds',safe)
    historical_status=probe('https://api.the-odds-api.com/v4/historical/sports/americanfootball_ncaaf/odds?'+urllib.parse.urlencode({**params,'date':historical_at}),{},'odds','historical/sports/americanfootball_ncaaf/odds',{**safe,'date':historical_at})
    return [dict(provider='CFBD',provider_reachable=isinstance(cfbd_status,int),credential_present=bool(cfbd),historical_entitlement=None,endpoint_status=cfbd_status,available_seasons_date_coverage='not verified'),
            dict(provider='The Odds API',provider_reachable=isinstance(current_status,int),credential_present=bool(odds),historical_entitlement=True if historical_status==200 else False if odds and historical_status in (401,403,422) else None,endpoint_status=current_status,historical_endpoint_status=historical_status,available_seasons_date_coverage='not verified')]

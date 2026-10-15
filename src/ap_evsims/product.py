"""Local daily-card application. Market observations never masquerade as forecasts."""
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import json
from .integrity import utc, digest
from .odds import american_to_implied, devig_two_way
from .publication import atomic_json, atomic_text
from .research_store import ResearchStore
from .warehouse import Warehouse
from .operations import import_local_archive, collect_odds
from .providers.security import load_credentials
from .providers.live import http_get

MARKETS = {
    'CFB': ('Spread','Total','Moneyline'),
    'NHL': ('Shots on goal','Goalie saves','Moneyline','Total'),
    'NFL': ('Spread','Total','Receptions','Rushing attempts','Receiving yards','Passing yards','Rushing yards'),
    'MLB': ('Pitcher strikeouts','Pitcher outs','Hits allowed','Hitter hits','Total bases','Game total'),
    'NBA': ('Spread','Total','Points','Rebounds','Assists','Threes'),
}
BOOK_PRIORITY = {'draftkings':0,'fanduel':1}
BUILDERS = ('CORE singles','LEAN research','2–3 leg parlay','4–6 leg prop builder','Moneyline hammer','Tiny lotto')


@contextmanager
def card_lock(root):
    """OS-released lock: a crashed/restarted UI cannot strand a lock file."""
    path=Path(root)/'daily-card.lock';path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a+b') as handle:
        handle.seek(0,2)
        if handle.tell()==0:handle.write(b'0');handle.flush()
        handle.seek(0)
        import os
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(handle.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise ValueError('CARD_REFRESH_ALREADY_RUNNING') from None
        try:yield
        finally:
            handle.seek(0)
            if os.name=='nt':msvcrt.locking(handle.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(handle,fcntl.LOCK_UN)


def read_json(path, default):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError,ValueError):return default


def current_quotes(store,warehouse,at):
    """An omitted market in the latest full snapshot is suspended, not executable.

    Only this application's full US featured-market query can supersede a slate.
    A partial/book-specific query cannot assert that other markets disappeared.
    """
    with warehouse.connect() as db:
        sources=db.execute("SELECT snapshot_id,dataset FROM snapshots WHERE provider='odds' AND available_at<=? ORDER BY available_at DESC,snapshot_id DESC",[at]).fetchall()
    latest={}
    for sid,endpoint in sources:
        if not endpoint.startswith('sports/') or not endpoint.endswith('/odds') or endpoint in latest:continue
        m=store.manifest(sid);p=m['parameters']
        query={k:v for k,v in p.items() if k not in ('endpoint_status','error_payload_sanitized')}
        if query and (query.get('regions')!='us' or set(query.get('markets','').split(','))!={'h2h','spreads','totals'} or 'bookmakers' in query):continue
        if p.get('endpoint_status',200)==200:latest[endpoint]=sid
    quotes=warehouse.as_of_quotes(at)
    active=[q for q in quotes if q['snapshot_id'] in latest.values()]
    return active,len(quotes)-len(active)


def preflight(quotes,at,previous=()):
    pairs={}
    for q in quotes:pairs.setdefault(q['pair_id'],[]).append(q)
    key=lambda r:(r['event_id'],r['book'],r['market'],r['selection'])
    old={key(r):r for r in previous}
    rows=[]
    for q in quotes:
        others=[r for r in pairs[q['pair_id']] if r['selection']!=q['selection']]
        opposite=others[0] if len(others)==1 else None
        age=(utc(at)-utc(q['observed_at'])).total_seconds()
        reasons=['MODEL_NOT_CALIBRATED','MISSING_FEATURES','UNVERIFIED_LINEUP','QUOTE_EXECUTION_UNVERIFIED','UNKNOWN_SETTLEMENT_RULE']
        if age>180:reasons.insert(0,'STALE_PRICE')
        if age<0 or not utc(q['observed_at'])<=utc(q['available_at'])<=utc(at)<utc(q['event_start']):reasons.insert(0,'LOOKAHEAD_RISK')
        if q['sport']=='NHL':reasons.append('UNCONFIRMED_GOALIE')
        if not opposite:reasons.append('NO_MARKET_PAIR')
        prior=old.get(key(q))
        if prior and (prior['line'],prior['odds'])!=(q['line'],q['american_odds']):reasons.insert(0,'PRICE_MOVED')
        rows.append(dict(candidate_id=q['quote_id'],sport=q['sport'],event_id=q['event_id'],home_team=q['home_team'],away_team=q['away_team'],
            event_start=q['event_start'].isoformat(),book=q['book'],market=q['market'],selection=q['selection'],line=q['line'],odds=q['american_odds'],
            opposite_odds=opposite['american_odds'] if opposite else None,quote_timestamp=q['observed_at'].isoformat(),quote_age_seconds=age,
            market_implied_probability=american_to_implied(q['american_odds']),
            market_no_vig_probability=devig_two_way(q['american_odds'],opposite['american_odds'])[0] if opposite else None,
            model_probability=None,calibrated_probability=None,p_low=None,fair_odds=None,expected_value=None,max_acceptable_price=None,
            model_version=None,calibration_version=None,model_status='UNVALIDATED',decision='PASS',pass_reason=reasons,
            decision_stage='INPUT_PREFLIGHT',phase1_eligible=False,mode='PREGAME',stake=None,exposure_status='UNRECONCILED',
            source_snapshot_id=q['snapshot_id'],source_hash=q['raw_payload_hash'],
            data_timestamps=dict(event_start=q['event_start'].isoformat(),sportsbook_quote=q['observed_at'].isoformat(),
                provider_available=q['available_at'].isoformat(),ingested=q['ingested_at'].isoformat(),
                lineup_injury=None,feature_snapshot=None,model_prediction=None,decision=utc(at).isoformat())))
    return sorted(rows,key=lambda r:(BOOK_PRIORITY.get(r['book'],2),r['sport'],r['event_start'],r['event_id'],r['market'],r['selection']))


def model_catalog(rows):
    raw={'Spread':'spreads','Total':'totals','Game total':'totals','Moneyline':'h2h'}
    return [dict(sport=sport,market=market,status='UNVALIDATED',champion_model=None,model_version=None,
        observed_market_sides=sum(r['sport']==sport and r['market']==raw.get(market) for r in rows),
        real_training_sample=0,real_evaluation_sample=0,synthetic_performance_sample=0,
        probability=None,ev=None,brier_score=None,log_loss=None,roi=None,clv=None,
        blocker='NO_APPROVED_EMPIRICAL_MODEL' if market in raw else 'PROP_PRICES_AND_VERIFIED_ROLE_FEATURES_MISSING')
        for sport,markets in MARKETS.items() for market in markets]


def daily_card(repo, *, offline=False,sports=('CFB',),daily_credit_cap=24,reserve_credits=50,now=None,transport=http_get,force_refresh=False):
    repo=Path(repo).resolve();store=ResearchStore(repo/'data')
    with card_lock(store.root):
        warehouse=Warehouse(store.root)
        credentials=load_credentials(repo/'.env')
        imported=import_local_archive(store,warehouse)
        collection=None
        if not offline:
            collection=collect_odds(store,warehouse,sports=sports,daily_credit_cap=daily_credit_cap,reserve_credits=reserve_credits,transport=transport,force_refresh=force_refresh)
        # Capture the decision AFTER network responses, never backdate availability.
        at=utc(now or datetime.now(timezone.utc)).isoformat()
        quotes,suspended=current_quotes(store,warehouse,at)
        previous=read_json(repo/'outputs/latest_passes.json',[])
        rows=preflight(quotes,at,previous)
        preferred=[r for r in rows if r['book'] in BOOK_PRIORITY]
        comparisons=[r for r in rows if r['book'] not in BOOK_PRIORITY]
        from .cfb_universe import build_cfb_universe
        universe=build_cfb_universe(store,warehouse,at,quotes)
        catalog=model_catalog(rows)
        providers=read_json(store.root/'evaluations/application-provider-status.json',read_json(repo/'outputs/provider_status.json',{}))
        for name,env_name in (('cfbd','CFBD_API_KEY'),('odds_api','THE_ODDS_API_KEY')):
            providers.setdefault(name,{})['credential_present']=credentials[env_name]
        last_collection=collection or read_json(store.root/'evaluations/odds-collection-latest.json',None)
        providers['odds_api'].update(latest_collection=last_collection,refresh_mode='OFFLINE' if offline else 'BOUNDED_CURRENT_ODDS',
            historical_access_note='Separate entitlement check; current odds access does not prove historical access')
        if last_collection:
            quota=last_collection.get('quota',{})
            if quota.get('requests_remaining') is not None:
                providers['odds_api'].setdefault('quota_metadata',{}).update({
                    'x-requests-remaining':quota['requests_remaining'],'x-requests-used':quota.get('provider_requests_used')})
        failures=[r for r in (collection or {}).get('results',[]) if r['status'] not in ('ARCHIVED','CACHED_CADENCE')]
        state=read_json(repo/'TASK_STATE.json',{}); prior_last=read_json(repo/'outputs/last_update.json',{})
        values={'latest_predictions.json':[], 'latest_edges.json':[], 'latest_passes.json':preferred,
            'model_status.json':catalog,'provider_status.json':providers,'cfb_universe.json':universe}
        summary=dict(generated_at=at,status='NO QUALIFYING BETS',mode='PREGAME',
            games_scanned=len({r['event_id'] for r in rows}),market_sides_scanned=len(rows),preferred_market_sides=len(preferred),qualified_edges=0,models_validated=0,
            suspended_or_superseded_quotes=suspended,cfb_schedule_games=universe['games_scanned'],
            real_model_evaluation_sample=0,synthetic_performance_sample=0,refresh_failures=failures,
            data_quality_failures=imported['failures'],reference_unit=22,reference_unit_semantics='DISPLAY_REFERENCE_ONLY_NOT_A_STAKE',
            current_task='LOCAL_DASHBOARD_AND_DAILY_CARD',next_task='CFB verified pregame features and timestamp-authentic evaluation',
            branch=state.get('branch'),git_commit=prior_last.get('git_commit'),tests_passed=state.get('tests',{}).get('passed'),
            tests_failed=state.get('tests',{}).get('failed'),tests_semantics='Last independently run full suite, not rerun by daily_card',
            sports_updated=sorted({r['sport'] for r in rows}),providers_ok=None if offline else not failures and bool(collection) and
                all(providers.get(p,{}).get('authentication_status')=='OK' for p in ('cfbd','odds_api')),
            provider_check_basis='LAST_RECORDED_CHECKS_ONLY' if offline else 'BOUNDED_CURRENT_REFRESH_PLUS_RECORDED_CFBD_AUTH',
            card_builders=[dict(name=n,status='UNAVAILABLE',reason='NO_VALIDATED_ELIGIBLE_LEGS') for n in BUILDERS])
        generation=digest(dict(at=at,values=values));summary.update(publication_generation=generation,
            feed_hashes={name:digest(value) for name,value in values.items()},
            local_comparison_hash=digest(comparisons),
            reader_contract='Verify canonical JSON SHA256; retry if any file differs from this generation.')
        atomic_json(store.root/'snapshots'/(generation+'-comparison_markets.json'),comparisons)
        for name,value in values.items():atomic_json(store.root/'snapshots'/(generation+'-'+name),value)
        for name,value in values.items():atomic_json(repo/'outputs'/name,value)
        atomic_text(repo/'reports/MORNING_CARD.md','\n'.join(['# AP EV/SIMS Morning Card','',f'Generated: {at}',
            '', '**NO QUALIFYING BETS**','',f"Games with archived market quotes: {summary['games_scanned']}. Market sides: {len(rows)}.",
            f"CFB captured schedule universe: {universe['games_scanned']} games; query coverage is incomplete.",
            'All models UNVALIDATED. No fitted real model is approved; probability, p_low and EV remain unavailable.',
            'DraftKings first, FanDuel second, remaining books for comparison. Prices are archived observations, not execution guarantees.',
            f'Suspended or superseded quote sides withheld: {suspended}. Refresh failures: {len(failures)}.',
            'Every displayed market has explicit PASS reasons and exact line/price/source timestamps in latest_passes.json.',
            'Model evaluation sample: 0. Brier, log loss, ROI and CLV unavailable. Fixtures do not contribute performance.',
            'CORE, LEAN and parlay builders unavailable until their model, correlation and exposure requirements pass.',
            '$22 is a configurable display reference, not a bankroll or authorized stake. No wagers are placed.'])+'\n')
        atomic_json(repo/'outputs/last_update.json',summary)
        return summary


def read_card(repo):
    """Reject partially published generations instead of mixing stale and new files."""
    folder=Path(repo)/'outputs';summary=read_json(folder/'last_update.json',{})
    values={}
    for name,expected in summary.get('feed_hashes',{}).items():
        if Path(name).name!=name:raise ValueError('INVALID_FEED_PATH')
        value=read_json(folder/name,None)
        if digest(value)!=expected:raise ValueError('PUBLICATION_IN_PROGRESS_OR_HASH_MISMATCH')
        values[name]=value
    if summary.get('local_comparison_hash'):
        generation=summary.get('publication_generation','')
        if len(generation)!=64 or any(c not in '0123456789abcdef' for c in generation):raise ValueError('INVALID_GENERATION')
        local=read_json(Path(repo)/'data/snapshots'/(generation+'-comparison_markets.json'),None)
        # A remote checkout may intentionally lack private/local comparison data.
        if local is not None:
            if digest(local)!=summary['local_comparison_hash']:raise ValueError('PUBLICATION_IN_PROGRESS_OR_HASH_MISMATCH')
            values['comparison_markets.json']=local
    return summary,values

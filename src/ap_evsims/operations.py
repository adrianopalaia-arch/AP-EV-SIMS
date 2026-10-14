"""Explicit network ingestion separated from local-only research operations."""
from datetime import datetime,timezone
import json
from pathlib import Path
from .integrity import utc,digest
from .research_store import ResearchStore
from .warehouse import Warehouse
from .providers.validation import ProviderValidator,SPORTS
from .providers.live import http_get
from .publication import atomic_json,atomic_text

def import_local_archive(store,warehouse):
    counts={'snapshots_ingested':0,'snapshots_cached':0,'error_payloads_excluded':0,'quotes_inserted':0,'failures':[]}
    for path in sorted((store.root/'manifests').glob('*.json')):
        if len(path.stem)!=64:continue
        try:
            manifest=store.manifest(path.stem)
            result=warehouse.ingest_manifest(store,manifest)
            if result['status']=='PROVIDER_ERROR_EXCLUDED':counts['error_payloads_excluded']+=1;continue
            counts['snapshots_ingested' if result['status']=='INGESTED' else 'snapshots_cached']+=1
            if manifest['provider']=='odds' and manifest['endpoint'].endswith('/odds'):
                with warehouse.connect() as db:
                    already=db.execute('SELECT count(*) FROM odds_quotes WHERE snapshot_id=?',[manifest['snapshot_id']]).fetchone()[0]
                if not already:
                    recorded=warehouse.record_odds(store,manifest)
                    counts['quotes_inserted']+=recorded['quotes_inserted'];counts['failures']+=recorded['failures']
        except ValueError as error:
            counts['failures'].append(dict(snapshot_id=path.stem,reason=str(error)))
    return counts

def cadence_seconds(seconds_to_start):
    if seconds_to_start<=0:return 21600  # No live eligibility or live collection policy yet.
    if seconds_to_start<=900:return 60
    if seconds_to_start<=3600:return 300
    if seconds_to_start<=21600:return 900
    if seconds_to_start<=86400:return 3600
    return 21600

def collect_odds(store,warehouse, *, sports=('CFB',),now=None,daily_credit_cap=24,reserve_credits=50,transport=http_get):
    now=utc(now or datetime.now(timezone.utc)).isoformat()
    if daily_credit_cap<0 or reserve_credits<0:raise ValueError('INVALID_QUOTA_POLICY')
    validator=ProviderValidator(store,transport=transport,max_odds_credits=daily_credit_cap)
    ledger=validator.ledger
    with ledger.connect() as db:
        spent=db.execute('SELECT coalesce(sum(cost),0) FROM requests WHERE provider="odds" AND substr(requested_at,1,10)=?',[now[:10]]).fetchone()[0]
    result=[]
    for sport in sports:
        if sport not in SPORTS:raise ValueError('UNSUPPORTED_SPORT')
        with warehouse.connect() as db:
            row=db.execute('SELECT max(ingested_at),min(event_start) FILTER (WHERE event_start>?) FROM odds_quotes WHERE sport=?',[now,sport]).fetchone()
        if row[0]:
            age=(utc(now)-utc(row[0])).total_seconds()
            interval=cadence_seconds((utc(row[1])-utc(now)).total_seconds()) if row[1] else 21600
            if age<interval:
                result.append(dict(sport=sport,status='CACHED_CADENCE',next_refresh_seconds=max(0,interval-age)));continue
        remaining=ledger.summary()['requests_remaining']
        if spent+3>daily_credit_cap or (remaining is not None and remaining-3<reserve_credits):
            result.append(dict(sport=sport,status='QUOTA_BUDGET_LIMIT'));continue
        record,payload=validator.request('odds','sports/'+SPORTS[sport]+'/odds',
            {'regions':'us','markets':'h2h,spreads,totals','oddsFormat':'american'},credit_cost=3)
        spent+=record.get('quota',{}).get('x-requests-last',3)
        if record['status']==200:
            manifest=store.manifest(record['snapshot_id']);warehouse.ingest_manifest(store,manifest)
            result.append(dict(sport=sport,status='ARCHIVED',snapshot_id=manifest['snapshot_id'],**warehouse.record_odds(store,manifest)))
        else:result.append(dict(sport=sport,status='CURRENT_DATA_UNAVAILABLE',endpoint_status=record['status']))
    report=dict(collected_at=now,results=result,quota=ledger.summary())
    atomic_json(store.root/'evaluations/odds-collection-latest.json',report)
    return report

def sync_data(store,warehouse, *, cfbd_year=None,cfbd_week=None,transport=http_get):
    local=import_local_archive(store,warehouse)
    downloaded=[]
    if cfbd_year is not None:
        parameters={'year':cfbd_year,'seasonType':'regular'}
        if cfbd_week is not None:parameters['week']=cfbd_week
        with warehouse.connect() as db:
            rows=db.execute('SELECT parameters FROM snapshots WHERE provider=\'cfbd\' AND dataset=\'games\'').fetchall()
        metadata={'endpoint_status','error_payload_sanitized'}
        present=any({k:v for k,v in json.loads(r[0]).items() if k not in metadata}==parameters for r in rows)
        if not present:
            validator=ProviderValidator(store,transport=transport)
            record,_=validator.request('cfbd','games',parameters)
            downloaded.append(dict(endpoint='games',status=record['status']))
            if record['status']==200:warehouse.ingest_manifest(store,store.manifest(record['snapshot_id']))
    return dict(local_import=local,downloaded=downloaded,health=warehouse.health())

def data_health(store,warehouse,report_path=None):
    health=warehouse.health()
    with warehouse.connect() as db:
        health['datasets']=[dict(provider=p,dataset=d,snapshots=n,earliest=str(lo),latest=str(hi)) for p,d,n,lo,hi in
            db.execute('SELECT provider,dataset,count(*),min(available_at),max(available_at) FROM snapshots GROUP BY provider,dataset ORDER BY provider,dataset').fetchall()]
    atomic_json(store.root/'evaluations/data-health.json',health)
    if report_path:
        lines=['# Data health','',f"Source snapshots: {health['snapshots']}; source rows: {health['source_records']}; quote observations: {health['odds_quotes']}.",
            f"Hash failures: {health['hash_failures']}; identity/schema failures: {health['identity_conflicts']}.",
            f"Logical disk bytes (hard links may be counted twice): {health['disk_bytes']}.",'',
            'Historical publication availability is not inferred from event dates. Zero rows currently qualify for a historical CFB betting evaluation.',
            'A complete eligible-game universe has not yet been audited. Missing-period and selection-bias rates are unmeasured, not zero.','',
            '| Sport | Quote observations | Events | First capture | Last capture |','|---|---:|---:|---|---|']
        lines += [f"| {r['sport']} | {r['quotes']} | {r['events']} | {r['earliest']} | {r['latest']} |" for r in health['quote_ranges']]
        atomic_text(report_path,'\n'.join(lines)+'\n')
    return health

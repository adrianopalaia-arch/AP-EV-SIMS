"""Local-only DuckDB warehouse; no provider imports or network calls."""
from pathlib import Path
import hashlib, json, os
import duckdb
from .integrity import digest, utc
from .odds import american_to_decimal

class Warehouse:
    def __init__(self,root):
        self.root=Path(root)
        for p in ('cfbd','odds','moneypuck','nflverse','statcast','nba','weather','availability'):
            (self.root/'raw_archive'/p).mkdir(parents=True,exist_ok=True)
        for p in ('cfb','odds','nhl','nfl','mlb','nba'):(self.root/'parquet'/p).mkdir(parents=True,exist_ok=True)
        (self.root/'warehouse').mkdir(parents=True,exist_ok=True)
        self.path=self.root/'warehouse/ap_evsims.duckdb'
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS snapshots (
                snapshot_id VARCHAR PRIMARY KEY,provider VARCHAR,dataset VARCHAR,
                parameters JSON,downloaded_at TIMESTAMPTZ,observed_at TIMESTAMPTZ,
                available_at TIMESTAMPTZ,payload_hash VARCHAR,source_url VARCHAR,
                revision_id VARCHAR,raw_path VARCHAR,qualification_reason VARCHAR)''')
            db.execute('''CREATE TABLE IF NOT EXISTS source_records (
                snapshot_id VARCHAR,row_index INTEGER,provider VARCHAR,dataset VARCHAR,
                available_at TIMESTAMPTZ,body JSON,PRIMARY KEY(snapshot_id,row_index))''')
            db.execute('''CREATE TABLE IF NOT EXISTS odds_quotes (
                quote_id VARCHAR PRIMARY KEY,series_id VARCHAR,snapshot_id VARCHAR,provider VARCHAR,
                book VARCHAR,sport VARCHAR,event_id VARCHAR,canonical_event_id VARCHAR,
                event_start TIMESTAMPTZ,market VARCHAR,period VARCHAR,selection VARCHAR,
                line DOUBLE,american_odds INTEGER,decimal_odds DOUBLE,observed_at TIMESTAMPTZ,
                available_at TIMESTAMPTZ,ingested_at TIMESTAMPTZ,raw_payload_hash VARCHAR,
                pair_id VARCHAR,settlement_rule_id VARCHAR,home_team VARCHAR,away_team VARCHAR)''')
            db.execute('''CREATE TABLE IF NOT EXISTS identity_conflicts (
                conflict_id VARCHAR PRIMARY KEY,kind VARCHAR,snapshot_id VARCHAR,details JSON)''')
            db.execute('''CREATE TABLE IF NOT EXISTS event_mappings (
                provider VARCHAR,provider_event_id VARCHAR,canonical_event_id VARCHAR,
                event_start TIMESTAMPTZ,source_snapshot VARCHAR,PRIMARY KEY(provider,provider_event_id,event_start))''')
            db.execute('''CREATE TABLE IF NOT EXISTS closing_prices (
                series_id VARCHAR PRIMARY KEY,quote_id VARCHAR,revealed_at TIMESTAMPTZ)''')
            db.execute('''CREATE TABLE IF NOT EXISTS prediction_time_prices (
                prediction_id VARCHAR PRIMARY KEY,quote_id VARCHAR,decision_at TIMESTAMPTZ)''')
            db.execute('''CREATE OR REPLACE VIEW opening_prices AS
                SELECT *, 'FIRST_OBSERVED_NOT_PROVEN_OPENER' AS opening_definition FROM odds_quotes
                QUALIFY row_number() OVER (PARTITION BY series_id ORDER BY available_at,observed_at,quote_id)=1''')
            db.execute('''CREATE OR REPLACE VIEW odds_movements AS
                SELECT * FROM (SELECT quote_id,series_id,available_at,line,american_odds,
                lag(line) OVER w AS previous_line,lag(american_odds) OVER w AS previous_odds
                FROM odds_quotes WINDOW w AS (PARTITION BY series_id ORDER BY available_at,observed_at,quote_id))
                WHERE previous_odds IS NOT NULL AND (line IS DISTINCT FROM previous_line OR american_odds<>previous_odds)''')
    def connect(self):
        connection=duckdb.connect(str(self.path));connection.execute("SET TimeZone='UTC'");return connection
    def ingest_manifest(self,store,manifest):
        # Verify the immutable manifest and raw hash before doing anything else.
        manifest=store.manifest(manifest['snapshot_id'])
        if manifest['parameters'].get('endpoint_status',200)!=200:return dict(status='PROVIDER_ERROR_EXCLUDED',rows=0)
        payload=store.payload(manifest)
        from .providers.schema import validate_provider_payload
        validate_provider_payload(manifest['provider'],manifest['endpoint'],payload)
        with self.connect() as db:
            cached=bool(db.execute('SELECT 1 FROM snapshots WHERE snapshot_id=?',[manifest['snapshot_id']]).fetchone())
        if cached:
            self.export_snapshot(manifest)
            return dict(status='CACHED',rows=0)
        raw=(store.root/manifest['raw_path']).resolve()
        folder={'nhl':'moneypuck','nfl':'nflverse','mlb':'statcast'}.get(manifest['provider'],manifest['provider'])
        target=self.root/'raw_archive'/folder/(manifest['payload_hash']+'.json')
        target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            try:os.link(raw,target)
            except OSError:
                # Reuse the original immutable archive rather than duplicate large bytes.
                target=raw
        if hashlib.sha256(target.read_bytes()).hexdigest()!=manifest['payload_hash']:raise ValueError('PAYLOAD_HASH_MISMATCH')
        rows=payload if isinstance(payload,list) else payload.get('data',[]) if isinstance(payload,dict) else []
        if not isinstance(rows,list):rows=[]
        if any(not isinstance(r,dict) for r in rows):raise ValueError('SCHEMA_DRIFT')
        bases={'cfbd':'https://api.collegefootballdata.com/','odds':'https://api.the-odds-api.com/v4/'}
        source_url=bases.get(manifest['provider'],'')+manifest['endpoint'] if manifest['provider'] in bases else None
        with self.connect() as db:
            db.execute('BEGIN TRANSACTION')
            try:
                db.execute('INSERT INTO snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',[
                    manifest['snapshot_id'],manifest['provider'],manifest['endpoint'],json.dumps(manifest['parameters']),
                    manifest['fetched_at'],manifest['observed_at'],manifest['available_at'],manifest['payload_hash'],source_url,
                    manifest.get('revision_id',manifest['payload_hash']),str(target),manifest['qualification_reason']])
                if rows:
                    import pyarrow as pa
                    batch=[dict(snapshot_id=manifest['snapshot_id'],row_index=i,provider=manifest['provider'],dataset=manifest['endpoint'],
                        available_at=manifest['available_at'],body=json.dumps(row,allow_nan=False)) for i,row in enumerate(rows)]
                    db.register('_incoming_source',pa.Table.from_pylist(batch))
                    try:db.execute('INSERT INTO source_records SELECT * FROM _incoming_source')
                    finally:db.unregister('_incoming_source')
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK');raise
        self.export_snapshot(manifest)
        return dict(status='INGESTED',rows=len(rows))
    def export_snapshot(self,manifest):
        partition={'cfbd':'cfb'}.get(manifest['provider'],manifest['provider'])
        if partition in ('cfb','odds','nhl','nfl','mlb','nba'):
            target_parquet=self.root/'parquet'/partition/(manifest['snapshot_id']+'.parquet')
            if not target_parquet.exists():
                temporary=target_parquet.with_suffix('.parquet.tmp')
                with self.connect() as db:
                    db.sql('SELECT * FROM source_records WHERE snapshot_id=?',params=[manifest['snapshot_id']]).write_parquet(str(temporary))
                os.replace(temporary,target_parquet)
    def local_records(self,provider,dataset,as_of, *, snapshot_id=None):
        utc(as_of)
        with self.connect() as db:
            if snapshot_id:
                rows=db.execute('SELECT body FROM source_records WHERE provider=? AND dataset=? AND snapshot_id=? AND available_at<=? ORDER BY row_index',
                    [provider,dataset,snapshot_id,as_of]).fetchall()
            else:
                # Do not silently concatenate revisions of the same provider query.
                ids=db.execute('SELECT snapshot_id FROM snapshots WHERE provider=? AND dataset=? AND available_at<=? ORDER BY available_at DESC LIMIT 1',[provider,dataset,as_of]).fetchall()
                rows=[] if not ids else db.execute('SELECT body FROM source_records WHERE snapshot_id=? ORDER BY row_index',[ids[0][0]]).fetchall()
        if not rows:raise ValueError('MISSING_LOCAL_DATA')
        return [json.loads(r[0]) for r in rows]
    def record_odds(self,store,manifest):
        manifest=store.manifest(manifest['snapshot_id']);payload=store.payload(manifest)
        if manifest['provider']!='odds' or not manifest['endpoint'].endswith('/odds'):raise ValueError('SCHEMA_DRIFT')
        if manifest['parameters'].get('endpoint_status',200)!=200:raise ValueError('PROVIDER_ERROR_EXCLUDED')
        events=payload.get('data') if isinstance(payload,dict) else payload
        if not isinstance(events,list):raise ValueError('SCHEMA_DRIFT')
        quotes=[];failures=[]
        sport_map={'americanfootball_ncaaf':'CFB','americanfootball_nfl':'NFL','icehockey_nhl':'NHL','baseball_mlb':'MLB','basketball_nba':'NBA'}
        for e in events:
            try:
                if not all(k in e for k in ('id','sport_key','commence_time','home_team','away_team','bookmakers')):raise ValueError('SCHEMA_DRIFT')
                sport=sport_map[e['sport_key']];start=utc(e['commence_time']).isoformat()
                for b in e['bookmakers']:
                    for m in b['markets']:
                        if m['key'] not in ('h2h','spreads','totals'):continue
                        outcomes=m['outcomes']
                        if len(outcomes)!=2:raise ValueError('NO_MARKET_PAIR')
                        names={o['name'] for o in outcomes}
                        expected={'Over','Under'} if m['key']=='totals' else {e['home_team'],e['away_team']}
                        if names!=expected:raise ValueError('NO_MARKET_PAIR')
                        if m['key']=='spreads' and sum(o['point'] for o in outcomes)!=0:raise ValueError('NO_MARKET_PAIR')
                        if m['key']=='totals' and outcomes[0]['point']!=outcomes[1]['point']:raise ValueError('NO_MARKET_PAIR')
                        observed=m.get('last_update',b.get('last_update'))
                        if observed is None:raise ValueError('SCHEMA_DRIFT')
                        if utc(observed)>utc(manifest['available_at']):raise ValueError('LOOKAHEAD_RISK')
                        pair=digest([manifest['snapshot_id'],e['id'],b['key'],m])
                        pair_quotes=[]
                        for o in outcomes:
                            price=o['price'];decimal=american_to_decimal(price)
                            line=o.get('point')
                            if m['key']!='h2h' and (isinstance(line,bool) or not isinstance(line,(float,int)) or not -1000<=line<=1000):raise ValueError('SCHEMA_DRIFT')
                            series=digest([sport,e['id'],start,b['key'],m['key'],'full_game',o['name']])
                            identity=digest([series,line,price,observed,manifest['available_at'],manifest['snapshot_id']])
                            pair_quotes.append((identity,series,manifest['snapshot_id'],'odds',b['key'],sport,'odds:'+e['id'],None,
                                start,m['key'],'full_game',o['name'],line,price,decimal,observed,manifest['available_at'],manifest['fetched_at'],manifest['payload_hash'],pair,None,e['home_team'],e['away_team']))
                        quotes.extend(pair_quotes)
            except (KeyError,TypeError,ValueError) as error:
                reason=str(error) if str(error) in ('NO_MARKET_PAIR','LOOKAHEAD_RISK') else 'SCHEMA_DRIFT'
                failures.append(dict(event_id=e.get('id') if isinstance(e,dict) else None,reason=reason))
        with self.connect() as db:
            before=db.execute('SELECT count(*) FROM odds_quotes').fetchone()[0]
            db.execute('BEGIN TRANSACTION')
            try:
                if quotes:
                    # One transactional batch avoids thousands of per-row native
                    # calls during a current-slate refresh on Windows.
                    import pyarrow as pa
                    names=[c[0] for c in db.execute('SELECT * FROM odds_quotes LIMIT 0').description]
                    db.register('_incoming_quotes',pa.Table.from_pylist([dict(zip(names,q)) for q in quotes]))
                    try:db.execute('INSERT OR IGNORE INTO odds_quotes SELECT * FROM _incoming_quotes')
                    finally:db.unregister('_incoming_quotes')
                for f in failures:db.execute('INSERT OR IGNORE INTO identity_conflicts VALUES (?,?,?,?)',[digest([manifest['snapshot_id'],f]),f['reason'],manifest['snapshot_id'],json.dumps(f)])
                db.execute('COMMIT')
            except Exception:
                db.execute('ROLLBACK');raise
            after=db.execute('SELECT count(*) FROM odds_quotes').fetchone()[0]
        return dict(quotes_inserted=after-before,duplicates_prevented=len(quotes)-(after-before),failures=failures)
    def as_of_quotes(self,at):
        utc(at)
        with self.connect() as db:
            result=db.execute('SELECT * FROM odds_quotes WHERE available_at<=? AND observed_at<=? AND event_start>? QUALIFY row_number() OVER (PARTITION BY series_id ORDER BY available_at DESC,observed_at DESC,quote_id DESC)=1',[at,at,at])
            names=[c[0] for c in result.description]
            return [dict(zip(names,row)) for row in result.fetchall()]
    def close_events(self,at):
        utc(at)
        with self.connect() as db:
            db.execute('''INSERT OR IGNORE INTO closing_prices SELECT series_id,quote_id,? FROM odds_quotes
                WHERE event_start<=? AND available_at<event_start AND observed_at<event_start
                QUALIFY row_number() OVER (PARTITION BY series_id ORDER BY available_at DESC,observed_at DESC,quote_id DESC)=1''',[at,at])
    def health(self):
        with self.connect() as db:
            totals={name:db.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('snapshots','source_records','odds_quotes','odds_movements','identity_conflicts','closing_prices')}
            ranges=db.execute('SELECT sport,count(*),count(DISTINCT event_id),min(available_at),max(available_at) FROM odds_quotes GROUP BY sport ORDER BY sport').fetchall()
            hashes=db.execute('SELECT raw_path,payload_hash FROM snapshots').fetchall()
        failures=sum(not Path(p).is_file() or hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h for p,h in hashes)
        return dict(**totals,hash_failures=failures,quote_ranges=[dict(sport=s,quotes=n,events=e,earliest=str(lo),latest=str(hi)) for s,n,e,lo,hi in ranges],
            disk_bytes=sum(p.stat().st_size for p in self.root.rglob('*') if p.is_file()),
            missing_periods='UNMEASURED_NO_COMPLETE_ELIGIBLE_UNIVERSE',historical_availability='CAPTURE_TIME_ONLY_UNLESS_PROVIDER_SNAPSHOT_PROVEN')

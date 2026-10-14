"""Canonical joins bind features/prices/results to archived provider responses."""
from dataclasses import asdict,replace
import json
from .integrity import digest,utc
from .models.base import FeatureSnapshot
from .providers.normalize import canonical_cfbd_results,odds_contexts,require_historical_availability
from .cfb_features import normalize_cfbd_plays,rolling_matchup_features
from .historical import HistoricalObservation,validate_dataset

def materialize_rolling_features(store, *, plays_snapshot_id,results_snapshot_id,event_id,home_team,away_team,as_of,
                                 minimum_plays=100,minimum_games=3):
    plays_manifest=store.manifest(plays_snapshot_id); results_manifest=store.manifest(results_snapshot_id)
    require_historical_availability(plays_manifest,as_of); require_historical_availability(results_manifest,as_of)
    from .warehouse import Warehouse
    warehouse=Warehouse(store.root)
    for manifest in (plays_manifest,results_manifest):warehouse.ingest_manifest(store,manifest)
    results=canonical_cfbd_results(warehouse.local_records('cfbd',results_manifest['endpoint'],as_of,snapshot_id=results_snapshot_id),results_manifest)
    # Proof that a game was completed exists at response capture, not at an
    # assumed three-hour duration or a reconstructed postgame clock time.
    known={r['event_id']:r['result_available_at'] for r in results if r['status']=='final'}
    plays,rejections=normalize_cfbd_plays(warehouse.local_records('cfbd',plays_manifest['endpoint'],as_of,snapshot_id=plays_snapshot_id),plays_manifest,game_observed_times=known)
    features=rolling_matchup_features(plays,event_id=event_id,home_team=home_team,away_team=away_team,as_of=as_of,
        minimum_plays=minimum_plays,minimum_games=minimum_games)
    body=dict(algorithm_version='rolling-cfb-v1',source_snapshots=[plays_snapshot_id,results_snapshot_id],as_of=features.timestamp,
        event_id=event_id,sport='CFB',values={k:v.value for k,v in features.values.items()},
        minimum_plays=minimum_plays,minimum_games=minimum_games)
    fingerprint=digest(body); identity='derived-'+fingerprint
    store._immutable(store.root/'features'/(fingerprint+'.json'),json.dumps(body,sort_keys=True,allow_nan=False,indent=2).encode())
    available=max(utc(m['available_at']) for m in (plays_manifest,results_manifest)).isoformat()
    # Derived values use the complete input capture time as availability.
    values={k:replace(v,snapshot_id=identity,payload_hash=fingerprint,observed_at=available,available_at=available) for k,v in features.values.items()}
    return replace(features,values=values),rejections

def verify_feature_sources(store,features):
    features.validate(features.timestamp)
    for name,value in features.values.items():
        if value.snapshot_id.startswith('derived-'):
            fingerprint=value.snapshot_id.removeprefix('derived-')
            if len(fingerprint)!=64 or any(c not in '0123456789abcdef' for c in fingerprint): raise ValueError('INVALID_DERIVED_SNAPSHOT_ID')
            path=store.root/'features'/(fingerprint+'.json')
            if not path.exists(): raise ValueError('MISSING_DERIVED_FEATURE_MANIFEST')
            body=json.loads(path.read_text(encoding='utf-8'))
            if digest(body)!=fingerprint or value.payload_hash!=fingerprint or body['values'].get(name)!=value.value or body['event_id']!=features.event_id or body['as_of']!=features.timestamp:
                raise ValueError('FEATURE_HASH_MISMATCH')
            for identity in body['source_snapshots']: require_historical_availability(store.manifest(identity),features.timestamp)
        else:
            manifest=store.manifest(value.snapshot_id)
            if manifest['payload_hash']!=value.payload_hash: raise ValueError('FEATURE_HASH_MISMATCH')
            require_historical_availability(manifest,features.timestamp)
            if utc(value.available_at)<utc(manifest['available_at']): raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
            if not value.source_path or not value.source_path.startswith('/'): raise ValueError('HISTORICAL_FEATURE_VALUE_UNVERIFIED')
            actual=store.payload(manifest)
            try:
                for part in value.source_path[1:].split('/'):
                    part=part.replace('~1','/').replace('~0','~')
                    actual=actual[int(part)] if isinstance(actual,list) else actual[part]
            except (KeyError,IndexError,ValueError,TypeError): raise ValueError('FEATURE_SOURCE_PATH_INVALID')
            if isinstance(actual,bool) or not isinstance(actual,(int,float)) or actual!=value.value: raise ValueError('FEATURE_VALUE_MISMATCH')

def join_canonical(store, *, odds_snapshot_id,results_snapshot_id,event_mapping,feature_snapshots,prediction_at,
                   book='draftkings',market_type='spread'):
    odds_manifest=store.manifest(odds_snapshot_id); results_manifest=store.manifest(results_snapshot_id)
    results=canonical_cfbd_results(store.payload(results_manifest),results_manifest)
    results_by_id={r['event_id']:r for r in results}
    contexts,rejections=odds_contexts(store.payload(odds_manifest),odds_manifest,prediction_at=prediction_at,event_mapping=event_mapping)
    rows=[]
    for context in contexts:
        if context.book!=book or context.market_type!=market_type: continue
        result=results_by_id.get(context.event_id); features=feature_snapshots.get(context.event_id)
        try:
            if result is None or result['status']!='final': raise ValueError('UNSETTLED_RESULT')
            mapping=next((r for r in event_mapping.values() if r['event_id']==context.event_id),None)
            if mapping is None or (mapping.get('cfbd_home_team',mapping['home_team']),mapping.get('cfbd_away_team',mapping['away_team']))!=(result['home_team'],result['away_team']): raise ValueError('EVENT_MAPPING_UNVERIFIED')
            if (mapping['home_team'],mapping['away_team'])!=(result['home_team'],result['away_team']) and not mapping.get('alias_source'):
                raise ValueError('TEAM_ALIAS_PROVENANCE_REQUIRED')
            if features is None: raise ValueError('MISSING_FEATURES')
            verify_feature_sources(store,features)
            features.validate(context.prediction_timestamp)
            row=HistoricalObservation(digest(dict(event=context.event_id,market=market_type,selection=context.selection)),features,context,
                result['home_score'],result['away_score'],result['result_available_at'],results_snapshot_id,result['payload_hash'],'final',result['overtime'])
            row=replace(row,event_mapping=mapping)
            row.validate(); rows.append(row)
        except (ValueError,KeyError,TypeError) as e:
            rejections.append(dict(event_id=context.event_id,reason=str(e)))
    rows=validate_dataset(rows)
    table=store.write_table('canonical-'+market_type,[asdict(r) for r in rows])
    return dict(table=table,rejections=rejections,rows=rows)

def verify_provider_dataset(store,rows):
    for row in rows:
        verify_feature_sources(store,row.features)
        odds=store.manifest(row.context.snapshot_id); results=store.manifest(row.result_snapshot_id)
        if odds['provider']!='odds' or results['provider'] not in ('cfbd','results'): raise ValueError('WRONG_PROVIDER_IDENTITY')
        if results['payload_hash']!=row.result_payload_hash or utc(results['available_at'])>utc(row.result_available_at):
            raise ValueError('RESULT_PROVENANCE_MISMATCH')
        as_of=row.context.snapshot_available_at or row.context.quote_timestamp
        require_historical_availability(odds,as_of)
        result=next((r for r in canonical_cfbd_results(store.payload(results),results) if r['event_id']==row.context.event_id),None)
        if result is None or result['status']!='final' or (result['home_score'],result['away_score'])!=(row.home_score,row.away_score):
            raise ValueError('RESULT_PROVENANCE_MISMATCH')
        payload=store.payload(odds); events=payload['data'] if isinstance(payload,dict) else payload
        declared=row.event_mapping or dict(event_id=row.context.event_id,home_team=result['home_team'],away_team=result['away_team'])
        if (declared.get('cfbd_home_team',declared['home_team']),declared.get('cfbd_away_team',declared['away_team']))!=(result['home_team'],result['away_team']):
            raise ValueError('EVENT_MAPPING_UNVERIFIED')
        if (declared['home_team'],declared['away_team'])!=(result['home_team'],result['away_team']) and not declared.get('alias_source'):
            raise ValueError('TEAM_ALIAS_PROVENANCE_REQUIRED')
        mapping={e['id']:declared for e in events if (e['home_team'],e['away_team'],e['commence_time'])==(declared['home_team'],declared['away_team'],row.context.event_timestamp)}
        candidates,_=odds_contexts(payload,odds,prediction_at=row.context.prediction_timestamp,event_mapping=mapping)
        if not any(asdict(c)==asdict(row.context) for c in candidates): raise ValueError('MARKET_PROVENANCE_MISMATCH')

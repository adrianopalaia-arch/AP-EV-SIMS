"""Append-only, idempotent prediction and result reveal ledger. No network access."""
from dataclasses import asdict
import json,math
from .integrity import utc,digest,database

class ReplayLedger:
    def __init__(self,path):
        self.path=str(path)
        with database(self.path) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS frozen_predictions (
                id TEXT PRIMARY KEY,economic_id TEXT,event_id TEXT,event_start TEXT,
                decision_at TEXT,dataset_kind TEXT,body TEXT,body_hash TEXT);
                CREATE TABLE IF NOT EXISTS result_revisions (
                revision_id TEXT PRIMARY KEY,prediction_id TEXT,available_at TEXT,body TEXT,body_hash TEXT);
                CREATE TABLE IF NOT EXISTS replay_audits (
                id TEXT PRIMARY KEY,kind TEXT,body TEXT);''')
    def freeze(self, *, features,context,prediction,decision,decision_at,source_manifests,dataset_kind='provider_history',provenance_store=None):
        if dataset_kind not in ('provider_history','synthetic_test'):raise ValueError('UNKNOWN_DATASET_KIND')
        features.validate(context.prediction_timestamp);context.validate()
        at=utc(decision_at)
        if not utc(context.quote_timestamp)<=at<utc(context.event_timestamp):raise ValueError('LOOKAHEAD_RISK')
        if context.snapshot_available_at and utc(context.snapshot_available_at)>at:raise ValueError('LOOKAHEAD_RISK')
        if not source_manifests:raise ValueError('MISSING_SOURCE_MANIFEST')
        if dataset_kind=='provider_history':
            if provenance_store is None:raise ValueError('PROVIDER_PROVENANCE_REQUIRED')
            from .canonical import verify_feature_sources
            verify_feature_sources(provenance_store,features)
            for source in source_manifests:
                if source!=provenance_store.manifest(source['snapshot_id']):raise ValueError('SOURCE_MANIFEST_MISMATCH')
        for manifest in source_manifests:
            if manifest.get('available_at') is None:raise ValueError('HISTORICAL_AVAILABILITY_UNVERIFIED')
            if utc(manifest['available_at'])>at:raise ValueError('LOOKAHEAD_RISK')
        if prediction.data_fingerprint!=features.fingerprint:raise ValueError('PREDICTION_FEATURE_MISMATCH')
        if prediction.feature_snapshot_timestamp!=features.timestamp or prediction.market_type!=context.market_type:raise ValueError('PREDICTION_CONTEXT_MISMATCH')
        if decision.get('status') not in ('PASS','RESEARCH_CANDIDATE'):raise ValueError('INVALID_PHASE1_DECISION')
        economic=digest(dict(event=context.event_id,sport=context.sport,market=context.market_type,
            selection=context.selection,book=context.book,line=context.line))
        identity=digest(dict(economic=economic,snapshot=context.snapshot_id,model=prediction.model_version,
            artifact=prediction.model_artifact_id,calibration=prediction.calibration_version,decision_at=decision_at))
        body=dict(prediction_id=identity,economic_id=economic,features=asdict(features),context=asdict(context),
            prediction=prediction.to_dict(),decision=decision,decision_at=decision_at,
            source_snapshot_ids=sorted(m['snapshot_id'] for m in source_manifests),dataset_kind=dataset_kind)
        serialized=json.dumps(body,sort_keys=True,allow_nan=False);fingerprint=digest(body)
        with database(self.path) as db:
            existing=db.execute('SELECT body_hash FROM frozen_predictions WHERE id=?',(identity,)).fetchone()
            if existing and existing[0]!=fingerprint:raise ValueError('FROZEN_PREDICTION_MUTATION')
            db.execute('INSERT OR IGNORE INTO frozen_predictions VALUES (?,?,?,?,?,?,?,?)',
                (identity,economic,context.event_id,context.event_timestamp,decision_at,dataset_kind,serialized,fingerprint))
        return identity
    def reveal(self,prediction_id, *, result,available_at,clock,source_snapshot_id,source_hash):
        if utc(available_at)>utc(clock):raise ValueError('RESULT_NOT_YET_AVAILABLE')
        if not source_snapshot_id or len(source_hash)!=64:raise ValueError('MISSING_RESULT_PROVENANCE')
        with database(self.path) as db:
            prior=db.execute('SELECT event_start,decision_at FROM frozen_predictions WHERE id=?',(prediction_id,)).fetchone()
            if not prior:raise ValueError('UNKNOWN_FROZEN_PREDICTION')
            if utc(available_at)<=utc(prior[0]) or utc(available_at)<=utc(prior[1]):raise ValueError('LOOKAHEAD_RISK')
            body=dict(prediction_id=prediction_id,result=result,available_at=available_at,
                source_snapshot_id=source_snapshot_id,source_hash=source_hash)
            revision=digest(body)
            db.execute('INSERT OR IGNORE INTO result_revisions VALUES (?,?,?,?,?)',
                (revision,prediction_id,utc(available_at).isoformat(),json.dumps(body,sort_keys=True,allow_nan=False),digest(body)))
        return revision
    def predictions(self, *, dataset_kind='provider_history'):
        with database(self.path) as db:
            rows=db.execute('SELECT body,body_hash FROM frozen_predictions WHERE dataset_kind=? ORDER BY decision_at,id',(dataset_kind,)).fetchall()
        result=[]
        for raw,fingerprint in rows:
            body=json.loads(raw)
            if digest(body)!=fingerprint:raise ValueError('FROZEN_PREDICTION_HASH_MISMATCH')
            result.append(body)
        return result
    def results_as_of(self,prediction_id,clock):
        with database(self.path) as db:
            rows=db.execute('SELECT body,body_hash FROM result_revisions WHERE prediction_id=? AND available_at<=? ORDER BY available_at,revision_id',(prediction_id,utc(clock).isoformat())).fetchall()
        result=[]
        for raw,fingerprint in rows:
            body=json.loads(raw)
            if digest(body)!=fingerprint:raise ValueError('RESULT_HASH_MISMATCH')
            if utc(body['available_at'])<=utc(clock):result.append(body)
        return result

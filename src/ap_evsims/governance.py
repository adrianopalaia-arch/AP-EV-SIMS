"""Pre-registered experiments, one-use final holdouts and conservative comparisons."""
import json,math,statistics
from .integrity import digest,utc,database
from .calibration import brier_score,log_loss

class ExperimentLedger:
    def __init__(self,path):
        self.path=str(path)
        with database(self.path) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS holdouts (
                id TEXT PRIMARY KEY,dataset_hash TEXT,start_at TEXT,end_at TEXT,used_by TEXT,result TEXT);
                CREATE TABLE IF NOT EXISTS experiments (
                id TEXT PRIMARY KEY,registered_at TEXT,body TEXT,result TEXT);
                CREATE TABLE IF NOT EXISTS hypotheses (
                id TEXT PRIMARY KEY,created_at TEXT,body TEXT);''')
    def lock_holdout(self,dataset_hash,start,end):
        if len(dataset_hash)!=64 or utc(start)>=utc(end):raise ValueError('INVALID_HOLDOUT')
        identity=digest([dataset_hash,start,end])
        with database(self.path) as db:
            old=db.execute('SELECT start_at,end_at FROM holdouts WHERE dataset_hash=?',(dataset_hash,)).fetchall()
            for lo,hi in old:
                if max(utc(lo),utc(start))<min(utc(hi),utc(end)):
                    if lo==start and hi==end:return identity
                    raise ValueError('OVERLAPPING_FINAL_HOLDOUT')
            db.execute('INSERT INTO holdouts VALUES (?,?,?,?,NULL,NULL)',(identity,dataset_hash,start,end))
        return identity
    def register(self, *, hypothesis,registered_at,training_end,validation_end,calibration_end,holdout_id,
                 dataset_hash,features,model,threshold,feature_version):
        if not hypothesis or not model or not feature_version:raise ValueError('MISSING_EXPERIMENT_SPEC')
        if not utc(training_end)<utc(validation_end)<utc(calibration_end):raise ValueError('EXPERIMENT_LOOKAHEAD_RISK')
        if not isinstance(threshold,(float,int)) or not math.isfinite(threshold):raise ValueError('INVALID_THRESHOLD')
        body=dict(hypothesis=hypothesis,registered_at=registered_at,training_end=training_end,validation_end=validation_end,
            calibration_end=calibration_end,holdout_id=holdout_id,dataset_hash=dataset_hash,features=list(features),model=model,
            threshold=threshold,feature_version=feature_version)
        identity=digest(body)
        with database(self.path) as db:
            holdout=db.execute('SELECT dataset_hash,start_at,used_by FROM holdouts WHERE id=?',(holdout_id,)).fetchone()
            if not holdout or holdout[0]!=dataset_hash:raise ValueError('HOLDOUT_DATASET_MISMATCH')
            if utc(calibration_end)>=utc(holdout[1]):raise ValueError('EXPERIMENT_LOOKAHEAD_RISK')
            if holdout[2]:raise ValueError('FINAL_HOLDOUT_ALREADY_CONSUMED')
            db.execute('INSERT OR IGNORE INTO experiments VALUES (?,?,?,NULL)',(identity,registered_at,json.dumps(body,sort_keys=True)))
        return identity
    def seal_final_result(self,experiment_id,result):
        with database(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT body,result FROM experiments WHERE id=?',(experiment_id,)).fetchone()
            if not row:raise ValueError('UNKNOWN_EXPERIMENT')
            body=json.loads(row[0]);holdout=body['holdout_id']
            consumed=db.execute('SELECT used_by FROM holdouts WHERE id=?',(holdout,)).fetchone()[0]
            if consumed:raise ValueError('FINAL_HOLDOUT_ALREADY_CONSUMED')
            payload=json.dumps(result,sort_keys=True,allow_nan=False)
            db.execute('UPDATE experiments SET result=? WHERE id=?',(payload,experiment_id))
            db.execute('UPDATE holdouts SET used_by=?,result=? WHERE id=?',(experiment_id,payload,holdout))
    def variant_count(self):
        with database(self.path) as db:return db.execute('SELECT count(*) FROM experiments').fetchone()[0]
    def postmortem_hypothesis(self,text,created_at,source_prediction_id):
        body=dict(hypothesis=text,created_at=created_at,source_prediction_id=source_prediction_id,status='UNTESTED_NO_MODEL_CHANGE')
        identity=digest(body)
        with database(self.path) as db:db.execute('INSERT OR IGNORE INTO hypotheses VALUES (?,?,?)',(identity,created_at,json.dumps(body)))
        return identity

def assess_challenger(champion,challenger, *, minimum_n=300,critical_failures=0,complexity_increased=False):
    def indexed(rows):
        result={}
        for r in rows:
            key=(r['event_id'],r['market'],r['selection'])
            if key in result:raise ValueError('DUPLICATE_EVALUATION_OBSERVATION')
            result[key]=r
        return result
    left,right=indexed(champion),indexed(challenger)
    reasons=[]
    if set(left)!=set(right):reasons.append('UNMATCHED_EVALUATION_ROWS')
    keys=sorted(set(left)&set(right));a=[left[k] for k in keys];b=[right[k] for k in keys]
    if len(keys)<minimum_n:reasons.append('INSUFFICIENT_OOS_SAMPLE')
    if any(r.get('dataset_kind')!='provider_history' for r in a+b):reasons.append('NON_EMPIRICAL_EVIDENCE')
    if critical_failures:reasons.append('CRITICAL_RED_TEAM_FAILURE')
    if any(x['outcome']!=y['outcome'] for x,y in zip(a,b)):reasons.append('OUTCOME_MISMATCH')
    metrics={}
    if keys:
        outcomes=[r['outcome'] for r in b]
        for label,rows in [('champion',a),('challenger',b)]:
            p=[r['probability'] for r in rows]
            if any(not math.isfinite(v) or not 0<v<1 for v in p):raise ValueError('INVALID_PROBABILITY')
            metrics[label]=dict(brier=brier_score(p,outcomes),log_loss=log_loss(p,outcomes),
                bias=abs(statistics.mean(p)-statistics.mean(outcomes)))
        if any(metrics['challenger'][k]>=metrics['champion'][k] for k in ('brier','log_loss')):reasons.append('NO_INCREMENTAL_PROPER_SCORE_VALUE')
        if metrics['challenger']['bias']>metrics['champion']['bias']:reasons.append('CALIBRATION_WORSENED')
        seasons={r.get('season') for r in b};regimes={r.get('regime') for r in b}
        if None in seasons or len(seasons)<2:reasons.append('INSUFFICIENT_CROSS_SEASON_EVIDENCE')
        if None in regimes or len(regimes)<2:reasons.append('INSUFFICIENT_REGIME_EVIDENCE')
        if any(r.get('clv') is None for r in a+b):reasons.append('MISSING_CLV_EVIDENCE')
        elif statistics.mean(r['clv'] for r in b)<=statistics.mean(r['clv'] for r in a):reasons.append('NO_INCREMENTAL_CLV')
    # Detailed interval/season/readiness review remains required even for a candidate.
    return dict(action='KEEP_CHAMPION' if reasons else 'PROMOTION_CANDIDATE',reasons=reasons,matched_n=len(keys),
        metrics=metrics,complexity_increased=complexity_increased,automatic_promotion=False,
        ready_for_stakes=False,requires_review=['clustered score/ROI intervals','drawdown','each season/regime','prospective evidence','uncertainty coverage'])

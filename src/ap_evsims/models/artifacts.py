"""Hash-checked model/calibration persistence; authenticity requires external approval."""
import json
from pathlib import Path
from ..integrity import digest
from .cfb import CFBSpreadModel,CFBTotalModel,CFBWinModel,DiscreteTilt
from .numerics import Ridge
from .probability_calibration import CalibratedProbability

def save_model(model,path):
    state=dict(fitted=model.fitted_state(),calibration=model.calibrator.state() if model.calibrator else None,
        model_version=model.model_version,artifact_id=model.artifact_id)
    payload=dict(schema_version=1,fingerprint=digest(state),state=state)
    Path(path).write_text(json.dumps(payload,sort_keys=True,allow_nan=False,indent=2),encoding='utf-8')

def load_model(path):
    payload=json.loads(Path(path).read_text(encoding='utf-8')); s=payload['state']
    if payload.get('schema_version')!=1 or digest(s)!=payload['fingerprint']: raise ValueError('MODEL_ARTIFACT_HASH_MISMATCH')
    f=s['fitted']; spec=f['spec']; kind=spec['market_type']
    cls={'spread':CFBSpreadModel,'total':CFBTotalModel,'win':CFBWinModel}.get(kind)
    if cls is None: raise ValueError('UNSUPPORTED_MODEL_ARTIFACT')
    model=cls(**{k:spec[k] for k in ('feature_keys','minimum_train','ridge_penalty','bootstrap_samples','seed')})
    if model.model_version!=s['model_version'] or digest(f)!=s['artifact_id'] or digest(model.spec)!=digest(spec): raise ValueError('MODEL_VERSION_MISMATCH')
    for name in ('training_cutoff','training_fingerprint','training_n','training_blocks','training_ranges'): setattr(model,name,f[name])
    model.regressor=Ridge.from_state(f['regression']); model.distribution=DiscreteTilt.from_state(f['distribution'])
    model.bootstrap=[(Ridge.from_state(b['regression']),DiscreteTilt.from_state(b['distribution'])) for b in f['bootstrap']]
    model.artifact_id=s['artifact_id']
    if s['calibration']: model.attach_calibration(CalibratedProbability(**s['calibration']))
    return model

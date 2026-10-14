"""Daily research ranking; model output never creates a wagering classification."""
import csv
from pathlib import Path
import json

FIELDS=('sport','event_id','market','book','line','odds','raw_probability','calibrated_probability','lower_bound',
        'implied_probability','no_vig_probability','edge','conservative_ev','fair_odds','max_acceptable_price',
        'model_version','calibration_version','data_age_seconds','status','pass_reasons')

def write_ranking(records,directory):
    root=Path(directory); root.mkdir(parents=True,exist_ok=True)
    rows=sorted(records,key=lambda r: (r.get('conservative_ev') is not None,r.get('conservative_ev') or -999),reverse=True)
    with (root/'ranking.csv').open('w',newline='',encoding='utf-8') as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS); writer.writeheader()
        for row in rows:
            output={k:row.get(k) for k in FIELDS}; output['pass_reasons']=';'.join(output.get('pass_reasons') or [])
            writer.writerow(output)
    (root/'cfb-diagnostics.json').write_text(json.dumps([dict(event_id=r['event_id'],market=r['market'],
        model_version=r['model_version'],diagnostics=r.get('explanation',{})) for r in rows],allow_nan=False,indent=2),encoding='utf-8')
    return root/'ranking.csv'

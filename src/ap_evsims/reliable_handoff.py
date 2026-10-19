"""Reconcile existing handoff feeds without changing frozen model evidence."""
import json
from pathlib import Path
from .integrity import digest,utc
from .publication import atomic_json
from .product import card_lock,read_card
from .p0_results import publication_base

def sync(root,*,force=False):
    root=Path(root);out=root/'outputs';data=root/'data'
    status=json.loads((out/'reliability_status.json').read_text());at=status['generated_at']
    results=json.loads((out/'prospective_settlements.json').read_text())
    with card_lock(data):
        summary,values=publication_base(root)
        prior=summary.get('reliable_checkpoint_at')
        if not force and prior and (utc(at)-utc(prior)).total_seconds()<1200 and summary.get('prospective_scored_forecasts')==results['settled_forecast_observations']:
            return
        local=values.pop('comparison_markets.json',[])
        if (out/'p0_preservation_audit.json').exists():values['p0_preservation_audit.json']=json.loads((out/'p0_preservation_audit.json').read_text())
        models=values.get('model_status.json',[])
        for model in models:
            cohorts=[c for c in results['cohorts'] if c['sport']==model['sport'] and c['model_version']==model.get('model_version') and (c['market']==model.get('market') or model['sport']=='CFB')]
            model.update(prospective_cohorts=cohorts,prospective_scored_n=sum(c['n'] for c in cohorts),
                prospective_evidence_as_of=at,betting_validated=False,recommendations_enabled=False)
            if model['sport']=='CFB':model['prospective_metric_scope']='Game margins and win probabilities; no qualified price-specific spread or moneyline settlement'
        values['model_status.json']=models;values['latest_edges.json']=[]
        provider=values.get('provider_status.json',{})
        provider['reliable_collection']={k:v for k,v in status['activity'].items() if k in ('prop_collection','cfb_collection','cfbd_results','book_rules')}
        provider['reliable_collection_checked_at']=at;provider['current_quota']=status['quota']
        values['provider_status.json']=provider
        predictions=[]
        for sport in ('nhl','nba','nfl','mlb'):
            predictions.extend(f for f in json.loads((out/(sport+'_challenger_prospective.json')).read_text())['predictions'] if utc(f['event_start'])>utc(at))
        wanted={f['forecast_hash'] for f in json.loads((out/'week_ahead_game_probabilities.json').read_text())['game_forecasts']}
        for path in (data/'predictions/cfb-score').glob('*.json'):
            f=json.loads(path.read_text())
            if f['forecast_hash'] in wanted:predictions.append(dict(f,sport='CFB',market='game_margin'))
        values['latest_predictions.json']=[dict(f,decision='PASS',phase1_eligible=False) for f in predictions]
        candidates=json.loads((out/'live_research_candidates.json').read_text())['candidates']
        fields=('sport','market','event_id','event_start','forecast_hash','comparison_hash','player_name','selection','line','book','odds',
                'quote_timestamp','quote_age_seconds','current_price_fresh','decision','pass_reasons','model_version')
        values['latest_passes.json']=[{k:c.get(k) for k in fields} for c in candidates]
        summary.update(generated_at=at,checkpoint_at=at,reliable_checkpoint_at=at,current_task='P0_VERIFIED_PROSPECTIVE_SETTLEMENT',
            real_predictions_published=len(predictions),prospective_scored_forecasts=results['settled_forecast_observations'],
            prospective_distinct_games=results['distinct_games'],prospective_priced_settled=results['priced_settled_observations'],
            additional_simulation_draws_this_refresh=0,models_validated=0,qualified_edges=0,
            next_task='Verify participation and bookmaker applicability; capture authentic closes and expand independent prospective cohorts',
            sports_updated=['CFB','NHL','NBA','NFL','MLB'],reliable_outputs_manifest='reliability_manifest.json')
        generation=digest(dict(at=at,values=values));summary.update(publication_generation=generation,
            feed_hashes={n:digest(v) for n,v in values.items()},local_comparison_hash=digest(local))
        atomic_json(data/'snapshots'/(generation+'-comparison_markets.json'),local)
        for name,value in values.items():
            atomic_json(data/'snapshots'/(generation+'-'+name),value);atomic_json(out/name,value)
        atomic_json(out/'last_update.json',summary);read_card(root)

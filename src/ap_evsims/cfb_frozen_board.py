"""Seven-day forecasts from the existing model, with immutable issue times."""
from datetime import datetime,timedelta,timezone
import json
from pathlib import Path
from .cfb_scores import ScoreMarginModel,score_observations,margin_distribution,market_mass
from .cfb_universe import verified_sources
from .cfb_score_research import freeze
from .integrity import utc,digest
from .research_store import ResearchStore
from .warehouse import Warehouse
from .identity import map_cfb_events
from .paper_market import archived_quotes,fresh,consensus
from .display_pricing import opposite_side,market_calculations,outcome_ev
from .odds import american_to_implied


def run(root):
    root=Path(root);s=ResearchStore(root/'data');w=Warehouse(s.root);at=datetime.now(timezone.utc).isoformat()
    status=json.loads((root/'outputs/cfb_score_research_status.json').read_text());h=status['artifact_hash']
    artifact=json.loads((s.root/'models'/('cfb-score-'+h+'.json')).read_text())
    if digest(artifact)!=h:raise ValueError('MODEL_HASH_MISMATCH')
    model=ScoreMarginModel();model.state=artifact['model'];model.counts=model.state['team_counts']
    if utc(model.state['latest_source_capture'])>utc(at):raise ValueError('MODEL_LOOKAHEAD')
    sources=verified_sources(s,w,'games',at);_,future,_=score_observations(sources,at)
    quotes=archived_quotes(s,w,at);snapshots={q['snapshot_id']:s.manifest(q['snapshot_id']) for q in quotes}
    current=[m for m in snapshots.values() if m['endpoint']=='sports/americanfootball_ncaaf/odds']
    latest=max(current,key=lambda m:utc(m['fetched_at']))['snapshot_id'] if current else None
    quotes=[q for q in quotes if q['snapshot_id']==latest]
    teams=verified_sources(s,w,'teams',at);mapping={}
    if teams:
        tm,tp=teams[-1];events={q['event_id']:dict(id=q['event_id'],home_team=q['home_team'],away_team=q['away_team'],commence_time=q['event_start']) for q in quotes}
        mapping,_=map_cfb_events(tp,[g for g,m in future],list(events.values()),alias_snapshot=tm['snapshot_id'],game_snapshot=digest([m['snapshot_id'] for m,p in sources]),available_at=at)
    board=[];candidates=[];rejections=[];new=0
    for g,m in future:
        if not utc(at)<utc(g['startDate'])<=utc(at)+timedelta(days=7):continue
        try:mean=model.predict(str(g['homeId']),str(g['awayId']),g['neutralSite']);pmf=margin_distribution(mean,artifact['residuals'])
        except ValueError as e:rejections.append(dict(event_id=str(g['id']),reason=str(e)));continue
        if pmf is None:rejections.append(dict(event_id=str(g['id']),reason='INSUFFICIENT_RESIDUALS'));continue
        body=dict(event_id=str(g['id']),event_start=utc(g['startDate']).isoformat(),home_id=str(g['homeId']),away_id=str(g['awayId']),home_team=g['homeTeam'],away_team=g['awayTeam'],
            generated_at=at,feature_cutoff=model.state['training_cutoff'],model_version=model.state['model_version'],artifact_hash=h,
            training_n=model.state['training_n'],training_fingerprint=model.state['training_fingerprint'],source_hashes=sorted(set(model.state['source_hashes']+[m['payload_hash']])),
            schedule_snapshot=m['snapshot_id'],latest_source_capture=max(model.state['latest_source_capture'],m['fetched_at']),expected_home_margin=mean,
            margin_distribution=pmf,home_moneyline_mass=market_mass(pmf),calibrated_probability=None,p_low=None,model_status='UNVALIDATED',mode='RESEARCH_ONLY',
            recommendations_enabled=False,cash_staked=0,reference_unit=22,priced_markets=[],matched_odds_event_ids=[],
            training_provenance='RECONSTRUCTED_HISTORY_UNVERIFIED_AS_OF',prediction_provenance='FROZEN_BEFORE_KICKOFF',
            pass_reasons=['MODEL_NOT_CALIBRATED','PROSPECTIVE_EVIDENCE_INSUFFICIENT','UNVERIFIED_LINEUP'])
        f,created=freeze(s,body);new+=created
        if (f['home_id'],f['away_id'],utc(f['event_start']))!=(str(g['homeId']),str(g['awayId']),utc(g['startDate'])):
            rejections.append(dict(event_id=f['event_id'],reason='FROZEN_SCHEDULE_REVISION'));continue
        board.append(dict(sport='CFB',event_id=f['event_id'],event_start=f['event_start'],home=f['home_team'],away=f['away_team'],
            home_probability=f['home_moneyline_mass']['p_win'],away_probability=f['home_moneyline_mass']['p_loss'],forecast_hash=f['forecast_hash'],
            generated_at=f['generated_at'],model_version=f['model_version'],calibrated_probability=None,p_low=None,status='RESEARCH_FORECAST',decision='PASS'))
        for q in quotes:
            match=mapping.get(q['event_id'])
            if not match or match['event_id']!=f['event_id'] or utc(q['event_start'])!=utc(f['event_start']) or q['book'] not in ('draftkings','fanduel') or q['market'] not in ('h2h','spreads') or q['period']!='full_game':continue
            other=opposite_side(q,[x for x in quotes if x['pair_id']==q['pair_id']]);calc=market_calculations(q,other)
            if other is None:continue
            sign=1 if q['selection']==q['home_team'] else -1 if q['selection']==q['away_team'] else None
            if sign is None:continue
            mass=market_mass({sign*int(k):v for k,v in f['margin_distribution'].items()},q['line'] or 0);outside=consensus(q,quotes,at)
            raw=mass['p_win']/(1-mass['p_push']) if mass['p_push']<1 else None
            reasons=['MODEL_NOT_CALIBRATED','UNVERIFIED_LINEUP','BOOK_SETTLEMENT_RULE_UNVERIFIED','PROSPECTIVE_EVIDENCE_INSUFFICIENT']
            if not fresh(q,at):reasons.append('STALE_PRICE')
            if raw is not None and outside['probability'] is not None and abs(raw-outside['probability'])>=.15:reasons.append('MODEL_MARKET_DISAGREEMENT')
            c=dict(sport='CFB',event_id=f['event_id'],event_start=f['event_start'],game=f['away_team']+' @ '+f['home_team'],market=q['market'],selection=q['selection'],line=q['line'],book=q['book'],odds=q['american_odds'],
                raw_model_outcome_mass=mass,raw_probability_conditional_on_non_push=raw,calibrated_probability=None,p_low=None,conservative_ev=None,
                conditional_model_ev=outcome_ev(mass['p_win'],mass['p_loss'],mass['p_push'],q['american_odds']),market_no_vig=calc['market_no_vig_probability'],independent_consensus=outside,
                break_even_probability=american_to_implied(q['american_odds']),raw_fair_decimal_odds=1+mass['p_loss']/mass['p_win'] if mass['p_win'] else None,
                quote_timestamp=q['observed_at'],quote_captured_at=q['available_at'],quote_id=q['quote_id'],quote_snapshot=q['snapshot_id'],source_quote=q,
                decision_timestamp=at,forecast_hash=f['forecast_hash'],forecast_generated_at=f['generated_at'],model_version=f['model_version'],
                decision='PASS',pass_reasons=reasons,recommendations_enabled=False,reference_unit=22,stake=None)
            c['comparison_hash']=digest(c);folder=s.root/'predictions/cfb-market-research';folder.mkdir(exist_ok=True)
            if fresh(q,at):s._immutable(folder/(c['comparison_hash']+'.json'),json.dumps(c,sort_keys=True).encode())
            candidates.append(c)
    return dict(generated_at=at,forecasts=board,new_forecasts=new,candidates=candidates,rejections=rejections,model_retrained=False,new_simulation_draws=0)

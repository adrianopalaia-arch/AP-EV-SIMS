"""Score immutable forecasts from final official results; never backfill forecasts."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json,math,statistics
import numpy as np
from pathlib import Path
from .integrity import digest,utc
from .publication import atomic_json
from .research_store import ResearchStore
from .providers.public_stats import PublicStatsArchive
from .prop_research import PlayerOutcome
from .prop_settlement import settlement
from .prop_price_evidence import first_comparisons,grade
from .prop_prices import normalize_props
from .cfb_scores import score_observations
from .cfb_universe import verified_sources
from .warehouse import Warehouse


def nhl_result(f,p,m,at):
    if m['sport']!='NHL' or m['url']!='https://api-web.nhle.com/v1/gamecenter/'+f['event_id']+'/boxscore':raise ValueError('RESULT_SOURCE_IDENTITY')
    if str(p['id'])!=f['event_id'] or utc(p['startTimeUTC'])!=utc(f['event_start']):raise ValueError('RESULT_EVENT_START_MISMATCH')
    if p.get('gameState') not in ('OFF','FINAL') or p.get('gameType')!=2:raise ValueError('RESULT_NOT_FINAL_OR_MODEL_DOMAIN')
    if not utc(f['generated_at'])<utc(f['event_start'])<utc(m['captured_at'])<=utc(at):raise ValueError('RESULT_LOOKAHEAD')
    side=next((s for s in ('homeTeam','awayTeam') if p[s]['abbrev']==f['team_id']),None)
    if side is None:raise ValueError('RESULT_TEAM_MISMATCH')
    other='awayTeam' if side=='homeTeam' else 'homeTeam';group=p['playerByGameStats'][side]
    players=group['goalies'] if f['market']=='goalie_saves' else group['forwards']+group['defense']
    rows=[r for r in players if str(r['playerId'])==f['player_id']]
    if len(rows)!=1:raise ValueError('PARTICIPATION_OR_RESULT_UNVERIFIED')
    r=rows[0];minutes,seconds=map(int,r['toi'].split(':'))
    if minutes*60+seconds<=0:raise ValueError('DID_NOT_PARTICIPATE_NOT_ZERO')
    stat=r['saves'] if f['market']=='goalie_saves' else r['sog']
    opportunity=r['shotsAgainst'] if f['market']=='goalie_saves' else minutes+seconds/60
    row=PlayerOutcome('NHL',f['market'],f['event_id'],f['player_id'],f['player_name'],f['team_id'],p[other]['abbrev'],
        p['gameDate'],int(str(p['season'])[-4:]),opportunity,stat,m['manifest_id'],m['hash'],m['captured_at'])
    row.validate();return row


def probability_scores(p,y):
    if not isinstance(p,(int,float)) or not math.isfinite(p) or not 0<=p<=1 or y not in (0,1):raise ValueError('INVALID_PROBABILITY_SCORE')
    return dict(brier=(p-y)**2,log_loss=-math.log(max(1e-12,p if y else 1-p)))


def bands(rows,pkey='raw_probability',ykey='observed_binary'):
    out=[]
    for i in range(10):
        rs=[r for r in rows if r.get(pkey) is not None and r.get(ykey) is not None and min(9,int(r[pkey]*10))==i]
        out.append(dict(lower=i/10,upper=(i+1)/10,n=len(rs),mean_probability=statistics.mean(r[pkey] for r in rs) if rs else None,
                        observed_frequency=statistics.mean(r[ykey] for r in rs) if rs else None))
    return out


def paired_event_interval(rows,left='absolute_error',right='baseline_absolute_error'):
    """Descriptive paired cluster bootstrap; never a promotion or power test."""
    groups=defaultdict(list)
    for row in rows:groups[row['event_id']].append(row[left]-row[right])
    if len(groups)<20:return dict(interval_95=None,event_clusters=len(groups),reason='TOO_FEW_EVENT_CLUSTERS')
    values=np.array([statistics.mean(v) for _,v in sorted(groups.items())])
    samples=np.random.default_rng(731).choice(values,(2000,len(values)),replace=True).mean(axis=1)
    return dict(interval_95=list(map(float,np.quantile(samples,[.025,.975]))),event_clusters=len(values),
        mean_event_weighted_difference=float(values.mean()),bootstrap_seed=731,bootstrap_replicates=2000,
        reason='EXPLORATORY_EVENT_BOOTSTRAP_NOT_MULTIPLICITY_ADJUSTED; cross-game dependence may remain')


def run(root,*,refresh=False):
    root=Path(root);s=ResearchStore(root/'data');a=PublicStatsArchive(s.root);w=Warehouse(s.root);at=datetime.now(timezone.utc).isoformat()
    forecasts=[]
    for folder in ('props','cfb-score'):
        for path in s.root.joinpath('predictions',folder).glob('*.json'):
            f=json.loads(path.read_text(encoding='utf-8'))
            if digest({k:v for k,v in f.items() if k!='forecast_hash'})!=f['forecast_hash']:raise ValueError('FORECAST_HASH_MISMATCH')
            forecasts.append(f)
    final_sources={};source_failures=[]
    cached=[json.loads(p.read_text()) for p in a.folder.glob('*.json')]
    for event in sorted({f['event_id'] for f in forecasts if f.get('sport')=='NHL' and utc(f['event_start'])<utc(at)}):
        url='https://api-web.nhle.com/v1/gamecenter/'+event+'/boxscore'
        try:
            matches=[m for m in cached if m['sport']=='NHL' and m['url']==url and m['status']==200]
            if not matches and not refresh:raise ValueError('RESULT_NOT_ARCHIVED')
            m=max(matches,key=lambda x:utc(x['captured_at'])) if matches else a.capture('NHL',url)
            p=a.read(m);age=(utc(at)-utc(m['captured_at'])).total_seconds()
            final=p.get('gameState') in ('OFF','FINAL')
            revision_due=final and age>86400 and 0<(utc(at)-utc(p['startTimeUTC'])).total_seconds()<7*86400
            if refresh and ((not final and age>1800) or revision_due):
                m=a.capture('NHL',url,refresh=True);p=a.read(m)
            final_sources[event]=(m,p)
        except (ValueError,KeyError,OSError) as e:source_failures.append(dict(sport='NHL',event_id=event,category=type(e).__name__))
    at=datetime.now(timezone.utc).isoformat()
    scores,_,_=score_observations(verified_sources(s,w,'games',at),at);cfb={r.event_id:r for r in scores}
    records=[];pending=[];outcomes={};byhash={f['forecast_hash']:f for f in forecasts}
    for f in forecasts:
        sport=f.get('sport','CFB');market=f.get('market','game_margin');reason=None
        if utc(f['event_start'])>=utc(at):reason='EVENT_NOT_STARTED'
        elif sport=='NHL':
            try:
                if f['event_id'] not in final_sources:raise ValueError('OFFICIAL_RESULT_UNAVAILABLE')
                m,p=final_sources[f['event_id']];row=nhl_result(f,p,m,at);outcomes[(f['event_id'],f['player_id'],market)]=row
                r=settlement(f,row);r.update(outcome_role='OFFICIAL_FINAL_BOX_PARTICIPATION',event_start=f['event_start'],
                    independent_baseline_absolute_error=r['baseline_absolute_error'],baseline_squared_error=(f['projection']['baseline']-row.outcome)**2)
                records.append(r)
            except (ValueError,KeyError) as e:reason=str(e)
        elif sport=='CFB':
            row=cfb.get(f['event_id'])
            if row is None:reason='CANONICAL_FINAL_RESULT_UNAVAILABLE'
            elif (row.home_id,row.away_id,utc(row.kickoff))!=(f['home_id'],f['away_id'],utc(f['event_start'])):reason='RESULT_IDENTITY_OR_SCHEDULE_REVISION'
            elif not utc(f['generated_at'])<utc(row.kickoff)<utc(row.available_at)<=utc(at):reason='RESULT_LOOKAHEAD'
            else:
                artifact=json.loads((s.root/'models'/('cfb-score-'+f['artifact_hash']+'.json')).read_text())
                if digest(artifact)!=f['artifact_hash']:raise ValueError('MODEL_HASH_MISMATCH')
                baseline=0 if row.neutral else artifact['model']['baseline_home_advantage'];p=f['home_moneyline_mass']['p_win'];y=int(row.margin>0)
                r=dict(sport='CFB',market='game_margin',forecast_hash=f['forecast_hash'],event_id=f['event_id'],event_start=f['event_start'],
                    model_version=f['model_version'],observed_margin=row.margin,absolute_error=abs(f['expected_home_margin']-row.margin),
                    squared_error=(f['expected_home_margin']-row.margin)**2,baseline_absolute_error=abs(baseline-row.margin),baseline_squared_error=(baseline-row.margin)**2,
                    raw_probability=p,observed_binary=y,probability_scores=probability_scores(p,y),
                    fair_coin_diagnostic_scores=probability_scores(.5,y),baseline_probability_note='Predefined coin benchmark, not sportsbook consensus',
                    result_snapshot=row.source_id,result_hash=row.source_hash,result_available_at=row.available_at,recommendations_enabled=False)
                records.append(r)
        else:reason='OFFICIAL_PROP_RESULT_ADAPTER_PENDING'  # No missing player becomes a zero.
        if reason:pending.append(dict(sport=sport,market=market,forecast_hash=f['forecast_hash'],event_id=f['event_id'],model_version=f['model_version'],reason=reason))
    allquotes=[];allcomparisons=[];captures=[]
    for path in s.root.joinpath('manifests').glob('*.json'):
        m=json.loads(path.read_text())
        if m.get('provider')=='odds' and '/events/' in m['endpoint'] and m['endpoint'].endswith('/odds') and m['parameters'].get('endpoint_status')==200:
            try:
                verified=s.manifest(m['snapshot_id']);qs,_=normalize_props(s,verified,'NHL',at);allquotes+=qs
                payload=s.payload(verified);captures.append(dict(odds_event_id=payload['id'],captured_at=m['fetched_at'],
                    markets=m['parameters'].get('markets','').split(','),books=list(filter(None,m['parameters'].get('bookmakers','').split(',')))))
            except ValueError:pass
    for path in s.root.joinpath('predictions/market-research').glob('*.json'):
        c=json.loads(path.read_text());allcomparisons.append(c)
    priced=[];price_pending=[]
    # Fixed reporting direction avoids counting both sides. The policy was
    # registered after the first settled games, so those scores are exploratory.
    policy_path=s.root/'evaluations/reliable-evidence-policy.json'
    policy_at=json.loads(policy_path.read_text())['registered_at'] if policy_path.exists() else None
    first=[c for c in first_comparisons(allcomparisons,eligible_only=True) if c['selection']=='Over']
    for c in first:
        f=byhash[c['forecast_hash']];row=outcomes.get((c['event_id'],c['player_id'],c['market']))
        if row is None:price_pending.append(dict(comparison_hash=c['comparison_hash'],sport=c['sport'],reason='RESULT_NOT_AVAILABLE'));continue
        try:
            r=grade(c,f,row,allquotes,at,captures=captures);r.update(event_id=f['event_id'],player_id=f['player_id'],model_version=f['model_version'],
                event_start=f['event_start'],risk_group=f['sport']+':'+f['event_id'],correlated_player_group=f['event_id']+':'+f['player_id'])
            consensus=c.get('independent_consensus',{}).get('probability')
            r['independent_consensus_probability']=consensus
            r['cohort_policy_registered_before_entry']=bool(policy_at and utc(policy_at)<=utc(c['decision_timestamp']))
            r['independent_consensus_scores']=probability_scores(consensus,r['observed_binary']) if consensus is not None and r['observed_binary'] is not None else None
            priced.append(r)
        except (ValueError,KeyError) as e:price_pending.append(dict(comparison_hash=c['comparison_hash'],sport=c['sport'],reason=str(e)))
    folder=s.root/'settlements/reliable';folder.mkdir(exist_ok=True)
    for r in records+priced:s._immutable(folder/(digest(r)+'.json'),json.dumps(r,sort_keys=True,allow_nan=False).encode())
    grouped=defaultdict(list)
    for r in records:grouped[(r['sport'],r['market'],r['model_version'])].append(r)
    cohorts=[]
    for (sport,market,version),rs in sorted(grouped.items()):
        cohorts.append(dict(sport=sport,market=market,model_version=version,n=len(rs),distinct_games=len({r['event_id'] for r in rs}),
            mae=statistics.mean(r['absolute_error'] for r in rs),baseline_mae=statistics.mean(r['baseline_absolute_error'] for r in rs),
            rmse=math.sqrt(statistics.mean(r['squared_error'] for r in rs)),baseline_rmse=math.sqrt(statistics.mean(r['baseline_squared_error'] for r in rs)),
            brier=statistics.mean(r['probability_scores']['brier'] for r in rs) if sport=='CFB' else None,
            log_loss=statistics.mean(r['probability_scores']['log_loss'] for r in rs) if sport=='CFB' else None,
            paired_mae_difference=paired_event_interval(rs),
            calibration_bins=bands(rs) if sport=='CFB' else [],validation_status='INSUFFICIENT_INDEPENDENT_PROSPECTIVE_EVIDENCE'))
    priced_cohorts=[]
    for version,market,book in sorted({(r['model_version'],r['market'],r['book']) for r in priced}):
        rs=[r for r in priced if (r['model_version'],r['market'],r['book'])==(version,market,book) and r['raw_brier'] is not None]
        priced_cohorts.append(dict(model_version=version,sport='NHL',market=market,book=book,n=len(rs),distinct_games=len({r['event_id'] for r in rs}),
            distinct_player_games=len({(r['event_id'],r['player_id']) for r in rs}),
            raw_brier=statistics.mean(r['raw_brier'] for r in rs) if rs else None,raw_log_loss=statistics.mean(r['raw_logloss'] for r in rs) if rs else None,
            entry_book_brier=statistics.mean(r['descriptive_market_brier'] for r in rs) if rs else None,
            entry_book_log_loss=statistics.mean(r['descriptive_market_logloss'] for r in rs) if rs else None,
            independent_consensus_n=sum(r['independent_consensus_scores'] is not None for r in rs),calibration_bins=bands(rs),
            evaluation_policy_preregistered=all(r['cohort_policy_registered_before_entry'] for r in rs),
            hypothetical_roi=None,qualified_clv=None,return_interval=None,drawdown=None,book_rules_status='NOT_FROZEN_BEFORE_ENTRY'))
    report=dict(generated_at=at,settled_forecast_observations=len(records),distinct_games=len({(r['sport'],r['event_id']) for r in records}),
        cohorts=cohorts,priced_cohorts=priced_cohorts,records=records,priced_records=priced,pending=pending,source_failures=source_failures,
        pending_reasons=dict(Counter(r['reason'] for r in pending)),price_pending=price_pending,priced_settled_observations=len(priced),
        sample_policy='Model versions separate; fixed Over reporting direction adopted after initial results; inspect evaluation_policy_preregistered. Event/player clusters are correlated; DNP never becomes zero.',
        recommendations_enabled=False,validated_edges=0,qualified_roi=None,qualified_clv=None)
    atomic_json(root/'outputs/prospective_settlements.json',report);return report

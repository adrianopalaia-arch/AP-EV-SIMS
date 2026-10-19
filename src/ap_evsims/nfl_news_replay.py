"""Offline availability repair audit against immutable, actually captured sources.

python -m ap_evsims.nfl_news_replay --root .
This is a newly executed replay, never a backdated prospective prediction.
No network calls, sportsbook requests, training or changes to frozen predictions.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from .integrity import digest, utc
from .nfl_forecast_news import VERSION, interpret_nfl, player_context, game_context
from .nfl_game_model import scores
from .nfl_sweep import frozen_lookup
from .prop_market_research import comparison
from .providers.public_stats import PublicStatsArchive
from .publication import atomic_json, atomic_text
from .research_store import ResearchStore


def rebuild_news(root, old, created_at):
    """Reinterpret the exact historical roster/summary bytes, without fetching."""
    if digest({k:v for k,v in old.items() if k!='snapshot_hash'}) != old['snapshot_hash']:
        raise ValueError('AVAILABILITY_SNAPSHOT_HASH_MISMATCH')
    archive = PublicStatsArchive(Path(root)/'data')
    game = old['event']; sources = {}; payloads = {}
    for ref in old['sources']:
        m = json.loads((archive.folder/(ref['manifest_id']+'.json')).read_text())
        if any(m[k]!=ref[k] for k in ('manifest_id','hash','captured_at','url')):
            raise ValueError('AVAILABILITY_SOURCE_REFERENCE_MISMATCH')
        if utc(m['captured_at']) > utc(old['latest_source_capture']):
            raise ValueError('AVAILABILITY_SOURCE_LOOKAHEAD')
        sources[m['url']] = m
        payloads[m['url']] = archive.read(m)
    crosswalk = defaultdict(set)
    for url, rows in payloads.items():
        if 'roster_weekly_' in url:
            for row in rows:
                if row.get('espn_id') and row.get('gsis_id'):
                    crosswalk[str(row['espn_id'])].add(row['gsis_id'])
    players = []
    for side, team in game['espn_teams'].items():
        url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/teams/'+str(team['id'])+'/roster'
        roster = payloads[url]; m = sources[url]
        if str(roster['team']['id']) != str(team['id']):
            raise ValueError('ROSTER_TEAM_MISMATCH')
        for p in [p for g in roster['athletes'] for p in g['items']]:
            ids = crosswalk[str(p['id'])]
            if len(ids)!=1:
                continue
            players.append(dict(player_id=next(iter(ids)),provider_player_id=str(p['id']),name=p['displayName'],
                team_id=game[side+'_code'],position=p.get('position',{}).get('abbreviation'),injuries=p.get('injuries',[]),
                status=p.get('status',{}).get('type'),roster_source={k:m[k] for k in ('manifest_id','hash','captured_at')}))
    url = 'https://site.api.espn.com/apis/site/v2/sports/football/nfl/summary?event='+game['availability_event_id']
    records = interpret_nfl(game,players,payloads[url],sources[url])
    news = dict(event=game,records=records,latest_source_capture=old['latest_source_capture'],
        generated_at=created_at,original_snapshot_hash=old['snapshot_hash'],policy_version=VERSION,
        evidence_interpretation='REPLAY_CREATED_NOW_FROM_AUTHENTIC_ARCHIVED_PREGAME_SOURCES',sources=old['sources'])
    news['snapshot_hash'] = digest(news)
    return news


def calibration(rows, key):
    binary = [r for r in rows if r['margin']!=0]
    bands = []
    for i in range(10):
        group = [r for r in binary if min(9,int(r[key]['p_home_win']*10))==i]
        n = len(group)
        bands.append(dict(lower=i/10,upper=(i+1)/10,n=n,
            mean_probability=sum(r[key]['p_home_win'] for r in group)/n if n else None,
            observed_home_win_rate=sum(r['margin']>0 for r in group)/n if n else None))
    return dict(bins=bands,non_tie_n=len(binary),
        expected_calibration_error=sum(b['n']*abs(b['mean_probability']-b['observed_home_win_rate']) for b in bands if b['n'])/len(binary)
        if binary else None,calibrated_probability_fitted=False)


def evaluation(root):
    root=Path(root); report=json.loads((root/'outputs/nfl_game_model_status.json').read_text())
    path=(root/'data'/report['evaluation_path']).resolve()
    if (root/'data').resolve() not in path.parents:
        raise ValueError('EVALUATION_PATH_ESCAPE')
    rows=[json.loads(line) for line in path.read_text().splitlines() if line]
    if digest(rows)!=report['evaluation_fingerprint']:
        raise ValueError('EVALUATION_HASH_MISMATCH')
    models={key:dict(scores(rows,key),calibration=calibration(rows,key)) for key in ('ridge','home_field','elo')}
    # An authentic snapshot must predate the fold, not merely the target kickoff.
    folds={r['event_id']:r['fold_at'] for r in rows}; matched=set()
    for p in (root/'data/evaluations/availability').glob('*.json'):
        a=json.loads(p.read_text()); eid=a.get('event',{}).get('event_id')
        if eid in folds and utc(a['latest_source_capture'])<=utc(folds[eid]):
            if digest({k:v for k,v in a.items() if k!='snapshot_hash'})!=a['snapshot_hash']:
                raise ValueError('AVAILABILITY_SNAPSHOT_HASH_MISMATCH')
            rebuild_news(root,a,datetime.now(timezone.utc).isoformat());matched.add(eid)
    props=json.loads((root/'outputs/nfl_challenger_status.json').read_text())
    from .challenger_delivery import verified_model
    benchmarks={}
    at=datetime.now(timezone.utc).isoformat()
    for market, entry in props['markets'].items():
        _, benchmark=verified_model(root,'NFL',market,entry,at)
        benchmarks[market]=benchmark
    return dict(evaluation_fingerprint=report['evaluation_fingerprint'],previously_inspected_games=len(rows),
        untouched_evaluation_games=0,training_n=report['training_n'],available_outcome_games=report['available_outcome_games'],
        historical_provenance=report['historical_provenance'],baseline_models=models,prop_benchmarks=benchmarks,
        authentic_availability_snapshots_before_oos_fold_games=len(matched),
        injury_adjusted_model_evaluation=None,injury_adjusted_model_evaluation_n=0,
        explanation='This repair changes eligibility/assumptions, not numeric models. No fitted replacement-QB or workload model exists.',
        cover_accuracy=None,cover_evaluation_n=0,roi=None,roi_evaluation_n=0,clv=None,
        matched_oos_execution_price_n=0,price_metrics_blocker='No authenticated matching historical execution prices and settlement-rule cohort in this game evaluation',
        predictive_improvement_demonstrated=False,betting_validated=False)


def run(root):
    root=Path(root);store=ResearchStore(root/'data');at=datetime.now(timezone.utc).isoformat()
    original_paths=list((store.root/'predictions/props').glob('*.json'))+list((store.root/'predictions/nfl-games').glob('*.json'))
    original_hashes={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in original_paths}
    lookup=frozen_lookup(store)
    published=json.loads((root/'outputs/nfl_prop_research.json').read_text())
    game_report=json.loads((root/'outputs/nfl_game_probabilities.json').read_text())
    base_games={f['event_id']:f for f in game_report['predictions']}
    snapshot_index=json.loads((root/'outputs/nfl_availability.json').read_text())
    games=[]; reviews=[]; rejected=[]; rebuilt={}; examples=[]
    for h in snapshot_index['snapshots']:
        old=json.loads((store.root/'evaluations/availability'/(h+'.json')).read_text())
        news=rebuild_news(root,old,at); eid=news['event']['event_id'];asof=news['latest_source_capture']
        if utc(asof)>=utc(news['event']['event_start']):
            raise ValueError('ARCHIVED_NEWS_NOT_PREGAME')
        rebuilt[eid]=news;people={p['player_id']:p for p in news['records']}
        context=game_context(news['event'],news,asof)
        original=base_games.get(eid)
        games.append(dict(event_id=eid,evidence_as_of=asof,event_start=news['event']['event_start'],
            original_forecast_hash=original['forecast_hash'] if original else None,
            projected_home_margin_before=original['projected_home_margin'] if original else None,
            projected_home_margin_after=original['projected_home_margin'] if original else None,
            p_home_win_before=original['p_home_win'] if original else None,
            p_home_win_after=original['p_home_win'] if original else None,
            availability_context=context,decision='PASS',core_enabled=False))
        for row in published['predictions']:
            if row['event_id']!=eid:
                continue
            f=lookup[row['forecast_hash']]
            if utc(f['generated_at'])>utc(asof):
                rejected.append(dict(event_id=eid,forecast_hash=f['forecast_hash'],reason='FORECAST_AFTER_REPLAY_HORIZON'))
                continue
            person=people.get(f['player_id']);c=player_context(f,person,asof)
            r=dict(event_id=eid,player_id=f['player_id'],player_name=f['player_name'],team_id=f['team_id'],market=f['market'],
                original_forecast_hash=f['forecast_hash'],original_generated_at=f['generated_at'],
                evidence_as_of=asof,original_availability_snapshot=f.get('availability_snapshot'),
                reviewed_availability_snapshot=news['snapshot_hash'],baseline_projection=f['projection']['projection'],
                baseline_opportunity=f['projection']['projected_opportunity'],eligible_projected_opportunity=None,
                before_role_confirmed=f['role_confirmed'],after_role_confirmed=False,
                availability_state=c['availability_state'],news_adjustment_applied=False,
                scoring_recommendation_eligible=False,pass_reasons=c['reasons'],decision='PASS')
            reviews.append(r)
            if c['availability_state'] in {'REPORTED_OUT','CONFIRMED_OUT','QUESTIONABLE'} and len(examples)<10:
                examples.append(dict(r,source_evidence=c['evidence']))
    # Reprice ONLY frozen authentic old offers at their original decision horizons.
    # This is a policy replay; these offers are not executable now.
    changed_prices=[];price_rejections=Counter()
    comparisons=json.loads((root/'outputs/nfl_market_comparisons.json').read_text())['comparisons']
    for summary in comparisons:
        if 'comparison_hash' not in summary:
            continue
        path=store.root/'predictions/market-research'/(summary['comparison_hash']+'.json')
        old=json.loads(path.read_text())
        if digest({k:v for k,v in old.items() if k!='comparison_hash'})!=old['comparison_hash']:
            raise ValueError('COMPARISON_HASH_MISMATCH')
        news=rebuilt.get(old['event_id'])
        if news is None:
            price_rejections['NO_MATCHED_NEWS']+=1;continue
        f=lookup[old['forecast_hash']];asof=news['latest_source_capture']
        person=next((p for p in news['records'] if p['player_id']==f['player_id']),None)
        if person is None:
            price_rejections['PLAYER_NOT_ON_VERIFIED_CURRENT_ROSTER']+=1;continue
        c=player_context(f,person,asof)
        # Reuse archived paired quotes through normal normalization and identity guards.
        from .prop_prices import normalize_props
        qs,_=normalize_props(store,store.manifest(old['quote_snapshot']),'NFL',asof)
        matching=[q for q in qs if q['quote_id']==old['quote_id']]
        if not matching:
            # quote IDs include the analysis time in some normalizers; use immutable identity fields.
            from .identity import normalized_name
            matching=[q for q in qs if q['odds_event_id']==f['event_mapping']['odds_event_id'] and q['market']==f['market']
                and q['line']==old['line'] and q['book']==old['book'] and normalized_name(q['player_name'])==normalized_name(f['player_name'])]
        if len(matching)!=1:
            price_rejections['ARCHIVED_QUOTE_IDENTITY_UNVERIFIED']+=1;continue
        revised=next(r for r in comparison(f,matching[0],person,old['benchmark'],asof) if r['selection']==old['selection'])
        changed_prices.append(dict(event_id=f['event_id'],player_id=f['player_id'],player_name=f['player_name'],market=f['market'],
            selection=old['selection'],book=old['book'],line=old['line'],odds=old['odds'],
            original_comparison_hash=old['comparison_hash'],quote_timestamp=old['quote_timestamp'],quote_snapshot=old['quote_snapshot'],
            original_decision_timestamp=old['decision_timestamp'],replay_evidence_as_of=asof,
            before_conditional_ev=old['conditional_model_ev'],after_conditional_ev=revised['conditional_model_ev'],
            before_research_rank_eligible=old['research_rank_eligible'],after_research_rank_eligible=revised['research_rank_eligible'],
            availability_state=c['availability_state'],pass_reasons=revised['pass_reasons'],decision='PASS',
            executable_now=False))
    preserved=all(p.is_file() and hashlib.sha256(p.read_bytes()).hexdigest()==h for p,h in original_hashes.items())
    if not preserved:
        raise ValueError('ORIGINAL_FORECAST_CHANGED')
    e=evaluation(root)
    report=dict(generated_at=at,policy_version=VERSION,mode='RETROSPECTIVE_POLICY_REPLAY_OF_AUTHENTIC_PREGAME_CAPTURES',
        new_prospective_forecasts=0,new_simulations=0,sportsbook_api_requests=0,
        games_reviewed=len(games),prop_forecasts_reviewed=len(reviews),price_comparisons_reviewed=len(changed_prices),
        original_frozen_files_checked=len(original_hashes),original_frozen_files_unchanged=preserved,
        availability_counts=dict(Counter(r['availability_state'] for r in reviews)),
        pass_reason_counts=dict(Counter(reason for r in reviews for reason in r['pass_reasons'])),
        conditional_ev_suppressed=sum(r['before_conditional_ev'] is not None and r['after_conditional_ev'] is None for r in changed_prices),
        games=games,forecast_reviews=reviews,before_after_examples=examples,
        price_reviews=changed_prices,rejections=rejected,price_rejections=dict(price_rejections),
        evaluation=e,validated_edges=0,core_enabled=False,
        limitations=['No new injury-adjusted numerical model; original means and distributions remain conditional historical baselines',
            'ESPN reports are secondary; no official active/starter or workload feed is implemented',
            'No replacement-QB model or supported scenario probabilities; NEWS_ADJUSTMENT_UNAVAILABLE',
            'Old/stale reports and roster active status cannot prove current gameday participation',
            'All October 18 games have begun; this replay cannot be counted as newly frozen prospective evidence',
            'No untouched injury-adjusted evaluation cohort or authenticated historical execution-price cohort'])
    folder=store.root/'evaluations/nfl-availability-replay';folder.mkdir(exist_ok=True)
    ResearchStore._immutable(folder/(digest(report)+'.json'),json.dumps(report,sort_keys=True,allow_nan=False).encode())
    atomic_json(root/'outputs/nfl_availability_repair.json',report)
    atomic_text(root/'reports/NFL_AVAILABILITY_REPAIR.md',markdown(report))
    return report


def markdown(r):
    lines=['# NFL availability forecast repair','',f"Executed: {r['generated_at']}. Policy: {VERSION}.",
        '', 'This is an offline replay of archived pregame inputs, performed after the events. It is not a new prospective prediction or proof of improved accuracy.',
        '', 'The game freeze now consumes availability before publication. The player forecast path attaches a bound availability review and an append-only revision. Current roster status, event injury status, starter confirmation and projected workload are separate. A reported-out player has no eligible prop probability/EV; an unsupported QB change retains the baseline and blocks approval.',
        '',f"Reviewed {r['games_reviewed']} games, {r['prop_forecasts_reviewed']} prop forecasts and {r['price_comparisons_reviewed']} actual archived side comparisons. Suppressed {r['conditional_ev_suppressed']} previously displayed conditional EV values with unsupported participation/role evidence. All {r['original_frozen_files_checked']} checked original forecast files are byte-identical. No odds API requests, new simulations or new prospective forecasts.",
        '',f"Availability states: {json.dumps(r['availability_counts'],sort_keys=True)}",'',
        '| Existing numerical benchmark | OOS games | Win accuracy | MAE | RMSE | Brier | Log loss | Calibration ECE |',
        '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name,m in r['evaluation']['baseline_models'].items():
        lines.append(f"| {name} | {m['n']} | {m['accuracy']:.4f} | {m['mae']:.4f} | {m['rmse']:.4f} | {m['brier']:.6f} | {m['log_loss']:.6f} | {m['calibration']['expected_calibration_error']:.6f} |")
    lines+=['', 'These are the previously inspected, chronologically evaluated samples. No coefficients changed. They are not an untouched test of the new eligibility policy. Ridge still fails to beat Elo consistently. Calibration bins in the JSON are descriptive; no calibrated probabilities are fitted.',
        '',f"Historical availability snapshots preceding an existing OOS fold: {r['evaluation']['authentic_availability_snapshots_before_oos_fold_games']}. Injury-adjusted evaluation N=0; untouched N=0; matched historical execution-price N=0. Cover accuracy, CLV and ROI remain null rather than invented.",
        '', '## Real archived examples', '', '| Player / market | Baseline mean | Baseline workload | Evidence state | Eligible workload | Decision |',
        '|---|---:|---:|---|---|---|']
    for x in r['before_after_examples'][:6]:
        lines.append(f"| {x['player_name']} / {x['market']} | {x['baseline_projection']:.3f} | {x['baseline_opportunity']:.3f} | {x['availability_state']} | unavailable | PASS |")
    lines+=['', 'Baseline numerical values are retained for audit, not relabeled injury-adjusted. Source timestamps/hashes and original forecast/comparison hashes are in the JSON.',
        '', '## Reproduce', '', '`python -m ap_evsims.nfl_news_replay --root .` (offline; requires existing local immutable data).',
        '', '## Remaining limitations','']+['- '+x for x in r['limitations']]+['']
    return '\n'.join(lines)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',default='.')
    r=run(p.parse_args().root)
    print(json.dumps({k:r[k] for k in ('games_reviewed','prop_forecasts_reviewed','price_comparisons_reviewed','availability_counts',
        'conditional_ev_suppressed','original_frozen_files_checked','original_frozen_files_unchanged','new_prospective_forecasts','sportsbook_api_requests')}))


if __name__=='__main__':main()

"""Rolling prior-game features. Missing EPA is never replaced by CFBD PPA.

Only play/game manifests demonstrably available before as_of may contribute.
The feature definitions and opponent adjustment are deliberately transparent;
they need empirical validation before deployment.
"""
from collections import defaultdict
from dataclasses import dataclass
import math
from .integrity import utc,digest
from .models.base import FeatureSnapshot,FeatureValue
from .providers.normalize import require_historical_availability

ELIGIBLE_PLAY_TYPES={'Rush','Pass Reception','Pass Incompletion','Passing Touchdown','Rushing Touchdown','Sack','Interception','Fumble Recovery (Own)','Fumble Recovery (Opponent)'}

@dataclass(frozen=True)
class PlayFact:
    play_id: str
    event_id: str
    offense: str
    defense: str
    down: int
    distance: float
    yards: float
    play_type: str
    epa: float | None
    ppa: float | None
    observed_at: str
    available_at: str | None
    snapshot_id: str
    payload_hash: str

def normalize_cfbd_plays(payload,manifest, *, game_observed_times):
    out=[]; excluded=[]
    for row in payload:
        game=str(row.get('gameId','')); observed=game_observed_times.get(game)
        if observed is None:
            excluded.append(dict(play_id=str(row.get('id')),reason='GAME_COMPLETION_TIME_UNVERIFIED')); continue
        # CFBD exposes PPA. EPA is accepted only if explicitly present in a
        # separately verified enrichment; it is never relabeled from PPA.
        try:
            if row.get('playType') not in ELIGIBLE_PLAY_TYPES: continue
            values=[row['distance'],row['yardsGained']]
            if row['down'] not in (1,2,3,4) or any(not isinstance(x,(int,float)) or not math.isfinite(x) for x in values): continue
            if not row.get('offense') or not row.get('defense'): continue
            ppa=row.get('ppa')
            if ppa is not None and (not isinstance(ppa,(int,float)) or not math.isfinite(ppa)): ppa=None
            out.append(PlayFact(str(row['id']),game,row['offense'],row['defense'],row['down'],row['distance'],row['yardsGained'],row['playType'],
                None,ppa,observed,manifest.get('available_at'),manifest['snapshot_id'],manifest['payload_hash']))
        except (KeyError,TypeError): excluded.append(dict(play_id=str(row.get('id')),reason='MISSING_PLAY_FIELDS'))
    return out,excluded

def adjusted_efficiency(plays,metric,shrinkage=100,iterations=60):
    """Opponent-adjusted attack and conceded efficiencies from prior plays only."""
    usable=[p for p in plays if getattr(p,metric) is not None]
    if not usable: return {},{}
    mean=sum(getattr(p,metric) for p in usable)/len(usable)
    offenses=defaultdict(list); defenses=defaultdict(list)
    for p in usable: offenses[p.offense].append(p); defenses[p.defense].append(p)
    attack={team:0. for team in offenses}; conceded={team:0. for team in defenses}
    for _ in range(iterations):
        next_attack={team:sum(getattr(p,metric)-mean-conceded[p.defense] for p in rows)/(len(rows)+shrinkage) for team,rows in offenses.items()}
        next_conceded={team:sum(getattr(p,metric)-mean-next_attack[p.offense] for p in rows)/(len(rows)+shrinkage) for team,rows in defenses.items()}
        delta=max([abs(next_attack[k]-attack[k]) for k in attack]+[abs(next_conceded[k]-conceded[k]) for k in conceded])
        attack,conceded=next_attack,next_conceded
        if delta<1e-9: break
    return {t:mean+v for t,v in attack.items()},{t:mean+v for t,v in conceded.items()}

def rolling_matchup_features(plays, *, event_id,home_team,away_team,as_of,minimum_plays=100,minimum_games=3):
    if minimum_plays<1 or minimum_games<1: raise ValueError('invalid feature policy')
    prior=[]; seen=set()
    for p in plays:
        if p.play_id in seen: raise ValueError('DUPLICATE_PLAY')
        seen.add(p.play_id)
        if p.event_id==event_id: continue
        if p.available_at is None: continue
        if not utc(p.observed_at)<=utc(p.available_at): raise ValueError('LOOKAHEAD_RISK')
        if utc(p.available_at)<=utc(as_of): prior.append(p)
    by_team={t:[p for p in prior if p.offense==t] for t in (home_team,away_team)}
    if any(len(rows)<minimum_plays or len({p.event_id for p in rows})<minimum_games for rows in by_team.values()):
        raise ValueError('INSUFFICIENT_PRIOR_PLAY_DATA')
    values={}; provenance=digest([p.__dict__ for p in prior]); available=max(utc(p.available_at) for p in prior).isoformat()
    observed=max(utc(p.observed_at) for p in prior).isoformat()
    def emit(name,value):
        values[name]=FeatureValue(value,'cfbd rolling prior plays v1',observed,available,'derived-'+provenance,provenance)
    for metric in ('epa','ppa'):
        attack,conceded=adjusted_efficiency(prior,metric)
        if all(t in attack and t in conceded for t in (home_team,away_team)):
            if metric=='epa':
                emit('offensive_epa_diff',attack[home_team]-attack[away_team]); emit('offensive_epa_sum',attack[home_team]+attack[away_team])
                emit('defensive_epa_diff',conceded[home_team]-conceded[away_team]); emit('defensive_epa_sum',conceded[home_team]+conceded[away_team])
            else: emit('ppa_diff',attack[home_team]-attack[away_team])
    def success(p): return p.yards >= (p.distance*.5 if p.down==1 else p.distance*.7 if p.down==2 else p.distance)
    rates={t:sum(success(p) for p in rows)/len(rows) for t,rows in by_team.items()}
    emit('success_rate_diff',rates[home_team]-rates[away_team]); emit('success_rate_sum',rates[home_team]+rates[away_team])
    # Plays/game is a volume measure, not clock-based neutral pace or possessions.
    emit('plays_sum',sum(len(rows)/len({p.event_id for p in rows}) for rows in by_team.values()))
    result=FeatureSnapshot(event_id,'CFB',utc(as_of).isoformat(),values); result.validate(as_of)
    return result

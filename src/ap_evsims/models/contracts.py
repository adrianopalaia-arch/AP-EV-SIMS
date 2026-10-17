"""Market-specific feature/opportunity contracts. Contracts are not fitted predictors."""
from dataclasses import dataclass,asdict
from ..integrity import digest,utc

@dataclass(frozen=True)
class Field:
    unit:str
    minimum:float
    maximum:float

R=Field('fraction',0,1);COUNT=Field('count',0,1000);DIFF=Field('difference',-1000,1000)
MINUTES=Field('minutes',0,70);DAYS=Field('days',0,365);MILES=Field('miles',0,15000)
FIELDS={
    'opponent_adjusted_epa':Field('points_per_play',-10,10),'offensive_success_rate':R,'defensive_success_rate':R,
    'explosiveness':Field('yards_per_successful_play',0,100),'line_yards':Field('yards_per_rush',-10,30),
    'havoc_rate':R,'pressure_rate':R,'qb_efficiency':Field('points_per_dropback',-10,10),
    'scoring_opportunities':COUNT,'pace_plays':COUNT,'red_zone_efficiency':R,'injury_depth_impact':DIFF,
    'wind_mph':Field('mph',0,150),'temperature_f':Field('fahrenheit',-100,140),'precipitation_probability':R,
    'home_field':DIFF,'rest_days':DAYS,'travel_miles':MILES,'market_movement_points':DIFF,
    'goalie_gsax':DIFF,'goalie_save_quality':R,'five_on_five_xg_share':R,'shot_attempt_share':R,
    'high_danger_chances':COUNT,'projected_toi':MINUTES,'line_assignment':Field('line_number',1,4),
    'pp_share':R,'individual_shot_attempts_per_60':Field('attempts_per_60_minutes',0,100),
    'opponent_shots_per_60':Field('shots_per_60_minutes',0,100),'back_to_back':Field('indicator',0,1),
    'opponent_expected_shots':COUNT,'minutes':MINUTES,'usage_share':R,'route_share':R,'target_share':R,
    'catch_rate':R,'team_pass_attempts':COUNT,'rush_share':R,'team_rush_attempts':COUNT,
    'yards_per_catch':Field('yards',0,100),'yards_per_carry':Field('yards',-10,100),
    'yards_per_attempt':Field('yards',-10,100),'snap_share':R,'pitch_count':Field('pitches',0,200),
    'batters_faced':Field('batters',0,60),'strikeout_rate':R,'out_rate':R,'hit_rate':R,
    'plate_appearances':Field('plate_appearances',0,10),'lineup_position':Field('batting_order',1,9),
    'platoon_advantage':Field('indicator',0,1),'bases_per_hit':Field('bases',1,4),
    'pace_possessions':Field('possessions',0,200),'points_per_minute':Field('points_per_minute',0,5),
    'rebounds_per_minute':Field('rebounds_per_minute',0,3),'assists_per_minute':Field('assists_per_minute',0,3),
    'threes_per_minute':Field('threes_per_minute',0,3),'offense_rating':DIFF,'defense_rating':DIFF,
}
COMMON=('rest_days','travel_miles','injury_depth_impact')
CFB=('opponent_adjusted_epa','offensive_success_rate','defensive_success_rate','explosiveness','line_yards',
     'havoc_rate','pressure_rate','qb_efficiency','scoring_opportunities','pace_plays','red_zone_efficiency',
     'wind_mph','temperature_f','precipitation_probability','home_field','market_movement_points')+COMMON
NHL=('goalie_gsax','goalie_save_quality','five_on_five_xg_share','shot_attempt_share','high_danger_chances','back_to_back')+COMMON
TEAM=('offense_rating','defense_rating','home_field')+COMMON

@dataclass(frozen=True)
class MarketContract:
    sport:str
    market:str
    family:str
    required:tuple
    role_requirement:str
    player_market:bool=False
    @property
    def version(self):return 'contract-v1-'+digest(asdict(self))[:16]

CONTRACTS={}
def add(sport,market,family,required,role,player=False):
    CONTRACTS[sport,market]=MarketContract(sport,market,family,tuple(dict.fromkeys(required)),role,player)
for market in ('spread','total','moneyline'):add('CFB',market,'discrete_score_distribution',CFB,'lineup')
add('NHL','SOG','toi_x_attempt_rate',NHL+('projected_toi','line_assignment','pp_share','individual_shot_attempts_per_60','opponent_shots_per_60'),'lineup',True)
add('NHL','goalie_saves','shots_faced_x_save_quality',NHL+('projected_toi','opponent_expected_shots'),'goalie',True)
for market in ('ML','totals'):add('NHL',market,'team_goal_distribution',NHL,'goalie')
for market in ('spread','total'):add('NFL',market,'discrete_score_distribution',TEAM+('pace_plays','qb_efficiency','pressure_rate'),'lineup')
NFL={
 'receptions':('route_share','target_share','catch_rate','team_pass_attempts','snap_share'),
 'rushing':('rush_share','team_rush_attempts','yards_per_carry','snap_share'),
 'receiving':('route_share','target_share','catch_rate','team_pass_attempts','yards_per_catch','snap_share'),
 'passing':('team_pass_attempts','yards_per_attempt','snap_share')}
for market,fields in NFL.items():add('NFL',market,'opportunity_x_efficiency',fields+COMMON,'active_role',True)
for market,rate in [('pitcher_K','strikeout_rate'),('pitcher_outs','out_rate'),('hits_allowed','hit_rate')]:
    add('MLB',market,'pitch_count_to_batters_faced',('pitch_count','batters_faced',rate)+COMMON,'listed_pitcher',True)
for market in ('hitter_hits','total_bases'):
    fields=('plate_appearances','lineup_position','platoon_advantage','hit_rate')+COMMON
    if market=='total_bases':fields+=('bases_per_hit',)
    add('MLB',market,'plate_appearance_outcome_distribution',fields,'confirmed_batting_order',True)
for market in ('spread','total'):add('NBA',market,'possession_score_distribution',TEAM+('pace_possessions',),'lineup')
for market in ('points','rebounds','assists','threes'):
    add('NBA',market,'minutes_x_role_rate',('minutes','usage_share',market+'_per_minute')+COMMON,'minutes_role',True)

def validate_contract(contract,features,context, *, units,role,player_id=None,team_id=None):
    if features.sport!=contract.sport or context.sport!=contract.sport or features.event_id!=context.event_id:raise ValueError('CONTRACT_IDENTITY_MISMATCH')
    compatible={'moneyline':'win','ML':'win','totals':'total'}.get(contract.market,contract.market)
    if context.market_type!=compatible:raise ValueError('CONTRACT_MARKET_MISMATCH')
    context.validate();features.validate(context.prediction_timestamp,contract.required)
    if compatible!='win' and (context.line is None or context.line!=context.opposite_line):raise ValueError('MISSING_MARKET_PAIR')
    if contract.player_market and (not player_id or not team_id):raise ValueError('UNVERIFIED_PLAYER_IDENTITY')
    for name in contract.required:
        field=FIELDS[name];value=features.values[name].value
        if units.get(name)!=field.unit:raise ValueError('FEATURE_UNIT_MISMATCH:'+name)
        if not field.minimum<=value<=field.maximum:raise ValueError('FEATURE_RANGE_ERROR:'+name)
        if name in ('lineup_position','line_assignment','back_to_back','platoon_advantage') and value!=int(value):raise ValueError('FEATURE_DISCRETE_VALUE_REQUIRED:'+name)
    if not role or role.get('requirement')!=contract.role_requirement or role.get('event_id')!=context.event_id or role.get('confirmed') is not True or not role.get('source'):
        raise ValueError('UNCONFIRMED_GOALIE' if contract.role_requirement=='goalie' else 'UNVERIFIED_LINEUP')
    if not role.get('available_at') or utc(role['available_at'])>utc(context.prediction_timestamp):raise ValueError('LOOKAHEAD_RISK')
    if (utc(context.prediction_timestamp)-utc(role['available_at'])).total_seconds()>600:raise ValueError('STALE_AVAILABILITY')
    if role.get('limited') is not False:raise ValueError('ROLE_LIMITATION_UNVERIFIED')
    return dict(contract_version=contract.version,status='CONTRACT_COMPLETE',model_status='UNVALIDATED',wager_eligible=False)

"""Market-specific inputs are required evidence, not an arbitrary confidence score."""
import math
from .integrity import utc

CFB = ('opponent_adjusted_epa','offensive_success_rate','defensive_success_rate',
       'explosiveness','line_yards','havoc_pressure','qb_efficiency','scoring_opportunities',
       'pace_plays','red_zone_efficiency','injury_depth_impact','weather','home_field',
       'rest_travel','market_line','american_odds','market_movement')
NHL = ('confirmed_starting_goalie','goalie_gsax','goalie_save_quality','five_on_five_xg_share',
       'shot_attempt_share','high_danger_chances','projected_toi','line_assignment','pp_role',
       'individual_shot_attempt_rate','opponent_shot_suppression','rest_back_to_back',
       'travel','injuries','american_odds')

def feature_reasons(sport, values, feature_time):
    required = CFB if sport == 'CFB' else NHL if sport == 'NHL' else ()
    reasons = []
    if not required: return ['UNSUPPORTED_SPORT']
    for name in required:
        item = values.get(name)
        if not isinstance(item, dict) or item.get('value') is None or not item.get('source') or not item.get('available_at'):
            reasons.append('MISSING_FEATURES'); continue
        try:
            if utc(item['available_at']) > utc(feature_time): reasons.append('LOOKAHEAD_RISK')
            v = item['value']
            if isinstance(v, (int,float)) and not math.isfinite(v): reasons.append('MISSING_FEATURES')
            if isinstance(v,str) and not v.strip(): reasons.append('MISSING_FEATURES')
            if name == 'confirmed_starting_goalie' and v is not True: reasons.append('UNCONFIRMED_GOALIE')
            if name == 'projected_toi' and (not isinstance(v,(int,float)) or v <= 0): reasons.append('MISSING_FEATURES')
            if name.endswith('share') or name in ('offensive_success_rate','defensive_success_rate','red_zone_efficiency'):
                if not isinstance(v,(int,float)) or not 0 <= v <= 1: reasons.append('MISSING_FEATURES')
        except (ValueError, TypeError): reasons.append('LOOKAHEAD_RISK')
    return list(dict.fromkeys(reasons))

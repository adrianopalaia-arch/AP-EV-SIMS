"""Versioned structural ingestion checks; unknown numeric units remain unusable features."""
import math
from ..integrity import utc

CFBD_REQUIRED={
 'games':{'id':(int,str),'homeTeam':str,'awayTeam':str,'startDate':str,'completed':bool},
 'plays':{'id':(int,str),'gameId':(int,str),'offense':str,'defense':str,'playType':str,'yardsGained':(int,float)},
 'teams':{'id':(int,str),'school':str},'venues':{'id':(int,str),'name':str},
 'stats/game/advanced':{'gameId':(int,str),'season':int,'week':int,'team':str,'opponent':str,'offense':dict,'defense':dict},
 'ratings/elo':{'year':int,'team':str},
 'lines':{'id':(int,str),'homeTeam':str,'awayTeam':str,'startDate':str,'lines':list}}

def validate_provider_payload(provider,endpoint,payload):
    if provider!='cfbd' or endpoint not in CFBD_REQUIRED:return
    if not isinstance(payload,list):raise ValueError('SCHEMA_DRIFT')
    def valid_type(value,kind):
        return isinstance(value,kind) and (kind is bool or not isinstance(value,bool))
    for row in payload:
        if not isinstance(row,dict):raise ValueError('SCHEMA_DRIFT')
        for key,kind in CFBD_REQUIRED[endpoint].items():
            if key not in row or not valid_type(row[key],kind):raise ValueError('SCHEMA_DRIFT')
        if 'startDate' in row:utc(row['startDate'])
        if endpoint=='games' and row['completed']:
            for key in ('homePoints','awayPoints'):
                value=row.get(key)
                if not valid_type(value,(int,float)) or not math.isfinite(value) or value<0 or value!=int(value):raise ValueError('SCHEMA_DRIFT')
        if endpoint=='plays':
            if not math.isfinite(row['yardsGained']) or not -110<=row['yardsGained']<=110:raise ValueError('SCHEMA_DRIFT')
        if endpoint=='ratings/elo' and row.get('elo') is not None:
            if not valid_type(row['elo'],(int,float)) or not math.isfinite(row['elo']):raise ValueError('SCHEMA_DRIFT')

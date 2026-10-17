"""Failure-mode fixtures, never empirical betting evidence."""
import copy,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from ap_evsims.integrity import digest
from ap_evsims.event_resolution import validate_nhl_records,resolve_nhl
from ap_evsims.providers.public_stats import PublicStatsArchive
from ap_evsims.research_store import ResearchStore
from ap_evsims.prop_price_evidence import first_comparisons,close_for,grade
from ap_evsims.prop_market_research import comparison
from ap_evsims.prop_availability import interpret
from ap_evsims.prop_research import PlayerOutcome
from ap_evsims.p0_results import publication_base
from test_prop_market_research import inputs


AT='2026-10-16T01:01:00Z'

def hockey():
    event=dict(event_id='1',odds_event_id='book1',event_start='2026-10-17T17:00:00Z',home_team='Washington Capitals',away_team='New Jersey Devils')
    quote=dict(event,odds_event_id='book1',event_start='2026-10-17T17:10:00Z',sport='NHL')
    g=dict(id=1,startTimeUTC=event['event_start'],gameState='FUT',gameScheduleState='OK',gameType=2,
        homeTeam=dict(id=15,placeName={'default':'Washington'},commonName={'default':'Capitals'}),
        awayTeam=dict(id=1,placeName={'default':'New Jersey'},commonName={'default':'Devils'}))
    return event,quote,{'gameWeek':[{'games':[g]}]},copy.deepcopy(g)


class EventEvidenceTests(unittest.TestCase):
    def test_resolved_offset_preserves_both_starts_and_earlier_deadline(self):
        e,q,s,g=hockey();r=validate_nhl_records(e,q,s,g,AT)
        self.assertEqual(r['offset_seconds'],600);self.assertFalse(r['timestamp_override']);self.assertFalse(r['phase1_authority'])
        self.assertEqual(r['pregame_deadline'],r['canonical_start'])
    def test_after_earlier_start_rejects_even_if_book_not_started(self):
        with self.assertRaisesRegex(ValueError,'STARTED'):validate_nhl_records(*hockey(),'2026-10-17T17:05:00Z')
    def test_large_or_earlier_book_offset_rejected(self):
        for t in ('2026-10-17T16:59:00Z','2026-10-17T17:16:00Z'):
            e,q,s,g=hockey();q['event_start']=t
            with self.assertRaisesRegex(ValueError,'OFFSET'):validate_nhl_records(e,q,s,g,AT)
    def test_wrong_teams_and_competition_rejected(self):
        e,q,s,g=hockey();q['home_team']='Other'
        with self.assertRaisesRegex(ValueError,'TEAM'):validate_nhl_records(e,q,s,g,AT)
        e,q,s,g=hockey();g['gameType']=3
        with self.assertRaisesRegex(ValueError,'DOMAIN'):validate_nhl_records(e,q,s,g,AT)
    def test_ambiguous_or_revised_schedule_rejected(self):
        e,q,s,g=hockey();s['gameWeek'][0]['games'].append(copy.deepcopy(g))
        with self.assertRaisesRegex(ValueError,'AMBIGUOUS'):validate_nhl_records(e,q,s,g,AT)
        e,q,s,g=hockey();g['startTimeUTC']='2026-10-17T17:05:00Z'
        with self.assertRaisesRegex(ValueError,'REVISION'):validate_nhl_records(e,q,s,g,AT)
    def test_mismatched_league_team_ids_rejected(self):
        e,q,s,g=hockey();g['homeTeam']['id']=99
        with self.assertRaisesRegex(ValueError,'TEAM_ID'):validate_nhl_records(e,q,s,g,AT)
    def test_real_archive_hashes_required_for_resolution(self):
        with tempfile.TemporaryDirectory() as d:
            e,q,s,g=hockey();store=ResearchStore(d)
            archive=PublicStatsArchive(d,lambda url,headers:SimpleNamespace(status=200,body=json.dumps(g if '/gamecenter/' in url else s).encode(),fetched_at=AT))
            sm=archive.capture('NHL','https://api-web.nhle.com/v1/schedule/2026-10-17')
            lm=archive.capture('NHL','https://api-web.nhle.com/v1/gamecenter/1/landing')
            bp=dict(id='book1',commence_time=q['event_start'],home_team=q['home_team'],away_team=q['away_team'])
            bm=store.archive(provider='odds',endpoint='/fixture',parameters={},body=json.dumps(bp).encode(),fetched_at=AT)
            q['snapshot_id']=bm['snapshot_id'];a={'source_manifest':lm['manifest_id']}
            r=resolve_nhl(store,e,q,a,AT);self.assertEqual(r['gamecenter_hash'],lm['hash'])
            (Path(d)/lm['path']).write_bytes(b'{}')
            with self.assertRaisesRegex(ValueError,'HASH'):resolve_nhl(store,e,q,a,AT)
    def test_caller_flag_does_not_bypass_missing_mapping_evidence(self):
        f,q,a,e=inputs();f['sport']=q['sport']=a['sport']='NHL';q['event_start']='2026-10-20T19:10:00Z'
        f['event_mapping']['market_identity_verified']=True
        self.assertFalse(comparison(f,q,a,e,AT)[0]['price_identity_verified'])
    def test_postseason_mlb_stays_outside_regular_season_model_domain(self):
        event=dict(event_id='1',event_start='2026-10-17T01:00:00Z',home_team='Home',away_team='Away',competition_type='L')
        p=dict(player_id='1',name='Player',team_id='A',position='OF')
        payload={'teams':{'home':{'team':{'id':'A','name':'Home'},'battingOrder':list(range(1,10))},'away':{'team':{'id':'B','name':'Away'}}}}
        m=dict(captured_at=AT,manifest_id='a'*64,hash='b'*64)
        r=interpret('MLB',event,[p],payload,m)[0]
        self.assertTrue(r['role_confirmed']);self.assertIn('MODEL_COMPETITION_DOMAIN_MISMATCH',r['reasons'])


def priced():
    f,q,a,e=inputs();f['projection']['baseline']=4;f['priced_markets']=[]
    f['forecast_hash']=digest({k:v for k,v in f.items() if k!='forecast_hash'})
    c=comparison(f,q,a,e,AT)[0];c['comparison_hash']=digest(c)
    row=PlayerOutcome('NBA','rebounds','1','p','Player','A','B','2026-10-20',2026,30.,7,'a'*64,'b'*64,'2026-10-21T00:00:00Z')
    return f,c,row,q


class PriceEvidenceTests(unittest.TestCase):
    def test_partial_publication_recovers_only_hash_verified_generation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'outputs').mkdir();(root/'data/snapshots').mkdir(parents=True)
            value={'original':True};generation='a'*64;h=digest(value)
            (root/'outputs/last_update.json').write_text(json.dumps(dict(publication_generation=generation,feed_hashes={'feed.json':h})))
            (root/'outputs/feed.json').write_text('{}')
            snapshot=root/'data/snapshots'/(generation+'-feed.json');snapshot.write_text(json.dumps(value))
            self.assertEqual(publication_base(root)[1]['feed.json'],value)
            snapshot.write_text('{}')
            with self.assertRaisesRegex(ValueError,'SNAPSHOT_HASH'):publication_base(root)
    def test_refreshes_do_not_inflate_evaluation_sample(self):
        f,c,row,q=priced();later=dict(c,decision_timestamp='2026-10-16T01:02:00Z');later['comparison_hash']=digest({k:v for k,v in later.items() if k!='comparison_hash'})
        self.assertEqual(first_comparisons([later,c]),[c])
    def test_invalid_first_update_does_not_poison_later_valid_cohort(self):
        f,c,row,q=priced();bad=dict(c,price_identity_verified=False,decision_timestamp='2026-10-16T01:00:30Z');bad['comparison_hash']=digest({k:v for k,v in bad.items() if k!='comparison_hash'})
        self.assertEqual(first_comparisons([bad,c],eligible_only=True),[c])
    def test_comparison_mutation_rejected(self):
        f,c,row,q=priced();c['odds']=200
        with self.assertRaisesRegex(ValueError,'HASH'):first_comparisons([c])
        with self.assertRaisesRegex(ValueError,'HASH'):grade(c,f,row,[],'2026-10-21T01:00:00Z')
    def test_statistic_scores_separate_from_qualified_roi(self):
        f,c,row,q=priced();r=grade(c,f,row,[],'2026-10-21T01:00:00Z')
        self.assertEqual(r['statistic_result'],'WIN');self.assertAlmostEqual(r['descriptive_market_brier'],.25)
        self.assertIsNone(r['hypothetical_roi']);self.assertIsNone(r['qualified_clv']);self.assertIsNone(r['qualified_market_brier'])
    def test_future_result_capture_cannot_settle(self):
        f,c,row,q=priced()
        with self.assertRaisesRegex(ValueError,'NOT_YET_AVAILABLE'):grade(c,f,row,[],'2026-10-20T21:00:00Z')
    def test_closing_quote_must_be_captured_before_earlier_start(self):
        f,c,row,q=priced();c['odds_event_id']='o'
        q.update(quote_timestamp='2026-10-20T18:59:00Z',captured_at='2026-10-20T18:59:10Z')
        self.assertEqual(close_for(c,[q],'2026-10-21T00:00:00Z'),q)
        q['captured_at']='2026-10-20T19:00:01Z';self.assertIsNone(close_for(c,[q],'2026-10-21T00:00:00Z'))
    def test_closing_quote_wrong_line_or_event_cannot_match(self):
        f,c,row,q=priced();c['odds_event_id']='o';q.update(quote_timestamp='2026-10-20T18:59:00Z',captured_at='2026-10-20T18:59:10Z')
        for update in ({'line':5.5},{'odds_event_id':'other'},{'period':'first_half'}):
            self.assertIsNone(close_for(c,[dict(q,**update)],'2026-10-21T00:00:00Z'))


if __name__=='__main__':unittest.main()

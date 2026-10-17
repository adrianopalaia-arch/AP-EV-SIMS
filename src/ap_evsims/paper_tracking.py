"""Prospective 100-candidate diagnostic ledger. No cash/account/exposure writes.

Every considered DK CFB side and rejection is frozen. The cohort uses one fixed
direction (home/over) per event/market, so complementary sides are not two trials.
"""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import statistics

from .integrity import database, digest, utc
from .paper_market import archived_quotes, family, fresh, consensus, closing_evidence
from .display_pricing import opposite_side, market_calculations
from .calibration import brier_score, log_loss, calibration_bins
from .historical import unit_profit
from .models.base import MarketContext
from .settlement import SettlementRule, grade
from .results import cfbd_results_as_of
from .publication import atomic_json, atomic_text

PHASE='cfb-market-benchmark-100-v1'


class PaperLedger:
    def __init__(self,path):
        self.path=str(path);Path(path).parent.mkdir(parents=True,exist_ok=True)
        with database(self.path) as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS paper_phase(id TEXT PRIMARY KEY, body TEXT, hash TEXT);
                CREATE TABLE IF NOT EXISTS paper_observations(id TEXT PRIMARY KEY, family TEXT, captured_at TEXT, body TEXT, hash TEXT);
                CREATE TABLE IF NOT EXISTS paper_cohort(family TEXT PRIMARY KEY, observation_id TEXT UNIQUE, sequence INTEGER UNIQUE);
                CREATE TABLE IF NOT EXISTS paper_revisions(id TEXT PRIMARY KEY, observation_id TEXT, kind TEXT, known_at TEXT, body TEXT, hash TEXT);''')
    def start(self,at):
        policy=dict(id=PHASE,started_at=utc(at).isoformat(),target=100,reference_unit=22,scope='CFB full-game DK spread/total/moneyline',
            cohort_rule='first fresh paired home/over quote per event/market within 24h; >=2 external books; exact canonical game identity',
            max_quote_age_seconds=180,close_window_seconds=300,core_enabled=False,automatic_cash_commitments=False,
            minimum_model_validation_unchanged=True,unit_semantics='paper reference, not bankroll or spend authorization',
            diagnostic_only=True,actual_cash_roi=None)
        with database(self.path) as db:
            old=db.execute('SELECT body,hash FROM paper_phase WHERE id=?',(PHASE,)).fetchone()
            if old:return self._verified(old)
            db.execute('INSERT INTO paper_phase VALUES (?,?,?)',(PHASE,json.dumps(policy,sort_keys=True),digest(policy)))
        return policy
    @staticmethod
    def _verified(row):
        body=json.loads(row[0])
        if digest(body)!=row[1]:raise ValueError('PAPER_LEDGER_HASH_MISMATCH')
        return body
    def policy(self):
        with database(self.path) as db:r=db.execute('SELECT body,hash FROM paper_phase WHERE id=?',(PHASE,)).fetchone()
        return self._verified(r) if r else None
    def observe(self,body,*,cohort_eligible):
        policy=self.policy()
        if policy is None:raise ValueError('PAPER_PHASE_NOT_STARTED')
        if not utc(policy['started_at'])<=utc(body['decision_at']):raise ValueError('PAPER_BACKFILL_FORBIDDEN')
        if body.get('decision')!='PASS' or body.get('cash_committed')!=0 or body.get('core_label') is not None:raise ValueError('PAPER_HAS_NO_WAGER_AUTHORITY')
        identity=digest([PHASE,body['quote']['quote_id'],body['model'].get('artifact'),body['model'].get('feature_fingerprint'),body['pass_reasons']])
        fam=digest(family(body['quote']))
        with database(self.path) as db:
            db.execute('BEGIN IMMEDIATE')
            old=db.execute('SELECT body,hash FROM paper_observations WHERE id=?',(identity,)).fetchone()
            if old:return self._verified(old)
            n=db.execute('SELECT count(*) FROM paper_cohort').fetchone()[0]
            prior=db.execute('SELECT 1 FROM paper_cohort WHERE family=?',(fam,)).fetchone()
            included=cohort_eligible and not prior and n<policy['target']
            body=dict(body,observation_id=identity,in_cohort=included,cohort_sequence=n+1 if included else None)
            if cohort_eligible and not included:body['cohort_rejections']=body['cohort_rejections']+['COHORT_MARKET_ALREADY_FROZEN' if prior else 'COHORT_TARGET_REACHED']
            db.execute('INSERT INTO paper_observations VALUES (?,?,?,?,?)',(identity,fam,body['decision_at'],json.dumps(body,sort_keys=True,allow_nan=False),digest(body)))
            if included:db.execute('INSERT INTO paper_cohort VALUES (?,?,?)',(fam,identity,n+1))
        return body
    def observations(self,cohort=False):
        with database(self.path) as db:
            sql='SELECT o.body,o.hash FROM paper_observations o'
            if cohort:sql+=' JOIN paper_cohort c ON c.observation_id=o.id ORDER BY c.sequence'
            else:sql+=' ORDER BY o.captured_at,o.id'
            rows=db.execute(sql).fetchall()
        return [self._verified(r) for r in rows]
    def revise(self,identity,kind,known_at,body):
        if kind not in ('result','close'):raise ValueError('INVALID_PAPER_REVISION')
        revision=digest([identity,kind,utc(known_at).isoformat(),body])
        with database(self.path) as db:
            if not db.execute('SELECT 1 FROM paper_observations WHERE id=?',(identity,)).fetchone():raise ValueError('UNKNOWN_PAPER_OBSERVATION')
            previous=db.execute('SELECT id,body,hash FROM paper_revisions WHERE observation_id=? AND kind=? ORDER BY known_at DESC,rowid DESC LIMIT 1',(identity,kind)).fetchone()
            if previous and self._verified(previous[1:])==body:return previous[0]
            db.execute('INSERT OR IGNORE INTO paper_revisions VALUES (?,?,?,?,?,?)',(revision,identity,kind,utc(known_at).isoformat(),json.dumps(body,sort_keys=True,allow_nan=False),digest(body)))
        return revision
    def latest(self,identity,kind,at):
        with database(self.path) as db:
            row=db.execute('SELECT body,hash FROM paper_revisions WHERE observation_id=? AND kind=? AND known_at<=? ORDER BY known_at DESC,rowid DESC LIMIT 1',
                           (identity,kind,utc(at).isoformat())).fetchone()
        return self._verified(row) if row else None


def capture_candidates(ledger,store,warehouse,quotes,rows,universe,at):
    policy=ledger.policy()
    if policy is None:return
    archive=archived_quotes(store,warehouse,at);by_id={q['quote_id']:q for q in archive}
    current=[by_id[q['quote_id']] for q in quotes if q['sport']=='CFB']
    pairs={}
    for q in current:pairs.setdefault(q['pair_id'],[]).append(q)
    games={}
    for g in universe.get('games',[]):
        for oid in g['matched_odds_event_ids']:games.setdefault(oid,[]).append(g)
    for row in rows:
        if row['sport']!='CFB' or row['book']!='draftkings':continue
        q=by_id[row['candidate_id']];why=[]
        if q['period']!='full_game':why.append('UNSUPPORTED_PERIOD')
        if not fresh(q,at):why.append('STALE_OR_IMPOSSIBLE_PRICE')
        if not 0<(utc(q['event_start'])-utc(at)).total_seconds()<=86400:why.append('OUTSIDE_24H_COHORT_WINDOW')
        if q['selection']!=('Over' if q['market']=='totals' else q['home_team']):why.append('COMPLEMENTARY_SIDE_NOT_COHORT')
        opposite=opposite_side(q,pairs[q['pair_id']]);market=market_calculations(q,opposite)
        if opposite is None:why.append('MISSING_OPPOSITE_SIDE')
        if market['push_policy']=='UNKNOWN':why.append('UNSUPPORTED_PAYOUT_RULE')
        benchmark=consensus(q,current,at)
        if benchmark['reason']:why.append(benchmark['reason'])
        mapped=games.get(q['event_id'],[])
        canonical=mapped[0] if len(mapped)==1 and utc(mapped[0]['event_start'])==utc(q['event_start']) else None
        if canonical is None:why.append('EVENT_MAPPING_UNVERIFIED')
        first=min((v for v in archive if family(v)==family(q) and v['book']==q['book'] and utc(v['available_at'])<=utc(at)),
                  key=lambda v:(utc(v['available_at']),v['quote_id']),default=None)
        model=dict(raw=row.get('model_probability'),calibrated=row.get('calibrated_probability'),p_low=row.get('p_low'),
            raw_ev=row.get('ap_raw_ev'),calibrated_ev=row.get('ap_calibrated_ev'),version=row.get('model_version'),
            artifact=row.get('model_artifact_id'),feature_fingerprint=row.get('feature_fingerprint'),training_cutoff=row.get('training_cutoff'),
            calibration_version=row.get('calibration_version'),status='UNVALIDATED',p_low_status=row.get('p_low_status','UNAVAILABLE'))
        if model['raw'] is not None and (not model['artifact'] or not model['feature_fingerprint']):raise ValueError('UNVERIFIED_PAPER_MODEL')
        # No raw forecast or odds-derived baseline is promoted to a calibrated forecast.
        if model['calibrated'] is not None and not model['calibration_version']:raise ValueError('UNVERIFIED_PAPER_CALIBRATION')
        body=dict(decision_at=utc(at).isoformat(),quote=q,canonical_event_id=None if canonical is None else canonical['event_id'],
            canonical_home=None if canonical is None else canonical['home_team'],canonical_away=None if canonical is None else canonical['away_team'],
            data_timestamps=row['data_timestamps'],model=model,market=market,consensus=benchmark,
            opening_price=None,opening_price_reason='TRUE_OPENER_UNVERIFIED',first_observed_price=first,
            candidate_price=q,recommended_price=None,recommendation_reason='NO_PHASE1_APPROVED_RECOMMENDATION',
            decision='PASS',pass_reasons=list(dict.fromkeys(row['pass_reason']+['PAPER_ONLY_CORE_DISABLED'])),cohort_rejections=why,
            model_selected=False,core_label=None,cash_committed=0,reference_unit=22,estimated_cost_per_unit=None,net_ev_after_costs=None,
            cost_note='Unknown execution costs remain unknown; any scenario report is hypothetical.')
        ledger.observe(body,cohort_eligible=not why)


def reconcile(ledger,store,warehouse,at):
    entries=[o for o in ledger.observations(cohort=True) if utc(o['decision_at'])<=utc(at)]
    if not entries:return
    quotes=archived_quotes(store,warehouse,at)
    results={r['event_id']:r for r in cfbd_results_as_of(store,warehouse,at)}
    for entry in entries:
        q=entry['quote'];identity=entry['observation_id']
        close=closing_evidence(store,q,quotes,at)
        ledger.revise(identity,'close',at,close)
        r=results.get(entry['canonical_event_id'])
        if r is None:continue
        reason=None;outcome=None
        if (r['home_team'],r['away_team'],utc(r['event_timestamp']))!=(entry['canonical_home'],entry['canonical_away'],utc(q['event_start'])):reason='RESULT_EVENT_IDENTITY_MISMATCH'
        elif r['status']!='final':reason='UNSETTLED_RESULT'
        elif utc(r['result_available_at'])<=utc(q['event_start']):reason='LOOKAHEAD_RISK'
        else:
            kind={'spreads':'spread','totals':'total','h2h':'win'}[q['market']]
            selection='over' if kind=='total' else 'home'
            context=MarketContext(entry['canonical_event_id'],'CFB',kind,selection,'draftkings',q['line'],q['american_odds'],None,
                entry['decision_at'],q['observed_at'],q['event_start'],q['snapshot_id'])
            rule=SettlementRule('draftkings','CFB',kind,'full_game',True,kind!='win',False,0,False,
                'AP paper full-game final-score convention; not proof of DK cash settlement rules',ledger.policy()['started_at'],'paper-score-v1')
            value=r['home_score']+r['away_score'] if kind=='total' else r['home_score']-r['away_score']
            try:outcome=grade(rule,context=context,observed_stat=value,final_status=r['status'],decision_at=entry['decision_at'])
            except ValueError:reason='UNVERIFIED_SETTLEMENT'
        body=dict(source_snapshot_id=r['snapshot_id'],source_hash=r['payload_hash'],available_at=r['result_available_at'],
            status=r['status'],outcome=outcome,reason=reason,home_score=r['home_score'],away_score=r['away_score'],
            hypothetical_unit_profit=unit_profit(outcome,q['american_odds']) if outcome else None,
            sportsbook_settlement_verified=False,actual_cash_profit=None,
            convention='complete official CFB final score including overtime; no assumed cancellation or abandonment grading')
        ledger.revise(identity,'result',r['result_available_at'],body)


def score_comparison(entries,key):
    rows=[r for r in entries if r['result'] and r['result']['outcome'] in ('WIN','LOSS') and r['observation']['model'].get(key) is not None
          and r['observation']['consensus']['probability'] is not None]
    if not rows:return dict(n=0,brier=None,logloss=None,market_brier=None,market_logloss=None,calibration=[])
    y=[int(r['result']['outcome']=='WIN') for r in rows];p=[r['observation']['model'][key] for r in rows];market=[r['observation']['consensus']['probability'] for r in rows]
    return dict(n=len(rows),brier=brier_score(p,y),logloss=log_loss(p,y),market_brier=brier_score(market,y),market_logloss=log_loss(market,y),calibration=calibration_bins(p,y))


def grouped_diagnostics(entries):
    """Predefined descriptive groups; never select or promote a winning subgroup."""
    def bucket(entry,axis):
        o=entry['observation'];q=o['quote']
        if axis in ('sport','market'):return q[axis]
        if axis=='odds_range':
            return 'below_-150' if q['american_odds'] < -150 else '-150_through_+150' if q['american_odds'] <=150 else 'above_+150'
        p=o['model']['calibrated']
        return 'UNAVAILABLE' if p is None else 'below_40pct' if p<.4 else '40_to_60pct' if p<=.6 else 'above_60pct'
    result={}
    for axis in ('sport','market','odds_range','calibrated_probability_band'):
        result[axis]={}
        for label in sorted({bucket(e,axis) for e in entries}):
            group=[e for e in entries if bucket(e,axis)==label]
            binary=[e for e in group if e['result'] and e['result']['outcome'] in ('WIN','LOSS')]
            p=[e['observation']['consensus']['probability'] for e in binary];y=[int(e['result']['outcome']=='WIN') for e in binary]
            result[axis][label]=dict(candidates=len(group),unique_games=len({e['observation']['quote']['event_id'] for e in group}),
                binary_n=len(binary),market_brier=brier_score(p,y) if p else None,market_logloss=log_loss(p,y) if p else None,
                paired_raw=score_comparison(group,'raw'),paired_calibrated=score_comparison(group,'calibrated'))
    return result


def report(ledger,at):
    policy=ledger.policy();observations=[o for o in ledger.observations() if utc(o['decision_at'])<=utc(at)]
    cohort=[o for o in ledger.observations(cohort=True) if utc(o['decision_at'])<=utc(at)]
    entries=[dict(observation=o,result=ledger.latest(o['observation_id'],'result',at),close=ledger.latest(o['observation_id'],'close',at)) for o in cohort]
    settled=[r for r in entries if r['result'] and r['result']['outcome'] in ('WIN','LOSS','PUSH','VOID')]
    binary=[r for r in settled if r['result']['outcome'] in ('WIN','LOSS')]
    p=[r['observation']['consensus']['probability'] for r in binary];y=[int(r['result']['outcome']=='WIN') for r in binary]
    point=[r['close']['point_clv'] for r in entries if r['close'] and r['close']['point_clv'] is not None]
    price=[r['close']['price_clv'] for r in entries if r['close'] and r['close']['price_clv'] is not None]
    comparisons={k:score_comparison(entries,k) for k in ('raw','calibrated')}
    by_model={}
    for version in sorted({r['observation']['model']['version'] for r in entries if r['observation']['model']['version']}):
        group=[r for r in entries if r['observation']['model']['version']==version]
        by_model[version]={k:score_comparison(group,k) for k in ('raw','calibrated')}
    hypothetical=sum(r['result']['hypothetical_unit_profit'] for r in settled)
    roi_denominator=sum(r['result']['outcome']!='VOID' for r in settled)
    total=peak=drawdown=0.
    for r in sorted(settled,key=lambda r:r['result']['available_at']):
        total+=22*r['result']['hypothetical_unit_profit'];peak=max(peak,total);drawdown=max(drawdown,peak-total)
    summary=dict(generated_at=utc(at).isoformat(),phase_id=PHASE,status='COLLECTING' if len(cohort)<100 else 'TARGET_COLLECTED_AWAITING_SETTLEMENT' if len(settled)<100 else 'INITIAL_DIAGNOSTIC_COMPLETE',
        target=100,cohort_candidates=len(cohort),unique_games=len({o['quote']['event_id'] for o in cohort}),observations_logged=len(observations),
        rejected_observations=sum(bool(o['cohort_rejections']) for o in observations),pass_reasons=dict(Counter(v for o in observations for v in o['pass_reasons'])),
        cohort_rejections=dict(Counter(v for o in observations for v in o['cohort_rejections'])),settled_candidates=len(settled),
        results=dict(Counter(r['result']['outcome'] for r in settled)),reference_unit=22,cash_committed=0,actual_cash_roi=None,model_selected_roi=None,
        performance_groups=grouped_diagnostics(entries),
        baseline_probability_score=dict(n=len(binary),brier=brier_score(p,y) if p else None,logloss=log_loss(p,y) if p else None,
                                        calibration=calibration_bins(p,y) if p else []),paired_model_comparison=comparisons,performance_by_model=by_model,
        point_clv=dict(n=len(point),mean=statistics.mean(point) if point else None),price_clv=dict(n=len(price),mean=statistics.mean(price) if price else None),
        hypothetical_fixed_direction_cohort=dict(n=len(settled),roi_denominator=roi_denominator,roi=hypothetical/roi_denominator if roi_denominator else None,profit_at_22=hypothetical*22 if settled else None,
            max_drawdown_at_22=drawdown if settled else None,not_a_model_strategy=True,sportsbook_rules_and_execution_unverified=True,
            cost_scenarios=[dict(cost_per_unit=c,roi=(hypothetical/roi_denominator-c) if roi_denominator else None) for c in (0,.005,.01)]),
        model_predictions=sum(o['model']['raw'] is not None for o in cohort),calibrated_predictions=sum(o['model']['calibrated'] is not None for o in cohort),
        core_enabled=False,models_validated=0,synthetic_performance_sample=0,profitability_demonstrated=False,
        limitations=['100 candidates are an initial diagnostic, not model validation; candidates share games and are not independent.',
            'Paired scores use identical settled observations; pushes/voids are excluded from binary scoring.',
            'Missing models, costs, book-rule proof, true openers and near-start closes remain missing.',
            'Market movement is evidence to investigate, not proof of profitability; fixed-direction ROI is counterfactual.',
            'NHL goalie/line changes, NFL injury usage, MLB lineups and CFB depth surprises remain unproven research hypotheses.'])
    return summary,entries


def update_paper(repo,store,warehouse,quotes,rows,universe,at):
    path=store.root/'predictions/paper-tracking.sqlite'
    if not path.exists():return dict(status='NOT_STARTED',core_enabled=False)
    ledger=PaperLedger(path)
    if ledger.policy() is None:return dict(status='NOT_STARTED',core_enabled=False)
    capture_candidates(ledger,store,warehouse,quotes,rows,universe,at)
    reconcile(ledger,store,warehouse,at);summary,entries=report(ledger,at)
    atomic_json(store.root/'evaluations/paper-tracking-observations.json',ledger.observations())
    atomic_json(store.root/'evaluations/paper-tracking-settlements.json',entries)
    atomic_json(Path(repo)/'outputs/paper_tracking_status.json',summary)
    atomic_text(Path(repo)/'reports/PERFORMANCE_AUDIT.md','\n'.join([
        '# AP EV/SIMS paper tracking performance audit','',f'Generated UTC: {at}', '',
        f"Cohort: {summary['cohort_candidates']}/100 candidates across {summary['unique_games']} games. Settled: {summary['settled_candidates']}.",
        f"Considered quote/model observations: {summary['observations_logged']}. Rejections: {summary['rejected_observations']}.",
        f"Real model forecasts: {summary['model_predictions']}; calibrated forecasts: {summary['calibrated_predictions']}. CORE remains disabled.",
        'The $22 unit is a paper reference. Cash committed: $0. Actual cash ROI and model-selected ROI are unavailable.',
        'The fixed home/over cohort is a collection policy, not a recommended betting strategy. Its outcome arithmetic is hypothetical.',
        'Raw/calibrated model scores are compared with the ex-DraftKings consensus only on the same settled observations.',
        'A first-observed price is not a proven opener. A last quote older than five minutes before kickoff is not accepted as a close.',
        'No probabilities, settlement receipts, execution costs, cancelled outcomes or closing prices are invented.',
        '', 'Machine-readable metrics: outputs/paper_tracking_status.json',
        'Local candidate/rejection evidence: data/evaluations/paper-tracking-observations.json',
        'Local settlement and closing revisions: data/evaluations/paper-tracking-settlements.json',
        '', '100 observations are diagnostic only. Chronological calibration, p_low coverage and Phase 1 risk gates remain required.'])+'\n')
    return summary


def start_paper(repo,at=None):
    return PaperLedger(Path(repo)/'data/predictions/paper-tracking.sqlite').start(at or datetime.now(timezone.utc).isoformat())

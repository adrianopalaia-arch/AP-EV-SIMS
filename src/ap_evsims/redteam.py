"""Auditable readiness inventory. Passing mechanics never substitutes for missing evidence."""
from datetime import datetime,timezone
from .publication import atomic_json,atomic_text
from .diagnostics import readiness_gate,bankroll_stress

NAMES=('EXECUTION REALITY','DRAFTKINGS / FANDUEL MARKET IDENTITY','MARKET AVAILABILITY BIAS',
 'MULTIPLE TESTING / DATA SNOOPING','FINAL HOLDOUT LOCK','SURVIVORSHIP BIAS','ROSTER IDENTITY / NAME COLLISIONS',
 'STAT CORRECTIONS','TIMEZONE / DST / DATE BOUNDARY','GAME POSTPONEMENTS / CANCELLATIONS','SETTLEMENT RULES',
 'ALT LINES','PRICE / LINE JOINT CONSISTENCY','LATENCY','STALE LINEUP / ROLE INFORMATION','WEATHER REVISION RISK',
 'MARKET-MAKER INFORMATION','CLOSING LINE VALUE CAVEAT','BOOKMAKER HOLD / VIG CHANGES',
 'CORRELATED FEATURE DUPLICATION','ENSEMBLE FALSE CONFIDENCE','REGIME SHIFT','SMALL SAMPLE STARS',
 'ROLE CHANGE DETECTION','INJURY RETURN / LIMITATION','BLOWOUT / GAME-STATE RISK','COACHING / SYSTEM CHANGES',
 'PROVIDER SCHEMA DRIFT','PROVIDER OUTAGE / PARTIAL RESPONSE','UNIT / SCALE ERRORS','NUMERIC INSTABILITY',
 'CLASS IMBALANCE','PUSH / VOID IMPACT ON ROI','PROMOTIONS','LIVE BETTING DANGER','DATA-SNOOPING FROM MISSES',
 'BACKTEST REALISM','BOOTSTRAP UNCERTAINTY','MONTE CARLO BANKROLL STRESS','KELLY ESTIMATION RISK',
 'SAME-DAY EXPOSURE','BETTER-THAN-MARKET REQUIREMENT','NEGATIVE CONTROL TESTS','LABEL SHUFFLE TEST',
 'TIME-SHIFT LEAKAGE TEST','ADVERSARIAL MARKET TEST','MIRACLE GAME TEST','FALSE CONFIDENCE AUDIT','RED TEAM REPORT','READINESS GATE')

# (test module, implemented control, remaining risk). None means no targeted test.
CONTROLS={
1:('test_governance_execution.py','Stale/suspended/unverified execution rejects; slippage arithmetic','No historical execution proof or realistic empirical backtest.'),
2:('test_identity.py','Exact alias/start matching and market/rule identity','Player mappings and actual book rule versions absent.'),
3:('test_diagnostics_redteam.py','Eligible/included strata and selection-bias diagnostic','Complete historical eligible universe not ingested.'),
4:('test_governance_execution.py','Immutable experiment specifications and variant count','Retrospective registration cannot prove an analyst never saw a holdout.'),
5:('test_governance_execution.py','One-use holdout consumption and overlap rejection','No genuine prospective holdout has elapsed.'),
6:(None,'Missing rows are retained as PASS where evaluable','Retired/traded/minor-league population coverage not audited.'),
7:('test_governance_execution.py','Player markets require player and team IDs','Real cross-provider player roster mappings absent.'),
8:('test_replay_settlement.py','Append-only corrected results and account corrections','Book-specific correction timing not integrated.'),
9:('test_governance_execution.py','UTC normalization, DST offset, naive-time rejection','Host/provider clock offsets are not measured.'),
10:('test_identity.py','Exact start changes force remapping; cancellations void','Schedule revision histories need live observation.'),
11:('test_replay_settlement.py','Unknown, regulation-only, pitcher and participation rules reject','Actual book rule documents and identities unavailable.'),
12:('test_phase2_cfb.py','CFB line monotonicity and discrete push mass','Prop alternate-line distributions not fitted.'),
13:('test_governance_execution.py','Line/rule/start changes require new probability','No empirical execution observations.'),
14:('test_diagnostics_redteam.py','Latency ordering and P50/P90/P99 diagnostic','No real candidate latency or edge half-life sample.'),
15:('test_sport_contracts.py','Event-specific confirmation age and restrictions','No historical availability/role archive.'),
16:('test_phase2_history.py','Current weather cannot be backdated','Historical forecast revision proof and sensitivity analysis absent.'),
17:(None,'No automatic contrarian movement signal enabled','Market-disagreement penalty must be estimated from untouched data.'),
18:('test_phase2_backtest.py','Point CLV and same-line price CLV remain separate','No qualifying outcome/close evaluation sample.'),
19:('test_governance_execution.py','Paired-price timing tolerance and exact same line','Snapshot presence is not execution proof.'),
20:(None,'Feature/source ablation comparison requires matched rows','Real feature correlation and incremental contribution unmeasured.'),
21:('test_phase2_backtest.py','Correlated prediction errors reject ensemble weight','No real ensemble independence evidence.'),
22:(None,'Group diagnostics preserve season/regime distinctions','Regime drift thresholds and empirical regime samples absent.'),
23:('test_phase2_cfb.py','Model minimum training sample; props remain disabled','Sport-specific prior estimates and role shrinkage not fitted.'),
24:(None,'Unknown or limited roles fail contract validation','Structural-break detection not fitted.'),
25:('test_sport_contracts.py','Unverified limitations cannot use normal opportunity','Actual restriction/injury return data absent.'),
26:('test_phase2_calibration.py','Scenario probabilities cannot bypass calibration','Empirical blowout/script mixtures unmeasured.'),
27:(None,'No coach/system effect enabled','Timestamp-safe coaching/system regimes absent.'),
28:('test_warehouse.py','Odds schema and pair validation; feature units explicit','CFBD generic records need per-endpoint semantic schema versions.'),
29:('test_provider_validation.py','401/403, invalid/error payloads, quota limits fail closed','Long-run outage recovery remains unobserved.'),
30:('test_sport_contracts.py','Explicit units, fractions, ranges and discrete roles','Provider-to-feature mappings still require verified conversions.'),
31:('test_phase1.py','Finite bounded probabilities; finite JSON; stable sigmoid','Extreme empirical tails unvalidated.'),
32:('test_phase2_calibration.py','Proper scores and single-class calibration rejection','Rare-event calibration requires real tails.'),
33:('test_accounting_promotions.py','Cash/bonus journals and push/void denominators','External account/exposure reconciliation not connected.'),
34:('test_accounting_promotions.py','Boost/free-bet/no-sweat payoff separate from probability','Real terms and conversion assumptions unverified; research only.'),
35:('test_engine.py','Pregame cannot qualify as live','No synchronized live model/state/quote feed; live disabled.'),
36:('test_governance_execution.py','Postmortem hypotheses never auto-modify models','Independent hypothesis evaluation awaits data.'),
37:('test_governance_execution.py','Slippage and execution gates available','Ideal versus realistic end-to-end empirical comparison absent.'),
38:('test_phase2_backtest.py','Proper-score intervals resample weeks','ROI cluster intervals require actual qualified selections.'),
39:('test_diagnostics_redteam.py','Hypothetical bankroll path, drawdown and ruin stress','No empirical joint-outcome distribution; scenario assumptions explicit.'),
40:('test_diagnostics_redteam.py','Quarter-Kelly ceiling and extra-error sensitivity','No empirically approved probabilities or stakes.'),
41:('test_phase1.py','Atomic persistent team/player/game/correlation exposure','All external open slips must be imported; no actual account provided.'),
42:('test_phase1.py','Registry requires proper-score advantage versus market','No empirically qualifying model.'),
43:('test_diagnostics_redteam.py','Noise features fail unseen advantage on mechanics fixture','Full provider-history negative-control reruns blocked.'),
44:('test_diagnostics_redteam.py','Shuffled-label training loses unseen fixture signal','Full sport-specific shuffled-label backtests blocked.'),
45:('test_diagnostics_redteam.py','Future features, revisions and forbidden postgame fields reject','Provider availability proof still required; caller labels alone insufficient.'),
46:('test_governance_execution.py','Adverse exact-line changes demand recalculation','No current eligible model can issue a recommendation.'),
47:('test_phase2_cfb.py','Finite nonzero CFB tails; no outcome-triggered retraining','Requested real extreme-game reconstructions lack historical snapshots.'),
48:('test_handoff_cycle.py','PASS-only unvalidated feed; no guaranteed outcome classifications','Legacy documentation may quote prohibited terms as warnings, not classifications.'),
49:('test_diagnostics_redteam.py','All 50 requested categories enumerated','A complete inventory is not a successful readiness audit.'),
50:('test_diagnostics_redteam.py','Untested critical failures prohibit readiness','No real/prospective evidence; all markets RESEARCH_ONLY.')}

def audit_inventory():
    critical={1,2,5,7,8,10,11,15,16,28,29,30,31,35,37,41,42,45,50}
    # These pass narrowly specified regression checks. Broad evidence-dependent
    # categories remain FAIL until that evidence exists, even if unit tests pass.
    passed={9,13,19,29,31,33,34,35,40,41,45,46,48,49,50}
    return [dict(id=i,name=name,tested=CONTROLS[i][0] is not None,result='PASS' if i in passed else 'FAIL',
        severity='CRITICAL' if i in critical else 'HIGH',affected_sports=['CFB','NHL','NFL','MLB','NBA'],affected_markets='ALL',
        tests=['tests/'+CONTROLS[i][0]] if CONTROLS[i][0] else [],fix=CONTROLS[i][1],remaining_risk=CONTROLS[i][2],
        evidence_scope='MECHANICS_ONLY',real_sample_size=0) for i,name in enumerate(NAMES,1)]

def write_redteam(repo, *, tests_passed,tests_failed):
    rows=audit_inventory();at=datetime.now(timezone.utc).isoformat()
    status=dict(timestamp=at,critical_failures=sum(r['severity']=='CRITICAL' and r['result']!='PASS' for r in rows),
        high_failures=sum(r['severity']=='HIGH' and r['result']!='PASS' for r in rows),medium_failures=0,
        tests_added=tests_passed-36,tests_passed=tests_passed,tests_failed=tests_failed,
        test_count_scope='whole suite; original Phase 1 baseline = 36',categories=rows,
        readiness=readiness_gate(rows,empirical_n=0,prospective_n=0,beats_market=False,coverage_validated=False))
    atomic_json(repo/'outputs/red_team_status.json',status)
    lines=['# Red-team report','',f'Generated: {at}',
        f'Full suite: {tests_passed} passed; {tests_failed} failed. Critical unresolved audit categories: {status["critical_failures"]}.',
        'FAIL below includes missing evidence and incomplete implementation, not just failing unit tests. Mechanics PASS does not approve a market.',
        'All markets remain RESEARCH_ONLY. No real model evaluation or prospective performance sample exists.','',
        '| ID | Failure mode | Tested | Result | Severity | Fix/control | Remaining risk | Tests |',
        '|---:|---|---|---|---|---|---|---|']
    lines += ['| '+ ' | '.join([str(r['id']),r['name'],str(r['tested']),r['result'],r['severity'],r['fix'],r['remaining_risk'],', '.join(r['tests'])])+' |' for r in rows]
    atomic_text(repo/'reports/RED_TEAM_REPORT.md','\n'.join(lines)+'\n')
    atomic_json(repo/'outputs/tail_stress_status.json',bankroll_stress([],starting_bankroll=1,unit=1))
    atomic_text(repo/'reports/TAIL_EVENT_STRESS_REPORT.md','\n'.join([
        '# Tail-event stress report','',f'Generated: {at}',
        'Real stress sample: 0. Historical case reconstruction: INSUFFICIENT_HISTORICAL_SNAPSHOT.',
        'CFB distribution tests preserve nonzero upset mass and explicit integer pushes. Hypothetical bankroll stress tests cover common-group losses, drawdown, ruin and quarter-Kelly sensitivity.',
        'No synthetic stress statistic is reported as model performance. Empirical tail calibration, game-script mixtures, clustered ROI intervals and extreme-game replays remain blocked by qualifying data.',
        'The implemented simulator declares common-uniform positive dependence within each group and independence between groups. These are scenario assumptions, not fitted correlations.',
        'No stake increase, model promotion or feature addition follows an upset.'])+'\n')
    return status

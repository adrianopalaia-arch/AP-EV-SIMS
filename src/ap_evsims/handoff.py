"""Read-only review feed: missing model evidence produces explicit PASS records."""
from datetime import datetime,timezone
import json
from pathlib import Path
from hashlib import sha256
from .integrity import utc,digest
from .odds import american_to_implied,devig_two_way
from .publication import atomic_json,atomic_text,write_status_checkpoint
from .replay import ReplayLedger

def publish_handoff(repo,store,warehouse, *, now=None,source_commit=None):
    repo=Path(repo);at=utc(now or datetime.now(timezone.utc)).isoformat()
    quotes=warehouse.as_of_quotes(at)
    pairs={}
    for q in quotes:pairs.setdefault(q['pair_id'],[]).append(q)
    passes=[]
    for quote in quotes:
        if quote['book'] not in ('draftkings','fanduel'):continue
        reasons=['MODEL_NOT_CALIBRATED','MISSING_FEATURES','UNVERIFIED_LINEUP','UNKNOWN_SETTLEMENT_RULE','QUOTE_EXECUTION_UNVERIFIED']
        age=(utc(at)-utc(quote['observed_at'])).total_seconds()
        if age>180:reasons.insert(0,'STALE_PRICE')
        pair=pairs[quote['pair_id']];opposite=next((r for r in pair if r['selection']!=quote['selection']),None)
        market_probability=None
        if opposite is None:reasons.append('NO_MARKET_PAIR')
        else:market_probability=devig_two_way(quote['american_odds'],opposite['american_odds'])[0]
        passes.append(dict(candidate_id=quote['quote_id'],generated_at=at,sport=quote['sport'],event_id=quote['event_id'],
            event_start=quote['event_start'].isoformat(),home_team=quote['home_team'],away_team=quote['away_team'],market=quote['market'],
            selection=quote['selection'],book=quote['book'],line=quote['line'],odds=quote['american_odds'],
            quote_timestamp=quote['observed_at'].isoformat(),quote_age_seconds=age,odds_snapshot_id=quote['snapshot_id'],
            opposite_odds=opposite['american_odds'] if opposite else None,
            fair_odds=None,expected_value=None,max_acceptable_price=None,model_version=None,calibration_version=None,
            data_timestamps=dict(event_start=quote['event_start'].isoformat(),sportsbook_quote=quote['observed_at'].isoformat(),
                lineup_injury=None,feature_snapshot=None,model_prediction=None,decision=at,
                provider_available=quote['available_at'].isoformat(),ingested=quote['ingested_at'].isoformat()),
            model_probability=None,calibrated_probability=None,p_low=None,market_implied_probability=american_to_implied(quote['american_odds']),
            market_no_vig_probability=market_probability,decision='PASS',pass_reason=reasons,data_quality='FAIL',
            decision_stage='INPUT_PREFLIGHT',phase1_eligible=False))
    frozen=ReplayLedger(store.root/'predictions/replay.sqlite').predictions()
    predictions=[p for p in frozen if utc(p['context']['event_timestamp'])>utc(at)]
    # No approved artifacts currently exist. Never translate an arbitrary ledger
    # status into an executable recommendation without a fresh Phase 1 evaluation.
    edges=[]
    # Public feeds never disclose private account balances or infer a bankroll.
    balance=dict(cash_balance=None,bonus_balance=None,unit_size=22,unit_semantics='REFERENCE_ONLY_NOT_A_STAKE',
        open_cash_exposure=None,open_bonus_exposure=None,reserved_exposure=None,
        exposure_reconciliation='UNKNOWN; no external sportsbook positions imported')
    values={'latest_edges.json':edges,'latest_predictions.json':predictions,'latest_passes.json':passes,'bankroll_state.json':balance}
    generation_id=digest(dict(at=at,quote_ids=[q['quote_id'] for q in quotes],predictions=[p['prediction_id'] for p in predictions]))
    # Prepare and validate the whole generation before replacing public files.
    for name,value in values.items():
        atomic_json(store.root/'snapshots'/(generation_id+'-'+name),value)
    for name,value in values.items():atomic_json(repo/'outputs'/name,value)
    atomic_text(repo/'reports/MORNING_CARD.md','\n'.join([
        '# AP EV/SIMS Morning Card','',f'Generated: {at}','',
        '## Model health','All markets UNVALIDATED. Zero qualifying empirical model observations.','',
        '## Top current candidates','No qualified candidates. PASS. No model is approved for wagering.','',
        '## Price-sensitive candidates','None eligible. No maximum acceptable wager price can be claimed without a calibrated model.','',
        '## Passes',f'{len(passes)} DraftKings/FanDuel market-side records rejected at input preflight.',
        'Reasons include missing calibrated models/features, unverified availability and settlement rules, unproven execution, and stale prices.',
        'All records and exact archived prices are retained in outputs/latest_passes.json.','',
        '## Model warnings','Historical odds access returned 401. Current provider access succeeds. Captured historical CFBD values cannot be backdated.',
        'Bankroll and actual stakes are unknown; balances remain null. Publication does not place a wager.'])+'\n')
    atomic_text(repo/'reports/DAILY_DIAGNOSTIC.md','\n'.join([
        '# Daily diagnostic','',f'Generated: {at}',f'Real frozen predictions: {len(frozen)}. Current preflight PASS records: {len(passes)}.',
        'No calibrated or qualified model predictions have been generated from real data. No confirmed actual stakes exist.',
        'Brier, log loss, calibration, ROI, CLV, drawdown, miss classification and drift: unavailable until their required observations exist.',
        'No single miss triggers training. Synthetic tests are excluded from all performance fields.'])+'\n')
    atomic_text(repo/'reports/MODEL_HEALTH.md','\n'.join([
        '# Model health','',f'Generated: {at}','All models: UNVALIDATED.',
        'Blockers: historical odds entitlement; historical feature availability; book-specific settlement and execution proof; no calibrated empirical model.',
        'No champion has been approved; no automatic promotion is enabled. Read TASK_STATE.json for implementation progress.',
        'No readiness designation is permitted while critical red-team conditions remain untested.'])+'\n')
    last=write_status_checkpoint(repo,source_commit=source_commit)
    last.update(generated_at=at,publication_generation=generation_id,publication_task='FOUNDATION.GitHub_handoff',
        current_passes=len(passes),current_predictions=len(predictions),current_edges=0,
        feed_hashes={name:digest(value) for name,value in values.items()},
        reader_contract='Verify canonical JSON SHA256 (sorted keys, compact separators, ensure_ascii=True) against this manifest; retry on a generation mismatch.')
    atomic_json(repo/'outputs/last_update.json',last)  # manifest published last
    return dict(generation_id=generation_id,passes=len(passes),predictions=len(predictions),edges=0)

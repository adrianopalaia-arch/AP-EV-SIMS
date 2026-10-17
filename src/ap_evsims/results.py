"""Local CFBD result revisions, visible only at their proven availability time."""
from .integrity import utc
from .providers.normalize import canonical_cfbd_results
from .providers.schema import validate_provider_payload


def cfbd_results_as_of(store, warehouse, clock):
    """Latest observation per game across queries; never silently choose conflicting scores.

    An unsettled revision supersedes an earlier final observation. Missing games
    are not inferred to be final, cancelled, or a complete historical universe.
    Every returned observation carries the source hash and immutable snapshot ID.
    """
    at=utc(clock)
    with warehouse.connect() as db:
        snapshots=db.execute('''SELECT snapshot_id,available_at FROM snapshots
            WHERE provider='cfbd' AND dataset='games' AND available_at<=?
            ORDER BY available_at,snapshot_id''',[at]).fetchall()
    latest={}
    fields=('event_id','home_team','away_team','event_timestamp','home_score','away_score','status','overtime')
    for snapshot_id,available_at in snapshots:
        manifest=store.manifest(snapshot_id)
        if (manifest['provider']!='cfbd' or manifest['endpoint']!='games'
                or manifest['parameters'].get('endpoint_status',200)!=200
                or manifest.get('availability_basis')!='recorded_response'
                or not manifest.get('available_at')):
            raise ValueError('RESULT_PROVENANCE_MISMATCH')
        available=utc(manifest['available_at'])
        if available!=utc(available_at) or available!=utc(manifest['fetched_at']) or available>at:
            raise ValueError('LOOKAHEAD_RISK')
        payload=store.payload(manifest)
        validate_provider_payload('cfbd','games',payload)
        seen=set()
        for result in canonical_cfbd_results(payload,manifest):
            event=result['event_id']
            if event in seen:raise ValueError('DUPLICATE_RESULT_ID')
            seen.add(event)
            if result['status']=='final' and utc(result['event_timestamp'])>=available:
                raise ValueError('LOOKAHEAD_RISK')
            previous=latest.get(event)
            if previous and utc(previous['result_available_at'])==available:
                if any(previous[k]!=result[k] for k in fields):
                    raise ValueError('CONFLICTING_RESULT_REVISION')
            latest[event]=result
    return [latest[event] for event in sorted(latest)]


def reconcile_cfbd_replay(store, warehouse, ledger, clock):
    """Reveal verified revisions to frozen real predictions, without betting/account writes."""
    results={r['event_id']:r for r in cfbd_results_as_of(store,warehouse,clock)}
    revealed=[];pending=[]
    for prediction in ledger.predictions(dataset_kind='provider_history'):
        context=prediction['context'];result=results.get(context['event_id'])
        if (result is None or utc(result['result_available_at'])<=utc(context['event_timestamp'])
                or utc(result['result_available_at'])<=utc(prediction['decision_at'])):
            pending.append(prediction['prediction_id']);continue
        if utc(result['event_timestamp'])!=utc(context['event_timestamp']):
            raise ValueError('RESULT_EVENT_START_MISMATCH')
        revision=ledger.reveal(prediction['prediction_id'],result=result,
            available_at=result['result_available_at'],clock=clock,
            source_snapshot_id=result['snapshot_id'],source_hash=result['payload_hash'],provenance_store=store)
        revealed.append(revision)
    return dict(result_observations=len(results),revision_ids=revealed,pending_prediction_ids=pending,
                accounting_status='NOT_RECONCILED')

# Reproduce the saved research execution

Run these in PowerShell from the existing local repository. They use the local real-data archives, model artifacts and credentials; neither raw archives nor credentials are distributed through GitHub. This checkpoint publishes outputs only. Some local source/test improvements remain uncommitted, and their exact hashes are recorded in `outputs/execution_status.json`.

```powershell
Set-Location 'C:\Users\adria\Documents\Codex\2026-10-13\files-mentioned-by-the-user-ap\outputs\AP-EV-SIMS'
$env:PYTHONPATH='src'
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_research --root . --sport all
& '.\.venv\Scripts\python.exe' -m ap_evsims.cfb_score_research --root .
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_prospective --root . --sport all
& '.\.venv\Scripts\python.exe' -m ap_evsims.prop_settlement --root . --sport all
& '.\.venv\Scripts\python.exe' -m ap_evsims daily_card --sports CFB,NFL,NBA,NHL,MLB --force-refresh
```

The price command retains the existing 24-credit daily ceiling, 50-credit reserve and refresh cooldown. It may return `QUOTA_BUDGET_LIMIT`; do not increase limits merely to make a report look fresh. `daily_card` currently rebuilds the older application feed: it does not aggregate the separate five-sport research reports. The output-only execution checkpoint explicitly reconciles those reports. That persistent integration remains unfinished.

To reproduce every published marginal simulation from the published frozen distributions, without API requests or private datasets:

```powershell
@'
import json
from pathlib import Path
import numpy as np
from ap_evsims.integrity import digest

forecasts = json.loads(Path('outputs/latest_predictions.json').read_text())
run = json.loads(Path('outputs/simulation_execution.json').read_text())
by_id = {f['forecast_hash']: f for f in forecasts}
draws_completed = 0
for simulation in run['simulations']:
    f = by_id[simulation['forecast_hash']]
    # Publication metadata was added without altering the frozen forecast body.
    added = ('publication_at', 'status', 'decision', 'phase1_eligible', 'stake')
    original = {k:v for k,v in f.items() if k not in added and k != 'forecast_hash'}
    if f['sport'] == 'CFB':
        original.pop('sport'); original.pop('market')
    assert digest(original) == f['forecast_hash']
    pmf = f['margin_distribution'] if f['sport'] == 'CFB' else f['projection']['distribution']
    pairs = sorted((int(k), float(p)) for k,p in pmf.items())
    support = np.array([k for k,p in pairs])
    probability = np.array([p for k,p in pairs])
    assert abs(probability.sum() - 1) < 1e-10
    for replica in simulation['replicates']:
        rng = np.random.default_rng(replica['seed'])
        sample = rng.choice(support, size=replica['draws'], p=probability)
        counts = np.bincount(np.searchsorted(support, sample), minlength=len(support))
        actual = {str(k):int(n) for k,n in zip(support, counts) if n}
        assert actual == replica['histogram']
        error = float(np.max(np.abs(np.cumsum(counts / len(sample)) - np.cumsum(probability))))
        assert error <= run['convergence']['maximum_allowed_error']
        draws_completed += len(sample)
print({'forecast_simulations_reproduced': len(run['simulations']), 'draws_reproduced': draws_completed})
'@ | & '.\.venv\Scripts\python.exe' -
```

This reproduces marginal empirical-PMF simulations, not shared-state games or parlays. Draw counts do not increase empirical evaluation counts. Missing lineup confirmation, joint dynamics and calibrated betting evidence remain blockers. All recommendations remain disabled.

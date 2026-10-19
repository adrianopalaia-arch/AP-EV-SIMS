# Pregame updates

Reload the running AP EV/SIMS dashboard. Select sports in the sidebar, then enable **Auto-refresh prices toward game time**. This switch starts off. Keep the Streamlit server and browser session active. No external scheduler or automatic wager placement was added.

Sportsbook prices are the connected updating feed. The selected-market evidence table shows the source and quote timestamp separately from the display check time. The screen rechecks age and removes started or impossible-timestamp observations every minute. Repainting the screen does not make a quote fresh. Saved prices older than three minutes remain STALE_PRICE and PASS.

The collector uses the nearest future event in each selected sport: 6 hours beyond 24 hours, hourly within 24 hours, 15 minutes within 6 hours, 5 minutes within 1 hour, and 1 minute in the final 15 minutes. These intervals are collection targets, not freshness guarantees. Requests remain subject to the existing daily credit ceiling, 50-credit reserve and exclusive refresh lock. Failures or quota exhaustion impose at least a five-minute retry delay. Explicit manual refresh retains its 60-second minimum cooldown. Live mode disables collection and pregame model reuse.

The app uses Streamlit's active-session fragment timer; closing/disconnecting the dashboard does not create an overnight collector. [Streamlit fragment behavior](https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment).

## Still unavailable

Injury/lineup confirmations, starting goalies/pitchers, opponent-adjusted EPA/QB pressure, xG/GSAx and bullpen workload do not yet have complete verified refreshing feeds. Their evidence status remains UNVERIFIED or UNAVAILABLE. Refreshing prices does not advance those timestamps. Model probability, p_low and EV remain unavailable and every model remains UNVALIDATED.

The Research preview tab contains the dated October 14 audit, including source links and missing information. That saved audit is separate from current prices and is not updated by the price timer. Personal wager details remain only in ignored local storage.

## Verified delivery

197 tests passed; 0 failed; 0 skipped. The original 195 tests and 18 frozen Phase 1 files are preserved. Real-data Streamlit AppTest passes, including the audit panel. Visual acceptance in the user's browser remains user-operated.

Current-price check: CFB and NHL archived new real payloads; NFL and MLB hit the existing daily credit ceiling; NBA retained cached observations under its cadence. No cap was raised. Real qualifying model evaluation sample remains zero. Exact capture times and quota metadata are in outputs/provider_status.json.

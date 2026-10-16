"""Local Streamlit view. No credentials, private balances or automatic wagers."""
import argparse
from datetime import datetime, timezone, timedelta
from pathlib import Path
import streamlit as st
from ap_evsims.product import daily_card,read_card,MARKETS,model_catalog
from ap_evsims.integrity import utc
from ap_evsims.display_pricing import dashboard_market


def pregame_display_rows(rows, at):
    """Recheck saved cards against the clock, including without provider access."""
    clock=utc(at);visible=[]
    for row in rows:
        try:
            available=row['data_timestamps']['provider_available']
            if utc(row['quote_timestamp'])<=utc(available)<=clock<utc(row['event_start']):
                visible.append(row)
        except (KeyError,TypeError,ValueError):continue
    return visible


def refresh_watch(repo, sports, cap, state, at):
    """Session-only refresh; existing collector enforces cadence, quota and lock.

    Five-minute failure backoff prevents a tab from retrying an outage each tick.
    Returned messages never include provider exceptions or authenticated URLs.
    """
    clock=utc(at)
    if not sports or cap<=0:return 'PAUSED'
    key='pregame_watch:'+str(repo)+':'+','.join(sorted(sports))+':'+str(cap)
    if state.get(key) and clock<utc(state[key]):return 'WAITING'
    state[key]=(clock+timedelta(seconds=300)).isoformat()
    try:result=daily_card(repo,sports=tuple(sports),daily_credit_cap=int(cap),force_refresh=False)
    except Exception:return 'REFRESH_FAILED'
    if result.get('refresh_failures'):return 'REFRESH_FAILED'
    state[key]=(clock+timedelta(seconds=60)).isoformat()
    return 'CHECKED'


def main(repo):
    st.set_page_config(page_title='AP EV/SIMS',page_icon='◈',layout='wide')
    st.markdown('''<style>
    .stApp {background:#f5f7fa;color:#142434}
    .block-container {max-width:1480px;padding-top:2.5rem}
    [data-testid="stMetric"] {background:white;border:1px solid #dce3ea;border-radius:14px;padding:22px}
    [data-testid="stMetricLabel"] {color:#5b6d7f}
    .eyebrow {color:#007f76;letter-spacing:2px;font-size:12px;font-weight:700}
    h1 {letter-spacing:-1.8px}
    </style>''',unsafe_allow_html=True)
    st.markdown('<div class="eyebrow">RESEARCH • PRICE DISCIPLINE • BANKROLL PROTECTION</div>',unsafe_allow_html=True)
    st.title('AP EV/SIMS')
    st.caption('Local research dashboard · Real archived prices when available · No automatic wagers')
    with st.sidebar:
        st.header('Research desk')
        mode=st.radio('Session',['Pregame','Live'])
        selected=st.multiselect('Refresh sports',list(MARKETS),default=['CFB'])
        st.number_input('Reference unit ($)',min_value=1.0,max_value=10000.0,value=22.0,step=1.0)
        st.caption('Display reference only. This is not your bankroll or a suggested stake. Saved in this browser session only.')
        cap=st.number_input('Daily API credit ceiling',min_value=0,max_value=120,value=24,step=3)
        automatic=st.checkbox('Auto-refresh prices toward game time',value=False,disabled=mode=='Live')
        st.caption('While this dashboard session is active: every 6h beyond 24h; hourly within 24h; every 15m within 6h; every 5m within 1h; every minute in the last 15m. Daily credit ceiling and 50-credit reserve still apply.')
        st.caption('Automatic updates currently cover sportsbook prices. Advanced stats, injuries and confirmed starters are not connected refresh feeds yet.')
        refresh=st.button('Refresh Quotes',type='primary',disabled=not selected or mode=='Live')
        cached=st.button('Recalculate',disabled=mode=='Live',help='Recompute from the current immutable local quotes. No API calls.')
    if mode=='Live':
        st.warning('LIVE MODE UNAVAILABLE — live models and latency controls are not validated.')
        st.info('Pregame forecasts are never reused as live predictions.')
        return
    if refresh or cached or not (repo/'outputs/last_update.json').is_file():
        try:
            with st.spinner('Checking local evidence and rebuilding the card…'):
                daily_card(repo,offline=not refresh,sports=tuple(selected),daily_credit_cap=int(cap),force_refresh=refresh)
        except Exception:
            # Provider/library exceptions may contain authenticated URLs. Never
            # forward exception text or a traceback to the UI.
            st.error('Refresh could not complete. The previous card is retained. Check local data integrity or retry after another refresh finishes.')
        # A local rebuild or explicit refresh must not also cause an automatic
        # request in the same run. Manual refresh already has its own cooldown.
        key='pregame_watch:'+str(repo)+':'+','.join(sorted(selected))+':'+str(int(cap))
        st.session_state[key]=(datetime.now(timezone.utc)+timedelta(seconds=60)).isoformat()

    @st.fragment(run_every=60)
    def current_card():
        if automatic:
            result=refresh_watch(repo,selected,cap,st.session_state,datetime.now(timezone.utc))
            if result=='REFRESH_FAILED':
                st.warning('Automatic refresh could not obtain current data. Retaining saved evidence; retrying no sooner than five minutes. Check Provider & model health.')
            elif result=='PAUSED':st.caption('Automatic collection paused: choose sports and a positive API credit ceiling.')
            else:st.caption('Automatic price checks enabled. Collection follows time to the nearest upcoming game and available quota.')
        _render_card(repo)
    current_card()


def _render_card(repo):
    try:summary,feeds=read_card(repo)
    except (ValueError,TypeError):
        st.warning('The card is being updated or failed its integrity check. Rebuild from local data before using it.')
        return
    saved_rows=feeds.get('latest_passes.json',[])+feeds.get('comparison_markets.json',[])
    checked_at=datetime.now(timezone.utc)
    rows=pregame_display_rows(saved_rows,checked_at)
    catalog=feeds.get('model_status.json') or model_catalog(rows)
    # Existing pre-product handoff remains readable; no model readiness is inferred.
    a,b,c=st.columns(3)
    a.metric('Games scanned',summary.get('games_scanned',len({r['event_id'] for r in rows})))
    b.metric('Qualified edges',0)
    c.metric('Models validated',0)
    st.info('NO QUALIFYING BETS — model approval and required pregame evidence are incomplete.')
    if summary.get('refresh_failures'):st.warning('Some provider requests failed or reached the quota ceiling. Cached observations may be stale.')
    if summary.get('data_quality_failures'):
        st.warning(f"{len(summary['data_quality_failures'])} source snapshot(s) failed validation and were excluded.")
    st.caption('Card generated: '+str(summary.get('generated_at','Not generated'))+' · All timestamps UTC')
    st.caption('Display freshness checked: '+checked_at.isoformat()+' · Refreshing the screen does not change source timestamps.')
    if len(rows)!=len(saved_rows):
        st.caption(str(len(saved_rows)-len(rows))+' saved quote sides withheld: game started or source timestamp ordering is invalid.')
    markets_tab,research_tab,coverage_tab,providers_tab=st.tabs(['Daily ranked markets','Research preview','CFB coverage','Provider & model health'])
    with markets_tab:
        left,right=st.columns([3,1]);left.subheader('Daily ranked markets');right.caption('DK PRIORITY • FD SECOND')
        st.caption('Book-priority display. Market probabilities and baseline EV come from paired prices. AP probabilities come only from a trained research model with verified inputs.')
        st.caption('No-vig and AP probabilities on push-capable lines are conditional on no push. Unknown push mass leaves unconditional market EV blank; conditional EV is shown separately. All EV figures are percent of stake, excluding voids. No displayed EV authorizes a bet.')
        sport=st.selectbox('Sport',['All']+list(MARKETS))
        books=st.multiselect('Sportsbooks',sorted({r['book'] for r in rows}),default=[b for b in ('draftkings','fanduel') if any(r['book']==b for r in rows)])
        available=[r for r in rows if (sport=='All' or r['sport']==sport) and r['book'] in books]
        if available:
            st.dataframe([dashboard_market(r,checked_at) for r in available],hide_index=True,width='stretch')
            st.caption('Odds are American; quote age is in minutes. MARKET BASELINE ONLY means there is no AP model forecast. A fresh captured price still needs execution verification.')
            chosen=st.selectbox('Inspect a market',range(len(available)),format_func=lambda i:available[i]['sport']+' · '+available[i]['selection']+' · '+available[i]['market']+' · '+available[i]['book'])
            row=dict(available[chosen]);reasons=list(row['pass_reason'])
            if (datetime.now(timezone.utc)-utc(row['quote_timestamp'])).total_seconds()>180 and 'STALE_PRICE' not in reasons:reasons.insert(0,'STALE_PRICE')
            st.caption('PASS reasons: '+', '.join(reasons))
            st.caption('Probability source: '+row.get('probability_source','MARKET BASELINE ONLY')+' · Push policy: '+row.get('push_policy','UNKNOWN'))
            if row.get('p_low') is not None:st.warning('AP p_low is a research diagnostic; coverage is unvalidated and it cannot authorize wagering.')
            st.subheader('Pregame evidence for this market')
            stamps=row['data_timestamps']
            st.dataframe([
                {'Information':'Sportsbook line and price','Source':'The Odds API · '+row['book'],'Updated (UTC)':row['quote_timestamp'],'Availability':'STALE' if 'STALE_PRICE' in reasons else 'Captured; execution unverified'},
                {'Information':'Lineups, injuries and starter confirmation','Source':'Not connected','Updated (UTC)':stamps.get('lineup_injury'),'Availability':'UNVERIFIED'},
                {'Information':'Advanced matchup statistics','Source':'Verified feature feed incomplete','Updated (UTC)':stamps.get('feature_snapshot'),'Availability':'UNAVAILABLE'},
                {'Information':'Model probability / p_low / EV','Source':row.get('model_version') or 'No trained model with verified inputs','Updated (UTC)':stamps.get('model_prediction'),'Availability':'UNVALIDATED'},
            ],hide_index=True,width='stretch')
            st.caption('A newer price does not verify a lineup or update advanced statistics. Those require separate dated sources.')
            with st.expander('Price, timestamps and evidence'):st.json(row)
        else:st.caption('Await data — refresh current markets or select another sport/book. No predictions are fabricated.')
        st.subheader('Market coverage')
        st.dataframe([{'Sport':r['sport'],'Market':r['market'],'AP model approval':'UNVALIDATED',
            'Status':'Market observations available' if r.get('observed_market_sides',0) else 'Await data'}
            for r in catalog if sport=='All' or r['sport']==sport],hide_index=True,width='stretch')
        with st.expander('Card builders'):
            st.write('CORE singles, LEAN research, 2–3 leg parlays, 4–6 leg prop builders, moneyline hammer and tiny lotto: unavailable.')
            st.caption('No eligible validated legs. Correlation, exposure and price requirements must pass before these can produce a card.')
        report=repo/'reports/MORNING_CARD.md'
        if report.is_file():st.download_button('Download morning card',report.read_text(encoding='utf-8'),file_name='MORNING_CARD.md')
    with research_tab:
        st.subheader('Research in progress')
        st.caption('Verified evidence can be displayed before a model is approved. Missing statistics remain unavailable. This panel does not authorize picks.')
        paper=feeds.get('paper_tracking_status.json',{})
        if paper.get('phase_id'):
            st.subheader('100-candidate paper diagnostic')
            st.write(f"{paper['cohort_candidates']}/100 candidates across {paper['unique_games']} games; {paper['settled_candidates']} settled. {paper['observations_logged']} quote/model observations retained.")
            st.caption('$22 paper reference; $0 cash committed. Fixed home/over sampling is not a betting strategy. 100 candidates do not establish profitability or model validation.')
            st.caption(f"Real model forecasts: {paper['model_predictions']}. Calibrated forecasts: {paper['calibrated_predictions']}. CORE disabled.")
            with st.expander('Paper benchmark, rejections and settlement diagnostics'):st.json(paper)
        u=feeds.get('cfb_universe.json',{})
        st.dataframe([
            {'Stage':'Captured sportsbook prices','Evidence':str(summary.get('market_sides_scanned',0))+' quote sides; check each quote timestamp'},
            {'Stage':'CFB research baseline feature sets','Evidence':str(u.get('games_with_research_baseline_features',0))},
            {'Stage':'CFB complete Phase 1 feature sets','Evidence':str(u.get('games_with_phase1_feature_contract',0))},
            {'Stage':'Real qualifying model evaluations','Evidence':str(summary.get('real_model_evaluation_sample',0))},
            {'Stage':'Approved predictive models','Evidence':'0 — UNVALIDATED'},
            {'Stage':'Next validation work','Evidence':'Verified pregame features → chronological evaluation → uncertainty approval → prospective tracking'},
        ],hide_index=True,width='stretch')
        st.info('EPA, QB efficiency, pressure, xG, GSAx and bullpen workload are not yet complete verified dashboard feeds. No placeholder probability or EV is used.')
        audit=repo/'reports/OCTOBER_14_FAILURE_AUDIT.md'
        if audit.is_file():
            try:audit_text=audit.read_text(encoding='utf-8')
            except (OSError,UnicodeError):st.warning('The saved research audit could not be read.')
            else:
                st.caption('Dated October 14 evidence, with source links and missing-data notes. Audit prices are historical observations, not current offers. Market refresh does not update this saved audit.')
                with st.expander('October 14 audit: available stats, prices and process findings',expanded=True):
                    st.markdown(audit_text)
                st.download_button('Download research audit',audit_text,file_name='OCTOBER_14_FAILURE_AUDIT.md')
        else:st.caption('No dated research audit has been saved in this checkout yet.')
    with coverage_tab:
        u=feeds.get('cfb_universe.json',{})
        st.subheader('Schedule-first CFB audit')
        st.caption('Captured queries only. This is not a complete-season denominator. Games without matched prices stay in the audit.')
        st.write({'Schedule games':u.get('games_scanned',0),'Upcoming FBS matchups':u.get('upcoming_fbs_games',0),
            'Matched games':u.get('matched_games',0),'Verified rolling feature sets':u.get('games_with_verified_rolling_features',0)})
        if u.get('games'):
            st.dataframe([{'Game':g['away_team']+' @ '+g['home_team'],'Start':g['event_start'],'Season':g['season'],
                'Quote sides':g['market_sides'],'Reasons':', '.join(g['pass_reason'])} for g in u['games']],hide_index=True,width='stretch')
        else:st.info('Await CFBD schedule data.')
    with providers_tab:
        st.subheader('Provider access')
        st.caption('Current odds and historical entitlement are separate checks. A saved successful check does not guarantee present availability.')
        st.json(feeds.get('provider_status.json',{}),expanded=False)
        with st.expander('Excluded source snapshots'):st.json(summary.get('data_quality_failures',[]))
        st.subheader('Validation status')
        st.write('0 qualifying real evaluation observations. All models UNVALIDATED. Brier, log loss, ROI and CLV are unavailable.')
        st.caption('Historical prices, timestamp-safe feature coverage, calibrated uncertainty and prospective evidence remain required. Tests verify software behavior; they are not betting performance.')


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--repo',type=Path,default=Path.cwd())
    args,_=parser.parse_known_args()
    main(args.repo.resolve())

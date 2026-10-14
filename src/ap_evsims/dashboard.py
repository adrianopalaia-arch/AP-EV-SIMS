"""Local Streamlit view. No credentials, private balances or automatic wagers."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import streamlit as st
from ap_evsims.product import daily_card,read_card,MARKETS,model_catalog
from ap_evsims.integrity import utc


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
        st.caption('Refresh obeys collection cadence and keeps at least 50 credits in reserve. No background polling.')
        refresh=st.button('Refresh current markets',type='primary',disabled=not selected or mode=='Live')
        cached=st.button('Rebuild from local data',disabled=mode=='Live')
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
    try:summary,feeds=read_card(repo)
    except (ValueError,TypeError):
        st.warning('The card is being updated or failed its integrity check. Rebuild from local data before using it.')
        return
    rows=feeds.get('latest_passes.json',[])+feeds.get('comparison_markets.json',[])
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
    markets_tab,coverage_tab,providers_tab=st.tabs(['Daily ranked markets','CFB coverage','Provider & model health'])
    with markets_tab:
        left,right=st.columns([3,1]);left.subheader('Daily ranked markets');right.caption('DK PRIORITY • FD SECOND')
        st.caption('Book-priority display. A probability from sportsbook prices is a market baseline, not a model prediction.')
        sport=st.selectbox('Sport',['All']+list(MARKETS))
        books=st.multiselect('Sportsbooks',sorted({r['book'] for r in rows}),default=[b for b in ('draftkings','fanduel') if any(r['book']==b for r in rows)])
        available=[r for r in rows if (sport=='All' or r['sport']==sport) and r['book'] in books]
        names={'h2h':'Moneyline','spreads':'Spread','totals':'Total'}
        if available:
            def view(r):
                age=max(0,(datetime.now(timezone.utc)-utc(r['quote_timestamp'])).total_seconds())
                return {'Sport':r['sport'],'Game':r['away_team']+' @ '+r['home_team'],'Market':names.get(r['market'],r['market']),
                    'Selection':r['selection'],'Book':r['book'],'Line':r['line'],'Price':f"{r['odds']:+d}",
                    'Probability':'—','p_low':'—','EV':'—','Status':'PASS · STALE_PRICE' if age>180 else 'PASS · UNVALIDATED',
                    'Quote age (min)':round(age/60,1),'No-vig market':round(r['market_no_vig_probability'],4) if r['market_no_vig_probability'] is not None else None}
            st.dataframe([view(r) for r in available],hide_index=True,width='stretch')
            chosen=st.selectbox('Inspect a market',range(len(available)),format_func=lambda i:available[i]['sport']+' · '+available[i]['selection']+' · '+available[i]['market']+' · '+available[i]['book'])
            row=dict(available[chosen]);reasons=list(row['pass_reason'])
            if (datetime.now(timezone.utc)-utc(row['quote_timestamp'])).total_seconds()>180 and 'STALE_PRICE' not in reasons:reasons.insert(0,'STALE_PRICE')
            st.caption('PASS reasons: '+', '.join(reasons))
            with st.expander('Price, timestamps and evidence'):st.json(row)
        else:st.caption('Await data — refresh current markets or select another sport/book. No predictions are fabricated.')
        st.subheader('Market coverage')
        st.dataframe([{'Sport':r['sport'],'Market':r['market'],'Probability':'—','EV':'—',
            'Status':'UNVALIDATED' if r.get('observed_market_sides',0) else 'Await data','Model':'UNVALIDATED'}
            for r in catalog if sport=='All' or r['sport']==sport],hide_index=True,width='stretch')
        with st.expander('Card builders'):
            st.write('CORE singles, LEAN research, 2–3 leg parlays, 4–6 leg prop builders, moneyline hammer and tiny lotto: unavailable.')
            st.caption('No eligible validated legs. Correlation, exposure and price requirements must pass before these can produce a card.')
        report=repo/'reports/MORNING_CARD.md'
        if report.is_file():st.download_button('Download morning card',report.read_text(encoding='utf-8'),file_name='MORNING_CARD.md')
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

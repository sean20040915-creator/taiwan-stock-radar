"""Streamlit dashboard for Taiwan Stock Radar V3.0 MVP.

No trade execution, no fake full-SOP score, no unverified market data labels.
"""
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from src.storage import make_engine, database_url, load_prices, load_runs
from src.strategy import scored_frame, latest_scans, SCORE_MAX, VERSION
from src.backtest import simulate, metrics, signal_outcomes
from src.demo import synthetic_prices

st.set_page_config(page_title="台股飆股雷達 V3.0 | 技術預篩",page_icon="📈",layout="wide")
st.markdown("""<style>
.block-container{max-width:1370px;padding-top:1.5rem}
[data-testid="stMetric"]{background:#eff6f4;border-radius:12px;padding:12px}
h1{letter-spacing:-.03em}
</style>""",unsafe_allow_html=True)

@st.cache_resource
def get_engine():
    return make_engine()

@st.cache_data(ttl=600,show_spinner=False)
def get_live_prices():
    return load_prices(get_engine(),lookback_calendar_days=390)

@st.cache_data(ttl=600,show_spinner=False)
def analyze(frame):
    return scored_frame(frame)


st.sidebar.title("📈 飆股雷達 V3.0")
st.sidebar.caption("短線3～5交易日 | SOP技術預篩 MVP")
st.sidebar.divider()
try:
    real = get_live_prices()
    db_problem = None
except Exception as e:
    real=pd.DataFrame()
    db_problem=f"資料庫連線失敗：{type(e).__name__}。請確認 DATABASE_URL 與網路。"
mode = "真實資料（官方行情）" if not real.empty else "示範資料（虛構）"
if not real.empty:
    show_demo=st.sidebar.toggle("切換虛構 DEMO 資料",value=False)
    if show_demo:
        mode="示範資料（虛構）"
        prices=synthetic_prices()
    else:
        prices=real
else:
    prices=synthetic_prices()
    st.sidebar.warning("尚無持久化官方行情；目前僅顯示 DEMO")
if db_problem:
    st.sidebar.error(db_problem)
if st.sidebar.button("重新讀取資料",use_container_width=True):
    get_live_prices.clear()
    st.rerun()
st.sidebar.caption(f"資料模式：{mode}")
st.sidebar.caption("這是研究工具，不會提供必漲保證或自動下單。")

raw=analyze(prices)
latest=latest_scans(raw)
latest_day=str(prices.day.max()) if not prices.empty else "—"
today=datetime.now(ZoneInfo("Asia/Taipei")).date()
age=(today-pd.Timestamp(latest_day).date()).days if latest_day!="—" else None

st.title("台股飆股雷達 V3.0")
st.caption("先蓄勢，再突破；先驗證資料，再計算分數。適用 3～5 日短線策略研究。")
if "示範" in mode:
    st.warning("🧪 **DEMO 模式**：所有股價、股票代號、排名與交易績效均為程式產生的虛構資料，不代表台灣股市。")
else:
    if age is not None and age>4:
        st.error(f"官方資料最新日期 {latest_day}，與今天已相隔 {age} 天；請先確認盤後更新狀態，不應視為即時訊號。")
    else:
        st.info(f"目前官方行情最新日期：{latest_day}。不同市場可能更新不同步；請到『資料品質』檢查。")
st.info("目前僅有 **技術預篩 57分**（股價結構35 + 量能12 + 未過熱10）。市場／族群15、法人8、相對強弱10、營收及公告10等共43分尚未介接，不會虛構完整100分與A級評價。處置與普通股身份亦尚待完整驗證。")

p1,p2,p3,p4,p5=st.tabs(["🏠 今日預篩","🔍 個股分析","⏱ 追蹤訊號","📊 策略回測","🛠 資料品質"])

with p1:
    good=latest[latest.setup] if not latest.empty else pd.DataFrame()
    confirmed=latest[latest.trigger] if not latest.empty else pd.DataFrame()
    c1,c2,c3,c4=st.columns(4)
    c1.metric("目前收錄檔數", f"{len(latest):,}")
    c2.metric("歷史資料達65根",f"{int((latest.bars>=65).sum()):,}" if not latest.empty else "0")
    c3.metric("技術候選",f"{len(good):,}")
    c4.metric("突破確認（技術）",f"{len(confirmed):,}")
    st.subheader("技術排名與篩選")
    if latest.empty:
        st.info("還沒有資料。請參考 README 匯入官方行情。")
    else:
        f1,f2,f3=st.columns([1,1,2])
        choices=["全部"]+sorted(latest.market.unique().tolist())
        market=f1.selectbox("市場",choices)
        min_score=f2.slider("最低技術分（57分滿分）",0,SCORE_MAX,25)
        only_setup=f3.checkbox("只看技術候選／突破確認",value=False)
        view=latest[latest.score>=min_score]
        if market!="全部":view=view[view.market==market]
        if only_setup:view=view[view.setup | view.trigger]
        view=view.sort_values(["trigger","setup","score"],ascending=[False,False,False]).copy()
        use=["day","market","code","name","close","score","score_max","ret5","ret20","vol_ratio5","distance20","status","reason"]
        display=view[use].copy()
        display["ret5"]=display["ret5"]*100
        display["ret20"]=display["ret20"]*100
        display["distance20"]=display["distance20"]*100
        st.dataframe(display.rename(columns={"day":"資料日","market":"市場","code":"代號","name":"股票名稱","close":"收盤價","score":"技術分","score_max":"滿分","ret5":"5日報酬","ret20":"20日報酬","vol_ratio5":"量能比","distance20":"距20日高點","status":"狀態","reason":"註記"}),hide_index=True,use_container_width=True,column_config={"5日報酬":st.column_config.NumberColumn(format="%.1f%%",help="顯示百分比，如 5.0%"),"技術分":st.column_config.ProgressColumn(min_value=0,max_value=57,format="%d"), "20日報酬":st.column_config.NumberColumn(format="%.1f%%"),"距20日高點":st.column_config.NumberColumn(format="%.1f%%")})
        st.download_button("下載當前篩選 CSV",view[use].to_csv(index=False).encode("utf-8-sig"),file_name="radar_technical_watchlist.csv",mime="text/csv")
        if len(good)==0:
            st.caption("無技術候選可能是行情未累積65交易日、硬性條件不合格，或樣本不足；不會為了湊名單提高分數。")

with p2:
    st.subheader("個股價格結構")
    if not latest.empty:
        options=latest.copy()
        options["key"]=options.market+":"+options.code+" "+options.name
        selection=st.selectbox("選擇股票",options.key.tolist())
        chosen=options.loc[options.key==selection].iloc[0]
        df=raw[(raw.market==chosen.market)&(raw.code==chosen.code)].sort_values("day").tail(90)
        x1,x2,x3,x4=st.columns(4)
        x1.metric("最新收盤",f"{chosen.close:.2f}")
        x2.metric("技術分",f"{int(chosen.score)}/{SCORE_MAX}")
        x3.metric("14日ATR",f"{chosen.atr14:.2f}" if pd.notna(chosen.atr14) else "待累積")
        x4.metric("狀態",str(chosen.status))
        fig=go.Figure(data=[go.Candlestick(x=df.day,open=df.open,high=df.high,low=df.low,close=df.close,name="K線")])
        fig.add_trace(go.Scatter(x=df.day,y=df.ma20,name="MA20",line=dict(color="#df9930",width=1.6)))
        fig.add_trace(go.Scatter(x=df.day,y=df.ma60,name="MA60",line=dict(color="#167d79",width=1.6)))
        fig.update_layout(height=430,margin=dict(l=5,r=5,t=10,b=5),xaxis_rangeslider_visible=False,legend=dict(orientation="h"))
        st.plotly_chart(fig,use_container_width=True)
        vol=go.Figure(data=[go.Bar(x=df.day,y=df.volume,name="成交股數")])
        vol.update_layout(height=180,margin=dict(l=5,r=5,t=10,b=5),yaxis_title="股")
        st.plotly_chart(vol,use_container_width=True)
        with st.expander("展開技術指標與資料限制",expanded=True):
            st.write(f"近10日整理振幅：{chosen.range10:.1%}" if pd.notna(chosen.range10) else "整理振幅：無資料")
            st.write(f"與先前20日高點距離：{chosen.distance20:.1%}" if pd.notna(chosen.distance20) else "20日高點：無資料")
            st.write(f"20日平均成交金額：NT${chosen.avg_amount20:,.0f}" if pd.notna(chosen.avg_amount20) else "平均金額：無資料")
            st.write(f"資料狀態：{chosen.reason}")
            st.caption("未介接法人、族群、新聞、處置與上市櫃普通股主檔；本畫面不是買進建議。")

with p3:
    st.subheader("訊號後5日客觀追蹤")
    st.caption("僅統計候選日後1～5個完整交易日之最高價是否曾達+7%；非實際可交易報酬。末5日尚無完整資料者不計。")
    outcomes=signal_outcomes(prices,scored=raw)
    if outcomes.empty:
        st.info("目前尚無具備完整後5日資料的技術候選訊號。")
    else:
        a,b,c=st.columns(3)
        a.metric("已成熟候選訊號",len(outcomes))
        b.metric("曾觸及+7%的比例",f"{outcomes['曾達7%'].mean():.1%}")
        c.metric("平均5日最高漲幅",f"{outcomes['後5日最高相對漲幅'].mean():.1%}")
        st.dataframe(outcomes.sort_values("訊號日",ascending=False),hide_index=True,use_container_width=True)
        st.download_button("下載訊號追蹤 CSV",outcomes.to_csv(index=False).encode("utf-8-sig"),"signal_outcomes.csv","text/csv")

with p4:
    st.subheader("技術突破策略 · 示範回測")
    st.warning("這是**57分技術預篩、最多最近390日行情的研究回測**，不是完整100分 SOP 回測；未包含真實歷史下市股、完整除權息校正、處置與財報等資訊，也未模擬全部投資組合的同時持股上限。不可依此績效直接投入資金。")
    i1,i2,i3=st.columns(3)
    cash=i1.number_input("研究帳戶本金（NT$）",min_value=100_000,max_value=100_000_000,value=1_000_000,step=100_000)
    fee=i2.number_input("單邊手續費率（%）",min_value=0.0,max_value=1.0,value=.1425,step=.01)/100
    slip=i3.number_input("單邊滑價（%）",min_value=0.0,max_value=2.0,value=.1,step=.05)/100
    trades=simulate(prices,cash=float(cash),fee=fee,slippage=slip,scored=raw)
    m=metrics(trades)
    aa,bb,cc,dd=st.columns(4)
    aa.metric("交易數",m["交易數"])
    bb.metric("扣費後勝率",f"{m['淨勝率']:.1%}" if m["淨勝率"] is not None else "—")
    cc.metric("平均淨R",f"{m['平均淨R']:.2f}" if m["平均淨R"] is not None else "—")
    dd.metric("模擬淨損益",f"NT${m['總淨損益']:,.0f}")
    if trades.empty:
        st.info("符合全部模擬進場條件的完整交易樣本不足，因此不展示虛假的高勝率。")
    else:
        st.dataframe(trades.sort_values("進場日",ascending=False),hide_index=True,use_container_width=True)
        st.download_button("下載模擬逐筆交易",trades.to_csv(index=False).encode("utf-8-sig"),"backtest_trades.csv","text/csv")
    st.caption("停損與停利同日觸及→先停損；跳空按開盤價計；進場次日起算不正確，本模擬進場當日即第1日，至第5日結束；賣出稅率假設0.3%、兩側費率可調。")

with p5:
    st.subheader("資料品質、覆蓋率與來源")
    if not latest.empty:
        st.dataframe(latest.groupby("market",as_index=False).agg(最新日期=("day","max"),股票數=("code","nunique"),足夠K線數=("bars",lambda x:int((x>=65).sum()))),hide_index=True,use_container_width=True)
    st.markdown("**已接入（每日最新快照）**：TWSE、TPEx 的盤後 OHLCV / 成交金額。GitHub Actions 可自動保存資料。")
    st.markdown("**尚未接入**：三大法人與投信、指數及族群領漲、月營收、重大利多公告、處置與完整證券分類、可靠的歷史除權息校正。由於資料不足，不能將技術候選等同於可交易標的。")
    st.markdown("**官方資料來源**：[TWSE OpenAPI](https://openapi.twse.com.tw/) · [TPEx OpenAPI](https://www.tpex.org.tw/zh-tw/openapi.html) · [公開資訊觀測站](https://mops.twse.com.tw/)")
    st.markdown("**部署說明**：本專案 `README.md`，以共用 PostgreSQL 的 DATABASE_URL 同時設定於 GitHub Actions 與 Streamlit Secrets。")
    if not real.empty:
        try:
            history=load_runs(get_engine())
            if not history.empty:
                st.markdown("**最近更新紀錄**")
                st.dataframe(history,hide_index=True,use_container_width=True)
        except Exception:
            st.caption("無法讀取更新紀錄。")
    if db_problem:
        st.error(db_problem)
    st.caption("本 MVP 不執行交易、不保證股票上漲，亦不宣稱已完成歷史樣本外驗證。")

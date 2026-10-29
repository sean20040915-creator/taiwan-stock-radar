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
from src.diagnostics import diagnose_triggers, historical_signal_outcomes
from src.validation import validation_observations, descriptive_summary
from src.coverage import archive_coverage
from src.data_audit import read_daily_counts, analyze_archive_coverage, backtest_data_gate
from src.forward_audit import verify_frozen_rules, forward_signal_report
from src.demo import synthetic_prices
from src.storage import load_prices_between
from src.research_v36 import research_integrity, research_readiness
from datetime import date, timedelta

st.set_page_config(page_title="台股飆股雷達 V3.6 | 技術預篩",page_icon="📈",layout="wide")
st.markdown("""<style>
.block-container{max-width:1370px;padding-top:1.5rem}
[data-testid="stMetric"]{background:rgba(128,128,128,.13);border:1px solid rgba(128,128,128,.18);border-radius:12px;padding:12px}
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


st.sidebar.title("📈 飆股雷達 V3.6")
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

st.title("台股飆股雷達 V3.6")
st.caption("先蓄勢，再突破；先驗證資料，再計算分數。適用 3～5 日短線策略研究。")
if "示範" in mode:
    st.warning("🧪 **DEMO 模式**：所有股價、股票代號、排名與交易績效均為程式產生的虛構資料，不代表台灣股市。")
else:
    if age is not None and age>4:
        st.error(f"官方資料最新日期 {latest_day}，與今天已相隔 {age} 天；請先確認盤後更新狀態，不應視為即時訊號。")
    else:
        st.info(f"目前官方行情最新日期：{latest_day}。不同市場可能更新不同步；請到『資料品質』檢查。")
if "示範" not in mode and not latest.empty and latest.groupby("market")["day"].max().nunique()>1:
    dates=", ".join(f"{m}: {d}" for m,d in latest.groupby("market")["day"].max().items())
    st.warning(f"⚠️ 市場日期尚未一致（{dates}），請勿把跨市場結果當成同一交易日；先等待／檢查來源是否更新。")
st.info("目前僅有 **技術預篩 57分**（股價結構35 + 量能12 + 未過熱10）。市場／族群15、法人8、相對強弱10、營收及公告10等共43分尚未介接，不會虛構完整100分與A級評價。處置與普通股身份亦尚待完整驗證。")

p1,p2,p3,p4,p6,p7,p8,p9,p10,p5=st.tabs(["🏠 今日預篩","🔍 個股分析","⏱ 追蹤訊號","📊 策略回測","🧪 訊號診斷","📐 歷史驗證 V3.3","🧭 前瞻追蹤 V3.4","🧾 資料稽核 V3.5","🔬 嚴格研究 V3.6","🛠 資料品質"])

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
        x2.metric("技術分",f"{int(chosen.score)}/{SCORE_MAX}" if chosen.bars>=65 else "資料不足")
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

with p6:
    st.subheader("V3.2｜突破進場診斷")
    st.caption("固定保留原先進場門檻：次日跳空不超過2%、停損距離2%～4.5%、單檔部位最多15%、整張1000股。診斷不會放寬規則。")
    st.warning("這是研究稽核，不是已驗證的交易策略。訊號發生在最後交易日時，次日行情尚未產生，會標記為「等待次日行情」。")
    diagnostics = diagnose_triggers(raw, cash=float(cash), slippage=slip)
    st.metric("歷史突破訊號", len(diagnostics))
    if diagnostics.empty:
        st.info("目前載入期間沒有技術突破訊號，尚無可診斷的進場樣本。")
    else:
        counts = diagnostics["判定"].value_counts().rename_axis("診斷狀態").reset_index(name="訊號數")
        st.subheader("進場條件排除原因")
        st.dataframe(counts, hide_index=True, use_container_width=True)
        st.subheader("逐筆訊號與排除明細")
        st.dataframe(diagnostics.sort_values("突破日", ascending=False), hide_index=True, use_container_width=True,
                     column_config={"跳空幅度": st.column_config.NumberColumn(format="%.2f"),
                                    "停損距離": st.column_config.NumberColumn(format="%.3f")})
        st.download_button("下載訊號診斷 CSV", diagnostics.to_csv(index=False).encode("utf-8-sig"),
                           file_name="v32_signal_diagnostics.csv", mime="text/csv")
        completed = int(diagnostics["已完成交易"].sum())
        st.caption(f"完成模擬交易判定：{completed} 筆。若和回測交易數不同，請勿依賴當前結果，應先檢查程式與資料。")
    st.divider()
    st.subheader("蓄勢與突破訊號｜後5日觀察")
    st.caption("採收盤後訊號價為觀察基準，計算後3日／5日收盤變動與後5日最高價是否觸及+7%；這些都不是可成交獲利。只有五個後續日線的訊號才納入。")
    observations = historical_signal_outcomes(raw)
    if observations.empty:
        st.info("沒有具備完整後5日資料的觀察樣本，暫時無法估計訊號表現。")
    else:
        overview = observations.groupby("訊號類型", as_index=False).agg(
            樣本數=("代號", "size"),
            第3日平均變動=("第3日收盤變動", "mean"),
            第5日平均變動=("第5日收盤變動", "mean"),
            曾觸及7pct=("曾觸及7%", "mean"),
        )
        for col in ("第3日平均變動", "第5日平均變動", "曾觸及7pct"):
            overview[col] = (overview[col] * 100).round(2)
        overview = overview.rename(columns={"曾觸及7pct": "觸及7%比例(%)", "第3日平均變動": "第3日平均變動(%)", "第5日平均變動": "第5日平均變動(%)"})
        st.dataframe(overview, hide_index=True, use_container_width=True)
        if len(observations) < 100:
            st.warning("完整後5日觀察樣本少於100筆，不應解讀為穩定勝率或可交易優勢。")
        else:
            st.info("樣本數雖增加，但尚未完成獨立樣本外、除權息、歷史下市股及行情可交易性驗證。")
        st.dataframe(observations.sort_values("訊號日", ascending=False), hide_index=True, use_container_width=True)
        st.download_button("下載後5日觀察 CSV", observations.to_csv(index=False).encode("utf-8-sig"),
                           file_name="v32_signal_observations.csv", mime="text/csv")

with p7:
    st.subheader("V3.3｜3～5日訊號有效性驗證")
    st.warning("目前是「描述性研究」，不是已證實有預測力的買進策略。使用訊號當日收盤作參考基準，未扣交易成本、未模擬可成交性；缺少歷史下市股、除權息調整及完整證券分類。")
    st.caption("固定57分技術模型，不降低門檻、不依照這份樣本最佳化。所有報酬對齊各市場真正的第3、第5個交易日；同市場基準是當日滿足65日及20日均成交金額5,000萬元的股票等權平均，並非加權指數。")
    report = validation_observations(raw)
    if report.empty:
        st.info("歷史資料仍不足以計算同日市場比較；先讓自動回補持續累積，或核對資料品質。")
    else:
        total = len(report)
        complete = report[report["5日狀態"] == "完整"]
        col_a,col_b,col_c,col_d = st.columns(4)
        col_a.metric("觀察股票日", f"{total:,}")
        col_b.metric("5日觀察完整", f"{len(complete):,}")
        col_c.metric("突破確認完整", f"{int((complete['訊號類型']=='突破確認').sum()):,}")
        col_d.metric("未成熟／缺漏", f"{total-len(complete):,}")
        st.markdown("#### 樣本完整性")
        st.dataframe(report["5日狀態"].value_counts().rename_axis("狀態").reset_index(name="筆數"),
                     hide_index=True, use_container_width=True)
        a,b = st.tabs(["依技術分數", "依訊號類型"])
        with a:
            score_table = descriptive_summary(report, "分數區間")
            if score_table.empty:
                st.info("目前沒有足夠的成熟期間比較樣本。")
            else:
                st.dataframe(score_table, hide_index=True, use_container_width=True)
        with b:
            signal_table = descriptive_summary(report, "訊號類型")
            if signal_table.empty:
                st.info("目前尚無成熟的候選或突破觀察樣本。")
            else:
                st.dataframe(signal_table, hide_index=True, use_container_width=True)
        st.caption("前70%／後30%只是時間區段檢查，不是獨立訓練後的真正樣本外回測；切分邊界的跨期觀察不列入區段比較。訊號可能連續多日高度相關，不可將股票日數當成獨立交易樣本。")
        st.download_button("下載完整 V3.3 逐日觀測 CSV", report.to_csv(index=False).encode("utf-8-sig"),
                           file_name="v33_signal_validation.csv", mime="text/csv")
        st.info("驗證不足時請維持原有57分規則；先擴充跨年度歷史資料、歷史下市股與公司行動調整，再做真正獨立的樣本外測試。")

with p8:
    st.subheader("V3.4｜兩年資料建置與凍結規則前瞻追蹤")
    frozen = verify_frozen_rules()
    if frozen["rules_unchanged"]:
        st.success("57分技術規則與 V3.3 驗證程式版本符合凍結記錄。")
    else:
        st.error("規則或驗證程式已更動：原本前瞻追蹤需暫停解讀，先核對規則版本。")
        st.write(frozen["issues"])
    st.caption("凍結截止：2026/10/19；前瞻訊號起點：2026/10/20。前瞻只代表時間順序，尚未涵蓋除權息、歷史下市股和真實成交條件。")
    st.markdown("#### 已保存歷史行情範圍")
    if "示範" in mode:
        st.info("DEMO 模式不顯示真實資料庫覆蓋情況。")
    else:
        try:
            archive = archive_coverage(get_engine())
            st.dataframe(archive, hide_index=True, use_container_width=True)
            st.caption("市場日數是資料庫實際保存的不同日期，非官方完整交易日曆；兩年目標尚需逐日核實缺漏。")
        except Exception as exc:
            st.warning(f"無法讀取資料庫歷史範圍：{type(exc).__name__}")
    st.markdown("#### 凍結規則前瞻訊號")
    if not frozen["rules_unchanged"]:
        st.warning("程式版本未通過凍結檢查，不呈現前瞻報酬統計。")
    else:
        future_obs = validation_observations(raw)
        summary, future_signals = forward_signal_report(future_obs)
        if summary.empty:
            st.info("2026/10/20 起尚沒有可整理的前瞻候選或突破訊號，會隨官方行情累積更新。")
        else:
            st.dataframe(summary, hide_index=True, use_container_width=True)
            st.caption("未滿完整後5個交易日的訊號不納入報酬；股票日資料高度相關，不能視為獨立樣本。")
            st.download_button("下載 V3.4 前瞻訊號觀察 CSV", future_signals.to_csv(index=False).encode("utf-8-sig"),
                               file_name="v34_forward_signals.csv", mime="text/csv")
    st.info("兩年回補請使用 GitHub Actions 的 V3.4 Long History Pilot，先以2天小量試跑。此階段不會宣稱樣本外交易策略已驗證。")

with p9:
    st.subheader("V3.5｜兩年歷史資料品質稽核")
    st.warning("此頁是只讀的歷史行情稽核，不會修改或補造任何價格。平日不一定是交易日；未登記的臨時休市也可能顯示缺口。")
    if "示範" in mode or db_problem:
        st.info("請使用已連接 Neon 的真實行情模式，才能查看資料庫稽核。")
    else:
        try:
            aggregate = read_daily_counts(get_engine())
            audit_summary, audit_detail = analyze_archive_coverage(aggregate)
            st.markdown("#### 2024/10/21～2026/10/19：市場日資料存在情況")
            st.dataframe(audit_summary, hide_index=True, use_container_width=True)
            can_validate, reason = backtest_data_gate(audit_summary)
            st.warning("正式策略驗證狀態：尚未通過。"+reason)
            st.caption("資料存在率不等於真正的歷史完整率，也不能用來推論選股勝率；目前未整合官方完整交易日曆、歷史下市股與除權息。")
            c1,c2 = st.columns(2)
            market_filter = c1.selectbox("查看市場", ["全部", "TWSE", "TPEX"], key="audit_market")
            status_filter = c2.selectbox("查看資料狀態", ["僅需注意", "全部"], key="audit_status")
            view = audit_detail.copy()
            if market_filter != "全部":
                view=view[view["市場"]==market_filter]
            if status_filter=="僅需注意":
                view=view[~view["狀態"].isin(["已登記休市","有行情（尚未認證完整）"])]
            st.dataframe(view, hide_index=True, use_container_width=True, height=450)
            st.download_button("下載完整 V3.5 缺口與異常明細 CSV",
                               audit_detail.to_csv(index=False).encode("utf-8-sig"),
                               "v35_data_audit.csv", "text/csv")
            st.info("回補自動流程照常執行；當資料缺口消失後，仍需先解決除權息／下市股／可成交性等偏誤，才能對3～5日回測作正式驗證。")
        except Exception as exc:
            st.error(f"資料稽核暫時無法執行：{type(exc).__name__}，請檢查 PostgreSQL 連線及資料表。")

with p10:
    st.subheader("V3.6｜連續交易日與研究資料品質驗證")
    st.warning("這是保守的描述性研究，不是可交易回測。使用未調整的收盤價，尚未納入除權息、下市股、停牌、交易成本及可成交性。")
    st.caption("研究資料與日常390天選股資料分開查詢，每次只讀取有限區間；保留原本57分技術規則。")
    d1,d2=st.columns(2)
    research_start=d1.date_input("訊號開始日期",value=date(2025,3,3),key="v36_start")
    research_end=d2.date_input("訊號結束日期",value=date(2025,3,14),key="v36_end")
    if "示範" in mode or db_problem:
        st.info("請在已連接 Neon 的真實行情模式使用。")
    elif st.button("執行 V3.6 嚴格研究",key="v36_run"):
        if research_end<research_start or (research_end-research_start).days>30:
            st.error("研究訊號日期必須遞增，且區間最多31個日曆日。")
        elif research_end>today:
            st.error("不能研究尚未發生的日期。")
        else:
            try:
                range_start=research_start-timedelta(days=135)
                range_end=min(today,research_end+timedelta(days=15))
                research_prices=load_prices_between(get_engine(),range_start,range_end)
                if research_prices.empty:
                    st.info("指定區間無已保存行情。")
                else:
                    readiness=research_readiness(research_prices,research_start,research_end)
                    st.markdown("#### 研究資料完整性（先檢查，再解讀訊號）")
                    st.dataframe(readiness,hide_index=True,use_container_width=True)
                    research_scored=scored_frame(research_prices)
                    audit=research_integrity(research_scored,research_start,research_end)
                    st.metric("偵測到的技術訊號數（含待核實）",len(audit))
                    if audit.empty:
                        if readiness["資料就緒判定"].str.contains("不足|缺口|缺乏").any():
                            st.warning("目前0訊號不能當成真正沒有符合條件的股票：研究資料尚有缺漏或不足，請先回補再重新驗證。")
                        else:
                            st.info("日期存在性初步足夠，但此期間未偵測到候選或突破訊號；仍需核實歷史下市股與公司行動。")
                    else:
                        st.dataframe(audit["判定"].value_counts().rename_axis("判定").reset_index(name="訊號數"),hide_index=True,use_container_width=True)
                        st.dataframe(audit,hide_index=True,use_container_width=True)
                        st.download_button("下載 V3.6 研究稽核 CSV",audit.to_csv(index=False).encode("utf-8-sig"),"v36_research.csv","text/csv")
                        st.warning("只有標示『僅可描述性觀察』的資料才有3／5日變動；仍不得用其宣稱歷史勝率或預測能力。")
            except Exception as exc:
                st.error(f"研究載入失敗：{type(exc).__name__}，請檢查資料庫／日期區間。")

with p5:
    st.subheader("資料品質、覆蓋率與來源")
    if not latest.empty:
        coverage = latest.groupby("market", as_index=False).agg(
            最新日期=("day", "max"),
            股票數=("code", "nunique"),
            中位K線數=("bars", lambda x: int(x.median())),
            最多K線數=("bars", "max"),
            足夠K線數=("bars", lambda x: int((x >= 65).sum())),
        )
        st.dataframe(coverage, hide_index=True, use_container_width=True)

        st.markdown("### 歷史日 K 累積進度（目標：65 根）")
        st.caption(
            "每個市場使用「最新交易日有行情股票的歷史日 K 根數中位數」顯示進度；"
            "不是所有股票都已累積相同天數。65 根只代表具備技術評分所需的最低資料量，"
            "不代表符合選股條件，也不代表完整100分 SOP 已完成。"
        )
        for market_name, group in latest.groupby("market", sort=True):
            bars = pd.to_numeric(group["bars"], errors="coerce").dropna()
            if bars.empty:
                continue
            median_bars = int(bars.median())
            ready = int((bars >= 65).sum())
            st.progress(
                min(max(median_bars / 65, 0.0), 1.0),
                text=f"{market_name}｜中位數 {median_bars}/65 根日 K｜已達標 {ready:,}/{len(group):,} 檔",
            )
            if median_bars < 65:
                st.caption(f"{market_name} 的中位數距門檻仍差 {65 - median_bars} 根；新上市、停牌或缺漏資料股票可能需要更久。")
        st.caption("進度依 Neon 已保存且 App 已載入的日線計算；資料更新後請按左側「重新讀取資料」。")
    else:
        st.info("目前沒有可計算進度的股票行情；請先確認資料庫或 DEMO 模式。")
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

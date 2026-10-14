# 台股飆股雷達 V3.0 — Streamlit / GitHub MVP

> **目前功能：官方最新盤後行情自動儲存 + 技術預篩 57 分 + 5 日訊號追蹤 + 保守日線回測 + Streamlit 網頁。**
> 不是完整 100 分 SOP，更不是漲停預測。沒有法人／月營收／指數族群／重大訊息／處置／除權息校正資料時，一律不能將技術分換算成100分，也不能宣稱「完整通過選股」。不含自動下單。

## 專案內容

```
app.py                         Streamlit 5個頁面
src/sources.py                 TWSE + TPEx 最新盤後行情解析器
src/storage.py                 SQLite / PostgreSQL 持久化及每日訊號快照
src/strategy.py                嚴格使用當時與過去資料的57分技術模型
src/backtest.py                訊號追蹤及含成本、停損的技術研究回測
src/demo.py                    完全虛構、固定種子的 DEMO 資料
scripts/update.py              盤後更新、驗證、儲存與掃描
scripts/import_csv.py          匯入有來源的歷史 OHLCV CSV
.github/workflows/daily-update.yml   平日台北19:15排程，可手動重跑
.github/workflows/tests.yml          Push/PR 自動單元測試
tests/                          核心規則及資料解析測試
```

## 1. 本機 2 步啟動

需先安裝 Python 3.12，然後在解壓後的根目錄執行：

```bash
python -m pip install -r requirements.txt
streamlit run app.py
```

打開瀏覽器顯示的網址（通常 http://localhost:8501）。如果本機資料庫尚無真實行情，App **自動顯示標記 DEMO 的虛構資料**，讓你立即測試 UI。絕對不混入真實股票排行榜。

### 手動執行一次正式盤後更新

```bash
python -m scripts.update
```

需要可以連接官方 TWSE / TPEx 的網路環境。若某個來源失敗，指令會顯示明確錯誤而不是捏造股價。成功行情存進本機 `data/stocks.sqlite3`。兩個官方 OpenAPI 主要提供**最新交易日快照**，並不因為傳入過去日期就自動完成多年回填。

**注意：MA60 及完整技術評估需累積至少 65 根有效日K。** 如果你今天才開始每天保存，現在只會看到「歷史資料不足」。這不是系統故障。

## 2. 部署到 GitHub / Streamlit Community Cloud

1. 在 GitHub 建立新 Repository，將此資料夾**所有檔案與隱藏資料夾**上傳到 `main`。不能只上傳 ZIP 本身；可以解壓後使用 GitHub 網頁 Upload files，或用 `git add . && git commit ... && git push`。
2. 開通一個可從 GitHub Actions、Streamlit Cloud 存取的 PostgreSQL 資料庫，例如 Supabase 或 Neon。使用資料庫提供的有效 PostgreSQL 連線字串（通常含 `sslmode=require`）。注意服務與使用量限制。
3. GitHub Repository → **Settings → Secrets and variables → Actions → New repository secret**，名稱填 `DATABASE_URL`，值填完整 PostgreSQL 連線字串。
4. 在 [Streamlit Community Cloud](https://share.streamlit.io/) 建立 App，選擇你的 Repository、`main`、入口檔 `app.py`，Python 選 **3.12**。
5. 在 Streamlit **App Settings → Secrets** 貼上同樣的值，TOML 格式：

   ```toml
   DATABASE_URL = "postgresql+psycopg2://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
   ```

6. GitHub → Actions → **Daily Taiwan Stock Update** → **Run workflow** 手動觸發一次，確認日誌顯示 `SUCCESS`。工作流程也會在**平日台北時間19:15**排程執行；排程不保證準時／不漏跑，假日返回上一交易日很正常。資料庫每日 upsert，不會重複累積相同日期。
7. 打開 Streamlit 網頁，重新讀取資料。若只累積了1根K線，會明確顯示歷史不足；請持續收集，或依法取得完整歷史資料並依下節匯入。

**請勿把 `.env`、`.streamlit/secrets.toml`、資料庫密碼上傳 GitHub。** `DATABASE_URL` 必須在 **GitHub Actions** 與 **Streamlit Community Cloud** 各設定一次，它們不共用 Secrets。若使用 PostgreSQL pooling 連線網址，請遵守供應商要求。

### 歷史行情 CSV 匯入（可選）

若你擁有已授權／已核實來源的完整歷史資料，可以在自己本機匯入、或在能連到雲端資料庫的安全環境執行：

```bash
python -m scripts.import_csv --file history.csv --source "your verified provider / source"
```

`history.csv` 欄位必須是：

```
day,market,code,name,open,high,low,close,volume,amount
2023-01-03,TWSE,2330,台積電,100,102,99,101,2500000,252500000
```

**這行是欄位格式示例，不是真實台積電2023-01-03成交資料。**
`day`=西元 `YYYY-MM-DD`；`market`=`TWSE`/`TPEX`；`volume`=股、`amount`=新台幣元。必須確認公司行動、除權息處理方式與數據權利。程式採用逐股票主鍵 upsert，因此匯入部分股票不會刪除其他個股；但完整策略評估仍需要**全市場歷史樣本**，不能只匯入表現良好的存活股票。長期歷史回測應加入**下市股票、過去成分股及當時真正可用的公告時點**。

## 3. SOP 已實作的評分（只有57/100）

| 可驗證的技術條件 | 分數 |
| --- | ---: |
| 收盤 > MA20 > MA60 | 10 |
| MA20 高於五日前 | 5 |
| 近10日振幅 ≤12% | 8 |
| 收盤距**昨日以前**20日高點 0～5% | 8 |
| ATR14 / 收盤價 2～6% | 4 |
| 近5均量 / 20均量介於0.65～1.30 | 6 |
| 近5日上漲日與下跌日成交量比 ≥1.15 | 6 |
| 最近5日漲幅0～8% | 5 |
| 最近20日漲幅 ≤20% | 5 |
| **合計** | **57** |

市場與族群15、法人8、相對大盤強弱10、月營收/公告10 → **43分尚未接入**。

技術候選示範門檻：至少65筆日線、近20日均成交金額≥NT$5,000萬元、近5日漲幅≤12%、近20日≤25%、ATR在2%～6%、技術分≥38/57、尚距先前20日高點0～5%。進場前**還需要完成風險分類及基本面檢查**。突破條件：Setup後1～2個交易日收盤突破先前10日高點、當日量≥前20日均量1.5倍、收盤在日區間上30%內、當日漲幅≤6%。次日開盤若比突破收盤高逾2%，取消追價。

## 4. 回測和研究的嚴格限制

為避免雲端免費方案一次載入數百萬行情而耗盡記憶體，**Streamlit 首版只讀取最近 390 個日曆日的行情供圖表／回測使用**。每日盤後掃描僅需近期180個日曆日的指標暖機資料；完整歷史仍保留在外部資料庫。正式3～5年回測需新增分批處理與獨立回測任務，**本 MVP 尚未完成**。

- 只使用已知的**歷史行情**與技術條件；會建立的**不是**正式完整100分 SOP 回測，也沒有處置、族群、籌碼、公司行動或市場指數過濾。
- Setup 在收盤 t 形成；t+1 / t+2 收盤才知道 Trigger；再用**下一個交易日開盤**模擬進場，避免盤後資訊偷看。
- 初始停損＝前5日低點與「進場價－1倍 ATR」取較低者；停損距離 2%～4.5%。目標至少7%且期望風險報酬≥2:1；最多持有5個交易日（進場當日算第1日）。
- 停損與停利同時在同一天K棒觸及時，**保守假設先停損**。跳空先按開盤價處理。費用預設買、賣手續費各0.1425%、賣出交易稅0.3%、兩側滑價各0.1%；實際稅費與折扣請自行確認。未模擬漲跌停鎖死、逐筆交易流動性及完整持倉組合限制，現有模型因此不適合直接執行交易。
- 「5日內最高價曾漲7%」只用於**訊號追蹤**，不是可達成的實際成交報酬。
- 回測 **不能** 使用示範價格驗證策略；需要多年真實歷史資料、歷史下市股票、公司行動校正和樣本外驗證，才能對績效下結論。

## 5. 目前限制與下一版工作

| 已完成 | 尚未完成（不假裝已完成） |
|---|---|
| 官方最新TWSE/TPEx日行情抓取、存DB | 過去多年全市場歷史資料自動回補 |
| MA20/MA60/ATR、57分技術預篩 | 指數／族群／投信／法人／營收／公告之剩餘43分 |
| Setup/Trigger、持久化掃描快照 | 官方處置股、完整證券身分辨識、除權息還原 |
| 5日訊號觀察、初級交易回測 | 事件發生日與公開時點一致的樣本外正式回測 |
| 排行榜、個股K線、下載CSV | 自動發送提醒／部署健康監控、授權管理 |

如需商業公開提供股市行情，請先確認資料源的授權、使用與轉載條款。這個專案僅供研究與學習，不建議對外發佈帳戶敏感資料。

## 6. 測試

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

CI 測試涵蓋日期格式、官方回應解析、無前瞻性指標、評分範圍、歷史不足、SQLite 更新、回測煙霧測試。**由於本產出環境無法連接官方網域，也沒有可執行的 Streamlit 套件，正式在線 API 呼叫與雲端佈署仍需你在有網路的機器／GitHub Actions 執行驗證。**

# 📈 Minervini VCP Super Screener (美股超級績效量化選股系統)

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.30%2B-FF4B4B.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

基於兩屆美國投資大賽（US Investing Champion）冠軍 **Mark Minervini** 的 **SEPA（Specific Entry Point Analysis）** 系統、**趨勢模板（Trend Template 8 大法則）** 以及 **VCP（Volatility Contraction Pattern，波動收縮型態）** 打造的現代化美股量化選股 Web 應用程式。

本系統自動對接美國證券交易委員會（SEC）官方名冊與 Yahoo Finance 市場行情，提供自適應明亮/黑暗模式的即時互動儀表板，支援一鍵匯出 CSV 與直接複製至 TradingView Watchlist 批次監控。

---

## 📑 目錄

- [系統核心選股邏輯](#-系統核心選股邏輯)
  - [1. 趨勢模板（Trend Template 8 大法則）](#1-趨勢模板trend-template-8-大法則)
  - [2. 機構級流動性防護網（Liquidity Shield）](#2-機構級流動性防護網liquidity-shield)
  - [3. VCP 波動收縮量化模型（Pivot Ready）](#3-vcp-波動收縮量化模型pivot-ready)
  - [4. IBD 風格相對強度評級（RS Rating）](#4-ibd-風格相對強度評級rs-rating)
- [專案結構](#-專案結構)
- [快速開始（本地運行）](#-快速開始本地運行)
- [雲端部署指南](#-雲端部署指南)
  - [Streamlit Community Cloud 部署（推薦）](#streamlit-community-cloud-部署推薦)
  - [為什麼不適合部署於 Vercel？](#為什麼不適合部署於-vercel)
- [指標與輸出欄位說明](#-指標與輸出欄位說明)
- [免責聲明](#-免責聲明)

---

## 🎯 系統核心選股邏輯

### 1. 趨勢模板（Trend Template 8 大法則）
確保標的處於 **Stage 2（第二階段上升趨勢）**，徹底排除處於底部盤整（Stage 1）、做頭（Stage 3）或下降走勢（Stage 4）的弱勢股：

1. **股價高於 150 日與 200 日移動平均線**：$Price > SMA_{150}$ 且 $Price > SMA_{200}$。
2. **150 日均線高於 200 日均線**：$SMA_{150} > SMA_{200}$（中長期多頭排列）。
3. **200 日均線上揚至少 1 個月**：$SMA_{200} > SMA_{200, 20-days-ago}$（長週期趨勢向上確立）。
4. **50 日均線高於 150 日與 200 日均線**：$SMA_{50} > SMA_{150}$ 且 $SMA_{50} > SMA_{200}$。
5. **當前股價高於 50 日均線**：$Price > SMA_{50}$（短期推升動能延續）。
6. **自 52 週低點上漲至少 30%**：$Price \ge 1.30 \times 52W\_Low$（已脫離底部且具機構建倉）。
7. **距離 52 週高點在 25% 以內**：$Price \ge 0.75 \times 52W\_High$（買高賣更高，強者恆強）。
8. **相對強度評級（RS Rating）**：全美股百分位排位 $\ge 70$（超級領導股通常分佈在 85~99）。

### 2. 機構級流動性防護網（Liquidity Shield）
Minervini 強調，缺乏機構資金推動的股票難以走出倍數級行情，且微型仙股存在嚴重的流動性滑價風險：

- **最低股價**：$\ge \$10.0$（排除仙股與大部分共同基金無法合規買入的個股）。
- **50 日平均成交量（ADV50）**：$\ge 300,000$ 股（確保大眾進出無摩擦）。
- **50 日平均日換手額（Dollar Volume）**：$\ge \$10,000,000$（$\ge \$10M$，機構主力具備無阻力建倉胃納量）。

### 3. VCP 波動收縮量化模型（Pivot Ready）
VCP 代表籌碼由「浮躁投資人（Weak Hands）」轉移至「強手主力（Strong Hands）」的過程，本系統將其抽象化為 4 個量化條件：

- **近 20 日價格震幅（Tightness）**：$\frac{High_{20} - Low_{20}}{Price} \le 12\%$（K 線趨於窄幅收斂）。
- **ATR 波動壓縮比**：$\frac{ATR_{10}}{ATR_{50}} \le 0.80$（短期真實波幅相較長期中樞萎縮 20% 以上）。
- **成交量急凍（Volume Dry-up）**：$\frac{Volume_{10}}{Volume_{50}} \le 0.90$（賣壓耗盡，惜售特徵顯現）。
- **臨近樞紐點（Pivot Proximity）**：現價處於近 20 日高點的 $95\%$ 以上（處於隨時可能放量突破的臨界點）。

### 4. IBD 風格相對強度評級（RS Rating）
採用 Investor's Business Daily (IBD) 經典的四季加權算法，回溯過去一年 252 個交易日的表現並賦予近季最高權重：

$$\text{Weighted Performance} = 0.40 \times R_{Q1} + 0.20 \times R_{Q2} + 0.20 \times R_{Q3} + 0.20 \times R_{Q4}$$

最後將全美股有效標的進行 1 至 99 的百分位（Percentile Rank）標準化排列。

---

## 📁 專案結構

```text
minervini_dashboard/
├── .streamlit/
│   └── config.toml          # 介面設定（預設跟隨系統明亮/黑暗模式）
├── requirements.txt         # 核心套件依賴清單
├── app.py                   # Streamlit Web App 核心程式碼
└── README.md                # 專案說明文件
```

---

## 🚀 快速開始（本地運行）

### 1. 環境需求
- Python 3.9 至 3.12

### 2. 下載專案並安裝依賴
```bash
# 複製專案
git clone https://github.com/your-username/minervini_dashboard.git
cd minervini_dashboard

# 建立並啟用虛擬環境（建議）
python -m venv venv
# Windows:
venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# 安裝依賴套件
pip install -r requirements.txt
```

### 3. 啟動 Web 服務
```bash
streamlit run app.py
```
啟動後瀏覽器會自動開啟 `http://localhost:8501`。

---

## ☁️ 雲端部署指南

### Streamlit Community Cloud 部署（推薦）
Streamlit 官方提供免費雲端託管，原生支援 WebSocket 長連線與多線程背景運算：

1. 將專案 Push 到個人的 **GitHub 倉庫**（公開或私有皆可）。
2. 前往 [share.streamlit.io](https://share.streamlit.io/) 並使用 GitHub 帳號登入。
3. 點擊 **"New app"**，選擇剛剛建立的倉庫與分支，Main file path 填入 `app.py`。
4. 點擊 **"Deploy"**，系統將自動依據 `requirements.txt` 安裝環境並生成專屬公開網址。

### 為什麼不適合部署於 Vercel？
- **超時限制（Execution Timeout）**：Vercel 是 Serverless 架構，免費方案單次請求強制於 10~15 秒內中斷。全美股數千檔標的的抓取與運算需要 2~4 分鐘，會直接觸發 `504 FUNCTION_INVOCATION_TIMEOUT`。
- **長連線機制限制**：Streamlit 需透過長連線 WebSocket 與伺服器維持 Session，而 Serverless 函式在回傳結果後便會立即銷毀狀態，兩者架構不相容。

---

## 📊 指標與輸出欄位說明

| 欄位名稱 | 類型 | 定義說明 | Minervini 理想參考值 |
| :--- | :--- | :--- | :--- |
| **Ticker** | 文字 | 美股交易代號（已自動排除 OTC 粉單與權證） | 主板上市普通股 |
| **Price** | 貨幣 | 最新收盤價 | $\ge \$10.0$（主力機構合規買進門檻） |
| **RS_Rating** | 評級 | 全美股四季加權相對強度百分位（1 - 99） | $\ge 70$（超級領導股多為 85~99） |
| **Tightness_20d_%** | 百分比 | 近 20 日最高點與最低點差距除以現價 | $\le 10\% \sim 12\%$（波動極致收縮） |
| **ATR_Ratio** | 數值 | 10 日 ATR 除以 50 日 ATR | $< 0.80$（短期真實波幅顯著萎縮） |
| **Vol_Dryup_Ratio** | 數值 | 10 日均量除以 50 日均量 | $< 0.85$（浮動籌碼清洗完畢，量能急凍） |
| **Dollar_Vol_M** | 貨幣 | 50 日平均每日成交金額（百萬美元） | $\ge \$10M$（確保機構進駐胃納量） |
| **SMA50 / SMA200** | 貨幣 | 50 日均線與 200 日均線數值 | 多頭排列狀態 ($SMA_{50} > SMA_{200}$) |
| **52W_High** | 貨幣 | 過去 52 週最高價 | 現價距離高點 $\le 25\%$ |
| **Pass_VCP** | 布林 | 是否同時符合波幅緊湊、ATR萎縮、量能枯竭與臨近突破高點 | `True`（優先關注之買點觀察名冊） |

---

## ⚠️ 免責聲明

本專案僅供程式開發、量化研究與學術探討使用，不構成任何形式的投資建議、買賣推薦或金融財務顧問服務。股市交易具有本金虧損風險，使用者應自行審慎評估並承擔投資後果。

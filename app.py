import io
import os
import sys
import time
import logging
import requests
import numpy as np
import pandas as pd
import streamlit as st
import yfinance as yf
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# 降低底層模組警告等級
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("urllib3").setLevel(logging.CRITICAL)

# ----------------- 頁面基礎設定 -----------------
st.set_page_config(
    page_title="Minervini VCP Super Screener",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自適應現代化 CSS 樣式 (適配 Dark & Light 模式)
st.markdown("""
<style>
    /* 全局卡片風格 */
    .metric-card {
        border: 1px solid rgba(128, 128, 128, 0.2);
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 12px;
        background: rgba(128, 128, 128, 0.05);
        box-shadow: 0 2px 4px rgba(0,0,0,0.02);
    }
    .badge-vcp {
        background-color: #10B981;
        color: white;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .badge-trend {
        background-color: #3B82F6;
        color: white;
        padding: 3px 8px;
        border-radius: 6px;
        font-weight: 600;
        font-size: 0.85rem;
    }
    .rule-title {
        font-weight: 700;
        font-size: 1.05rem;
        margin-bottom: 6px;
    }
</style>
""", unsafe_allow_html=True)

# ----------------- 核心篩選引擎 -----------------
def is_valid_us_equity(ticker):
    """過濾 OTC 粉單、外國普通股、權證及衍生品，只保留美股主板普通股"""
    if not ticker:
        return False
    clean_ticker = ticker.replace("-", "")
    if not clean_ticker.isalpha():
        return False
    if len(ticker) > 5:
        return False
    if len(ticker) == 5 and "-" not in ticker:
        if ticker[-1] in ("F", "Y", "W", "R", "U", "P", "Q"):
            return False
    return True

@st.cache_data(ttl=86400)
def get_us_stock_symbols():
    """從 SEC 官方 API 獲取美股主板清單 (快取 24 小時)"""
    url = "https://www.sec.gov/files/company_tickers.json"
    headers = {
        "User-Agent": "MinerviniWebScreener/1.0 (contact: quant@dashboard.local)",
        "Accept-Encoding": "gzip, deflate",
        "Host": "www.sec.gov"
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        if response.status_code == 200:
            data = response.json()
            symbols = []
            for item in data.values():
                t = item.get("ticker", "").strip().upper().replace(".", "-")
                if is_valid_us_equity(t):
                    symbols.append(t)
            return sorted(list(set(symbols)))
    except Exception:
        pass
    return []

def calculate_rs_score(close_series):
    """IBD 四季加權相對強度 (40%, 20%, 20%, 20%)"""
    if len(close_series) < 252:
        return np.nan
    p_now = close_series.iloc[-1]
    p_q1 = close_series.iloc[-63]
    p_q2 = close_series.iloc[-126]
    p_q3 = close_series.iloc[-189]
    p_q4 = close_series.iloc[-252]
    
    ret_q1 = (p_now - p_q1) / p_q1
    ret_q2 = (p_q1 - p_q2) / p_q2
    ret_q3 = (p_q2 - p_q3) / p_q3
    ret_q4 = (p_q3 - p_q4) / p_q4
    return (0.4 * ret_q1) + (0.2 * ret_q2) + (0.2 * ret_q3) + (0.2 * ret_q4)

def calculate_atr(df, period=14):
    """計算真實波幅 (ATR)"""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    prev_close = close.shift(1)
    tr1 = high - low
    tr2 = (high - prev_close).abs()
    tr3 = (low - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def process_single_ticker(ticker, hist_df, min_price, min_adv, min_dollar_vol, max_tightness, max_atr_ratio):
    """驗證流動性、Minervini 趨勢模板與 VCP 形態"""
    if hist_df is None or len(hist_df) < 260:
        return None

    close = hist_df["Close"].dropna()
    low = hist_df["Low"].dropna()
    high = hist_df["High"].dropna()
    volume = hist_df["Volume"].dropna()

    if len(close) < 260 or len(volume) < 60:
        return None

    current_price = close.iloc[-1]
    avg_vol_50 = volume.rolling(50).mean().iloc[-1]
    avg_dollar_vol_50 = (close * volume).rolling(50).mean().iloc[-1]

    # 1. 流動性過濾
    if current_price < min_price or avg_vol_50 < min_adv or avg_dollar_vol_50 < min_dollar_vol:
        return None

    # 2. 趨勢模板計算
    sma_50 = close.rolling(50).mean().iloc[-1]
    sma_150 = close.rolling(150).mean().iloc[-1]
    sma_200 = close.rolling(200).mean().iloc[-1]
    sma_200_20_ago = close.rolling(200).mean().iloc[-21]

    low_52w = low.iloc[-252:].min()
    high_52w = high.iloc[-252:].max()

    cond1 = (current_price > sma_150) and (current_price > sma_200)
    cond2 = sma_150 > sma_200
    cond3 = sma_200 > sma_200_20_ago
    cond4 = (sma_50 > sma_150) and (sma_50 > sma_200)
    cond5 = current_price > sma_50
    cond6 = current_price >= (low_52w * 1.30)
    cond7 = current_price >= (high_52w * 0.75)
    passes_trend = cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7

    # 3. VCP 形態指標計算
    atr_10 = calculate_atr(hist_df, 10).iloc[-1]
    atr_50 = calculate_atr(hist_df, 50).iloc[-1]
    atr_ratio = round(atr_10 / atr_50, 2) if atr_50 > 0 else 1.0

    high_20 = high.iloc[-20:].max()
    low_20 = low.iloc[-20:].min()
    tightness_20 = round(((high_20 - low_20) / current_price) * 100, 1)

    avg_vol_10 = volume.rolling(10).mean().iloc[-1]
    vol_dryup_ratio = round(avg_vol_10 / avg_vol_50, 2)
    near_pivot = current_price >= (high_20 * 0.95)

    passes_vcp = (
        tightness_20 <= max_tightness and
        atr_ratio <= max_atr_ratio and
        vol_dryup_ratio <= 0.90 and
        near_pivot
    )

    rs_raw = calculate_rs_score(close)

    return {
        "Ticker": ticker,
        "Price": round(current_price, 2),
        "SMA50": round(sma_50, 2),
        "SMA150": round(sma_150, 2),
        "SMA200": round(sma_200, 2),
        "52W_High": round(high_52w, 2),
        "ADV50_k": int(avg_vol_50 // 1000),
        "Dollar_Vol_M": round(avg_dollar_vol_50 / 1000000, 1),
        "Pass_Trend": passes_trend,
        "Tightness_20d_%": tightness_20,
        "ATR_Ratio": atr_ratio,
        "Vol_Dryup_Ratio": vol_dryup_ratio,
        "Pass_VCP": passes_vcp,
        "RS_Raw": rs_raw
    }

# ----------------- 側邊欄配置 -----------------
with st.sidebar:
    st.title("⚙️ 掃描參數設定")
    
    st.subheader("掃描範圍")
    scan_mode = st.radio(
        "選擇標的池規模",
        ["全美股主板 (約 5,000+ 檔)", "快速測試模式 (前 300 檔)", "微量抽樣 (前 100 檔)"],
        index=1
    )
    
    st.subheader("流動性門檻 (Minervini 理想值)")
    param_min_price = st.number_input("最低股價 ($)", value=10.0, step=1.0)
    param_min_adv = st.number_input("50日均成交股數 (股)", value=300000, step=50000)
    param_min_dollar_vol = st.number_input("50日平均日成交額 ($)", value=10000000, step=1000000, format="%d")

    st.subheader("VCP 波動收斂閥值")
    param_max_tightness = st.slider("近 20 日震幅上限 (%)", min_value=5.0, max_value=20.0, value=12.0, step=0.5)
    param_max_atr = st.slider("ATR10 / ATR50 比率上限", min_value=0.50, max_value=1.00, value=0.80, step=0.05)
    param_min_rs = st.slider("最低 RS Rating", min_value=50, max_value=95, value=70, step=1)

    start_scan = st.button("🚀 開始全市場掃描", use_container_width=True, type="primary")

# ----------------- 頂部導航與標題 -----------------
st.title("📈 Minervini 趨勢模板與 VCP 選股系統")
st.caption("基於 Mark Minervini 超級績效（SEPA）交易系統與 IBD 相對強度評級之量化掃描器")

tab_results, tab_strategy, tab_glossary = st.tabs([
    "📊 篩選結果 (Dashboard)", 
    "📑 策略與條件詳解 (Criteria)", 
    "📖 指標說明手冊 (Glossary)"
])

# ----------------- TAB 2: 策略與條件詳解 -----------------
with tab_strategy:
    st.markdown("### 🎯 Mark Minervini 趨勢模板（Trend Template 8 大法則）")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        <div class="metric-card">
            <div class="rule-title">1. 均線排列 (Stage 2 Uptrend)</div>
            <ul>
                <li><b>現價 > SMA150 且 現價 > SMA200</b>：股價必須維持於中期與長期均線之上。</li>
                <li><b>SMA150 > SMA200</b>：中長期多頭排列確認。</li>
                <li><b>SMA200 上揚至少 1 個月</b>：確保 200 日線斜率向上，排除剛脫離 Stage 4 的左側個股。</li>
                <li><b>SMA50 > SMA150 且 SMA50 > SMA200</b>：短期強勢推升確認。</li>
                <li><b>現價 > SMA50</b>：股價維持在短期動能線上。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    with c2:
        st.markdown("""
        <div class="metric-card">
            <div class="rule-title">2. 價格區間與相對強度</div>
            <ul>
                <li><b>自 52 週低點反彈 &ge; 30%</b>：真正具備超級潛力的個股不會在低點徘徊，至少已有初期主力建倉。</li>
                <li><b>距離 52 週高點 &le; 25%</b>：買高賣更高，強者恆強，永遠優先挑選接近歷史或波段新高的標的。</li>
                <li><b>相對強度評級 (RS Rating) &ge; 70</b>：過去四季加權回報超越全市場至少 70% 的股票（核心領導股常在 85~99）。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("### 💧 機構級流動性與 VCP 收縮量化模型")
    c3, c4 = st.columns(2)
    with c3:
        st.markdown("""
        <div class="metric-card">
            <div class="rule-title">最理想流動性防護網 (Liquidity Shield)</div>
            <p>Minervini 強調，缺乏機構資金推動的股票難以走出波瀾壯闊的波段：</p>
            <ul>
                <li><b>現價 &ge; $10</b>：徹底排除 Penny Stocks 與不受共同基金合規買進的低價標的。</li>
                <li><b>50 日均量 &ge; 300,000 股</b>：確保進出順暢，避免滑價損失。</li>
                <li><b>50 日日均成交額 &ge; $1,000 萬美元 ($10M)</b>：主力與避險基金能無摩擦建倉的硬指標。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)
    with c4:
        st.markdown("""
        <div class="metric-card">
            <div class="rule-title">VCP 波動收斂量化參數 (Cheat / Pivot Area)</div>
            <p>清洗浮額、籌碼沉澱完畢的關鍵特徵：</p>
            <ul>
                <li><b>20 日震幅 (Tightness) &le; 12%</b>：K 線走勢趨於平坦緊湊，賣壓不再傾瀉。</li>
                <li><b>ATR 比率 (ATR10 / ATR50) &le; 0.80</b>：短期真實波幅較長期中樞萎縮 20% 以上。</li>
                <li><b>成交量急凍 (Vol Dry-up) &le; 0.90</b>：近 10 日均量低於 50 日均量，代表浮動籌碼被鎖死。</li>
                <li><b>逼近樞紐點 (Near Pivot)</b>：現價距離近 20 日高點在 5% 以內，處於即將發動邊緣。</li>
            </ul>
        </div>
        """, unsafe_allow_html=True)

# ----------------- TAB 3: 指標說明手冊 -----------------
with tab_glossary:
    st.markdown("### 📖 篩選輸出欄位定義表")
    glossary_data = [
        {"欄位名稱": "Ticker", "定義說明": "美股交易代號（已自動排除 OTC 粉單與權證）", "理想參考值": "-"},
        {"欄位名稱": "Price", "定義說明": "最新收盤價", "理想參考值": "≥ $10 (最佳 ≥ $20)"},
        {"欄位名稱": "RS_Rating", "定義說明": "全美股 IBD 式加權相對強度百分位 (1 - 99)", "理想參考值": "≥ 70 (極品領導股 ≥ 85)"},
        {"欄位名稱": "Tightness_20d_%", "定義說明": "近 20 日最高最低震幅除以現價", "理想參考值": "≤ 10% ~ 12% (越窄越佳)"},
        {"欄位名稱": "ATR_Ratio", "定義說明": "10日 ATR 除以 50日 ATR（短期波動與長期中樞比）", "理想參考值": "< 0.80 (代表波動明顯壓縮)"},
        {"欄位名稱": "Vol_Dryup_Ratio", "定義說明": "10日均量除以 50日均量（成交量萎縮度）", "理想參考值": "< 0.85 (成交量急凍，賣盤耗盡)"},
        {"欄位名稱": "Dollar_Vol_M", "定義說明": "50日平均每日成交金額（百萬美元）", "理想參考值": "≥ $10M (具備機構大資金池)"},
        {"欄位名稱": "Pass_VCP", "定義說明": "是否同時滿足波幅收斂、ATR下降、量能枯竭且臨近突破高點", "理想參考值": "True（優先觀察形態）"}
    ]
    st.dataframe(pd.DataFrame(glossary_data), use_container_width=True, hide_index=True)

# ----------------- TAB 1: 篩選執行與結果展現 -----------------
with tab_results:
    if "results_df" not in st.session_state:
        st.session_state.results_df = None

    if start_scan:
        all_symbols = get_us_stock_symbols()
        if not all_symbols:
            st.error("無法取得 SEC 標的名冊，請檢查網路連線。")
        else:
            if scan_mode == "微量抽樣 (前 100 檔)":
                target_symbols = all_symbols[:100]
            elif scan_mode == "快速測試模式 (前 300 檔)":
                target_symbols = all_symbols[:300]
            else:
                target_symbols = all_symbols

            batch_size = 60
            batches = [target_symbols[i:i + batch_size] for i in range(0, len(target_symbols), batch_size)]
            
            progress_bar = st.progress(0, text="準備連線下載行情資料...")
            status_text = st.empty()
            
            scanned_records = []
            stderr_backup = sys.stderr
            sys.stderr = open(os.devnull, "w")

            def worker_fetch(b_tickers):
                batch_res = []
                try:
                    data = yf.download(
                        tickers=b_tickers,
                        period="2y",
                        interval="1d",
                        group_by="ticker",
                        auto_adjust=False,
                        progress=False,
                        threads=True
                    )
                    if len(b_tickers) == 1:
                        row = process_single_ticker(
                            b_tickers[0], data, param_min_price, param_min_adv, 
                            param_min_dollar_vol, param_max_tightness, param_max_atr
                        )
                        if row:
                            batch_res.append(row)
                    else:
                        for t in b_tickers:
                            if t in data.columns.levels[0]:
                                t_df = data[t].dropna(how="all")
                                row = process_single_ticker(
                                    t, t_df, param_min_price, param_min_adv, 
                                    param_min_dollar_vol, param_max_tightness, param_max_atr
                                )
                                if row:
                                    batch_res.append(row)
                except Exception:
                    pass
                return batch_res

            try:
                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = {executor.submit(worker_fetch, b): b for b in batches}
                    done_batches = 0
                    for future in as_completed(futures):
                        res = future.result()
                        scanned_records.extend(res)
                        done_batches += 1
                        pct = done_batches / len(batches)
                        progress_bar.progress(pct, text=f"正在掃描美股主板... ({done_batches}/{len(batches)} 批次)")
                        status_text.text(f"已處理 {int(pct*100)}% | 通過基本流動性檢驗個股: {len(scanned_records)} 檔")
                        time.sleep(0.08)
            finally:
                sys.stderr.close()
                sys.stderr = stderr_backup

            progress_bar.empty()
            status_text.empty()

            if scanned_records:
                df_all = pd.DataFrame(scanned_records)
                # 計算 RS Rating 百分位
                df_all["RS_Rating"] = (df_all["RS_Raw"].rank(pct=True) * 98 + 1).round().astype("Int64")
                st.session_state.results_df = df_all
                st.success(f"掃描完成！共評估 {len(target_symbols)} 檔標的，流動性達標標的共 {len(df_all)} 檔。")
            else:
                st.warning("所選範圍內未找到符合流動性門檻的標的。")

    # 呈現結果儀表板
    if st.session_state.results_df is not None:
        df = st.session_state.results_df

        # 過濾滿足 Trend Template 與 RS 門檻的標的
        qualified_trend = df[(df["Pass_Trend"] == True) & (df["RS_Rating"] >= param_min_rs)].copy()
        qualified_vcp = qualified_trend[qualified_trend["Pass_VCP"] == True].copy()

        # 頂部關鍵數據指標卡
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("符合流動性股票", f"{len(df)} 檔")
        m2.metric(f"趨勢模板強勢股 (RS ≥ {param_min_rs})", f"{len(qualified_trend)} 檔")
        m3.metric("★ VCP 形態收縮股", f"{len(qualified_vcp)} 檔")
        vcp_ratio = f"{round((len(qualified_vcp)/len(qualified_trend)*100), 1)}%" if len(qualified_trend) > 0 else "0%"
        m4.metric("VCP 聚焦比率", vcp_ratio)

        st.markdown("---")

        # 檢視切換按鈕
        view_choice = st.radio(
            "清單篩選檢視：",
            ["★ 僅顯示 VCP 波動急凍股 (Pivot Ready)", "顯示所有趨勢模板合格股 (Stage 2 Uptrend)"],
            horizontal=True
        )

        display_df = qualified_vcp if "VCP" in view_choice else qualified_trend
        display_df = display_df.sort_values(by="RS_Rating", ascending=False)

        cols_to_show = [
            "Ticker", "Price", "RS_Rating", "Tightness_20d_%", 
            "ATR_Ratio", "Vol_Dryup_Ratio", "Dollar_Vol_M", 
            "SMA50", "SMA200", "52W_High", "Pass_VCP"
        ]

        # 格式化展示
        st.dataframe(
            display_df[cols_to_show].style.background_gradient(
                subset=["RS_Rating"], cmap="YlGn"
            ).format({
                "Price": "${:.2f}",
                "Tightness_20d_%": "{:.1f}%",
                "ATR_Ratio": "{:.2f}",
                "Vol_Dryup_Ratio": "{:.2f}",
                "Dollar_Vol_M": "${:.1f}M",
                "SMA50": "${:.2f}",
                "SMA200": "${:.2f}",
                "52W_High": "${:.2f}"
            }),
            use_container_width=True,
            height=500
        )

        # 匯出區
        d1, d2 = st.columns([1, 2])
        with d1:
            csv_data = display_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                label="📥 下載篩選清單 (CSV)",
                data=csv_data,
                file_name=f"minervini_screen_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        with d2:
            # 方便直接複製進 TradingView Watchlist
            tv_tickers = ",".join(display_df["Ticker"].tolist())
            st.text_input("TradingView Watchlist 批次導入字串 (複製後直接貼入 TV):", value=tv_tickers)
    else:
        st.info("👈 請在左側側邊欄選擇掃描規模與閥值，並點擊『開始全市場掃描』。")
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ETH每日行情日报生成器 v1.0
覆盖: ETH 价格、资金费率、持仓量、多空比、爆仓数据、关键支撑阻力位
数据源: CoinGecko (免费API) + Binance API
"""

import requests
import json
import os
import sys
from datetime import datetime

# ============================================================
# 配置
# ============================================================
REPORT_DIR = r"C:\Users\ZhuanZ（无密码）\WorkBuddy\btc-git\eth\reports"
DATE_STR = datetime.now().strftime('%Y%m%d')
DATE_DISPLAY = datetime.now().strftime('%Y-%m-%d')
TIME_DISPLAY = datetime.now().strftime('%H:%M')
REPORT_FILE = os.path.join(REPORT_DIR, f"ETH_daily_report_{DATE_STR}.html")
INDEX_FILE = r"C:\Users\ZhuanZ（无密码）\WorkBuddy\btc-git\eth\index.html"

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

session = requests.Session()
session.headers.update(HEADERS)
session.timeout = 30


def safe_get(url, params=None):
    """安全HTTP GET请求"""
    try:
        r = session.get(url, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        print(f"  [WARN] {url} -> {r.status_code}")
        return None
    except Exception as e:
        print(f"  [ERR] {url} -> {e}")
        return None


# ============================================================
# 第一步：获取 ETH 价格数据 (CoinGecko)
# ============================================================
def fetch_eth_price():
    """获取ETH的当前价格、24h涨跌、高低、市值、成交量"""
    print("[1/4] 获取CoinGecko ETH价格数据...")
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": "ethereum",
        "order": "market_cap_desc",
        "sparkline": "false",
        "price_change_percentage": "1h,24h,7d"
    }
    data = safe_get(url, params)
    if not data or len(data) == 0:
        print("  CoinGecko API失败，使用备用...")
        return fetch_eth_fallback()

    coin = data[0]
    pcp = coin.get("price_change_percentage_24h_in_currency", 0) or 0
    result = {
        "name": coin["name"],
        "symbol": "ETH",
        "price": coin["current_price"],
        "change_24h": pcp,
        "change_1h": coin.get("price_change_percentage_1h_in_currency", 0) or 0,
        "change_7d": coin.get("price_change_percentage_7d_in_currency", 0) or 0,
        "high_24h": coin.get("high_24h", 0),
        "low_24h": coin.get("low_24h", 0),
        "market_cap": coin.get("market_cap", 0),
        "volume_24h": coin.get("total_volume", 0),
        "ath": coin.get("ath", 0),
        "ath_date": coin.get("ath_date", "")[:10],
        "atl": coin.get("atl", 0),
        "circulating_supply": coin.get("circulating_supply", 0),
    }
    print(f"  OK: ETH 价格 ${result['price']:,.2f}")
    return result


def fetch_eth_fallback():
    """备用：逐个获取ETH"""
    data = safe_get("https://api.coingecko.com/api/v3/coins/ethereum",
                    {"localization": "false", "tickers": "false", "market_data": "true", "community_data": "false"})
    if data:
        md = data.get("market_data", {})
        return {
            "name": data.get("name", "Ethereum"),
            "symbol": "ETH",
            "price": md.get("current_price", {}).get("usd", 0),
            "change_24h": md.get("price_change_percentage_24h", 0),
            "change_1h": md.get("price_change_percentage_1h_in_currency", {}).get("usd", 0),
            "change_7d": md.get("price_change_percentage_7d", 0),
            "high_24h": md.get("high_24h", {}).get("usd", 0),
            "low_24h": md.get("low_24h", {}).get("usd", 0),
            "market_cap": md.get("market_cap", {}).get("usd", 0),
            "volume_24h": md.get("total_volume", {}).get("usd", 0),
            "ath": md.get("ath", {}).get("usd", 0),
            "ath_date": str(md.get("ath_date", {}).get("usd", ""))[:10],
            "atl": md.get("atl", {}).get("usd", 0),
            "circulating_supply": md.get("circulating_supply", 0),
        }
    return None


def fetch_eth_history():
    """获取ETH 24h价格历史（用于走势图和支撑阻力）"""
    print("[1b/4] 获取ETH 24h走势数据...")
    data = safe_get(
        "https://api.coingecko.com/api/v3/coins/ethereum/market_chart",
        {"vs_currency": "usd", "days": "1"}
    )
    if data and "prices" in data:
        prices = data["prices"]
        step = max(1, len(prices) // 48)
        sampled = prices[::step]
        if len(sampled) > 48:
            sampled = sampled[:48]
        return sampled
    return []


def calc_support_resistance(prices_data):
    """基于24h数据估算支撑位和阻力位"""
    if not prices_data:
        return {"support1": 0, "support2": 0, "resist1": 0, "resist2": 0}

    all_prices = [p[1] for p in prices_data]
    current = all_prices[-1]
    low = min(all_prices)
    high = max(all_prices)

    # 简单支撑阻力计算
    resist1 = round(high * 1.01, 2)
    resist2 = round(high * 1.025, 2)
    support1 = round(low * 0.99, 2)
    support2 = round(low * 0.975, 2)

    return {
        "support1": support1,
        "support2": support2,
        "resist1": resist1,
        "resist2": resist2,
        "high_24h": high,
        "low_24h": low,
    }


# ============================================================
# 第二步：获取衍生品数据 (Binance)
# ============================================================
def fetch_funding_rate():
    """获取ETH资金费率"""
    print("[2/4] 获取ETH资金费率...")
    try:
        bd = safe_get("https://fapi.binance.com/fapi/v1/premiumIndex?symbol=ETHUSDT")
        if bd:
            return {
                "current_rate": float(bd.get("lastFundingRate", 0)) * 100,
                "mark_price": float(bd.get("markPrice", 0)),
                "index_price": float(bd.get("indexPrice", 0)),
            }
    except Exception as e:
        print(f"  [WARN] ETH资金费率获取失败: {e}")
    return {"current_rate": 0, "mark_price": 0, "index_price": 0}


def fetch_open_interest():
    """获取ETH持仓量数据"""
    print("[3/4] 获取ETH持仓量...")
    try:
        bd = safe_get("https://fapi.binance.com/fapi/v1/openInterest?symbol=ETHUSDT")
        if bd:
            oi_val = float(bd.get("openInterest", 0))
            return {
                "total_oi": oi_val,
                "total_oi_usd": oi_val,  # 以币数量返回，后续乘以价格
            }
    except Exception as e:
        print(f"  [WARN] ETH持仓量获取失败: {e}")
    return {"total_oi": 0, "total_oi_usd": 0}


def fetch_long_short_and_liquidations():
    """获取ETH多空比与爆仓数据"""
    print("[4/4] 获取ETH多空比与爆仓数据...")
    long_short = {}
    liquidations = {}

    # Binance: 多空比
    try:
        data = safe_get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=ETHUSDT&period=1h&limit=1")
        if data and len(data) > 0:
            long_short = {
                "long_ratio": round(float(data[0].get("longAccount", 0)) * 100, 2),
                "short_ratio": round(float(data[0].get("shortAccount", 0)) * 100, 2),
                "long_short_ratio": round(float(data[0].get("longShortRatio", 0)), 4),
            }
    except:
        long_short = {"long_ratio": 50, "short_ratio": 50, "long_short_ratio": 1.0}

    # Binance: 爆仓数据 (最近50笔)
    try:
        liq_data = safe_get("https://fapi.binance.com/futures/data/allForceOrders?limit=50")
        if liq_data:
            long_liq_count = sum(1 for x in liq_data if x.get("side") == "SELL")
            short_liq_count = sum(1 for x in liq_data if x.get("side") == "BUY")
            long_liq_usd = sum(float(x.get("price", 0)) * float(x.get("origQty", 0))
                              for x in liq_data if x.get("side") == "SELL")
            short_liq_usd = sum(float(x.get("price", 0)) * float(x.get("origQty", 0))
                               for x in liq_data if x.get("side") == "BUY")
            liquidations = {
                "long_liq_count": long_liq_count,
                "short_liq_count": short_liq_count,
                "long_liq_usd": long_liq_usd,
                "short_liq_usd": short_liq_usd,
                "total_liq_count": len(liq_data),
            }
    except:
        liquidations = {
            "long_liq_count": 0, "short_liq_count": 0,
            "long_liq_usd": 0, "short_liq_usd": 0, "total_liq_count": 0
        }

    print(f"  OK: 多空比 {long_short.get('long_short_ratio', 0)}, 爆仓数据已获取")
    return long_short, liquidations


# ============================================================
# 合约方向建议引擎
# ============================================================
def generate_trading_suggestion(price_data, funding, oi, long_short, liquidations, sr):
    """基于多维度数据生成合约方向建议"""
    eth_price = price_data.get("price", 0)
    eth_change = price_data.get("change_24h", 0)
    eth_funding = funding.get("current_rate", 0)
    eth_ls = long_short.get("long_short_ratio", 1.0)

    signals = []
    score = 0  # 正=看多, 负=看空

    # 1. 趋势信号 (24h涨跌)
    if eth_change > 3:
        signals.append(("bullish", f"24h上涨{eth_change:.2f}%，短期趋势偏多"))
        score += 1
    elif eth_change < -3:
        signals.append(("bearish", f"24h下跌{abs(eth_change):.2f}%，短期趋势偏空"))
        score -= 1
    else:
        signals.append(("neutral", f"24h波动{abs(eth_change):.2f}%，处于震荡区间"))

    # 2. 资金费率信号
    if eth_funding > 0.05:
        signals.append(("bearish", f"资金费率{eth_funding:.4f}%偏高，多头过热，注意回调风险"))
        score -= 1
    elif eth_funding < -0.02:
        signals.append(("bullish", f"资金费率{eth_funding:.4f}%为负，空头付费，可能反弹"))
        score += 1
    else:
        signals.append(("neutral", f"资金费率{eth_funding:.4f}%处于正常范围"))

    # 3. 多空比信号
    if eth_ls > 1.5:
        signals.append(("bearish", f"多空比{eth_ls:.2f}偏高，多头拥挤，警惕轧空或回调"))
        score -= 0.5
    elif eth_ls < 0.67:
        signals.append(("bullish", f"多空比{eth_ls:.2f}偏低，空头较多，可能存在轧空机会"))
        score += 0.5
    else:
        signals.append(("neutral", f"多空比{eth_ls:.2f}相对均衡"))

    # 4. 持仓量信号
    if oi.get("total_oi", 0) > 0:
        signals.append(("neutral", f"持仓量 {oi['total_oi']/1e6:.2f}M ETH"))

    # 5. 爆仓数据信号
    long_liq = liquidations.get("long_liq_usd", 0)
    short_liq = liquidations.get("short_liq_usd", 0)
    total_liq = long_liq + short_liq
    if total_liq > 0:
        if long_liq > short_liq * 2:
            signals.append(("bearish", f"多头爆仓${long_liq/1e6:.1f}M远超空头，市场恐慌"))
            score -= 0.5
        elif short_liq > long_liq * 2:
            signals.append(("bullish", f"空头爆仓${short_liq/1e6:.1f}M远超多头，轧空迹象"))
            score += 0.5
        else:
            signals.append(("neutral", f"多空爆仓相对均衡，总爆仓${total_liq/1e6:.1f}M"))

    # 综合判断
    if score >= 1.5:
        direction = "偏多"
        direction_color = "#3fb950"
        advice = "整体信号偏多，可关注回调做多的机会。注意设置止损。"
    elif score >= 0.5:
        direction = "轻多"
        direction_color = "#3fb950"
        advice = "信号略偏多，建议轻仓试多，严格止损。"
    elif score <= -1.5:
        direction = "偏空"
        direction_color = "#f85149"
        advice = "整体信号偏空，可关注反弹做空的机会。注意设置止损。"
    elif score <= -0.5:
        direction = "轻空"
        direction_color = "#f85149"
        advice = "信号略偏空，建议轻仓试空，严格止损。"
    else:
        direction = "观望"
        direction_color = "#d29922"
        advice = "多空信号混杂，建议暂时观望，等待方向明确后再入场。"

    return {
        "direction": direction,
        "direction_color": direction_color,
        "advice": advice,
        "signals": signals,
        "score": score,
    }


# ============================================================
# HTML报告生成
# ============================================================
def fmt_usd(val):
    """格式化美元金额"""
    if val >= 1e9:
        return f"${val/1e9:.2f}B"
    elif val >= 1e6:
        return f"${val/1e6:.2f}M"
    elif val >= 1e3:
        return f"${val/1e3:.2f}K"
    return f"${val:.2f}"


def fmt_pct(val):
    """格式化百分比"""
    sign = "+" if val >= 0 else ""
    return f"{sign}{val:.2f}%"


def generate_html(price_data, funding, oi, long_short, liquidations, sr, suggestion, history):
    """生成完整的HTML报告"""
    date_display = DATE_DISPLAY
    time_display = TIME_DISPLAY

    # 走势图数据
    chart_labels = []
    chart_prices = []
    if history:
        for ts, p in history:
            dt = datetime.fromtimestamp(ts / 1000)
            chart_labels.append(f"'{dt.strftime('%H:%M')}'")
            chart_prices.append(f"{p:.2f}")

    # 涨跌幅颜色
    ch = price_data.get("change_24h", 0)
    ch_color = "#3fb950" if ch >= 0 else "#f85149"
    ch_bg = "rgba(63,185,80,0.15)" if ch >= 0 else "rgba(248,81,73,0.15)"

    # 资金费率颜色
    fr = funding.get("current_rate", 0)
    fr_color = "#f85149" if fr > 0.05 else ("#3fb950" if fr < -0.01 else "#d29922")

    # 多空比
    ls = long_short.get("long_short_ratio", 1.0)
    l_ratio = long_short.get("long_ratio", 50)
    s_ratio = long_short.get("short_ratio", 50)
    bar_width = min(max(l_ratio, 5), 95)

    # 爆仓数据
    long_lq = liquidations.get("long_liq_usd", 0)
    short_lq = liquidations.get("short_liq_usd", 0)
    total_lq = long_lq + short_lq
    long_lq_c = liquidations.get("long_liq_count", 0)
    short_lq_c = liquidations.get("short_liq_count", 0)
    lq_bar_w = (long_lq / total_lq * 100) if total_lq > 0 else 50

    # 信号列表
    signals_html = ""
    for signal_type, desc in suggestion.get("signals", []):
        s_color = {"bullish": "#3fb950", "bearish": "#f85149", "neutral": "#d29922"}[signal_type]
        s_icon = {"bullish": "&#9650;", "bearish": "&#9660;", "neutral": "&#9679;"}[signal_type]
        s_label = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}[signal_type]
        signals_html += f'''
        <div style="display:flex;align-items:flex-start;gap:10px;padding:8px 0;border-bottom:1px solid var(--border);">
            <span style="color:{s_color};font-size:1.2em;">{s_icon}</span>
            <div>
                <span style="color:{s_color};font-weight:bold;">[{s_label}]</span>
                <span style="color:var(--sub);"> {desc}</span>
            </div>
        </div>'''

    # 距ATH百分比
    ath = price_data.get("ath", 0)
    price = price_data.get("price", 0)
    ath_pct = ((price / ath) - 1) * 100 if ath > 0 else 0

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETH 每日日报 {date_display}</title>
    <style>
        :root {{--bg:#0d0d14;--card:#161b22;--card-h:#1c2128;--border:#30363d;--text:#e6edf3;--sub:#8b949e;--purple:#a855f7;--orange:#f7931a;--green:#3fb950;--red:#f85149;--yellow:#d29922;--eth:#627eea;}}
        * {{margin:0;padding:0;box-sizing:border-box;}}
        body {{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--text);line-height:1.6;padding:20px;}}
        .c {{max-width:1400px;margin:0 auto;}}
        .h {{background:linear-gradient(135deg,#1a1a2e,#16213e);border:1px solid var(--purple);border-radius:16px;padding:30px;margin-bottom:24px;text-align:center;}}
        .h h1 {{font-size:2.2em;color:var(--eth);margin-bottom:8px;}}
        .h .sub {{color:var(--sub);font-size:1.1em;}}
        .s {{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:24px;margin-bottom:20px;position:relative;padding-left:32px;}}
        .s::before {{content:'';position:absolute;left:12px;top:0;bottom:0;width:4px;background:var(--purple);border-radius:4px;}}
        .sh {{display:flex;align-items:center;gap:12px;margin-bottom:20px;}}
        .sh h2 {{font-size:1.3em;}}
        .tag {{background:var(--purple);color:white;padding:2px 8px;border-radius:4px;font-size:0.75em;font-weight:bold;}}
        .g {{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:16px;}}
        .sc {{background:var(--card-h);border-radius:8px;padding:16px;text-align:center;}}
        .sc .lbl {{color:var(--sub);font-size:0.85em;margin-bottom:4px;}}
        .sc .val {{font-size:1.5em;font-weight:bold;}}
        .hero {{background:linear-gradient(135deg,#1a1a2e,#16213e);border-radius:16px;padding:40px;text-align:center;margin-bottom:24px;}}
        .hero .sym {{color:var(--eth);font-size:1.2em;margin-bottom:8px;}}
        .hero .price {{font-size:4em;font-weight:bold;margin-bottom:8px;}}
        .hero .chg {{font-size:1.5em;padding:4px 16px;border-radius:8px;display:inline-block;}}
        .hero .chg.up {{background:rgba(63,185,80,0.2);color:var(--green);}}
        .hero .chg.down {{background:rgba(248,81,73,0.2);color:var(--red);}}
        table {{width:100%;border-collapse:collapse;}}
        th {{text-align:left;padding:8px 12px;color:var(--sub);border-bottom:1px solid var(--border);font-size:0.9em;}}
        td {{border-bottom:1px solid rgba(48,54,61,0.5);padding:8px 12px;}}
        .dir-badge {{display:inline-block;padding:6px 20px;border-radius:20px;font-size:1.3em;font-weight:bold;margin:10px 0;}}
        .warn {{background:rgba(210,153,34,0.1);border:1px solid var(--yellow);border-radius:12px;padding:20px;margin-bottom:20px;}}
        .warn h2 {{color:var(--yellow);margin-bottom:10px;}}
        .foot {{text-align:center;color:var(--sub);font-size:0.85em;margin-top:30px;padding-top:20px;border-top:1px solid var(--border);}}
        @media(max-width:768px) {{.hero .price {{font-size:2.5em;}}}}
    </style>
</head>
<body>
<div class="c">

    <!-- 标题头 -->
    <div class="h">
        <div style="font-size:2.5em;margin-bottom:4px;">&#926;</div>
        <h1>ETH Daily Report</h1>
        <p class="sub">{date_display} | {time_display} UTC+8</p>
        <p style="color:var(--sub);font-size:0.85em;margin-top:4px;">MK Trading | bitebiwang1413</p>
    </div>

    <!-- ETH Hero -->
    <div class="hero">
        <div class="sym">ETH / USDT</div>
        <div class="price">${price:,.2f}</div>
        <div class="chg {"up" if ch >= 0 else "down"}">
            {"&#9650;" if ch >= 0 else "&#9660;"} {fmt_pct(ch)}
        </div>
        <div style="margin-top:12px;display:flex;justify-content:center;gap:24px;color:var(--sub);font-size:0.9em;">
            <span>24h高: <span style="color:#3fb950;">${price_data.get("high_24h", 0):,.2f}</span></span>
            <span>24h低: <span style="color:#f85149;">${price_data.get("low_24h", 0):,.2f}</span></span>
            <span>ATH: ${ath:,.2f} ({fmt_pct(ath_pct)})</span>
        </div>
    </div>

    <!-- ETH 概览卡片 -->
    <div class="s">
        <div class="sh">
            <h2>&#128200; ETH 行情概览</h2>
            <span class="tag">LIVE</span>
        </div>
        <div class="g" style="grid-template-columns:repeat(4,1fr);">
            <div class="sc">
                <div class="lbl">当前价格</div>
                <div class="val">${price:,.2f}</div>
            </div>
            <div class="sc">
                <div class="lbl">24h涨跌</div>
                <div class="val" style="color:{ch_color};">{fmt_pct(ch)}</div>
            </div>
            <div class="sc">
                <div class="lbl">1h涨跌</div>
                <div class="val" style="color:{'#3fb950' if price_data.get('change_1h',0) >= 0 else '#f85149'};">{fmt_pct(price_data.get("change_1h", 0))}</div>
            </div>
            <div class="sc">
                <div class="lbl">7d涨跌</div>
                <div class="val" style="color:{'#3fb950' if price_data.get('change_7d',0) >= 0 else '#f85149'};">{fmt_pct(price_data.get("change_7d", 0))}</div>
            </div>
            <div class="sc">
                <div class="lbl">市值</div>
                <div class="val">{fmt_usd(price_data.get("market_cap", 0))}</div>
            </div>
            <div class="sc">
                <div class="lbl">24h成交量</div>
                <div class="val">{fmt_usd(price_data.get("volume_24h", 0))}</div>
            </div>
            <div class="sc">
                <div class="lbl">流通供应量</div>
                <div class="val">{price_data.get("circulating_supply", 0)/1e6:.2f}M ETH</div>
            </div>
            <div class="sc">
                <div class="lbl">距ATH</div>
                <div class="val" style="color:{'#3fb950' if ath_pct >= 0 else '#f85149'};">{fmt_pct(ath_pct)}</div>
            </div>
        </div>
    </div>

    <!-- ETH 走势图 -->
    <div class="s">
        <div class="sh"><h2>&#128201; ETH 24H 价格走势</h2></div>
        <div style="height:300px;">
            <canvas id="priceChart"></canvas>
        </div>
    </div>

    <!-- 支撑阻力位 -->
    <div class="s">
        <div class="sh"><h2>&#127919; ETH 关键支撑/阻力位</h2><span class="tag">TECH</span></div>
        <div class="g" style="grid-template-columns:repeat(4,1fr);">
            <div class="sc">
                <div class="lbl">阻力位 R2</div>
                <div class="val" style="color:#f85149;">${sr.get("resist2", 0):,.2f}</div>
            </div>
            <div class="sc">
                <div class="lbl">阻力位 R1</div>
                <div class="val" style="color:#f85149;">${sr.get("resist1", 0):,.2f}</div>
            </div>
            <div class="sc">
                <div class="lbl">支撑位 S1</div>
                <div class="val" style="color:#3fb950;">${sr.get("support1", 0):,.2f}</div>
            </div>
            <div class="sc">
                <div class="lbl">支撑位 S2</div>
                <div class="val" style="color:#3fb950;">${sr.get("support2", 0):,.2f}</div>
            </div>
        </div>
        <div style="margin-top:12px;color:var(--sub);font-size:0.85em;">
            * 基于近24h高低点估算，仅供参考，实际交易需结合更多技术指标
        </div>
    </div>

    <!-- 资金费率 -->
    <div class="s">
        <div class="sh"><h2>&#128176; 资金费率 (Funding Rate)</h2><span class="tag">DERIVATIVES</span></div>
        <div class="g" style="grid-template-columns:repeat(3,1fr);">
            <div class="sc">
                <div class="lbl">当前费率</div>
                <div class="val" style="color:{fr_color};">{fr:.4f}%</div>
            </div>
            <div class="sc">
                <div class="lbl">标记价格</div>
                <div class="val">${funding.get("mark_price", 0):,.2f}</div>
            </div>
            <div class="sc">
                <div class="lbl">指数价格</div>
                <div class="val">${funding.get("index_price", 0):,.2f}</div>
            </div>
        </div>
        <div style="margin-top:12px;color:var(--sub);font-size:0.85em;">
            * 资金费率 > 0.05% 表示多头过热；< 0 表示空头付费做多，可能反弹
        </div>
    </div>

    <!-- 持仓量 -->
    <div class="s">
        <div class="sh"><h2>&#128202; 持仓量 (Open Interest)</h2><span class="tag">DERIVATIVES</span></div>
        <div class="g" style="grid-template-columns:repeat(2,1fr);">
            <div class="sc">
                <div class="lbl">总持仓量</div>
                <div class="val">{oi.get("total_oi", 0)/1e6:.2f}M ETH</div>
            </div>
            <div class="sc">
                <div class="lbl">持仓量估值</div>
                <div class="val">{fmt_usd(oi.get("total_oi", 0) * price)}</div>
            </div>
        </div>
    </div>

    <!-- 多空比 -->
    <div class="s">
        <div class="sh"><h2>&#9878;&#65039; 多空比 (Long/Short Ratio)</h2><span class="tag">DERIVATIVES</span></div>
        <div style="padding:16px;background:var(--card-h);border-radius:8px;">
            <div style="display:flex;align-items:center;gap:8px;margin-bottom:12px;">
                <span style="color:#3fb950;font-size:0.9em;">多头 {l_ratio:.1f}%</span>
                <div style="flex:1;height:10px;background:#21262d;border-radius:5px;overflow:hidden;">
                    <div style="width:{bar_width}%;height:100%;background:linear-gradient(90deg,#3fb950,#238636);border-radius:5px;"></div>
                </div>
                <span style="color:#f85149;font-size:0.9em;">空头 {s_ratio:.1f}%</span>
            </div>
            <div style="text-align:center;font-size:1.2em;font-weight:bold;">
                多空比: <span style="color:{'#3fb950' if ls >= 1 else '#f85149'}">{ls:.4f}</span>
            </div>
        </div>
        <div style="margin-top:12px;color:var(--sub);font-size:0.85em;">
            * 多空比 > 1.5 多头拥挤需警惕回调；< 0.67 空头拥挤可能存在轧空机会
        </div>
    </div>

    <!-- 爆仓数据 -->
    <div class="s">
        <div class="sh"><h2>&#128165; 24H 爆仓数据</h2><span class="tag">DERIVATIVES</span></div>
        <div class="g" style="grid-template-columns:repeat(3,1fr);">
            <div class="sc">
                <div class="lbl">多头爆仓</div>
                <div class="val" style="color:#f85149;">{fmt_usd(long_lq)}</div>
                <div style="color:var(--sub);font-size:0.85em;">{long_lq_c} 笔</div>
            </div>
            <div class="sc">
                <div class="lbl">空头爆仓</div>
                <div class="val" style="color:#3fb950;">{fmt_usd(short_lq)}</div>
                <div style="color:var(--sub);font-size:0.85em;">{short_lq_c} 笔</div>
            </div>
            <div class="sc">
                <div class="lbl">总爆仓金额</div>
                <div class="val">{fmt_usd(total_lq)}</div>
                <div style="color:var(--sub);font-size:0.85em;">{liquidations.get("total_liq_count", 0)} 笔</div>
            </div>
        </div>
        <div style="margin-top:16px;">
            <div style="height:20px;background:#21262d;border-radius:10px;overflow:hidden;display:flex;">
                <div style="width:{lq_bar_w}%;background:linear-gradient(90deg,#f85149,#da3633);height:100%;"></div>
                <div style="flex:1;background:linear-gradient(90deg,#238636,#3fb950);height:100%;"></div>
            </div>
            <div style="display:flex;justify-content:space-between;margin-top:4px;font-size:0.8em;color:var(--sub);">
                <span style="color:#f85149;">&#9660; 多头爆仓 {fmt_usd(long_lq)}</span>
                <span style="color:#3fb950;">空头爆仓 {fmt_usd(short_lq)} &#9650;</span>
            </div>
        </div>
    </div>

    <!-- 合约方向建议 -->
    <div class="s" style="border-left:4px solid {suggestion.get("direction_color", "#d29922")};">
        <div class="sh">
            <h2>&#128161; 合约方向建议</h2>
            <span class="dir-badge" style="background:{suggestion.get("direction_color", "#d29922")}20;color:{suggestion.get("direction_color", "#d29922")};border:1px solid {suggestion.get("direction_color", "#d29922")};">
                {suggestion.get("direction", "观望")}
            </span>
        </div>
        <p style="margin-bottom:16px;padding:12px;background:var(--card-h);border-radius:8px;color:var(--text);">
            {suggestion.get("advice", "")}
        </p>
        <h3 style="font-size:1em;margin-bottom:8px;color:var(--sub);">信号详情：</h3>
        {signals_html}
    </div>

    <!-- 风险提示 -->
    <div class="warn">
        <h2>&#9888;&#65039; 风险提示</h2>
        <ul style="padding-left:20px;color:var(--sub);font-size:0.9em;">
            <li>加密货币市场7x24运行，波动性极高，杠杆交易风险加倍</li>
            <li>合约交易存在强制平仓风险，请严格控制仓位和杠杆倍数</li>
            <li>资金费率、多空比等衍生品数据仅供参考，不构成交易信号</li>
            <li>本报告由自动化系统生成，数据可能存在延迟或偏差</li>
            <li>DYOR - 请自行研究后决策，理性交易</li>
        </ul>
    </div>

    <!-- 页脚 -->
    <div class="foot">
        <p>数据来源: CoinGecko | Binance</p>
        <p>自动生成于 {date_display} {time_display} | MK Trading</p>
        <p>免责声明: 本报告仅供参考，不构成任何投资建议。投资有风险，入市需谨慎。</p>
    </div>
</div>

<!-- Chart.js 走势图 -->
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
    (function() {{
        const labels = [{','.join(chart_labels)}];
        const prices = [{','.join(chart_prices)}];
        if (prices.length > 0) {{
            const ctx = document.getElementById('priceChart').getContext('2d');
            const isUp = prices[0] <= prices[prices.length - 1];
            new Chart(ctx, {{
                type: 'line',
                data: {{
                    labels: labels,
                    datasets: [{{
                        label: 'ETH/USDT',
                        data: prices,
                        borderColor: isUp ? '#3fb950' : '#f85149',
                        backgroundColor: isUp ? 'rgba(63,185,80,0.1)' : 'rgba(248,81,73,0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 0,
                        borderWidth: 2
                    }}]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {{ legend: {{ display: false }} }},
                    scales: {{
                        x: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#8b949e' }} }},
                        y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#8b949e' }} }}
                    }}
                }}
            }});
        }}
    }})();
</script>
</body>
</html>'''
    return html


def update_index_html():
    """更新 index.html，在顶部插入今日报告链接"""
    report_link = f"reports/ETH_daily_report_{DATE_STR}.html"
    report_entry = f'<div class="report-item"><a href="{report_link}">{DATE_DISPLAY} ETH日报</a><span class="tag">NEW</span></div>'

    if os.path.exists(INDEX_FILE):
        with open(INDEX_FILE, 'r', encoding='utf-8') as f:
            content = f.read()
        # 在报告列表顶部插入
        if '<div class="report-list">' in content:
            content = content.replace('<div class="report-list">', f'<div class="report-list">\n        {report_entry}')
        else:
            # 如果没有report-list，在body末尾添加
            content = content.replace('</body>', f'<div class="report-list">{report_entry}</div>\n</body>')
    else:
        # 创建新的 index.html
        content = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ETH 每日日报归档</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Microsoft YaHei", sans-serif; background: #0d0d14; color: #e6edf3; padding: 40px; }}
        .container {{ max-width: 800px; margin: 0 auto; }}
        h1 {{ color: #627eea; text-align: center; margin-bottom: 30px; }}
        .report-list {{ display: flex; flex-direction: column; gap: 12px; }}
        .report-item {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px 20px; display: flex; justify-content: space-between; align-items: center; }}
        .report-item:hover {{ border-color: #627eea; }}
        .report-item a {{ color: #e6edf3; text-decoration: none; font-size: 1.1em; }}
        .report-item a:hover {{ color: #627eea; }}
        .tag {{ background: #627eea; color: white; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; }}
        .footer {{ text-align: center; margin-top: 40px; color: #8b949e; font-size: 0.85em; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>&#926; ETH 每日日报归档</h1>
        <div class="report-list">
        {report_entry}
        </div>
        <div class="footer">
            <p>MK Trading | 自动生成的ETH日报</p>
        </div>
    </div>
</body>
</html>'''

    with open(INDEX_FILE, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"[OK] 已更新: {INDEX_FILE}")


# ============================================================
# 主函数
# ============================================================
def main():
    print("=" * 60)
    print(f"ETH Daily Report Generator v1.0 | {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    # 检查是否已存在
    if os.path.exists(REPORT_FILE):
        print(f"[SKIP] 今日报告已存在: {REPORT_FILE}")
        return True  # 返回True表示正常完成（跳过）

    os.makedirs(REPORT_DIR, exist_ok=True)

    # 1. 价格数据
    price_data = fetch_eth_price()
    if not price_data:
        print("[FATAL] 无法获取ETH价格数据，退出")
        return False

    history = fetch_eth_history()
    sr = calc_support_resistance(history)

    # 2. 衍生品数据
    funding = fetch_funding_rate()
    oi = fetch_open_interest()
    long_short, liquidations = fetch_long_short_and_liquidations()

    # 3. 生成建议
    suggestion = generate_trading_suggestion(price_data, funding, oi, long_short, liquidations, sr)

    # 4. 生成HTML
    print("\n[生成报告...]")
    html = generate_html(price_data, funding, oi, long_short, liquidations, sr, suggestion, history)

    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"[OK] 报告已保存: {REPORT_FILE}")
    print(f"[OK] ETH价格: ${price_data['price']:,.2f} ({price_data['change_24h']:+.2f}%)")
    print(f"[OK] 方向建议: {suggestion['direction']}")

    # 5. 更新 index.html
    update_index_html()

    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

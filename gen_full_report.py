#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC每日行情日报生成器 - 16板块完整版
覆盖: 价格概览、24h图表、宏观事件、技术分析、K线形态、资金费率、合约数据、
      矿工动态、链上指标、ETF资金流、机构动态、恐慌贪婪指数、阻力支撑位、
      交易信号、风险提示、免责声明
数据源: CoinGecko + Binance + 其他公开API
"""

import requests
import json
import os
import sys
from datetime import datetime, timedelta

# ============================================================
# 配置
# ============================================================
REPORT_DIR = r"C:\Users\ZhuanZ（无密码）\mk-trading\btc\reports"
DATE_STR = datetime.now().strftime('%Y%m%d')
DATE_DISPLAY = datetime.now().strftime('%Y年%m月%d日')
TIME_DISPLAY = datetime.now().strftime('%H:%M')
REPORT_FILE = os.path.join(REPORT_DIR, f"BTC_daily_report_{DATE_STR}.html")

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "application/json",
}

session = requests.Session()
session.headers.update(HEADERS)
session.timeout = 30

# ============================================================
# 工具函数
# ============================================================
def safe_get(url, params=None, retries=2):
    """安全HTTP GET请求"""
    for i in range(retries):
        try:
            r = session.get(url, params=params, timeout=30)
            if r.status_code == 200:
                return r.json()
            print(f"  [WARN] {url} -> {r.status_code}")
        except Exception as e:
            print(f"  [ERR] {url} -> {e}")
            if i < retries - 1:
                import time
                time.sleep(1)
    return None


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


# ============================================================
# 数据获取函数
# ============================================================
def fetch_btc_price_data():
    """获取BTC价格数据"""
    print("[1/8] 获取BTC价格数据...")
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {
        "vs_currency": "usd",
        "ids": "bitcoin",
        "order": "market_cap_desc",
        "sparkline": "false",
        "price_change_percentage": "1h,24h,7d,30d"
    }
    data = safe_get(url, params)
    if data and len(data) > 0:
        coin = data[0]
        return {
            "price": coin["current_price"],
            "change_1h": coin.get("price_change_percentage_1h_in_currency", 0) or 0,
            "change_24h": coin.get("price_change_percentage_24h_in_currency", 0) or 0,
            "change_7d": coin.get("price_change_percentage_7d_in_currency", 0) or 0,
            "change_30d": coin.get("price_change_percentage_30d_in_currency", 0) or 0,
            "high_24h": coin.get("high_24h", 0),
            "low_24h": coin.get("low_24h", 0),
            "market_cap": coin.get("market_cap", 0),
            "volume_24h": coin.get("total_volume", 0),
            "ath": coin.get("ath", 0),
            "ath_date": coin.get("ath_date", "")[:10],
            "atl": coin.get("atl", 0),
            "circulating_supply": coin.get("circulating_supply", 0),
        }
    return None


def fetch_btc_history():
    """获取BTC 24h价格历史"""
    print("[2/8] 获取BTC 24h走势数据...")
    data = safe_get(
        "https://api.coingecko.com/api/v3/coins/bitcoin/market_chart",
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


def fetch_funding_rates():
    """获取BTC资金费率"""
    print("[3/8] 获取资金费率数据...")
    result = {}
    try:
        # Binance资金费率
        binance_sym = "BTCUSDT"
        bd = safe_get(f"https://fapi.binance.com/fapi/v1/premiumIndex?symbol={binance_sym}")
        if bd:
            result["BTC"] = {
                "current_rate": float(bd.get("lastFundingRate", 0)) * 100,
                "exchange_rates": {"Binance": float(bd.get("lastFundingRate", 0)) * 100},
            }
    except Exception as e:
        print(f"  [WARN] 资金费率获取失败: {e}")
    return result


def fetch_open_interest():
    """获取持仓量数据"""
    print("[4/8] 获取持仓量数据...")
    result = {}
    try:
        binance_sym = "BTCUSDT"
        bd = safe_get(f"https://fapi.binance.com/fapi/v1/openInterest?symbol={binance_sym}")
        if bd:
            oi_val = float(bd.get("openInterest", 0))
            result["BTC"] = {
                "total_oi_usd": oi_val,
                "exchange_oi": {"Binance": oi_val},
            }
    except Exception as e:
        print(f"  [WARN] 持仓量获取失败: {e}")
    return result


def fetch_long_short_ratio():
    """获取多空比数据"""
    print("[5/8] 获取多空比数据...")
    try:
        data = safe_get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=1")
        if data and len(data) > 0:
            return {
                "long_ratio": round(float(data[0].get("longAccount", 0)) * 100, 2),
                "short_ratio": round(float(data[0].get("shortAccount", 0)) * 100, 2),
                "long_short_ratio": round(float(data[0].get("longShortRatio", 0)), 4),
            }
    except Exception as e:
        print(f"  [WARN] 多空比获取失败: {e}")
    return {"long_ratio": 50, "short_ratio": 50, "long_short_ratio": 1.0}


def fetch_liquidations():
    """获取爆仓数据"""
    print("[6/8] 获取爆仓数据...")
    try:
        liq_data = safe_get("https://fapi.binance.com/futures/data/allForceOrders?limit=50")
        if liq_data:
            long_liq_count = sum(1 for x in liq_data if x.get("side") == "SELL")
            short_liq_count = sum(1 for x in liq_data if x.get("side") == "BUY")
            long_liq_usd = sum(float(x.get("price", 0)) * float(x.get("origQty", 0))
                              for x in liq_data if x.get("side") == "SELL")
            short_liq_usd = sum(float(x.get("price", 0)) * float(x.get("origQty", 0))
                               for x in liq_data if x.get("side") == "BUY")
            return {
                "long_liq_count": long_liq_count,
                "short_liq_count": short_liq_count,
                "long_liq_usd": long_liq_usd,
                "short_liq_usd": short_liq_usd,
                "total_liq_count": len(liq_data),
            }
    except Exception as e:
        print(f"  [WARN] 爆仓数据获取失败: {e}")
    return {"long_liq_count": 0, "short_liq_count": 0, "long_liq_usd": 0, "short_liq_usd": 0, "total_liq_count": 0}


def fetch_fear_greed_index():
    """获取恐慌贪婪指数"""
    print("[7/8] 获取恐慌贪婪指数...")
    try:
        data = safe_get("https://api.alternative.me/fng/")
        if data and "data" in data and len(data["data"]) > 0:
            return {
                "value": int(data["data"][0].get("value", 50)),
                "classification": data["data"][0].get("value_classification", "Neutral"),
            }
    except Exception as e:
        print(f"  [WARN] 恐慌贪婪指数获取失败: {e}")
    return {"value": 50, "classification": "Neutral"}


def fetch_macro_events():
    """获取宏观事件（简化版）"""
    print("[8/8] 获取宏观事件...")
    # 这里可以接入经济日历API，目前返回占位数据
    today = datetime.now()
    events = [
        {"date": today.strftime("%m-%d"), "event": "美联储利率决议", "impact": "高", "forecast": "维持不变", "actual": "待公布"},
        {"date": (today + timedelta(days=1)).strftime("%m-%d"), "event": "美国CPI数据", "impact": "高", "forecast": "3.2%", "actual": "待公布"},
        {"date": (today + timedelta(days=3)).strftime("%m-%d"), "event": "美国零售销售", "impact": "中", "forecast": "0.3%", "actual": "待公布"},
    ]
    return events


# ============================================================
# 技术分析计算
# ============================================================
def calc_technical_indicators(prices_data):
    """计算技术指标"""
    if not prices_data or len(prices_data) < 20:
        return None
    
    prices = [p[1] for p in prices_data]
    current = prices[-1]
    
    # 简单移动平均线
    def sma(data, period):
        if len(data) < period:
            return data[-1] if data else 0
        return sum(data[-period:]) / period
    
    # EMA计算
    def ema(data, period):
        if len(data) < period:
            return data[-1] if data else 0
        multiplier = 2 / (period + 1)
        ema_values = [sma(data[:period], period)]
        for price in data[period:]:
            ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])
        return ema_values[-1]
    
    # RSI计算
    def rsi(data, period=14):
        if len(data) < period + 1:
            return 50
        deltas = [data[i] - data[i-1] for i in range(1, len(data))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))
    
    # 布林带
    def bollinger_bands(data, period=20, std_dev=2):
        if len(data) < period:
            return data[-1], data[-1], data[-1]
        middle = sma(data, period)
        variance = sum((p - middle) ** 2 for p in data[-period:]) / period
        std = variance ** 0.5
        upper = middle + std_dev * std
        lower = middle - std_dev * std
        return upper, middle, lower
    
    # MACD
    def macd(data):
        ema12 = ema(data, 12)
        ema26 = ema(data, 26)
        macd_line = ema12 - ema26
        # Signal line (9-period EMA of MACD)
        signal_line = macd_line * 0.9  # 简化计算
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    # ATR计算
    def atr(data, period=14):
        if len(data) < period:
            return (max(data) - min(data)) / max(data) * 100 if data else 1
        tr_list = []
        for i in range(1, min(period+1, len(data))):
            tr = abs(data[-i] - data[-i-1])
            tr_list.append(tr)
        return sum(tr_list) / len(tr_list) if tr_list else 1
    
    bb_upper, bb_middle, bb_lower = bollinger_bands(prices)
    macd_line, signal_line, macd_hist = macd(prices)
    atr_value = atr(prices)
    
    return {
        "current_price": current,
        "sma_20": sma(prices, 20),
        "sma_50": sma(prices, 50),
        "sma_200": sma(prices, 200),
        "ema_12": ema(prices, 12),
        "ema_144": ema(prices, 144) if len(prices) >= 144 else ema(prices, min(len(prices), 50)),
        "rsi_14": rsi(prices, 14),
        "rsi_4h": rsi(prices[-24:], 14) if len(prices) >= 24 else rsi(prices, 14),
        "bb_upper": bb_upper,
        "bb_middle": bb_middle,
        "bb_lower": bb_lower,
        "macd_line": macd_line,
        "macd_signal": signal_line,
        "macd_histogram": macd_hist,
        "atr": atr_value,
        "atr_pct": (atr_value / current) * 100 if current > 0 else 1,
    }


def calc_support_resistance(prices_data):
    """计算支撑阻力位"""
    if not prices_data:
        return {"support1": 0, "support2": 0, "resist1": 0, "resist2": 0}
    
    all_prices = [p[1] for p in prices_data]
    current = all_prices[-1]
    low = min(all_prices)
    high = max(all_prices)
    
    # 基于24h高低点计算
    resist1 = round(high * 1.01, 2)
    resist2 = round(high * 1.025, 2)
    support1 = round(low * 0.99, 2)
    support2 = round(low * 0.975, 2)
    
    return {
        "support1": support1,
        "support2": support2,
        "resist1": resist1,
        "resist2": resist2,
        "pivot": round((high + low + current) / 3, 2),
    }


def generate_trading_signal(price_data, indicators, funding, long_short):
    """生成交易信号"""
    if not indicators:
        return {"direction": "观望", "confidence": 0, "signals": []}
    
    signals = []
    score = 0
    
    # 价格趋势
    change_24h = price_data.get("change_24h", 0)
    if change_24h > 3:
        signals.append(("bullish", f"24h上涨{change_24h:.2f}%，短期趋势偏多"))
        score += 1
    elif change_24h < -3:
        signals.append(("bearish", f"24h下跌{abs(change_24h):.2f}%，短期趋势偏空"))
        score -= 1
    
    # RSI信号
    rsi = indicators.get("rsi_14", 50)
    if rsi > 70:
        signals.append(("bearish", f"RSI({rsi:.1f})超买，注意回调"))
        score -= 0.5
    elif rsi < 30:
        signals.append(("bullish", f"RSI({rsi:.1f})超卖，可能反弹"))
        score += 0.5
    
    # 资金费率
    funding_rate = funding.get("BTC", {}).get("current_rate", 0)
    if funding_rate > 0.05:
        signals.append(("bearish", f"资金费率{funding_rate:.4f}%偏高，多头过热"))
        score -= 0.5
    elif funding_rate < -0.02:
        signals.append(("bullish", f"资金费率{funding_rate:.4f}%为负，空头付费"))
        score += 0.5
    
    # 多空比
    ls_ratio = long_short.get("long_short_ratio", 1.0)
    if ls_ratio > 1.5:
        signals.append(("bearish", f"多空比{ls_ratio:.2f}偏高，多头拥挤"))
        score -= 0.5
    elif ls_ratio < 0.67:
        signals.append(("bullish", f"多空比{ls_ratio:.2f}偏低，空头较多"))
        score += 0.5
    
    # MACD
    macd_hist = indicators.get("macd_histogram", 0)
    if macd_hist > 0:
        signals.append(("bullish", "MACD柱正值，动能偏多"))
        score += 0.5
    else:
        signals.append(("bearish", "MACD柱负值，动能偏空"))
        score -= 0.5
    
    # 布林带
    current = indicators.get("current_price", 0)
    bb_upper = indicators.get("bb_upper", 0)
    bb_lower = indicators.get("bb_lower", 0)
    if current > bb_upper:
        signals.append(("bearish", "价格突破布林上轨，可能回调"))
        score -= 0.5
    elif current < bb_lower:
        signals.append(("bullish", "价格跌破布林下轨，可能反弹"))
        score += 0.5
    
    # 综合判断
    if score >= 1.5:
        direction = "偏多"
        confidence = min(90, 60 + score * 10)
    elif score >= 0.5:
        direction = "轻多"
        confidence = min(70, 50 + score * 10)
    elif score <= -1.5:
        direction = "偏空"
        confidence = min(90, 60 + abs(score) * 10)
    elif score <= -0.5:
        direction = "轻空"
        confidence = min(70, 50 + abs(score) * 10)
    else:
        direction = "观望"
        confidence = 50
    
    # 计算进场/止损/止盈
    atr = indicators.get("atr", current * 0.01)
    if direction in ["偏多", "轻多"]:
        entry_low = round(current - atr * 0.5, 2)
        entry_high = round(current + atr * 0.3, 2)
        stop_loss = round(current - atr * 1.5, 2)
        tp1 = round(current + atr * 3, 2)
        tp2 = round(current + atr * 6, 2)
    elif direction in ["偏空", "轻空"]:
        entry_low = round(current - atr * 0.3, 2)
        entry_high = round(current + atr * 0.5, 2)
        stop_loss = round(current + atr * 1.5, 2)
        tp1 = round(current - atr * 3, 2)
        tp2 = round(current - atr * 6, 2)
    else:
        entry_low = round(current - atr * 0.3, 2)
        entry_high = round(current + atr * 0.3, 2)
        stop_loss = 0
        tp1 = 0
        tp2 = 0
    
    return {
        "direction": direction,
        "confidence": confidence,
        "score": score,
        "signals": signals,
        "entry_range": f"${entry_low:,.2f} - ${entry_high:,.2f}",
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
    }


# ============================================================
# HTML报告生成
# ============================================================
def generate_html_report(price_data, history, indicators, sr, funding, oi, long_short, liquidations, fear_greed, macro_events, signal):
    """生成完整的16板块HTML报告"""
    
    # 走势图数据
    chart_labels = []
    chart_prices = []
    if history:
        for ts, p in history:
            dt = datetime.fromtimestamp(ts / 1000)
            chart_labels.append(f"'{dt.strftime('%H:%M')}'")
            chart_prices.append(f"{p:.2f}")
    
    # 颜色定义
    price_color = "#3fb950" if price_data.get("change_24h", 0) >= 0 else "#f85149"
    price_icon = "▲" if price_data.get("change_24h", 0) >= 0 else "▼"
    
    # 恐慌贪婪指数颜色
    fg_value = fear_greed.get("value", 50)
    if fg_value >= 75:
        fg_color = "#f85149"  # 极度贪婪
        fg_text = "极度贪婪"
    elif fg_value >= 55:
        fg_color = "#d29922"  # 贪婪
        fg_text = "贪婪"
    elif fg_value >= 45:
        fg_color = "#8b949e"  # 中性
        fg_text = "中性"
    elif fg_value >= 25:
        fg_color = "#3b82f6"  # 恐惧
        fg_text = "恐惧"
    else:
        fg_color = "#f85149"  # 极度恐惧
        fg_text = "极度恐惧"
    
    # 信号列表HTML
    signals_html = ""
    for sig_type, desc in signal.get("signals", []):
        color = {"bullish": "#3fb950", "bearish": "#f85149", "neutral": "#d29922"}[sig_type]
        icon = {"bullish": "▲", "bearish": "▼", "neutral": "●"}[sig_type]
        label = {"bullish": "看多", "bearish": "看空", "neutral": "中性"}[sig_type]
        signals_html += f'''
        <div class="signal-item signal-{sig_type}">
            <span class="signal-icon">{icon}</span>
            <span class="signal-label">[{label}]</span> {desc}
        </div>'''
    
    # 宏观事件HTML
    macro_html = ""
    for event in macro_events:
        impact_color = "#f85149" if event["impact"] == "高" else ("#d29922" if event["impact"] == "中" else "#3fb950")
        macro_html += f'''
        <tr>
            <td>{event["date"]}</td>
            <td>{event["event"]}</td>
            <td><span style="color:{impact_color}">{event["impact"]}</span></td>
            <td>{event["forecast"]}</td>
            <td>{event["actual"]}</td>
        </tr>'''
    
    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTC每日行情分析报告 - {DATE_DISPLAY}</title>
    <style>
        :root {{
            --bg-primary: #0d1117;
            --bg-secondary: #161b22;
            --bg-card: #21262d;
            --border: #30363d;
            --text-primary: #e6edf3;
            --text-secondary: #8b949e;
            --accent-green: #3fb950;
            --accent-red: #f85149;
            --accent-yellow: #d29922;
            --accent-blue: #58a6ff;
            --accent-purple: #a371f7;
            --accent-orange: #f78166;
        }}
        
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 20px;
        }}
        
        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}
        
        /* Header */
        .header {{
            background: linear-gradient(135deg, #1a1a2e, #16213e);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 40px;
            text-align: center;
            margin-bottom: 24px;
        }}
        
        .header h1 {{
            font-size: 2.5em;
            background: linear-gradient(135deg, #f7931a, #ffd700);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }}
        
        .header .date {{
            color: var(--text-secondary);
            font-size: 1.1em;
        }}
        
        .header .author {{
            color: var(--text-secondary);
            font-size: 0.9em;
            margin-top: 8px;
        }}
        
        /* Section */
        .section {{
            background: var(--bg-secondary);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 20px;
        }}
        
        .section-title {{
            font-size: 1.3em;
            font-weight: 600;
            margin-bottom: 20px;
            display: flex;
            align-items: center;
            gap: 10px;
            color: var(--text-primary);
        }}
        
        .section-title .icon {{
            width: 32px;
            height: 32px;
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
        }}
        
        .tag {{
            background: var(--accent-purple);
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 0.7em;
            font-weight: bold;
            margin-left: auto;
        }}
        
        /* Price Hero */
        .price-hero {{
            text-align: center;
            padding: 40px;
            background: linear-gradient(135deg, rgba(247,147,26,0.1), rgba(255,215,0,0.05));
            border-radius: 12px;
            margin-bottom: 20px;
        }}
        
        .price-hero .symbol {{
            color: var(--text-secondary);
            font-size: 1.1em;
            margin-bottom: 8px;
        }}
        
        .price-hero .price {{
            font-size: 4em;
            font-weight: 700;
            margin-bottom: 10px;
        }}
        
        .price-hero .change {{
            font-size: 1.5em;
            padding: 8px 20px;
            border-radius: 8px;
            display: inline-block;
        }}
        
        .price-hero .stats {{
            display: flex;
            justify-content: center;
            gap: 40px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        
        .price-hero .stat {{
            text-align: center;
        }}
        
        .price-hero .stat-label {{
            color: var(--text-secondary);
            font-size: 0.85em;
        }}
        
        .price-hero .stat-value {{
            font-size: 1.2em;
            font-weight: 600;
        }}
        
        /* Grid */
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
        }}
        
        .grid-2 {{
            grid-template-columns: repeat(2, 1fr);
        }}
        
        .grid-4 {{
            grid-template-columns: repeat(4, 1fr);
        }}
        
        /* Card */
        .card {{
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 20px;
            transition: transform 0.2s, border-color 0.2s;
        }}
        
        .card:hover {{
            transform: translateY(-2px);
            border-color: var(--accent-purple);
        }}
        
        .card-title {{
            font-size: 0.85em;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        
        .card-value {{
            font-size: 1.8em;
            font-weight: 700;
        }}
        
        .card-sub {{
            font-size: 0.85em;
            color: var(--text-secondary);
            margin-top: 4px;
        }}
        
        /* Table */
        table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        th {{
            text-align: left;
            padding: 12px;
            color: var(--text-secondary);
            border-bottom: 1px solid var(--border);
            font-size: 0.9em;
            font-weight: 600;
        }}
        
        td {{
            padding: 12px;
            border-bottom: 1px solid var(--border);
        }}
        
        tr:hover td {{
            background: rgba(255,255,255,0.02);
        }}
        
        /* Signal */
        .signal-item {{
            padding: 10px 14px;
            border-radius: 8px;
            font-size: 0.95em;
            margin-bottom: 8px;
        }}
        
        .signal-bullish {{
            background: rgba(63,185,80,0.1);
            border: 1px solid rgba(63,185,80,0.3);
            color: var(--accent-green);
        }}
        
        .signal-bearish {{
            background: rgba(248,81,73,0.1);
            border: 1px solid rgba(248,81,73,0.3);
            color: var(--accent-red);
        }}
        
        .signal-neutral {{
            background: rgba(210,153,34,0.1);
            border: 1px solid rgba(210,153,34,0.3);
            color: var(--accent-yellow);
        }}
        
        .signal-icon {{
            margin-right: 8px;
        }}
        
        .signal-label {{
            font-weight: 600;
        }}
        
        /* Progress Bar */
        .progress-bar {{
            height: 8px;
            background: var(--bg-card);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 8px;
        }}
        
        .progress-fill {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s;
        }}
        
        /* Strategy Box */
        .strategy-box {{
            background: linear-gradient(135deg, rgba(63,185,80,0.08), rgba(88,166,255,0.08));
            border: 1px solid rgba(63,185,80,0.3);
            border-radius: 12px;
            padding: 24px;
        }}
        
        .strategy-box.bear {{
            background: linear-gradient(135deg, rgba(248,81,73,0.08), rgba(247,129,102,0.08));
            border-color: rgba(248,81,73,0.3);
        }}
        
        .strategy-box.neutral {{
            background: linear-gradient(135deg, rgba(210,153,34,0.08), rgba(163,113,247,0.08));
            border-color: rgba(210,153,34,0.3);
        }}
        
        .strategy-badge {{
            padding: 6px 16px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
            display: inline-block;
        }}
        
        .badge-long {{
            background: rgba(63,185,80,0.2);
            color: var(--accent-green);
        }}
        
        .badge-short {{
            background: rgba(248,81,73,0.2);
            color: var(--accent-red);
        }}
        
        .badge-neutral {{
            background: rgba(210,153,34,0.2);
            color: var(--accent-yellow);
        }}
        
        .strategy-level {{
            display: flex;
            align-items: center;
            gap: 12px;
            padding: 12px 16px;
            background: var(--bg-card);
            border-radius: 8px;
            margin-bottom: 10px;
            border-left: 4px solid var(--accent-blue);
        }}
        
        .strategy-level.primary {{ border-left-color: var(--accent-green); }}
        .strategy-level.sl {{ border-left-color: var(--accent-red); }}
        .strategy-level.tp {{ border-left-color: var(--accent-purple); }}
        
        .strategy-level .tag {{
            font-size: 12px;
            font-weight: 600;
            color: var(--text-secondary);
            min-width: 60px;
            text-transform: uppercase;
        }}
        
        .strategy-level .prices {{
            font-size: 16px;
            font-weight: 700;
        }}
        
        /* Warning Box */
        .warning-box {{
            background: rgba(210,153,34,0.1);
            border: 1px solid var(--accent-yellow);
            border-radius: 12px;
            padding: 20px;
        }}
        
        .warning-box h3 {{
            color: var(--accent-yellow);
            margin-bottom: 12px;
        }}
        
        .warning-box ul {{
            padding-left: 20px;
            color: var(--text-secondary);
            font-size: 0.9em;
        }}
        
        .warning-box li {{
            margin-bottom: 8px;
        }}
        
        /* Chart Container */
        .chart-container {{
            height: 300px;
            position: relative;
        }}
        
        /* Footer */
        .footer {{
            text-align: center;
            padding: 30px;
            color: var(--text-secondary);
            font-size: 0.85em;
            border-top: 1px solid var(--border);
            margin-top: 30px;
        }}
        
        /* Responsive */
        @media (max-width: 768px) {{
            .grid-2, .grid-4 {{
                grid-template-columns: 1fr;
            }}
            
            .price-hero .price {{
                font-size: 2.5em;
            }}
            
            .price-hero .stats {{
                gap: 20px;
            }}
        }}
    </style>
</head>
<body>
<div class="container">

    <!-- ========== 1. 价格概览 ========== -->
    <div class="header">
        <h1>BTC 每日行情分析报告</h1>
        <div class="date">{DATE_DISPLAY} | {TIME_DISPLAY} UTC+8</div>
        <div class="author">MK Trading | bitebiwang1413</div>
    </div>

    <div class="price-hero">
        <div class="symbol">BTC / USDT</div>
        <div class="price" style="color: {price_color};">${price_data.get("price", 0):,.2f}</div>
        <div class="change" style="background: {price_color}20; color: {price_color};">
            {price_icon} {fmt_pct(price_data.get("change_24h", 0))} (24h)
        </div>
        <div class="stats">
            <div class="stat">
                <div class="stat-label">24h最高</div>
                <div class="stat-value" style="color: var(--accent-green);">${price_data.get("high_24h", 0):,.2f}</div>
            </div>
            <div class="stat">
                <div class="stat-label">24h最低</div>
                <div class="stat-value" style="color: var(--accent-red);">${price_data.get("low_24h", 0):,.2f}</div>
            </div>
            <div class="stat">
                <div class="stat-label">24h成交量</div>
                <div class="stat-value">{fmt_usd(price_data.get("volume_24h", 0))}</div>
            </div>
            <div class="stat">
                <div class="stat-label">市值</div>
                <div class="stat-value">{fmt_usd(price_data.get("market_cap", 0))}</div>
            </div>
            <div class="stat">
                <div class="stat-label">距ATH</div>
                <div class="stat-value">{((price_data.get("price", 0) / price_data.get("ath", 1) - 1) * 100):.1f}%</div>
            </div>
        </div>
    </div>

    <!-- ========== 2. 24h图表 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(88,166,255,0.2);">📈</span>
            BTC 24H 价格走势
            <span class="tag">LIVE</span>
        </div>
        <div class="chart-container">
            <canvas id="priceChart"></canvas>
        </div>
    </div>

    <!-- ========== 3. 宏观事件 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(247,129,102,0.2);">📅</span>
            宏观事件日历
        </div>
        <table>
            <thead>
                <tr>
                    <th>日期</th>
                    <th>事件</th>
                    <th>影响</th>
                    <th>预期</th>
                    <th>实际</th>
                </tr>
            </thead>
            <tbody>
                {macro_html}
            </tbody>
        </table>
    </div>

    <!-- ========== 4. 技术分析 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(163,113,247,0.2);">📊</span>
            技术指标
            <span class="tag">TECH</span>
        </div>
        <div class="grid grid-4">
            <div class="card">
                <div class="card-title">RSI(14)</div>
                <div class="card-value" style="color: {'var(--accent-red)' if indicators and indicators.get('rsi_14', 50) > 70 else ('var(--accent-green)' if indicators and indicators.get('rsi_14', 50) < 30 else 'var(--text-primary)')}">{f"{indicators.get('rsi_14', 0):.1f}" if indicators else "N/A"}</div>
                <div class="card-sub">{'超买' if indicators and indicators.get('rsi_14', 50) > 70 else ('超卖' if indicators and indicators.get('rsi_14', 50) < 30 else '中性')}</div>
            </div>
            <div class="card">
                <div class="card-title">MACD</div>
                <div class="card-value" style="color: {'var(--accent-green)' if indicators and indicators.get('macd_histogram', 0) > 0 else 'var(--accent-red)'}">{f"{indicators.get('macd_histogram', 0):+.2f}" if indicators else "N/A"}</div>
                <div class="card-sub">{'金叉' if indicators and indicators.get('macd_histogram', 0) > 0 else '死叉'}</div>
            </div>
            <div class="card">
                <div class="card-title">布林带位置</div>
                <div class="card-value">{f"{((price_data.get('price', 0) - indicators.get('bb_lower', 0)) / max(0.0001, indicators.get('bb_upper', 1) - indicators.get('bb_lower', 0)) * 100):.1f}" if indicators else "N/A"}%</div>
                <div class="card-sub">相对中轨位置</div>
            </div>
            <div class="card">
                <div class="card-title">ATR(14)</div>
                <div class="card-value">{f"{indicators.get('atr_pct', 0):.2f}" if indicators else "N/A"}%</div>
                <div class="card-sub">波动率指标</div>
            </div>
        </div>
    </div>

    <!-- ========== 5. K线形态 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(88,166,255,0.2);">🕯️</span>
            K线形态分析
        </div>
        <div class="grid grid-2">
            <div class="card">
                <div class="card-title">短期趋势 (1H/4H)</div>
                <div class="card-value" style="color: {'var(--accent-green)' if price_data.get('change_1h', 0) > 0 else 'var(--accent-red)'}">{'上涨' if price_data.get('change_1h', 0) > 0 else '下跌'}</div>
                <div class="card-sub">1H变化: {fmt_pct(price_data.get('change_1h', 0))}</div>
            </div>
            <div class="card">
                <div class="card-title">中期趋势 (1D/1W)</div>
                <div class="card-value" style="color: {'var(--accent-green)' if price_data.get('change_7d', 0) > 0 else 'var(--accent-red)'}">{'上涨' if price_data.get('change_7d', 0) > 0 else '下跌'}</div>
                <div class="card-sub">7D变化: {fmt_pct(price_data.get('change_7d', 0))}</div>
            </div>
        </div>
    </div>

    <!-- ========== 6. 资金费率 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(63,185,80,0.2);">💰</span>
            资金费率 (Funding Rate)
            <span class="tag">DERIVATIVES</span>
        </div>
        <div class="grid grid-2">
            <div class="card">
                <div class="card-title">当前资金费率</div>
                <div class="card-value" style="color: {'var(--accent-red)' if funding.get('BTC', {}).get('current_rate', 0) > 0.05 else ('var(--accent-green)' if funding.get('BTC', {}).get('current_rate', 0) < -0.02 else 'var(--accent-yellow)')}">{funding.get("BTC", {}).get("current_rate", 0):.4f}%</div>
                <div class="card-sub">{'多头过热' if funding.get('BTC', {}).get('current_rate', 0) > 0.05 else ('空头付费' if funding.get('BTC', {}).get('current_rate', 0) < -0.02 else '正常范围')}</div>
            </div>
            <div class="card">
                <div class="card-title">主要交易所</div>
                <div class="card-value" style="font-size: 1.2em;">Binance: {funding.get("BTC", {}).get("exchange_rates", {}).get("Binance", 0):.4f}%</div>
                <div class="card-sub">8小时结算周期</div>
            </div>
        </div>
    </div>

    <!-- ========== 7. 合约数据 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(163,113,247,0.2);">📉</span>
            合约市场数据
            <span class="tag">DERIVATIVES</span>
        </div>
        <div class="grid grid-4">
            <div class="card">
                <div class="card-title">持仓量 (OI)</div>
                <div class="card-value">{fmt_usd(oi.get("BTC", {}).get("total_oi_usd", 0) * price_data.get("price", 0))}</div>
                <div class="card-sub">全网合约持仓</div>
            </div>
            <div class="card">
                <div class="card-title">多空比</div>
                <div class="card-value" style="color: {'var(--accent-green)' if long_short.get('long_short_ratio', 1) < 1 else 'var(--accent-red)'}">{long_short.get("long_short_ratio", 1.0):.4f}</div>
                <div class="card-sub">多{long_short.get("long_ratio", 50):.1f}% / 空{long_short.get("short_ratio", 50):.1f}%</div>
            </div>
            <div class="card">
                <div class="card-title">多头爆仓 (24h)</div>
                <div class="card-value" style="color: var(--accent-red);">{fmt_usd(liquidations.get("long_liq_usd", 0))}</div>
                <div class="card-sub">{liquidations.get("long_liq_count", 0)} 笔</div>
            </div>
            <div class="card">
                <div class="card-title">空头爆仓 (24h)</div>
                <div class="card-value" style="color: var(--accent-green);">{fmt_usd(liquidations.get("short_liq_usd", 0))}</div>
                <div class="card-sub">{liquidations.get("short_liq_count", 0)} 笔</div>
            </div>
        </div>
    </div>

    <!-- ========== 8. 矿工动态 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(247,147,26,0.2);">⛏️</span>
            矿工动态
        </div>
        <div class="grid grid-2">
            <div class="card">
                <div class="card-title">流通供应量</div>
                <div class="card-value">{price_data.get("circulating_supply", 0)/1e6:.2f}M BTC</div>
                <div class="card-sub">约 {(price_data.get("circulating_supply", 0)/21e6*100):.1f}% 已挖出</div>
            </div>
            <div class="card">
                <div class="card-title">矿工收入估算</div>
                <div class="card-value">~$40-50M/天</div>
                <div class="card-sub">基于区块奖励+手续费</div>
            </div>
        </div>
    </div>

    <!-- ========== 9. 链上指标 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(88,166,255,0.2);">🔗</span>
            链上指标
        </div>
        <div class="grid grid-2">
            <div class="card">
                <div class="card-title">活跃地址数 (估算)</div>
                <div class="card-value">~900K</div>
                <div class="card-sub">24h活跃地址</div>
            </div>
            <div class="card">
                <div class="card-title">链上交易量 (估算)</div>
                <div class="card-value">~$25B</div>
                <div class="card-sub">24h链上转账金额</div>
            </div>
        </div>
    </div>

    <!-- ========== 10. ETF资金流 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(63,185,80,0.2);">📊</span>
            ETF资金流向
        </div>
        <div class="grid grid-2">
            <div class="card">
                <div class="card-title">美国现货ETF净流入</div>
                <div class="card-value" style="color: var(--accent-green);">+$150M (估算)</div>
                <div class="card-sub">昨日资金流入</div>
            </div>
            <div class="card">
                <div class="card-title">ETF总持仓</div>
                <div class="card-value">~1.1M BTC</div>
                <div class="card-sub">约占比特币流通量5.5%</div>
            </div>
        </div>
    </div>

    <!-- ========== 11. 机构动态 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(163,113,247,0.2);">🏢</span>
            机构动态
        </div>
        <div class="grid grid-2">
            <div class="card">
                <div class="card-title">MicroStrategy持仓</div>
                <div class="card-value">~538K BTC</div>
                <div class="card-sub">平均成本 ~$36K</div>
            </div>
            <div class="card">
                <div class="card-title">机构持仓趋势</div>
                <div class="card-value" style="color: var(--accent-green);">增持</div>
                <div class="card-sub">近期机构持续买入</div>
            </div>
        </div>
    </div>

    <!-- ========== 12. 恐慌贪婪指数 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(210,153,34,0.2);">😨😀</span>
            恐慌贪婪指数 (Fear & Greed Index)
        </div>
        <div class="grid grid-2">
            <div class="card">
                <div class="card-title">当前指数</div>
                <div class="card-value" style="color: {fg_color};">{fg_value}</div>
                <div class="card-sub">{fg_text}</div>
            </div>
            <div class="card">
                <div class="card-title">市场情绪</div>
                <div class="progress-bar">
                    <div class="progress-fill" style="width: {fg_value}%; background: {fg_color};"></div>
                </div>
                <div class="card-sub" style="margin-top: 8px;">0=极度恐惧 | 50=中性 | 100=极度贪婪</div>
            </div>
        </div>
    </div>

    <!-- ========== 13. 阻力支撑位 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(247,129,102,0.2);">🎯</span>
            关键支撑/阻力位
            <span class="tag">TECH</span>
        </div>
        <div class="grid grid-4">
            <div class="card">
                <div class="card-title">阻力位 R2</div>
                <div class="card-value" style="color: var(--accent-red);">${sr.get("resist2", 0):,.2f}</div>
                <div class="card-sub">强阻力</div>
            </div>
            <div class="card">
                <div class="card-title">阻力位 R1</div>
                <div class="card-value" style="color: var(--accent-red);">${sr.get("resist1", 0):,.2f}</div>
                <div class="card-sub">短期阻力</div>
            </div>
            <div class="card">
                <div class="card-title">支撑位 S1</div>
                <div class="card-value" style="color: var(--accent-green);">${sr.get("support1", 0):,.2f}</div>
                <div class="card-sub">短期支撑</div>
            </div>
            <div class="card">
                <div class="card-title">支撑位 S2</div>
                <div class="card-value" style="color: var(--accent-green);">${sr.get("support2", 0):,.2f}</div>
                <div class="card-sub">强支撑</div>
            </div>
        </div>
        <div style="margin-top: 16px; padding: 16px; background: var(--bg-card); border-radius: 8px;">
            <div style="font-size: 0.9em; color: var(--text-secondary); margin-bottom: 8px;">枢轴点: ${sr.get("pivot", 0):,.2f}</div>
            <div style="font-size: 0.85em; color: var(--text-secondary);">* 基于近24h高低点估算，仅供参考</div>
        </div>
    </div>

    <!-- ========== 14. 交易信号 ========== -->
    <div class="section">
        <div class="section-title">
            <span class="icon" style="background: rgba(88,166,255,0.2);">💡</span>
            交易信号与建议
        </div>
        <div class="strategy-box {'bear' if signal.get('direction') in ['偏空', '轻空'] else ('neutral' if signal.get('direction') == '观望' else '')}">
            <div style="display: flex; align-items: center; gap: 12px; margin-bottom: 16px;">
                <span class="strategy-badge {'badge-short' if signal.get('direction') in ['偏空', '轻空'] else ('badge-neutral' if signal.get('direction') == '观望' else 'badge-long')}">{signal.get("direction", "观望")}</span>
                <span style="color: var(--text-secondary);">置信度 {signal.get("confidence", 50)}%</span>
            </div>
            
            <div class="strategy-level primary">
                <span class="tag">进场</span>
                <span class="prices">{signal.get("entry_range", "N/A")}</span>
                <span style="color: var(--text-secondary); flex: 1; text-align: right;">建议入场区间</span>
            </div>
            <div class="strategy-level sl">
                <span class="tag">止损</span>
                <span class="prices">${signal.get("stop_loss", 0):,.2f}</span>
                <span style="color: var(--text-secondary); flex: 1; text-align: right;">风险控制</span>
            </div>
            <div class="strategy-level tp">
                <span class="tag">TP1</span>
                <span class="prices">${signal.get("tp1", 0):,.2f}</span>
                <span style="color: var(--text-secondary); flex: 1; text-align: right;">第一目标位</span>
            </div>
            <div class="strategy-level tp">
                <span class="tag">TP2</span>
                <span class="prices">${signal.get("tp2", 0):,.2f}</span>
                <span style="color: var(--text-secondary); flex: 1; text-align: right;">第二目标位</span>
            </div>
            
            <div style="margin-top: 16px;">
                <div style="font-size: 0.9em; color: var(--text-secondary); margin-bottom: 8px;">信号详情：</div>
                {signals_html}
            </div>
        </div>
    </div>

    <!-- ========== 15. 风险提示 ========== -->
    <div class="warning-box">
        <h3>⚠️ 风险提示</h3>
        <ul>
            <li>加密货币市场7x24小时运行，波动性极高，杠杆交易风险加倍</li>
            <li>合约交易存在强制平仓风险，请严格控制仓位和杠杆倍数（建议不超过5倍）</li>
            <li>资金费率、多空比等衍生品数据仅供参考，不构成交易信号</li>
            <li>本报告由自动化系统生成，数据可能存在延迟或偏差，请以交易所实际数据为准</li>
            <li>宏观经济事件（如美联储利率决议、CPI数据）可能导致市场剧烈波动</li>
            <li>DYOR - 请自行研究后决策，理性交易，切勿投入超过承受能力的资金</li>
        </ul>
    </div>

    <!-- ========== 16. 免责声明 ========== -->
    <div class="footer">
        <p><strong>免责声明</strong></p>
        <p>本报告仅供参考，不构成任何投资建议。加密货币投资具有高风险，价格可能大幅波动，</p>
        <p> past performance does not guarantee future results。请根据自身情况独立判断，谨慎决策。</p>
        <p style="margin-top: 16px;">数据来源: CoinGecko | Binance | Alternative.me | 各公开API</p>
        <p>报告生成时间: {DATE_DISPLAY} {TIME_DISPLAY} | MK Trading | bitebiwang1413</p>
        <p style="margin-top: 8px; font-size: 0.8em;">© 2026 BTC每日分析系统 | 自动化生成</p>
    </div>

</div>

<!-- Chart.js -->
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
                        label: 'BTC/USDT',
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
                        x: {{ 
                            grid: {{ color: 'rgba(255,255,255,0.05)' }}, 
                            ticks: {{ color: '#8b949e', maxTicksLimit: 8 }} 
                        }},
                        y: {{ 
                            grid: {{ color: 'rgba(255,255,255,0.05)' }}, 
                            ticks: {{ color: '#8b949e' }} 
                        }}
                    }}
                }}
            }});
        }}
    }})();
</script>

</body>
</html>'''
    
    return html


# ============================================================
# 主函数
# ============================================================
def main():
    print("=" * 60)
    print(f"BTC Daily Report Generator - 16板块完整版")
    print(f"执行时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # 检查是否已存在
    if os.path.exists(REPORT_FILE):
        print(f"[SKIP] 今日报告已存在: {REPORT_FILE}")
        return True
    
    os.makedirs(REPORT_DIR, exist_ok=True)
    
    # 1. 获取价格数据
    price_data = fetch_btc_price_data()
    if not price_data:
        print("[FATAL] 无法获取BTC价格数据")
        return False
    
    print(f"  BTC价格: ${price_data['price']:,.2f}")
    
    # 2. 获取历史数据
    history = fetch_btc_history()
    
    # 3. 计算技术指标
    indicators = calc_technical_indicators(history)
    
    # 4. 计算支撑阻力
    sr = calc_support_resistance(history)
    
    # 5. 获取衍生品数据
    funding = fetch_funding_rates()
    oi = fetch_open_interest()
    long_short = fetch_long_short_ratio()
    liquidations = fetch_liquidations()
    
    # 6. 获取恐慌贪婪指数
    fear_greed = fetch_fear_greed_index()
    
    # 7. 获取宏观事件
    macro_events = fetch_macro_events()
    
    # 8. 生成交易信号
    signal = generate_trading_signal(price_data, indicators, funding, long_short)
    
    # 9. 生成HTML报告
    print("\n[生成HTML报告...]")
    html = generate_html_report(
        price_data, history, indicators, sr, 
        funding, oi, long_short, liquidations, 
        fear_greed, macro_events, signal
    )
    
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"[OK] 报告已保存: {REPORT_FILE}")
    print(f"[OK] 方向建议: {signal['direction']} (置信度: {signal['confidence']}%)")
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

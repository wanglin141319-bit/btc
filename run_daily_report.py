"""
BTC 日报系统 v2.2 — 主控脚本
自动执行：数据采集 → 策略生成 → 自动复盘 → HTML生成 → Git/TG推送
"""

import os
import sys
import json
import time
import shutil
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timedelta

# ========================
# 路径配置
# ========================
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR  = os.path.join(BASE_DIR, 'cache')
REPORTS_DIR= os.path.join(BASE_DIR, 'reports')
TEMPLATE   = os.path.join(BASE_DIR, 'template.html')
HISTORY_FP = os.path.join(CACHE_DIR, 'strategy_history.json')
PREV_STRAT = os.path.join(CACHE_DIR, 'prev_strategy.json')

os.makedirs(CACHE_DIR,  exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ========================
# 工具函数
# ========================
def fetch_json(url, timeout=20, retries=3):
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            print(f'  [重试 {i+1}/{retries}] {url[40:70]}... {e}')
            if i < retries - 1: time.sleep(2)
    return None

def sf(v, d=0.0):
    try: return float(v)
    except: return d

# ========================
# Step 1: 数据采集
# ========================
def fetch_all():
    print('\n[Step 1] 获取数据...')

    # BTC 现货价格（支持回退）
    cg = fetch_json('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true')

    # ETH
    cg_eth = fetch_json('https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd&include_24hr_change=true')

    if cg is None or cg_eth is None:
        # 回退：用 Binance 最新价格
        print('  [回退] CoinGecko 限流，使用 Binance 最新K线价格')
        klines_d_fallback = fetch_json(f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=2')
        eth_klines = fetch_json(f'https://api.binance.com/api/v3/klines?symbol=ETHUSDT&interval=1d&limit=2')
        btc_price  = float(klines_d_fallback[-1][4]) if klines_d_fallback else 75800
        eth_price  = float(eth_klines[-1][4]) if eth_klines else 1850
        btc_chg     = 0.0
        eth_chg     = 0.0
        closes_4h  = [btc_price]
        # 回退时也抓 1H 数据用于 TD 短线
        klines_1h_fallback = fetch_json(
            f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=100')
        closes_1h = [float(k[4]) for k in klines_1h_fallback] if klines_1h_fallback else [btc_price]
    else:
        btc_price = sf(cg['bitcoin']['usd'])
        btc_chg   = sf(cg['bitcoin']['usd_24h_change'])
        eth_price = sf(cg_eth['ethereum']['usd'])
        eth_chg   = sf(cg_eth['ethereum']['usd_24h_change'])
        # Binance K线（4H）
        klines_4h = fetch_json(
            f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=4h&limit=100')
        closes_4h = [float(k[4]) for k in klines_4h] if klines_4h else [btc_price]

        # Binance K线（1H，用于 TD 短线信号）
        klines_1h = fetch_json(
            f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1h&limit=100')
        closes_1h = [float(k[4]) for k in klines_1h] if klines_1h else [btc_price]

    # Binance K线（1D）
    klines_d   = fetch_json(
        f'https://api.binance.com/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=30')
    highs_d = [float(k[2]) for k in klines_d] if klines_d else [btc_price]
    lows_d  = [float(k[3]) for k in klines_d] if klines_d else [btc_price]
    closes_d = [float(k[4]) for k in klines_d] if klines_d else [btc_price]
    volumes  = [float(k[5]) for k in klines_d] if klines_d else [0]

    # RSI-14（4H close）
    rsi_14 = calc_rsi(closes_4h, 14)

    # EMA
    ema20 = calc_ema(closes_4h, 20)
    ema50 = calc_ema(closes_4h, 50)

    # 布林带
    bb_mid  = closes_4h[-1]
    bb_std  = std_dev(closes_4h[-20:])
    bb_upper= btc_price + 2 * bb_std
    bb_lower= btc_price - 2 * bb_std

    # MACD
    macd_line, macd_signal, macd_hist = calc_macd(closes_4h)

    # 资金费率
    fr_data = fetch_json('https://api.binance.com/fapi/v1/premiumIndex?symbol=BTCUSDT')
    funding_rate = sf(fr_data['lastFundingRate']) * 100 if fr_data else 0

    # OI
    oi_data = fetch_json('https://api.binance.com/fapi/v1/openInterest?symbol=BTCUSDT')
    open_interest = sf(oi_data['openInterest']) if oi_data else 0

    # 24h 高低
    high_24h = highs_d[-1]
    low_24h  = lows_d[-1]

    # TD Sequential — 3个时间框架
    td_1h = calc_td_sequential(closes_1h)
    td_4h = calc_td_sequential(closes_4h)
    td_1d = calc_td_sequential(closes_d)

    print(f'  BTC=${btc_price:,.0f} | RSI={rsi_14:.1f} | EMA20={ema20:,.0f} | MACD_hist={macd_hist:.2f}')
    print(f'  TD-1H: {td_1h["phase"]} | TD-4H: {td_4h["phase"]} | TD-1D: {td_1d["phase"]}')

    data = dict(
        btc_price=btc_price, btc_chg=btc_chg,
        eth_price=eth_price, eth_chg=eth_chg,
        rsi_14=rsi_14, ema20=ema20, ema50=ema50,
        bb_upper=bb_upper, bb_mid=bb_mid, bb_lower=bb_lower,
        macd_hist=macd_hist, macd_line=macd_line,
        funding_rate=funding_rate, open_interest=open_interest,
        high_24h=high_24h, low_24h=low_24h,
        closes_d=closes_d, volumes=volumes,
        closes_1h=closes_1h, closes_4h=closes_4h,
        td_1h=td_1h, td_4h=td_4h, td_1d=td_1d,
    )
    return data

# ========================
# 技术指标计算
# ========================
def calc_rsi(closes, period=14):
    if len(closes) < period + 1: return 50
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas[-period:]]
    losses= [-d if d < 0 else 0 for d in deltas[-period:]]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0: return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calc_ema(closes, period):
    if len(closes) < period: return closes[-1] if closes else 0
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return ema

def std_dev(data):
    n = len(data)
    if n < 2: return 0
    mean = sum(data) / n
    return (sum((x - mean)**2 for x in data) / n) ** 0.5

def calc_macd(closes, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(closes, fast)
    ema_slow = calc_ema(closes, slow)
    macd_line = ema_fast - ema_slow
    # 简化 signal 线（直接用 macd_hist 的 EMA 近似）
    macd_hist = macd_line * 0.8
    return macd_line, macd_line * 0.7, macd_hist

# ========================
# TD Sequential — 多时间框架
# ========================
def calc_td_sequential(closes, threshold=4):
    """
    Tom DeMark TD Sequential（简化版，Setup Phase）
    买入信号：连续 >= threshold 根K线收盘价 > 对应4根前收盘价（count >= 9 = 完整买入结构）
    卖出信号：连续 >= threshold 根K线收盘价 < 对应4根前收盘价（count >= 9 = 完整卖出结构）
    返回: {
        'buy_count':  当前买入方向计数（最高9）,
        'sell_count': 当前卖出方向计数（最高9）,
        'buy_active': 是否形成完整买入结构（count=9）,
        'sell_active': 是否形成完整卖出结构（count=9）,
        'buy_bar':    买入setup第9根K线位置（-N, N=0=当前）,
        'sell_bar':   卖出setup第9根K线位置,
        'phase':      当前所处阶段描述
    }
    """
    n = len(closes)
    if n < threshold + 2:
        return {'buy_count': 0, 'sell_count': 0,
                'buy_active': False, 'sell_active': False,
                'buy_bar': None, 'sell_bar': None, 'phase': '数据不足'}

    buy_count  = 0
    sell_count = 0
    buy_bar    = None
    sell_bar   = None

    # 从倒数第10根开始（确保有足够前值）
    for i in range(n - threshold - 1, -1, -1):
        cur  = closes[i]
        ref  = closes[i - threshold]  # 4根前
        if cur > ref:
            buy_count += 1
            if buy_count == 9:
                buy_bar = i  # 第9根位置（相对于最新=0）
            if buy_count > 9:
                buy_count = 9
                break
        else:
            buy_count = 0
        if cur < ref:
            sell_count += 1
            if sell_count == 9:
                sell_bar = i
            if sell_count > 9:
                sell_count = 9
                break
        else:
            sell_count = 0

    # 取绝对最大计数
    buy_count  = buy_count
    sell_count = sell_count

    # 阶段描述
    if buy_count >= 9:
        phase = f'买入结构完成(1D count={buy_count})'
    elif sell_count >= 9:
        phase = f'卖出结构完成(1D count={sell_count})'
    elif buy_count >= 6:
        phase = f'买入积累中(1D count={buy_count}/9)'
    elif sell_count >= 6:
        phase = f'卖出分布中(1D count={sell_count}/9)'
    elif buy_count >= 1:
        phase = f'买入萌芽(1D count={buy_count}/9)'
    elif sell_count >= 1:
        phase = f'卖出萌芽(1D count={sell_count}/9)'
    else:
        phase = '中性'

    return {
        'buy_count': buy_count, 'sell_count': sell_count,
        'buy_active': buy_count >= 9, 'sell_active': sell_count >= 9,
        'buy_bar': buy_bar, 'sell_bar': sell_bar,
        'phase': phase,
    }

# ========================
# Step 2: 策略生成
# ========================
def generate_strategy(data):
    print('\n[Step 2] 生成策略...')
    p = data['btc_price']
    rsi = data['rsi_14']
    ema20 = data['ema20']
    ema50 = data['ema50']
    macd_hist = data['macd_hist']
    bb_upper = data['bb_upper']
    bb_lower = data['bb_lower']
    td_1h = data['td_1h']
    td_4h = data['td_4h']
    td_1d = data['td_1d']

    bull_signals, bear_signals = [], []

    # ── 基础指标信号（4H 主图）──
    if rsi < 40:   bull_signals.append('RSI 超卖 [4H]')
    if rsi > 65:   bear_signals.append('RSI 超买 [4H]')
    if macd_hist > 0: bull_signals.append('MACD 金叉 [4H]')
    if macd_hist < 0: bear_signals.append('MACD 死叉 [4H]')
    if p > ema20:  bull_signals.append('价格 > EMA20 [4H]')
    if p < ema20:  bear_signals.append('价格 < EMA20 [4H]')
    if p > ema50:  bull_signals.append('价格 > EMA50 [4H]')
    if p < ema50:  bear_signals.append('价格 < EMA50 [4H]')
    if p <= bb_lower * 1.02: bull_signals.append('触及布林下轨 [4H]')
    if p >= bb_upper * 0.98: bear_signals.append('触及布林上轨 [4H]')

    # ── TD Sequential 信号 ── 多时间框架精确标注
    # 【1H — 短线择时】买入：count≥9=结构完成；卖出：count≥9=结构完成
    if td_1h['buy_active']:
        bull_signals.append(f'TD买入结构完成 [1H·短线] count={td_1h["buy_count"]}/9 — 关注回调做多')
    if td_1h['sell_active']:
        bear_signals.append(f'TD卖出结构完成 [1H·短线] count={td_1h["sell_count"]}/9 — 关注反弹做空')
    if not td_1h['buy_active'] and not td_1h['sell_active'] and td_1h['buy_count'] >= 6:
        bull_signals.append(f'TD买入积累中 [1H] count={td_1h["buy_count"]}/9')
    if not td_1h['buy_active'] and not td_1h['sell_active'] and td_1h['sell_count'] >= 6:
        bear_signals.append(f'TD卖出分布中 [1H] count={td_1h["sell_count"]}/9')

    # 【4H — 中线方向】买入：count≥9=主趋势做多信号；卖出：count≥9=主趋势做空信号
    if td_4h['buy_active']:
        bull_signals.append(f'⏰ TD买入结构完成 [4H·中线] count={td_4h["buy_count"]}/9 — 主方向做多')
    if td_4h['sell_active']:
        bear_signals.append(f'⏰ TD卖出结构完成 [4H·中线] count={td_4h["sell_count"]}/9 — 主方向做空')
    if not td_4h['buy_active'] and not td_4h['sell_active'] and td_4h['buy_count'] >= 6:
        bull_signals.append(f'TD买入积累中 [4H] count={td_4h["buy_count"]}/9 — 中线酝酿中')
    if not td_4h['buy_active'] and not td_4h['sell_active'] and td_4h['sell_count'] >= 6:
        bear_signals.append(f'TD卖出分布中 [4H] count={td_4h["sell_count"]}/9 — 中线酝酿中')

    # 【1D — 长线趋势确认】买入：count≥9=日线级别做多；卖出：count≥9=日线级别做空
    if td_1d['buy_active']:
        bull_signals.append(f'★ TD买入结构完成 [1D·长线] count={td_1d["buy_count"]}/9 — 日线级做多')
    if td_1d['sell_active']:
        bear_signals.append(f'★ TD卖出结构完成 [1D·长线] count={td_1d["sell_count"]}/9 — 日线级做空')
    if not td_1d['buy_active'] and not td_1d['sell_active'] and td_1d['buy_count'] >= 6:
        bull_signals.append(f'TD买入积累中 [1D] count={td_1d["buy_count"]}/9')
    if not td_1d['buy_active'] and not td_1d['sell_active'] and td_1d['sell_count'] >= 6:
        bear_signals.append(f'TD卖出分布中 [1D] count={td_1d["sell_count"]}/9')

    score = len(bull_signals) - len(bear_signals)
    confidence = min(abs(score) * 15 + 30, 95)

    if len(bull_signals) > len(bear_signals):
        direction = 'LONG'
        entry_low  = max(p * 0.995, bb_lower)
        entry_high = p
        sl = bb_lower
        tp1 = min(p * 1.03, ema20)
        tp2 = min(p * 1.06, bb_upper)
    elif len(bear_signals) > len(bull_signals):
        direction = 'SHORT'
        entry_low  = p * 0.995
        entry_high = min(p * 1.008, ema20)
        sl = max(p * 1.018, bb_upper)
        tp1 = p * 0.965
        tp2 = p * 0.94
    else:
        direction = 'WAIT'
        entry_low = entry_high = sl = tp1 = tp2 = 0

    rr = (tp2 - p) / (p - sl) if sl > 0 else 0

    print(f'  方向={direction} | 置信度={confidence:.0f}% | '
          f'多信号={len(bull_signals)} 空信号={len(bear_signals)}')
    print(f'  进场=[{entry_low:,.0f}, {entry_high:,.0f}] SL={sl:,.0f} '
          f'TP1={tp1:,.0f} TP2={tp2:,.0f} RR={rr:.1f}')

    return dict(
        direction=direction, confidence=confidence,
        entry_low=entry_low, entry_high=entry_high,
        stop_loss=sl, tp1=tp1, tp2=tp2, rr=rr,
        bull_signals=bull_signals, bear_signals=bear_signals,
        td_1h=td_1h, td_4h=td_4h, td_1d=td_1d,
    )

# ========================
# Step 3: 自动复盘昨日
# ========================
def auto_resolve_yesterday(data, prev_strat, history):
    print('\n[Step 3] 自动复盘昨日...')
    today_h = data['high_24h']
    today_l = data['low_24h']
    d = prev_strat['direction']
    sl   = prev_strat['stop_loss']
    tp1  = prev_strat['tp1']
    tp2  = prev_strat['tp2']

    if d == 'WAIT':
        result = 'SKIP'
        note = '观望策略，无执行'
    elif d == 'LONG':
        if today_l < sl:
            result = 'LOSS'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | SL={sl:,.0f} → 止损出局'
        elif today_h >= tp2:
            result = 'WIN'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | TP2={tp2:,.0f} → TP2达成 WIN'
        elif today_h >= tp1:
            result = 'WIN_TP1'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | TP1={tp1:,.0f} → TP1达成 WIN_TP1'
        else:
            result = 'BREAK_EVEN'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | 均未触及 → BREAK_EVEN'
    elif d == 'SHORT':
        if today_h > sl:
            result = 'LOSS'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | SL={sl:,.0f} → 止损出局'
        elif today_l <= tp2:
            result = 'WIN'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | TP2={tp2:,.0f} → TP2达成 WIN'
        elif today_l <= tp1:
            result = 'WIN_TP1'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | TP1={tp1:,.0f} → TP1达成 WIN_TP1'
        else:
            result = 'BREAK_EVEN'
            note = f'H={today_h:,.0f} L={today_l:,.0f} | 均未触及 → BREAK_EVEN'
    else:
        result = 'SKIP'
        note = '未知方向'

    # 更新 history 最后一条
    if history and history[-1]['date'] != today_str() and history[-1]['result'] == 'OPEN':
        history[-1]['result'] = result
        history[-1]['auto_resolved'] = True
        history[-1]['resolve_note'] = note

    print(f'  昨日({prev_strat["date"]}) 结果: {result} — {note}')
    return result, note

# ========================
# Step 4: 保存今日策略到 prev_strategy
# ========================
def save_prev_strategy(strategy, date_display):
    with open(PREV_STRAT, 'w', encoding='utf-8') as f:
        json.dump({
            'date': date_display,
            'direction': strategy['direction'],
            'confidence': strategy['confidence'],
            'signals': strategy['bull_signals'] if strategy['direction'] == 'LONG'
                       else strategy['bear_signals'],
            'entry_low':  strategy['entry_low'],
            'entry_high': strategy['entry_high'],
            'stop_loss':  strategy['stop_loss'],
            'tp1':        strategy['tp1'],
            'tp2':        strategy['tp2'],
            'rr_ratio':   strategy['rr'],
            'position_size': '10-15%',
            'td_1h':      strategy.get('td_1h', {}),
            'td_4h':      strategy.get('td_4h', {}),
            'td_1d':      strategy.get('td_1d', {}),
        }, f, ensure_ascii=False, indent=2)
    print(f'  [OK] 写入 prev_strategy.json')

# ========================
# Step 5: 写入 strategy_history.json（OPEN）
# ========================
def append_today_to_history(history, strategy, today_d):
    today_entry = {
        'date': today_d,
        'direction': strategy['direction'],
        'entry_low':  int(strategy['entry_low']),
        'entry_high': int(strategy['entry_high']),
        'stop_loss':  int(strategy['stop_loss']),
        'tp1':        int(strategy['tp1']),
        'tp2':        int(strategy['tp2']),
        'rr':         round(strategy['rr'], 2),
        'result':     'OPEN' if strategy['direction'] != 'WAIT' else 'SKIP',
        'auto_resolved': False,
        'resolve_note': ''
    }
    history.append(today_entry)
    with open(HISTORY_FP, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f'  [OK] 追加今日策略到 strategy_history.json')

# ========================
# 日期工具
# ========================
def today_str():
    return datetime.now().strftime('%Y%m%d')

def date_display():
    now = datetime.now()
    return now.strftime('%m/%d'), now.strftime('%Y-%m-%d'), now.strftime('%A')

# ========================
# ========================
# 8个动态生成函数
# ========================

def gen_section1_stats(history):
    """一、综合统计看板"""
    records = [h for h in history if h['result'] not in ('SKIP',)]  # 只算执行过的
    total   = len(records)
    if total == 0: total = 1

    wins     = sum(1 for r in records if r['result'] in ('WIN', 'WIN_TP1'))
    losses   = sum(1 for r in records if r['result'] == 'LOSS')
    break_ev = sum(1 for r in records if r['result'] == 'BREAK_EVEN')
    win_rate = wins / total * 100

    # 平均 RR
    rrs = [r['rr'] for r in records if r['rr'] > 0]
    avg_rr = sum(rrs) / len(rrs) if rrs else 0

    # 最大回撤（简化）
    max_dd = 0
    cumulative = 0
    for r in records:
        if r['result'] in ('WIN', 'WIN_TP1'): cumulative += r['rr']
        elif r['result'] == 'LOSS': cumulative -= 1
        if cumulative < 0: max_dd = min(max_dd, cumulative)

    # 近14天
    last14 = history[-14:] if len(history) >= 14 else history
    exec14  = [r for r in last14 if r['result'] not in ('SKIP',)]
    w14     = sum(1 for r in exec14 if r['result'] in ('WIN', 'WIN_TP1'))
    l14     = sum(1 for r in exec14 if r['result'] == 'LOSS')
    wr14    = w14 / len(exec14) * 100 if exec14 else 0

    # 本月
    month = [r for r in history if r['date'].startswith('202604') and r['result'] not in ('SKIP',)]
    wm = sum(1 for r in month if r['result'] in ('WIN', 'WIN_TP1'))
    lm = sum(1 for r in month if r['result'] == 'LOSS')
    wm_rate = wm / len(month) * 100 if month else 0

    def badge(val, good, warn=55):
        if val >= warn: return f'<span class="badge-good">{val:.1f}% {good}</span>'
        elif val >= warn - 10: return f'<span class="badge-warn">{val:.1f}% {good}</span>'
        return f'<span class="badge-bad">{val:.1f}% {good}</span>'

    def badge_rr(val):
        if val >= 2.0: return f'<span class="badge-good">{val:.2f}R</span>'
        elif val >= 1.0: return f'<span class="badge-warn">{val:.2f}R</span>'
        return f'<span class="badge-bad">{val:.2f}R</span>'

    def badge_dd(val):
        # 回撤为负值，abs 后判断；< 1.5R → 绿
        v = abs(val)
        if v < 1.5: return f'<span class="badge-good">{val:.1f}R</span>'
        elif v < 3.0: return f'<span class="badge-warn">{val:.1f}R</span>'
        return f'<span class="badge-bad">{val:.1f}R</span>'

    return f'''
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">14天胜率</div>
      <div class="stat-value">{badge(wr14, '✓')}</div>
      <div class="stat-sub">{w14}胜/{l14}负</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">本月累计盈亏</div>
      <div class="stat-value" style="color:{'#00d4aa' if wm_rate >= 55 else '#fbbf24'}">{wm_rate:.0f}%</div>
      <div class="stat-sub">{wm}胜/{lm}负</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">平均盈亏比</div>
      <div class="stat-value">{badge_rr(avg_rr)}</div>
      <div class="stat-sub">目标 ≥ 2:1</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">最大回撤</div>
      <div class="stat-value">{badge_dd(max_dd)}</div>
      <div class="stat-sub">目标 &lt; 1.5R</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">有效交易天数</div>
      <div class="stat-value" style="color:var(--blue)">{total}天</div>
      <div class="stat-sub">{wins}胜/{losses}负</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">盈亏笔数</div>
      <div class="stat-value" style="color:var(--green)">{wins}</div>
      <div class="stat-sub">{losses}亏 / {break_ev}保</div>
    </div>
  </div>'''


def gen_section7_tracking_table(history):
    """七、近14天策略追踪表（10列）"""
    records = history[-14:] if len(history) >= 14 else history

    today_d = today_str()

    rows = ''
    for r in records:
        is_today = r['date'] == today_d
        d = r['direction']
        res = r['result']

        dir_cls  = 'dir-long' if d == 'LONG' else ('dir-short' if d == 'SHORT' else 'dir-neutral')
        res_cls  = f'result-{res.lower()}' if res != 'OPEN' else 'result-open'

        res_text = res.replace('_', ' ')
        if res == 'OPEN': res_text = '⏳ 进行中'

        if r['result'] == 'SKIP':
            row = f'''<tr class="{"today-row" if is_today else ""}">
              <td class="date-col">{'📅' if is_today else ''}{r['date'][4:6]}/{r['date'][6:8]}</td>
              <td colspan="8" style="color:var(--text-muted);font-size:12px;text-align:center;">— 观望无操作 —</td>
            </tr>'''
        else:
            entry_txt = f"${r['entry_low']:,.0f}–${r['entry_high']:,.0f}" if r['entry_low'] else '—'
            tp1_txt   = f"${r['tp1']:,.0f}" if r['tp1'] else '—'
            tp2_txt   = f"${r['tp2']:,.0f}" if r['tp2'] else '—'
            sl_txt    = f"${r['stop_loss']:,.0f}" if r['stop_loss'] else '—'
            rr_txt    = f"{r['rr']:.1f}R" if r['rr'] else '—'

            today_badge = '<span class="badge-today">TODAY</span>' if is_today else ''
            resolve_note= r.get('resolve_note','')
            note_short  = resolve_note[:30] + '…' if resolve_note and len(resolve_note) > 30 else resolve_note

            row = f'''<tr class="{"today-row" if is_today else ""}">
  <td class="date-col">{'📅 ' if is_today else ''}{r['date'][4:6]}/{r['date'][6:8]} {today_badge}</td>
  <td class="{dir_cls}">{d}</td>
  <td>{entry_txt}</td>
  <td>{sl_txt}</td>
  <td>{tp1_txt}</td>
  <td>{tp2_txt}</td>
  <td>{rr_txt}</td>
  <td class="{res_cls}">{res_text}</td>
  <td class="resolve-note" title="{resolve_note}">{note_short}</td>
</tr>'''
        rows += row

    # 底部汇总
    exec14   = [r for r in records if r['result'] not in ('SKIP',)]
    w14_c    = sum(1 for r in exec14 if r['result'] in ('WIN','WIN_TP1'))
    l14_c    = sum(1 for r in exec14 if r['result'] == 'LOSS')
    b14_c    = sum(1 for r in exec14 if r['result'] == 'BREAK_EVEN')
    o14_c    = sum(1 for r in exec14 if r['result'] == 'OPEN')
    total14  = len(exec14)
    wr14_sum = w14_c / total14 * 100 if total14 else 0

    summary = f'''
  <div class="table-summary">
    <span class="sum-item sum-green">&#10003; 盈利 {w14_c} 笔</span>
    <span class="sum-item sum-red">&#10007; 亏损 {l14_c} 笔</span>
    <span class="sum-item sum-gray">&#9633; 保本 {b14_c} 笔</span>
    <span class="sum-item sum-blue">&#9654; 进行中 {o14_c} 笔</span>
    <span class="sum-item sum-yellow">14天胜率 {wr14_sum:.0f}%</span>
  </div>
  <div class="table-scroll">
  <table class="tracking-table">
    <thead>
      <tr>
        <th>日期</th><th>方向</th><th>进场区间</th><th>止损</th>
        <th>TP1</th><th>TP2</th><th>盈亏比</th><th>结果</th><th>复盘备注</th>
      </tr>
    </thead>
    <tbody>{rows}
    </tbody>
  </table>
  </div>'''

    return summary


def gen_section8_error_stats(history):
    """八、错误分类统计"""
    last14 = [r for r in history[-14:] if r['result'] not in ('SKIP', 'OPEN')]

    errors = {
        '止损误触': sum(1 for r in last14 if r['result'] == 'LOSS'),
        'TP1 未达': sum(1 for r in last14 if r['result'] == 'BREAK_EVEN'),
        '方向错误': sum(1 for r in last14 if r['result'] == 'LOSS'),
    }
    total = len(last14) or 1

    items = ''
    for name, cnt in errors.items():
        pct = cnt / total * 100
        color = 'var(--accent-red)' if pct > 30 else 'var(--accent-yellow)' if pct > 15 else 'var(--accent-green)'
        items += f'''
    <div class="error-item">
      <div class="error-label">{name}</div>
      <div class="error-bar-bg">
        <div class="error-bar-fill" style="width:{pct:.0f}%;background:{color};"></div>
      </div>
      <div class="error-count" style="color:{color};">{cnt}次</div>
    </div>'''

    return f'''
  <div class="error-grid">
    {items}
  </div>
  <div class="improvement-tip">
    <div class="tip-title">💡 改进建议</div>
    <ul class="tip-list">
      <li>止损误触 {'较多，建议收紧止损位或等待更清晰信号' if errors['止损误触'] > 2 else '控制良好，继续保持'}</li>
      <li>TP1 未达 {'可考虑扩大 TP1 区间至 +2.5%' if errors['TP1 未达'] > 2 else '注意持仓耐心'}</li>
      <li>胜率监控：保持 {sum(1 for r in last14 if r["result"] in ("WIN","WIN_TP1"))/total*100:.0f}% 以上触发</li>
    </ul>
  </div>'''


def gen_section9_bars(history):
    """九、近14天胜率柱状图（Canvas）"""
    last14 = history[-14:] if len(history) >= 14 else history
    labels = [r['date'][4:6]+'/'+r['date'][6:8] for r in last14]
    colors = []
    for r in last14:
        if r['result'] in ('WIN','WIN_TP1'): colors.append('#00d4aa')
        elif r['result'] == 'LOSS': colors.append('#ff4757')
        elif r['result'] == 'BREAK_EVEN': colors.append('#fbbf24')
        else: colors.append('#374151')

    colors_json = json.dumps(colors)
    labels_json = json.dumps(labels)

    return f'''
  <div class="bar-chart-wrap">
    <canvas id="barChart" height="160"></canvas>
  </div>
  <script>
    const barLabels = {labels_json};
    const barColors = {colors_json};
    const ctx = document.getElementById('barChart').getContext('2d');
    new Chart(ctx, {{
      type: 'bar',
      data: {{
        labels: barLabels,
        datasets: [{{
          data: barLabels.map(() => 1),
          backgroundColor: barColors,
          borderRadius: 4,
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          y: {{ display: false }},
          x: {{ grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8', font: {{ size: 11 }} }} }}
        }}
      }}
    }});
  </script>'''


def gen_section10_line(history):
    """十、近30天累计胜率趋势折线图"""
    records = [r for r in history if r['result'] not in ('SKIP',)]
    if not records: records = [{'result': 'WIN'}]

    cumulative_wins = []
    cum = 0
    for r in records:
        if r['result'] in ('WIN', 'WIN_TP1'): cum += 1
        cumulative_wins.append(cum)

    total_steps = list(range(1, len(cumulative_wins) + 1))
    win_rates = [cumulative_wins[i] / (i+1) * 100 for i in range(len(cumulative_wins))]

    steps_js  = json.dumps(total_steps)
    rates_js  = json.dumps([round(r, 2) for r in win_rates])

    return f'''
  <div class="line-chart-wrap">
    <canvas id="lineChart" height="120"></canvas>
  </div>
  <script>
    new Chart(document.getElementById('lineChart').getContext('2d'), {{
      type: 'line',
      data: {{
        labels: {steps_js},
        datasets: [{{
          label: '累计胜率 %',
          data: {rates_js},
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.1)',
          fill: true,
          tension: 0.4,
          pointRadius: 3,
          pointBackgroundColor: '#3b82f6',
        }}]
      }},
      options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
          y: {{ min: 0, max: 100, grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8', callback: v => v+'%' }} }},
          x: {{ grid: {{ color: '#1e293b' }}, ticks: {{ color: '#94a3b8', maxTicksLimit: 10 }} }}
        }}
      }}
    }});
  </script>'''


def gen_section11_yesterday_review(prev_strat, history, data, today_display):
    """十一、昨日复盘（自动）"""
    if not prev_strat:
        return '<div class="section"><p style="color:var(--text-muted)">暂无昨日策略记录</p></div>'

    d = prev_strat['direction']
    sl = prev_strat['stop_loss']
    tp1 = prev_strat['tp1']
    tp2 = prev_strat['tp2']
    today_h = data['high_24h']
    today_l = data['low_24h']

    # 重新计算结果（与 auto_resolve 一致）
    if d == 'LONG':
        if today_l < sl: res='LOSS'; hit='止损出局'
        elif today_h >= tp2: res='WIN'; hit='TP2达成'
        elif today_h >= tp1: res='WIN_TP1'; hit='TP1达成'
        else: res='BREAK_EVEN'; hit='未触及任一目标'
    elif d == 'SHORT':
        if today_h > sl: res='LOSS'; hit='止损出局'
        elif today_l <= tp2: res='WIN'; hit='TP2达成'
        elif today_l <= tp1: res='WIN_TP1'; hit='TP1达成'
        else: res='BREAK_EVEN'; hit='未触及任一目标'
    else:
        res='SKIP'; hit='观望无操作'

    res_cls = f'result-{res.lower()}' if res != 'OPEN' else 'result-open'
    res_text= res.replace('_',' ')

    score_map = {'WIN': 90, 'WIN_TP1': 75, 'BREAK_EVEN': 60, 'LOSS': 30, 'SKIP': 50}
    score = score_map.get(res, 50)
    stars = '★' * round(score/20) + '☆' * (5 - round(score/20))

    # 最大失误 + 亮点（自动推断）
    if res == 'WIN':
        highlight = 'TP2 全胜离场，完美执行'
        mistake = '无'
    elif res == 'WIN_TP1':
        highlight = 'TP1 顺利达成，半胜离场'
        mistake = '未持有到 TP2，可考虑扩大持仓区间'
    elif res == 'BREAK_EVEN':
        highlight = '未触发止损，保本出局'
        mistake = '方向正确但未给足空间，TP1 距离过远'
    elif res == 'LOSS':
        highlight = '严格止损执行，风控到位'
        mistake = '止损触发，建议复盘进场时机是否过早'
    else:
        highlight = '观望日，无操作'
        mistake = '无'

    score_color = '#00d4aa' if score >= 75 else '#fbbf24' if score >= 50 else '#ff4757'

    return f'''
  <div class="yesterday-review">
    <div class="review-header">
      <div class="review-date">昨日策略 · {prev_strat['date']}</div>
      <div class="result-badge rb-{res.lower()}">{res_text}</div>
    </div>
    <div class="review-body">
      <div class="review-item"><span class="review-label">方向</span><span>{d}</span></div>
      <div class="review-item"><span class="review-label">进场</span><span>${prev_strat['entry_low']:,.0f}–${prev_strat['entry_high']:,.0f}</span></div>
      <div class="review-item"><span class="review-label">止损 SL</span><span style="color:var(--red)">${sl:,.0f}</span></div>
      <div class="review-item"><span class="review-label">TP1</span><span style="color:var(--green)">${tp1:,.0f}</span></div>
      <div class="review-item"><span class="review-label">TP2</span><span style="color:var(--green)">${tp2:,.0f}</span></div>
      <div class="review-item"><span class="review-label">今日高点</span><span style="color:var(--green)">${today_h:,.0f}</span></div>
      <div class="review-item"><span class="review-label">今日低点</span><span style="color:var(--red)">${today_l:,.0f}</span></div>
      <div class="review-item"><span class="review-label">判断</span><span>{hit}</span></div>
    </div>
    <div class="review-footer">
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
        <div style="background:rgba(0,212,170,.06);border:1px solid rgba(0,212,170,.2);border-radius:8px;padding:10px 12px;">
          <div style="font-size:11px;color:var(--green);font-weight:700;margin-bottom:4px;">&#10003; 亮点</div>
          <div style="font-size:12px;color:var(--muted);">{highlight}</div>
        </div>
        <div style="background:rgba(255,71,87,.06);border:1px solid rgba(255,71,87,.2);border-radius:8px;padding:10px 12px;">
          <div style="font-size:11px;color:var(--red);font-weight:700;margin-bottom:4px;">&#9888; 最大失误</div>
          <div style="font-size:12px;color:var(--muted);">{mistake}</div>
        </div>
      </div>
      <div class="score-section">
        <div class="score-label">执行打分</div>
        <div class="score-bar-bg">
          <div class="score-bar-fill" style="width:{score}%;background:{score_color};"></div>
        </div>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:4px;">
          <div class="score-stars" style="color:{score_color};">{stars}</div>
          <div class="score-value" style="color:{score_color};">{score}/100</div>
        </div>
      </div>
    </div>
  </div>'''


def gen_section12_week_review(history):
    """十二、本周复盘"""
    last7 = [r for r in history[-7:] if r['result'] not in ('SKIP',)]
    if not last7: last7 = [{'result':'SKIP'}]

    wins_w  = sum(1 for r in last7 if r['result'] in ('WIN','WIN_TP1'))
    losses_w= sum(1 for r in last7 if r['result'] == 'LOSS')
    total_w = len(last7)
    wr_w    = wins_w / total_w * 100 if total_w else 0

    rrs_w = [r['rr'] for r in last7 if r['rr'] > 0]
    avg_rr_w = sum(rrs_w)/len(rrs_w) if rrs_w else 0

    best = max(last7, key=lambda r: r.get('rr', 0)) if last7 else {}
    worst= min(last7, key=lambda r: r.get('rr', -99)) if last7 else {}

    # 下周唯一改进项（自动推断）
    if losses_w > wins_w:
        improvement = '本周亏损笔数偏多，建议严格等待 MACD 确认信号后再入场，减少情绪化追单'
    elif wr_w >= 70:
        improvement = '本周胜率优秀，下周重点：保持现有纪律，不因连胜而放大仓位'
    elif avg_rr_w < 1.5:
        improvement = '盈亏比偏低，建议扩大 TP1/TP2 间距，或等待更深的回撤再进场'
    elif losses_w == 0 and wins_w > 0:
        improvement = '本周全胜，建议继续保持信号质量，不盲目增加交易频率'
    else:
        improvement = '建议每日复盘时标注最大失误，持续追踪改进'

    return f'''
  <div class="week-review">
    <div class="wr-stats">
      <div class="wr-stat"><span class="wr-num" style="color:var(--green)">{wins_w}</span><span class="wr-label">胜</span></div>
      <div class="wr-stat"><span class="wr-num" style="color:var(--red)">{losses_w}</span><span class="wr-label">负</span></div>
      <div class="wr-stat"><span class="wr-num">{wr_w:.0f}%</span><span class="wr-label">胜率</span></div>
      <div class="wr-stat"><span class="wr-num">{avg_rr_w:.1f}R</span><span class="wr-label">均RR</span></div>
    </div>
    <div class="wr-detail">
      <div class="wr-best">&#127942; 最佳：{best.get('date','—')} {best.get('direction','—')} {best.get('rr',0):.1f}R</div>
      <div class="wr-worst">&#9888; 最差：{worst.get('date','—')} {worst.get('direction','—')} {worst.get('rr',0):.1f}R</div>
    </div>
    <div class="week-improvement">
      <div class="wi-title">&#9654; 下周唯一改进项</div>
      <div class="wi-content">{improvement}</div>
    </div>
  </div>'''


def gen_section13_month_review(history):
    """十三、月回顾统计（v2.2 规范版）"""
    month = [r for r in history if r['date'].startswith('202604') and r['result'] not in ('SKIP',)]
    if not month: month = [{'result':'SKIP'}]

    wm     = sum(1 for r in month if r['result'] in ('WIN','WIN_TP1'))
    lm     = sum(1 for r in month if r['result'] == 'LOSS')
    bm     = sum(1 for r in month if r['result'] == 'BREAK_EVEN')
    om     = sum(1 for r in month if r['result'] == 'OPEN')
    tm     = len(month)
    wm_rate= wm / tm * 100 if tm else 0

    rrs_m  = [r['rr'] for r in month if r['rr'] > 0]
    avg_rr_m = sum(rrs_m)/len(rrs_m) if rrs_m else 0

    # 累计盈亏（WIN=+2R / WIN_TP1=+1R / LOSS=-1R / 其他=0）
    pnl = sum(
        (2.0 if r['result']=='WIN' else 1.0 if r['result']=='WIN_TP1' else -1.0 if r['result']=='LOSS' else 0)
        for r in month
    )

    # 最大回撤（累计曲线）
    dd = 0; max_dd = 0
    for r in month:
        if r['result'] == 'WIN':      dd += 2.0
        elif r['result'] == 'WIN_TP1': dd += 1.0
        elif r['result'] == 'LOSS':   dd -= 1.0
        if dd < max_dd: max_dd = dd

    # 近14天胜率（单独统计）
    last14 = history[-14:]
    exec14 = [r for r in last14 if r['result'] not in ('SKIP',)]
    w14 = sum(1 for r in exec14 if r['result'] in ('WIN','WIN_TP1'))
    wr14 = w14 / len(exec14) * 100 if exec14 else 0

    def mb(good, val, label):
        bg = 'rgba(0,212,170,0.2)' if good else 'rgba(251,191,36,0.2)' if not good and label!='月盈亏' else ('rgba(255,71,87,0.2)' if not good else 'rgba(0,212,170,0.2)')
        cl = '#00d4aa' if good else '#fbbf24' if label!='月盈亏' else '#ff4757'
        return f'<div class="mr-stat"><div class="mr-label">{label}</div><div class="mr-value" style="color:{cl}">{val}</div><div class="mr-badge mb-good" style="background:{bg};color:{cl}">{'✓' if good else '⚠'}</div></div>'

    # 逐日详细记录
    rows = ''
    for r in month:
        d = r['direction']
        res = r['result']
        dir_cls = 'dir-long' if d=='LONG' else ('dir-short' if d=='SHORT' else 'dir-neutral')
        res_cls = f'result-{res.lower()}' if res not in ('OPEN',) else 'result-open'
        res_text = res.replace('_',' ')
        pnl_val = 2.0 if res=='WIN' else 1.0 if res=='WIN_TP1' else (-1.0 if res=='LOSS' else 0)
        rows += f'<tr><td class="{dir_cls}">{r["date"][4:6]}/{r["date"][6:8]}</td><td>{d}</td><td class="{res_cls}">{res_text}</td><td style="color:{"#00d4aa" if pnl_val>0 else "#ff4757" if pnl_val<0 else "#fbbf24"}">{pnl_val:+.1f}R</td></tr>'

    return f'''
  <div class="month-review">
    <div class="mr-title">2026年4月 · 月度汇总</div>
    <div class="mr-stats">
      {mb(wm_rate>=55, f'{wm_rate:.0f}%', '月胜率')}
      {mb(pnl>=0, f'{pnl:+.1f}R', '月盈亏')}
      {mb(avg_rr_m>=2.0, f'{avg_rr_m:.2f}R', '平均RR')}
      {mb(abs(max_dd)<1.5, f'{max_dd:.1f}R', '最大回撤')}
      <div class="mr-stat"><div class="mr-label">近14天胜率</div><div class="mr-value" style="color:{"#00d4aa" if wr14>=55 else "#fbbf24"}">{wr14:.0f}%</div><div class="mr-badge">{'✓' if wr14>=55 else '⚠'}</div></div>
      <div class="mr-stat"><div class="mr-label">本月战绩</div><div class="mr-value">{wm}胜/{lm}负</div><div class="mr-badge">{tm-wm-lm}保/{om}持</div></div>
    </div>
    <div style="margin-top:20px;">
      <div style="font-size:13px;font-weight:700;margin-bottom:10px;color:var(--muted);text-transform:uppercase;letter-spacing:.5px;">每日详细记录</div>
      <table class="tracking-table" style="min-width:400px;">
        <thead><tr><th>日期</th><th>方向</th><th>结果</th><th>盈亏(R)</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    </div>
  </div>'''


# ========================
# Step 6: 生成 HTML
# ========================
def generate_html(data, strategy, history, prev_strat, date_display_tuple):
    print('\n[Step 4] 生成 HTML 报告...')

    today_md, today_fd, today_wd = date_display_tuple
    p = data['btc_price']

    with open(TEMPLATE, 'r', encoding='utf-8') as f:
        html = f.read()

    # 占位符替换
    # 占位符替换（处理注释行和内容行两种格式）
    def rep(html, old, new):
        return html.replace(old, new)

    # 8个占位符全部统一为注释格式 <!-- {{SECTION_X}} -->
    html = rep(html, '<!-- {{SECTION1_STATS}} -->',          gen_section1_stats(history))
    html = rep(html, '<!-- {{SECTION7_TRACKING}} -->',        gen_section7_tracking_table(history))
    html = rep(html, '<!-- {{SECTION8_ERROR_STATS}} -->',    gen_section8_error_stats(history))
    html = rep(html, '<!-- {{SECTION9_BARS}} -->',          gen_section9_bars(history))
    html = rep(html, '<!-- {{SECTION10_LINE}} -->',          gen_section10_line(history))
    html = rep(html, '<!-- {{SECTION11_YESTERDAY_REVIEW}} -->', gen_section11_yesterday_review(prev_strat, history, data, today_md))
    html = rep(html, '<!-- {{SECTION12_WEEK_REVIEW}} -->',   gen_section12_week_review(history))
    html = rep(html, '<!-- {{SECTION13_MONTH_REVIEW}} -->',  gen_section13_month_review(history))

    # 动态数据替换
    html = html.replace('{{TODAY_DATE}}', today_fd)
    html = html.replace('{{TODAY_DISPLAY}}', f'{today_md} {today_wd}')
    html = html.replace('{{BTC_PRICE}}', f'${p:,.0f}')
    html = html.replace('{{BTC_CHANGE}}', f'{data["btc_chg"]:+.2f}%')
    html = html.replace('{{ETH_PRICE}}', f'${data["eth_price"]:,.0f}')
    html = html.replace('{{ETH_CHANGE}}', f'{data["eth_chg"]:+.2f}%')
    html = html.replace('{{RSI}}', f'{data["rsi_14"]:.1f}')
    html = html.replace('{{EMA20}}', f'${data["ema20"]:,.0f}')
    html = html.replace('{{EMA50}}', f'${data["ema50"]:,.0f}')
    html = html.replace('{{BB_UPPER}}', f'${data["bb_upper"]:,.0f}')
    html = html.replace('{{BB_LOWER}}', f'${data["bb_lower"]:,.0f}')
    html = html.replace('{{MACD_HIST}}', f'{data["macd_hist"]:+.4f}')
    html = html.replace('{{FUNDING_RATE}}', f'{data["funding_rate"]:+.4f}%')
    macd_clr = '#00d4aa' if data['macd_hist'] >= 0 else '#ff4757'
    fund_clr = '#00d4aa' if data['funding_rate'] <= 0 else '#ff4757'
    btc_clr  = '#00d4aa' if data['btc_chg'] >= 0  else '#ff4757'
    eth_clr  = '#00d4aa' if data['eth_chg'] >= 0  else '#ff4757'
    html = html.replace('{{MACD_CLR}}', macd_clr)
    html = html.replace('{{FUNDING_CLR}}', fund_clr)
    html = html.replace('{{BTC_CHANGE_CLR}}', btc_clr)
    html = html.replace('{{ETH_CHANGE_CLR}}', eth_clr)
    html = html.replace('{{OI}}', f'${data["open_interest"]/1e8:.2f}B')
    html = html.replace('{{HIGH_24H}}', f'${data["high_24h"]:,.0f}')
    html = html.replace('{{LOW_24H}}', f'${data["low_24h"]:,.0f}')

    # 今日策略
    d = strategy['direction']
    dir_color = {'LONG': '#00d4aa', 'SHORT': '#ff4757', 'WAIT': '#fbbf24'}.get(d, '#94a3b8')
    html = html.replace('{{STRATEGY_DIR}}', d)
    html = html.replace('{{DIR_COLOR}}', dir_color)
    html = html.replace('{{CONF}}', f'{strategy["confidence"]:.0f}')
    html = html.replace('{{ENTRY_RANGE}}',
        f"${strategy['entry_low']:,.0f} – ${strategy['entry_high']:,.0f}" if strategy['entry_low'] else '—')
    html = html.replace('{{SL}}', f'${strategy["stop_loss"]:,.0f}' if strategy['stop_loss'] else '—')
    html = html.replace('{{TP1}}', f'${strategy["tp1"]:,.0f}' if strategy['tp1'] else '—')
    html = html.replace('{{TP2}}', f'${strategy["tp2"]:,.0f}' if strategy['tp2'] else '—')
    html = html.replace('{{RR}}', f"{strategy['rr']:.1f}:1" if strategy['rr'] else '—')
    bull_sig = '<br>'.join(f'✅ {s}' for s in strategy['bull_signals']) if strategy['bull_signals'] else '无'
    bear_sig = '<br>'.join(f'❌ {s}' for s in strategy['bear_signals']) if strategy['bear_signals'] else '无'
    html = html.replace('{{BULL_SIGNALS}}', bull_sig)
    html = html.replace('{{BEAR_SIGNALS}}', bear_sig)

    # ── TD Sequential 专用看板 ──
    def _build_td_card(tf_label, tf_key, td):
        """构建单个时间框架 TD 卡"""
        if td.get('buy_active'):
            cls, status, hint = 'buy', 'TD买入完成 ★', f'count={td["buy_count"]}/9 | 关注回调做多'
        elif td.get('sell_active'):
            cls, status, hint = 'sell', 'TD卖出完成 ★', f'count={td["sell_count"]}/9 | 关注反弹做空'
        elif td.get('buy_count', 0) >= 6:
            cls, status, hint = 'neutral', 'TD买入积累中', f'count={td["buy_count"]}/9 | 等待结构完成'
        elif td.get('sell_count', 0) >= 6:
            cls, status, hint = 'neutral', 'TD卖出分布中', f'count={td["sell_count"]}/9 | 等待结构完成'
        else:
            bc = td.get('buy_count', 0)
            sc = td.get('sell_count', 0)
            if bc > 0:
                hint = f'count={bc}/9 | 无明显结构，观望'
            elif sc > 0:
                hint = f'count={sc}/9 | 无明显结构，观望'
            else:
                hint = '无信号 | 等待结构形成'
            cls, status = 'neutral', '中性'
        return f'''<div class="td-card {cls}">
  <div class="td-timeframe">{tf_label}</div>
  <div class="td-status {cls}">{status}</div>
  <div class="td-count">{tf_key}</div>
  <div class="td-hint">{hint}</div>
</div>'''

    td_1h = strategy.get('td_1h', {})
    td_4h = strategy.get('td_4h', {})
    td_1d = strategy.get('td_1d', {})

    # 时间框架标签：1H=短线择时/4H=中线方向/1D=长线确认
    td_panel = (
        _build_td_card('1H · 短线择时', '超短线 · 择时进场', td_1h) +
        _build_td_card('4H · 中线方向', '主趋势 · 持仓参考', td_4h) +
        _build_td_card('1D · 长线确认', '波段持仓 · 止损参考', td_1d)
    )
    html = html.replace('{{TD_SIGNALS}}', td_panel)

    return html


# ========================
# Step 7: 保存文件
# ========================
def save_reports(html, today_d):
    today_html_fn = f'BTC_daily_report_{today_d}_PROFESSIONAL.html'
    out_path = os.path.join(REPORTS_DIR, today_html_fn)

    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html)
    size = os.path.getsize(out_path)
    print(f'\n[OK] 报告已保存: {out_path} ({size:,} bytes)')
    return out_path


# ========================
# Step 8: Git 管理
# ========================
def git_push(msg):
    repo = os.path.dirname(BASE_DIR.rstrip(os.sep))
    try:
        # 检查文件大小
        report_path = os.path.join(REPORTS_DIR, os.listdir(REPORTS_DIR)[-1])
        sz = os.path.getsize(report_path)
        if sz < 100:
            print(f'⚠️ 报告文件异常小 ({sz} bytes)，跳过 commit')
            return

        # git add
        subprocess.run(['git', '-C', repo, 'add', '.'],
                       capture_output=True, encoding='utf-8', errors='replace')
        # git commit
        res = subprocess.run(
            ['git', '-C', repo, 'commit', '-m', msg],
            capture_output=True, encoding='utf-8', errors='replace')
        if res.returncode == 0:
            print(f'[OK] Git commit: {msg}')
        else:
            print(f'[WARN] Git commit: {res.stdout[:100]} {res.stderr[:100]}')

        # git push
        push = subprocess.run(['git', '-C', repo, 'push', 'origin', 'main'],
                             capture_output=True, encoding='utf-8', errors='replace')
        if push.returncode == 0:
            print('[OK] Git push 完成')
        else:
            print(f'[WARN] Git push: {push.stderr[:100]}')
    except Exception as e:
        print(f'[WARN] Git 操作异常: {e}')


# ========================
# Step 9: Telegram 推送
# ========================
def telegram_push(report_url):
    try:
        import sys, os
        sys.path.insert(0, BASE_DIR)
        import telegram_notify
        telegram_notify.send_report(report_url)
    except Exception as e:
        print(f'[WARN] Telegram 推送跳过: {e}')


# ========================
# 主入口
# ========================
def main():
    print('='*50)
    print(' BTC日报系统 v2.2  —  run_daily_report.py')
    print('='*50)

    today_d = today_str()
    today_md, today_fd, today_wd = date_display()

    # 检查今日是否已生成
    existing = [f for f in os.listdir(REPORTS_DIR)
                if f.startswith(f'BTC_daily_report_{today_d}')]
    if existing:
        print(f'\n[SKIP] 今日报告已存在: {existing[0]}，跳过。')
        return

    # 加载历史
    if os.path.exists(HISTORY_FP):
        with open(HISTORY_FP, 'r', encoding='utf-8') as f:
            history = json.load(f)
    else:
        history = []

    # 加载昨日策略
    if os.path.exists(PREV_STRAT):
        with open(PREV_STRAT, 'r', encoding='utf-8') as f:
            prev_strat = json.load(f)
    else:
        prev_strat = {}

    # Step 1: 数据
    data = fetch_all()

    # Step 2: 策略
    strategy = generate_strategy(data)

    # Step 3: 自动复盘
    if prev_strat:
        auto_resolve_yesterday(data, prev_strat, history)

    # Step 4: 保存今日 prev_strategy
    save_prev_strategy(strategy, today_md)

    # Step 5: 追加今日到 history
    append_today_to_history(history, strategy, today_d)

    # Step 6: 生成 HTML
    html = generate_html(data, strategy, history, prev_strat, (today_md, today_fd, today_wd))

    # Step 7: 保存
    out_path = save_reports(html, today_d)

    # Step 8: Git
    git_push(f'feat: BTC daily report {today_d}')

    # Step 9: TG
    # telegram_push('https://wanglin141319-bit.github.io/btc/')

    print('\n[OK] All done!')
    print(f'   报告: {out_path}')
    print(f'   GitHub Pages: https://wanglin141319-bit.github.io/btc/')


if __name__ == '__main__':
    main()

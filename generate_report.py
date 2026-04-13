#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC每日行情日报生成器
作者: MK (bitebiwang1413)
定时任务: 每天10:30自动执行
"""

import requests
import json
from datetime import datetime
from pycoingecko import CoinGeckoAPI
import warnings
warnings.filterwarnings('ignore')

# ============================================================
# 配置区
# ============================================================
REPORT_DIR = "reports"
TEMPLATE_FILE = "template.html"

# CoinGecko API 配置
cg = CoinGeckoAPI()

def get_btc_data():
    """获取BTC市场数据"""
    try:
        btc = cg.get_coin_market_chart_by_id(id='bitcoin', vs_currency='usd', days='1')

        # 当前价格
        prices = btc['prices']
        current_price = prices[-1][1] if prices else 0
        price_24h_ago = prices[0][1] if prices else 0
        change_24h = ((current_price - price_24h_ago) / price_24h_ago * 100) if price_24h_ago else 0

        # 24小时数据
        market_data = cg.get_coins_markets(vs_currency='usd', ids='bitcoin', order='market_cap_desc')[0]

        return {
            'price': current_price,
            'change_24h': change_24h,
            'high_24h': market_data.get('high_24h', 0),
            'low_24h': market_data.get('low_24h', 0),
            'volume_24h': market_data.get('total_volume', 0),
            'market_cap': market_data.get('market_cap', 0),
            'price_history': prices[-48:] if len(prices) > 48 else prices  # 24小时图表数据
        }
    except Exception as e:
        print(f"获取数据失败: {e}")
        return None

def generate_chart_html(price_history):
    """生成K线图表HTML"""
    if not price_history:
        return ""

    labels = []
    data = []
    for i, (timestamp, price) in enumerate(price_history):
        dt = datetime.fromtimestamp(timestamp / 1000)
        labels.append(f"'{dt.strftime('%H:%M')}'")
        data.append(str(round(price, 2)))

    return f"""
    const labels = [{','.join(labels)}];
    const prices = [{','.join(data)}];

    const ctx = document.getElementById('priceChart').getContext('2d');
    new Chart(ctx, {{
        type: 'line',
        data: {{
            labels: labels,
            datasets: [{{
                label: 'BTC/USDT',
                data: prices,
                borderColor: prices[0] <= prices[-1] ? '#ef4444' : '#22c55e',
                backgroundColor: 'rgba(0,0,0,0)',
                tension: 0.4,
                pointRadius: 0,
                borderWidth: 2
            }}]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {{ legend: {{ display: False }} }},
            scales: {{
                x: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#9ca3af' }} }},
                y: {{ grid: {{ color: 'rgba(255,255,255,0.05)' }}, ticks: {{ color: '#9ca3af' }} }}
            }}
        }}
    }});
    """

def generate_report(data):
    """生成HTML日报"""
    date_str = datetime.now().strftime('%Y年%m月%d日 %H:%M')
    price = data['price']
    change = data['change_24h']
    change_color = '#ef4444' if change >= 0 else '#22c55e'
    change_icon = '▲' if change >= 0 else '▼'

    chart_script = generate_chart_html(data.get('price_history', []))

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTC每日行情日报 - {datetime.now().strftime('%Y%m%d')}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }}
        .gradient-bg {{ background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%); }}
        .card {{ background: rgba(255,255,255,0.05); backdrop-filter: blur(10px); }}
    </style>
</head>
<body class="gradient-bg text-white min-h-screen p-6">
    <div class="max-w-6xl mx-auto">

        <!-- 标题 -->
        <header class="text-center mb-8">
            <h1 class="text-4xl font-bold mb-2">₿ BTC 每日行情日报</h1>
            <p class="text-gray-400">{date_str}</p>
        </header>

        <!-- 价格概览 -->
        <section class="card rounded-2xl p-6 mb-6">
            <h2 class="text-xl font-semibold mb-4 border-b border-white/10 pb-2">价格概览</h2>
            <div class="grid grid-cols-2 md:grid-cols-4 gap-6">
                <div>
                    <p class="text-gray-400 text-sm">当前价格</p>
                    <p class="text-3xl font-bold">${price:,.2f}</p>
                </div>
                <div>
                    <p class="text-gray-400 text-sm">24h涨跌</p>
                    <p class="text-3xl font-bold" style="color: {change_color}">
                        {change_icon} {abs(change):.2f}%
                    </p>
                </div>
                <div>
                    <p class="text-gray-400 text-sm">24h高/低</p>
                    <p class="text-xl">${data.get('high_24h', 0):,.2f} / ${data.get('low_24h', 0):,.2f}</p>
                </div>
                <div>
                    <p class="text-gray-400 text-sm">24h成交量</p>
                    <p class="text-xl">${data.get('volume_24h', 0) / 1e9:.2f}B</p>
                </div>
            </div>
        </section>

        <!-- 24h图表 -->
        <section class="card rounded-2xl p-6 mb-6">
            <h2 class="text-xl font-semibold mb-4 border-b border-white/10 pb-2">24小时价格走势</h2>
            <div class="h-64">
                <canvas id="priceChart"></canvas>
            </div>
        </section>

        <script>{chart_script}</script>

        <!-- 风险提示 -->
        <section class="card rounded-2xl p-6 mb-6 border-l-4 border-yellow-500">
            <h2 class="text-xl font-semibold mb-3">⚠️ 风险提示</h2>
            <ul class="text-gray-300 space-y-2 text-sm">
                <li>• 加密货币市场24/7运行，波动性极高</li>
                <li>• 合约交易存在强制平仓风险，请严格控制仓位</li>
                <li>• 本报告仅供参考，不构成投资建议</li>
                <li>•DYOR (Do Your Own Research) - 请自行研究后决策</li>
            </ul>
        </section>

        <!-- 免责声明 -->
        <footer class="text-center text-gray-500 text-sm mt-8">
            <p>本报告由自动化系统生成 | 数据来源: CoinGecko API</p>
            <p class="mt-1">免责声明: 本报告仅供参考，不构成任何投资建议。投资有风险，入市需谨慎。</p>
        </footer>
    </div>
</body>
</html>'''

    return html

def main():
    """主函数"""
    print("开始获取BTC数据...")
    data = get_btc_data()

    if data:
        print(f"获取成功: ${data['price']:,.2f}")
        html = generate_report(data)

        # 保存日报
        import os
        os.makedirs(REPORT_DIR, exist_ok=True)
        filename = f"{REPORT_DIR}/BTC_daily_{datetime.now().strftime('%Y%m%d')}.html"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(html)

        print(f"日报已保存: {filename}")
        return True
    else:
        print("获取数据失败")
        return False

if __name__ == "__main__":
    main()

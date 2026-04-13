# BTC Daily Reports

自动生成的BTC每日行情日报

## 自动更新

- 每天 10:30 (UTC+8) 自动生成日报
- 数据来源: CoinGecko API
- 托管平台: GitHub Pages

## 本地运行

```bash
# 生成日报
python generate_report.py

# 查看日报
# 直接打开 reports/ 目录下的 HTML 文件
```

## 文件结构

```
btc/
├── index.html              # 日报索引页
├── generate_report.py      # 日报生成脚本
├── reports/                # 日报存储目录
│   └── BTC_daily_YYYYMMDD.html
└── README.md
```

## 访问日报

GitHub Pages: https://wanglin141319-bit.github.io/btc/

## 免责声明

本仓库内容仅供参考，不构成任何投资建议。加密货币市场波动剧烈，投资有风险。

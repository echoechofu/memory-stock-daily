# 存储股情报局 📊

> 每日自动追踪 DRAM / NAND / HBM 价格信号 + 存储股行情，AI 生成中文早报推送 Telegram

## 这是什么

**存储股情报局**是一个全自动化的存储产业链日报系统。每天早上它会：

1. **抓取行情** — 富途 OpenD（优先）或 Yahoo Finance（备选），获取 MU / SNDK / NVDA / SOXX / SMH 的价格、成交量、5日/20日均线
2. **聚合新闻** — TrendForce、Google News RSS，覆盖 DRAM 合约价、NAND 行情、HBM 供需、宏观大宗（黄金/原油/美元）、重点存储股最新动态
3. **提取信号** — 正则引擎从新闻标题/摘要中识别涨价、缺货、需求超预期等信号
4. **量化评分** — 5 维度评分（行情强弱 / DRAM-NAND 价格 / HBM 供需 / 同行验证 / 下游需求），0–5 分
5. **生成报告** — MiniMax 大模型输出结构化中文日报，包含风险信号、行情解读、明日观测点
6. **推送 Telegram** — 完整报告直达手机，备选纯文本格式兜底

## 效果预览

生成的日报节选：

```
【存储股日报｜2026-05-07】

一、今日总判断
- 今日评分：4/5
- 状态：强正向
- 一句话解释：MU/SNDK 延续强势，DRAM/NAND 价格持续上行且 AI 需求强劲，
  但涨幅已大且 SNDK 今日小幅回调，需注意短期过热风险。

二、行情相对强弱
- MU：$651.80（+1.73%）| 5D +25.72% | 20D +60.25% |
  成交量 3730万（5日均 4460万 / 20日均 4010万）
...
```

## 项目结构

```
memory-watch/
├── main.py                    # 入口，每日 cron 调度
├── sources/
│   ├── futu_quotes.py         # 富途行情（需 OpenD）
│   ├── yfinance_quotes.py     # Yahoo Finance 备选行情
│   ├── trendforce.py          # TrendForce + 高价值媒体 RSS
│   ├── news.py                # 宏观/重点股票新闻
│   └── price_signal_extractor.py  # 正则价格信号提取
├── analysis/
│   ├── scoring.py             # 5 维度评分
│   └── signal_extractor.py    # 关键词信号提取
├── llm/
│   └── minimax_client.py      # MiniMax API 调用
├── push/
│   └── telegram.py            # Telegram 推送
└── prompts/
    └── daily_memory_report.md # 日报生成 Prompt 模板
```

## 快速启动

```bash
# 1. 克隆
git clone https://github.com/<your-username>/memory-watch.git
cd memory-watch

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置（复制模板，填入真实 Key）
cp .env.example .env
# 编辑 .env，填入：
#   MINIMAX_API_KEY=your_key
#   TELEGRAM_BOT_TOKEN=your_token
#   TELEGRAM_CHAT_ID=your_chat_id

# 4. 运行一次（富途 OpenD 可选，不开则自动走 Yahoo Finance）
python main.py
```

## 配置说明

| 变量 | 说明 |
|------|------|
| `MINIMAX_API_KEY` | [MiniMax API Key](https://platform.minimax.chat/)，用于生成 AI 日报 |
| `TELEGRAM_BOT_TOKEN` | Telegram Bot Token，[@BotFather](https://t.me/BotFather) 创建 |
| `TELEGRAM_CHAT_ID` | 接收推送的 Chat ID， [@userinfobot](https://t.me/userinfobot) 获取 |
| `FUTU_HOST` / `FUTU_PORT` | 富途 OpenD 地址（可选，不开则用 Yahoo Finance） |

> **安全提示**：`.env` 文件已加入 `.gitignore`，不会提交到 GitHub。请勿将真实 Key 写入代码。

## 新闻时效与去重

- 所有新闻强制 30 天时效过滤
- 两层去重：URL 精确去重 + 标题 Bigram Jaccard 相似度（阈值 0.6）
- Tom's Hardware 等高价值媒体已在 TrendForce Google News RSS 中覆盖，不重复抓取

## 评分维度

| 维度 | 满分 | 信号来源 |
|------|------|----------|
| 行情相对强弱 | 1/1 | 5D/20D 超额收益 vs SOXX |
| DRAM / NAND 价格信号 | 1/1 | 合约价涨幅、现货价走势 |
| HBM 供需信号 | 1/1 | 缺货报道、产能新闻 |
| 同行验证 | 1/1 | Micron / SK hynix / Samsung / Nanya |
| 下游需求 | 1/1 | NVIDIA / 云厂商 CapEx / AI Server |

## 自动化运行（macOS）

```bash
# 编辑 crontab
crontab -e

# 每天早上 8:30 运行
30 8 * * * cd /path/to/memory-watch && /usr/bin/python3 main.py >> memory-watch.log 2>&1
```

## 免责声明

- 本项目仅供个人学习研究，不构成任何投资建议
- 代码不预测股价，不推荐买卖，不对任何投资收益负责
- 生成内容来自公开新闻，准确性依赖数据源，不对内容负责

## License

MIT
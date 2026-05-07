# 存储股日报系统 (Memory-Watch)

自动化存储产业链分析系统，跟踪美光(Micron)、闪迪(SanDisk)、SK hynix、Samsung 等公司。

## ⚠️ 免责声明

- 本项目仅用于个人信息整理和研究辅助
- **不构成投资建议**
- 不包含自动交易功能
- 不调用富途交易接口
- 所有 API key 使用环境变量

## 系统架构

```
定时任务
  ↓
富途 OpenAPI 获取行情
  ↓
行业信息抓取模块
  ↓
关键词分类与证据提取
  ↓
信号打分模块
  ↓
MiniMax 生成中文日报
  ↓
推送到 Telegram
  ↓
保存 Markdown 日报和原始数据
```

## 目录结构

```
memory-watch/
├── config/
│   ├── stocks.yaml        # 股票配置
│   ├── keywords.yaml      # 关键词体系
│   └── sources.yaml       # 新闻源配置
├── sources/
│   ├── futu_quotes.py     # 富途行情
│   ├── trendforce.py      # TrendForce 新闻
│   ├── news.py            # 通用新闻
│   └── company_ir.py      # 公司 IR
├── analysis/
│   ├── signal_extractor.py # 信号提取
│   ├── scoring.py          # 评分系统
│   └── relative_strength.py # 相对强弱
├── llm/
│   └── minimax_client.py   # MiniMax API
├── push/
│   └── telegram.py         # Telegram 推送
├── prompts/
│   └── daily_memory_report.md
├── data/
│   ├── raw/               # 原始行情和新闻
│   └── processed/         # 处理后的信号
├── reports/               # 日报输出
├── main.py
├── requirements.txt
└── .env.example
```

## 环境配置

### 1. 富途 OpenD

下载并启动[富途 OpenD](https://www.futu5.com/)，默认连接：
- Host: `127.0.0.1`
- Port: `11111`

### 2. 环境变量

复制 `.env.example` 为 `.env`，填入你的 key：

```bash
# MiniMax API
MINIMAX_API_KEY=your_key_here
MINIMAX_BASE_URL=https://api.minimax.chat/v1
MINIMAX_MODEL=MiniMax-Text-01

# 富途
FUTU_HOST=127.0.0.1
FUTU_PORT=11111

# Telegram
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

## 运行

```bash
# 手动运行
python main.py

# 设置定时任务 (crontab)
# 每天早上 8:30 运行
30 8 * * * cd /path/to/memory-watch && python main.py
```

## 输出文件

运行成功后生成：
- `reports/YYYY-MM-DD.md` - 日报
- `data/raw/YYYY-MM-DD_quotes.json` - 行情原始数据
- `data/raw/YYYY-MM-DD_news.json` - 新闻原始数据
- `data/processed/YYYY-MM-DD_signals.json` - 处理后的信号

## 评分系统

每天 0-5 分，五个维度：
1. 行情相对强弱 (MU vs SOXX)
2. DRAM/NAND 价格信号
3. HBM 供需信号
4. 同行/竞争对手验证
5. 下游需求验证
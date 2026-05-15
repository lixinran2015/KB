# Stock KB - 股票知识库

个人投资者的本地股票知识库系统，覆盖 A 股 AI 与机器人产业链，支持数据自动采集、智能评分、估值分析和交互式看板。

---

## 核心功能

### 1. 产业地图
三层导航结构：
- **产业列表**：人工智能、机器人等产业的卡片式入口
- **产业详情**：上游 → 中游 → 下游 文档目录结构，每个环节展示标的数量、平均评分、价值链占比
- **股票列表**：环节内所有标的，附带智能画像标签

**股票画像标签**（基于财务数据自动计算）：
- 👑 龙头 / 🥈 龙二（评分前2）
- 🛡️ 中军（评分 3.0~4.0）
- 📈 业绩增长（营收/净利增长 > 30%）
- 📉 业绩下滑（营收/净利负增长）
- 💎 高毛利（毛利率 > 40%）
- 🏦 机构重仓（公募持仓 > 10%）
- 🦄 高分白马（评分 ≥ 4.5）

### 2. 个股档案
- 📊 财务评分雷达图（毛利率、净利率、营收增长、净利增长、ROE）
- 📈 估值矩阵（PE/PB/PS）+ **历史分位**（<30%低估、30-70%合理、>70%高估）
- 💡 决策建议（评分 + 估值 → 强烈关注/观望/谨慎/回避）
- 🏆 同环节排名
- 📉 历史评分趋势图
- 🎯 定性评分（全球排名、国产替代、客户健康度）

### 3. 关注清单与组合看板
- 多组合管理（"AI核心仓"、"机器人观察"）
- 筛选器（评分 ≥ 4.0、估值低估、环节筛选）
- 同环节横向对比雷达图
- 产业链仓位分布饼图
- 评分变化趋势图
- 拥挤度警示（公募持仓 > 15% 标红）

### 4. 触发器中心
- 📈 技术面触发器（成交量倍量、突破年线、板块强度）
- 📰 事件触发器管理（添加/查看事件，影响评分）
- 🗺️ 事件影响地图（自动标红/标绿关注清单中受影响股票）

### 5. 结构化知识库
**4 张核心表**：
- `industry_tree` — 全局统一 4 级行业分类树（制造业→汽车→汽车零部件→底盘与发动机系统）
- `concept_tag` — 统一概念标签池（人形机器人、新能源汽车、军工、低空经济等）
- `stock_industry_kb` — 个股绑定末级行业 + 业务简介
- `stock_concept_rel` — 个股-概念多对多关联

**管理页面**：
- 左侧行业树形导航（1~4级展开）
- 选中行业 → 右侧列出所有归属个股
- 个股编辑：修改行业、勾选概念标签、编辑业务简介
- 支持按概念筛选、模糊搜索（代码/名称/行业/概念）

### 6. CLI 工作流
```bash
# 初始化
python -m apps.cli.main init          # 创建数据库
python -m apps.cli.main init-kb       # 初始化知识库（行业树+概念标签+示范数据）

# 日常/季度更新
python -m apps.cli.main daily         # 日常增量更新
python -m apps.cli.main quarterly     # 季报季后完整更新（自动备份）

# 数据同步
python -m apps.cli.main sync          # 同步财务数据到数据库
python -m apps.cli.main sync-full     # 全量同步

# 评分与报告
python -m apps.cli.main score --all   # 全部股票评分
python -m apps.cli.main score --segment 光模块
python -m apps.cli.main report        # 生成 Markdown 个股报告

# 触发器与诊断
python -m apps.cli.main check-triggers
python -m apps.cli.main cache-stats   # 数据库统计
python -m apps.cli.main validate      # 配置校验

# 数据维护
python -m apps.cli.main revise --stock 300308 --period 2024Q1
python -m apps.cli.main rollback      # 回滚到最近备份

# 产业数据补充
python -m apps.cli.main enrich-industry --industry robot --apply
```

---

## 技术架构

```
┌─────────────────────────────────────────────┐
│  Streamlit Dashboard (交互看板)              │
│  - 产业地图 / 个股档案 / 关注清单 / 触发器    │
│  - 知识库管理页面                           │
├─────────────────────────────────────────────┤
│  CLI (命令行入口)                            │
│  - daily / quarterly / sync / score ...     │
├─────────────────────────────────────────────┤
│  Engines (业务引擎)                          │
│  - ScoringEngine   按环节独立阈值评分         │
│  - ValuationEngine 多指标估值 + 历史分位      │
│  - TriggerEngine   技术面触发检测             │
│  - ReportEngine    Jinja2 Markdown 报告       │
│  - WatchlistManager 关注清单管理              │
├─────────────────────────────────────────────┤
│  Adapters (数据适配器，熔断降级)              │
│  - AKShareAdapter  → CacheAdapter → Mock     │
│  - TushareIndustryAdapter (概念板块补充)      │
├─────────────────────────────────────────────┤
│  Domain (领域模型 + 时序数据库)               │
│  - SQLite + SQLAlchemy ORM                  │
│  - 财务数据 / 评分结果 / 触发事件 / 关注清单  │
│  - 知识库: industry_tree / concept_tag ...  │
├─────────────────────────────────────────────┤
│  Config (配置驱动)                           │
│  - scoring_rules.yml    环节独立评分阈值      │
│  - valuation_rules.yml  环节独立估值阈值      │
│  - stocks.yml           股票清单 + 环节归属   │
│  - industries/*.yml     产业链结构定义        │
└─────────────────────────────────────────────┘
```

---

## 目录结构

```
stock-kb/
├── apps/
│   ├── cli/main.py              # CLI 命令入口
│   └── dashboard/
│       ├── app.py               # Streamlit 主入口
│       └── pages/
│           ├── 1_首页.py
│           ├── 2_产业地图.py     # 三层导航 + 股票画像
│           ├── 3_个股档案.py     # 雷达图 + 估值 + 决策
│           ├── 4_关注清单.py     # 组合 + 筛选 + 对比
│           ├── 5_触发器中心.py   # 技术/事件触发器
│           └── 6_知识库管理.py   # 行业树 + 概念标签管理
├── packages/
│   ├── domain/
│   │   ├── models.py            # SQLAlchemy 模型（12张表）
│   │   ├── database.py          # 数据库初始化 + 连接
│   │   └── locks.py             # 工作流锁 + 备份回滚
│   ├── engines/
│   │   ├── scoring_engine.py    # 评分引擎
│   │   ├── valuation_engine.py  # 估值引擎（含历史分位）
│   │   ├── trigger_engine.py    # 触发器引擎
│   │   ├── report_engine.py     # 报告生成
│   │   └── watchlist_manager.py # 关注清单管理
│   ├── adapters/
│   │   ├── akshare_adapter.py   # AKShare 数据适配
│   │   ├── tushare_industry_adapter.py  # Tushare 概念板块
│   │   ├── cache_adapter.py     # 本地 SQLite 缓存
│   │   └── mock_adapter.py      # 测试用 Mock 数据
│   └── config/
│       └── loader.py            # YAML 配置加载
├── config/
│   ├── scoring_rules.yml        # 评分规则（光模块/服务器/减速器/机器人...）
│   ├── valuation_rules.yml      # 估值规则
│   ├── stocks.yml               # 股票清单 (~1000只)
│   ├── triggers.yml             # 触发器模板
│   └── industries/
│       ├── ai.yml               # AI 产业链结构
│       └── robot.yml            # 机器人产业链结构
├── scripts/
│   ├── init_kb_data.py          # 知识库初始化（行业树 + 概念标签 + 示范数据）
│   └── migrate_stocks_to_kb.py  # stocks.yml 迁移到知识库
├── docs/
│   └── stocks/                  # Markdown 个股报告
├── data/
│   ├── stock_kb.sqlite          # 主数据库
│   └── cache/                   # 适配器缓存
└── tests/                       # 单元/集成/E2E 测试
```

---

## 安装与配置

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

核心依赖：`streamlit`, `plotly`, `pandas`, `sqlalchemy`, `akshare`, `pyyaml`

### 2. 配置环境变量

```bash
# .env 文件
TUSHARE_TOKEN=your_tushare_token_here
```

Tushare Token 用于概念板块数据补充，非必需（系统会自动降级到 Mock 数据）。

### 3. 初始化数据库与知识库

```bash
# 创建数据库表
python -m apps.cli.main init

# 初始化知识库（行业树 + 概念标签 + 万向钱潮示范数据）
python -m apps.cli.main init-kb

# 将 stocks.yml 中的股票迁移到知识库
python -m apps.cli.main migrate-kb  # 或 python -m scripts.migrate_stocks_to_kb
```

### 4. 启动 Dashboard

```bash
streamlit run apps/dashboard/app.py
```

### 5. 运行日常更新

```bash
# 同步财务数据
python -m apps.cli.main sync

# 计算评分
python -m apps.cli.main score --all
```

---

## 数据库核心表

| 表名 | 说明 |
|------|------|
| `stock_financials` | 财务指标时序数据（营收、毛利、ROE、PE 等） |
| `score_results` | 评分结果（综合评分、财务评分、环节排名、数据血缘） |
| `trigger_events` | 事件触发器（政策、财报、合并等） |
| `watchlists` / `watchlist_items` | 关注清单与组合持仓 |
| `qualitative_scores` | 定性评分（全球排名、国产替代、客户健康度） |
| `workflow_runs` | 工作流执行日志（带备份路径） |
| `industry_tree` | **行业分类树**（4级自关联） |
| `concept_tag` | **概念标签池** |
| `stock_industry_kb` | **个股知识库**（绑定末级行业 + 业务简介） |
| `stock_concept_rel` | **个股-概念关联**（多对多） |

---

## 评分与估值体系

### 按环节独立阈值

不同环节财务基准完全不同，举例：

| 指标 | 光模块（优秀） | 服务器代工（优秀） | 减速器（优秀） |
|------|--------------|-----------------|--------------|
| 毛利率 | > 40% | > 12% | > 35% |
| 净利率 | > 15% | > 5% | > 15% |
| 营收增长 | > 50% | > 30% | > 40% |

### 估值历史分位

- 优先计算历史分位（需 ≥5 条历史记录）
- < 30% 分位 → 低估 | 30%~70% → 合理 | > 70% → 高估
- 历史数据不足时，回退到阈值规则（PE<30 cheap 等）

---

## 数据血缘

每个评分结果记录：
- `config_version`: 如 `scoring_rules.yml:2.0`
- `data_source_versions`: 如 `{"AKShareAdapter": "1.12.0"}`
- `workflow_run_id`: 关联工作流执行记录
- `ranking_in_segment`: 同环节排名

---

## 工作流事务与回滚

| 工作流 | 事务策略 | 回滚方式 |
|--------|---------|---------|
| `daily` | 子步骤独立事务 | 无 |
| `quarterly` | 整体单一事务 + 自动快照 | 失败自动回滚 |
| `sync-full` | 强制快照 | 手动 rollback |

---

## License

个人学习研究使用。

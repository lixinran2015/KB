# 股票知识库（Stock KB）设计文档

**版本**: v2.0 | **日期**: 2026-05-15 | **状态**: 待实现

---

## 目录

- [1. 概述](#1-概述)
- [2. 目标用户与场景](#2-目标用户与场景)
- [3. Monorepo 目录结构](#3-monorepo-目录结构)
- [4. 核心功能模块](#4-核心功能模块)
  - [4.1 产业地图](#41-产业地图)
  - [4.2 个股财务档案（评分卡）](#42-个股财务档案评分卡)
  - [4.3 估值体系](#43-估值体系)
  - [4.4 决策框架](#44-决策框架)
  - [4.5 关注清单与组合看板](#45-关注清单与组合看板)
  - [4.6 行情触发器](#46-行情触发器)
- [5. 数据架构](#5-数据架构)
- [6. 文档生成策略](#6-文档生成策略)
- [7. 用户界面设计](#7-用户界面设计)
- [8. CLI 工作流](#8-cli-工作流)
- [9. MVP 优先级](#9-mvp-优先级)
- [10. 技术栈](#10-技术栈)
- [11. 扩展性设计](#11-扩展性设计)
- [附录 A. 完整数据库 Schema](#附录-a-完整数据库-schema)
- [附录 B. 完整评分规则配置](#附录-b-完整评分规则配置)
- [附录 C. 产业链分类](#附录-c-产业链分类)

---

## 1. 概述

Stock KB 是一个面向个人投资者的本地股票知识库系统，采用**"文档 + 程序"双轨架构**：

| 层级 | 载体 | 职责 |
|------|------|------|
| 文档层 | Markdown | 产业图谱、深度分析笔记，支持手动精修 |
| 程序层 | Python + Streamlit | 自动采集数据、计算评分、检测触发器、生成交互看板 |

**核心解决三个投资决策问题**：

1. **买什么方向** → 产业地图（AI / 机器人产业链）
2. **买哪只股** → 个股财务档案 + 评分卡 + 横向对比
3. **什么时候买** → 事件驱动 + 技术面触发器 + 决策建议

---

## 2. 目标用户与场景

**用户画像**：个人股票分析师 / 进阶投资者，具备产业研究能力，需要系统化的数据支持。

**核心场景**：

| 场景 | 频率 | 使用功能 |
|------|------|----------|
| 每季度财报季后批量更新评分 | 季度 | `cli quarterly` + 首页仪表盘 |
| 日常开盘后查看预警 | 每日 | 首页仪表盘 + 触发器中心 |
| 研究新产业链 | 不定期 | 产业地图 + Markdown 笔记 |
| 同环节选股对比 | 每周 | 关注清单横向对比 |

---

## 3. Monorepo 目录结构

```
stock-kb/
├── packages/
│   ├── domain/              # 领域模型 + 时序数据库
│   │   ├── models.py
│   │   ├── database.py
│   │   └── schema.sql
│   ├── adapters/            # 数据源适配器（熔断降级）
│   │   ├── base.py
│   │   ├── akshare_adapter.py
│   │   ├── cache_adapter.py
│   │   └── manual_adapter.py
│   ├── engines/             # 业务引擎
│   │   ├── scoring_engine.py
│   │   ├── valuation_engine.py
│   │   ├── trigger_engine.py
│   │   └── report_engine.py
│   └── ui/                  # Streamlit 组件
│       └── components/
├── apps/
│   ├── cli/                 # 命令行入口
│   │   └── main.py
│   └── dashboard/           # Streamlit 主应用
│       ├── app.py
│       └── pages/
│           ├── 1_home.py
│           ├── 2_industry_map.py
│           ├── 3_stock_profile.py
│           ├── 4_watchlist.py
│           └── 5_trigger_center.py
├── config/                  # 配置驱动核心
│   ├── industries/          # ai.yml, robot.yml
│   ├── scoring_rules.yml
│   ├── valuation_rules.yml
│   ├── stocks.yml
│   └── triggers.yml
├── docs/                    # Markdown 知识库
│   ├── _templates/          # Jinja2 模板
│   ├── industries/          # 产业图谱（自动+手动）
│   ├── stocks/              # 个股档案
│   └── triggers/            # 事件日志
├── data/
│   └── stock_kb.sqlite
├── tests/
└── pyproject.toml
```

---

## 4. 核心功能模块

### 4.1 产业地图

**定位**：解决"买什么方向"。

产业链通过 YAML 配置定义，支持任意扩展：

```yaml
# config/industries/ai.yml
name: 人工智能
upstream:
  name: 算力底座
  segments:
    - name: 光模块/CPO
      value_chain_pct: 0.08
      localization_rate: 0.60
      key_stocks: [300308, 300502]
    - name: GPU/ASIC芯片
      value_chain_pct: 0.35
      localization_rate: 0.05
    # ... 更多环节

midstream:
  name: 模型平台
  segments:
    - name: 数据要素
      sub_segments:
        - name: 数据采集与标注
        - name: 数据存储与管理
    - name: 大模型厂商
    - name: 算法公司
```

**展示方式**：
- Streamlit 使用 Plotly Sunburst 交互式展示
- 节点颜色：绿色=高评分，红色=低评分，灰色=数据缺失
- 点击下钻到个股列表

> 完整产业链分类见 [附录 C](#附录-c-产业链分类)。

---

### 4.2 个股财务档案（评分卡）

**定位**：解决"买哪只股"。

#### 基础信息标签

```yaml
# config/stocks.yml
stocks:
  - code: "300308.SZ"
    name: "中际旭创"
    segment: "光模块"        # 决定使用哪套评分阈值
    style: "白马股"          # 白马股 / 弹性小票 / 次新股
    market_cap_tier: "大盘"   # 大盘(>500亿) / 中盘 / 小盘
```

#### 财务指标评分（按环节独立阈值）

**核心设计原则**：不同环节的财务基准完全不同。光模块毛利率 35% 很正常，服务器代工毛利率仅 8-10%，不能用同一套阈值。

**示例对比**：

| 指标 | 光模块阈值 | 服务器代工阈值 | 理由 |
|------|-----------|--------------|------|
| 毛利率(优秀) | >40% | >12% | 代工模式天然低毛利 |
| 净利率(优秀) | >15% | >5% | 同上 |
| 营收增长(优秀) | >50% | >30% | 代工增速预期较低 |

> 完整评分规则配置（含减速器、默认环节）见 [附录 B](#附录-b-完整评分规则配置)。

#### 定性评分（首次录入，按需更新）

| 维度 | 权重 | 5分标准 | 维护频率 |
|------|------|---------|----------|
| 全球竞争地位 | 15% | 全球Top 2 | 仅在格局重大变化时更新 |
| 国产替代空间 | 10% | 国产化率<20%，有突破 | 同上 |
| 客户结构健康度 | 10% | 前五大<30%，客户分散 | 同上 |

**维护策略**：首次配置时录入。超过 90 天未更新时，Streamlit 显示提醒角标，但不阻塞使用。

#### 市场空间维度（手动录入）

- TAM（全球可触达市场，亿美元）
- 当前渗透率
- 业绩兑现时间（2024H2 / 2025 / 2026+）

#### 评分计算

```
综合评分 = 财务评分(权重70%) + 定性评分(权重30%)
```

**缺失数据处理**：
- 缺失率 > 50% → 标记 `INSUFFICIENT_DATA`，不输出总分
- 缺失率 ≤ 50% → 对有效指标重新归一化权重后计算
- 异常值（如毛利率 > 100%）→ 标记 `DATA_QUALITY_ISSUE`

**数据质量物理约束**：

| 指标 | 最小值 | 最大值 | 说明 |
|------|--------|--------|------|
| 毛利率 | -100% | 100% | 不可能超出此范围 |
| PE_TTM | 0 | 1000 | PE 不可能为负 |
| 营收增长 | -100% | 1000% | 超此范围视为异常 |

---

### 4.3 估值体系

**多指标矩阵，自动适配**：

| 方法 | 适用条件 | 优先级 |
|------|----------|--------|
| PE_TTM | 净利润 > 0 且 利润波动 < 50% | 1 |
| PS_TTM | 净利润 ≤ 0 或 利润波动 ≥ 50% 或 营收增速 > 50% | 2 |
| PB | 重资产行业（固定资产/总资产 > 40%） | 3 |

**历史分位判断**：
- 低估：历史分位 < 30%
- 合理：30% ~ 70%
- 高估：> 70%

---

### 4.4 决策框架

评分必须输出可执行的行动建议：

| 综合评分 | 估值分位 | 建议行动 | 典型场景 |
|----------|----------|----------|----------|
| ≥ 4.5 | < 30% | **强烈关注** | 基本面优秀且低估，可建仓 |
| ≥ 4.0 | > 70% | **观望** | 基本面优秀但估值偏高，等回调 |
| ≥ 4.0 | 30%~70% | **关注** | 基本面优秀，估值合理，等催化剂 |
| < 3.0 | 任意 | **回避** | 基本面一般，暂不考虑 |

展示时附带：关注价位、 upcoming 催化剂、同环节排名。

---

### 4.5 关注清单与组合看板

**定位**：解决"我关注了哪些股票，当前状态如何"。

**核心数据结构**：

- `watchlists`：组合定义（"AI核心仓"、"机器人观察"）
- `watchlist_items`：组合内股票 + 状态（持仓/观察/预警/已退出）+ 价格提醒规则

**组合看板展示**：

```
┌─────────────────────────────────────────────────────────┐
│  我的关注清单                    [+ 添加股票]             │
├─────────────────────────────────────────────────────────┤
│  筛选: [全部 ▼] [评分>4 ▼] [估值低估 ▼] [有催化剂 ▼]       │
├─────────────────────────────────────────────────────────┤
│  股票    环节      评分   估值    催化剂      状态       │
│  中际旭创 光模块    4.6   偏高    1.6T出货    ▶ 持仓     │
│  新易盛   光模块    4.2   合理    -           ○ 观察     │
│  绿的谐波 减速器    3.8   合理    -           ⚠ 待重评   │
├─────────────────────────────────────────────────────────┤
│  [横向对比雷达图]  [产业链仓位分布]  [评分变化趋势]        │
└─────────────────────────────────────────────────────────┘
```

---

### 4.6 行情触发器

#### 事件驱动触发器

```yaml
# config/triggers.yml
templates:
  - id: nvda_earnings
    name: 英伟达财报
    category: ai
    auto_check: false
    impact_map:
      - {segment: 光模块, direction: positive}
      - {segment: 服务器代工, direction: positive}
      - {segment: GPU芯片, direction: negative}

  - id: sector_momentum
    name: 板块强度突破
    category: technical
    auto_check: true
    condition: "sector_rank <= 5"
```

**状态机定义**：

| 状态 | 可转换到 | 触发条件 | 超时规则 |
|------|----------|----------|----------|
| watching | triggered | 手动标记 / 自动检测 | 30天未触发 → expired |
| triggered | processed | 用户确认 | 7天未确认 → expired |
| processed | watching | 季度性事件重置 | - |
| expired | - | 终态 | - |

事件触发时，自动在关注清单中**标红/标绿**受影响的股票。

#### 技术面触发器（自动检测）

- 板块强度：板块涨幅排名进入全市场前 5
- 个股信号：评分 > 4 分股票出现成交量倍量或突破年线
- 拥挤度警示：公募持仓 > 15% 标红

---

## 5. 数据架构

### 5.1 数据库 Schema（核心表）

```sql
-- 财务指标（时序版本化）
CREATE TABLE stock_financials (
    stock_code       TEXT NOT NULL,
    report_period    TEXT NOT NULL,       -- 2024Q1
    snapshot_date    DATE NOT NULL,       -- 数据入库时间
    revenue          REAL, revenue_growth REAL,
    gross_margin     REAL, net_margin    REAL, roe REAL,
    net_profit       REAL, net_profit_growth REAL,
    pe_ttm           REAL, ps_ttm       REAL, pb REAL,
    northbound_pct   REAL, fund_hold_pct REAL,
    data_source      TEXT, is_filing     BOOLEAN DEFAULT 0,
    revision_seq     INTEGER DEFAULT 0,  -- 财报修正序号
    is_revised       BOOLEAN DEFAULT 0,  -- 是否被后续修正覆盖
    PRIMARY KEY (stock_code, report_period, snapshot_date)
);

-- 评分结果（支持历史对比）
CREATE TABLE score_results (
    stock_code        TEXT NOT NULL,
    report_period     TEXT NOT NULL,
    scored_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_score       REAL, financial_score REAL, qualitative_score REAL,
    breakdown         TEXT, raw_values    TEXT, benchmarks TEXT,
    ranking_in_segment INTEGER, total_in_segment INTEGER,
    config_version    TEXT,               -- 数据血缘：配置版本
    workflow_run_id   INTEGER,            -- 数据血缘：工作流ID
    PRIMARY KEY (stock_code, report_period, scored_at)
);

-- 事件触发器
CREATE TABLE trigger_events (
    id           INTEGER PRIMARY KEY,
    template_id  TEXT NOT NULL,
    status       TEXT,                    -- watching / triggered / processed / expired
    impact_score INTEGER,
    related_stocks TEXT,                  -- JSON
    created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 关注清单
CREATE TABLE watchlists (id INTEGER PRIMARY KEY, name TEXT NOT NULL);
CREATE TABLE watchlist_items (
    watchlist_id INTEGER, stock_code TEXT,
    status TEXT, alert_rules TEXT,        -- JSON: {"price_below": 100}
    PRIMARY KEY (watchlist_id, stock_code)
);
```

> 完整 Schema（含配置版本表、工作流日志表等）见 [附录 A](#附录-a-完整数据库-schema)。

### 5.2 数据源适配器（熔断降级）

**降级链路**：AKShare → 本地缓存 → 手动录入 → 空数据兜底

```python
def fetch_with_fallback(self, stock_code: str) -> pd.DataFrame:
    try:
        df = self.fetch(stock_code)           # L1: AKShare
        self.cache.save(stock_code, df)
        return df
    except APIChangedError:
        cached = self.cache.load(stock_code)  # L2: 缓存
        if cached is not None: return cached
        return self._try_manual(stock_code)   # L3: 手动
    except DataNotFoundError:
        return self._try_manual(stock_code)
    except Exception as e:                    # L4: 终极兜底
        logging.critical(f"All sources failed for {stock_code}: {e}")
        return self._empty_dataframe(stock_code, status="UNAVAILABLE")
```

**关键设计**：即使所有数据源失败，也返回带标记的空 DataFrame，避免调用方 `AttributeError`。

### 5.3 缓存策略

| 数据类型 | 缓存时长 | 存储位置 |
|----------|----------|----------|
| 行情数据 | 24 小时 | `data/cache/` SQLite |
| 财务数据 | 7 天 | 同上 |
| 首页仪表盘显示缓存命中率 | - | - |

### 5.4 配置校验

系统启动时所有 YAML 通过 Pydantic Schema 校验：

- 股票代码格式：`^\d{6}\.(SZ|SH|BJ)$`
- 评分权重和：`0.95 ~ 1.05`
- 阈值格式：`>40`、`<=30`

校验失败时报错到具体行号和字段，而非崩溃。

### 5.5 并发控制

- **工作流锁**：`fasteners` 文件锁确保同时只有一个 `daily`/`quarterly` 运行
- **事务边界**：`daily` 子步骤独立事务；`quarterly` 整体单一事务，失败回滚

### 5.6 财报修正机制

1. 公司发布财报修正公告
2. 用户运行 `cli revise --stock 300308 --period 2024Q1`
3. 原记录标记 `is_revised = 1`，插入新记录 `revision_seq + 1`
4. 自动重新计算该股票评分

### 5.7 日志与数据血缘

```python
# 日志：按 10MB 轮转，保留 5 个备份
RotatingFileHandler('data/logs/stock_kb.log', maxBytes=10*1024*1024, backupCount=5)
```

**数据血缘**：每个评分结果记录：
- `config_version`：如 `scoring_rules.yml:v2.0@2024-05-15`
- `data_source_versions`：`{"akshare": "1.12.0"}`
- `workflow_run_id`：关联工作流执行记录

---

## 6. 文档生成策略

**Jinja2 模板 + 手动插槽保护**

```markdown
<!-- AUTO-GENERATED: 2024-05-15 -->
<!-- 手动笔记请写入 upstream.notes.md -->

# 上游：算力底座

## 光模块
| 龙头股 | 评分 | 估值 |
|--------|------|------|
| {{ stocks['中际旭创'].name }} | {{ stocks['中际旭创'].score }} | {{ stocks['中际旭创'].pe }} |

<!-- MANUAL_BEGIN -->
<!-- 以下内容保留手动编辑，不会被覆盖 -->
<!-- MANUAL_END -->
```

**插槽保护机制**：生成器只替换 `MANUAL_BEGIN/END` 之外的区块，手动笔记永久保留。

**并行手动笔记文件**：每个 `.md` 对应一个 `.notes.md`，永不被覆盖。

---

## 7. 用户界面设计

### Page 1: 首页仪表盘

数据健康度 + 组合概览 + 最新触发器。顶部显示"运行日常更新"按钮。

### Page 2: 产业地图

Plotly Sunburst 交互式展示，节点颜色编码（绿/红/灰），点击下钻。

### Page 3: 个股档案（核心页面）

```
┌─────────────────────────────────────────────────────────┐
│  中际旭创 (300308.SZ) | 光模块 | 综合评分: 4.6            │
├─────────────────────────────────────────────────────────┤
│  [雷达图]          │  [估值矩阵: PE+PS]                    │
│  毛利率: 4.8       │  PE: 45x (65%分位)                   │
│  ROE: 3.5          │  PS: 8x  (40%分位)                   │
│  成长性: 5.0       │                                      │
│  竞争地位: 5.0     │                                      │
├─────────────────────────────────────────────────────────┤
│  市场空间: TAM $150亿 | 渗透率 15% | 兑现: 2024H2         │
├─────────────────────────────────────────────────────────┤
│  💡 建议: 基本面优秀，⚠️ 估值偏高，建议等PE<40x介入        │
├─────────────────────────────────────────────────────────┤
│  [加入关注清单]  [对比同类]  [历史评分]  [查看笔记]        │
└─────────────────────────────────────────────────────────┘
```

### Page 4: 关注清单

多组合切换、筛选器、横向对比雷达图、产业链仓位分布。

### Page 5: 触发器中心

事件时间线 + 技术面预警 + 事件影响地图（标红/标绿关注清单股票）。

---

## 8. CLI 工作流

```bash
# 日常更新（增量同步 + 评分 + 触发器检测）
python -m cli daily

# 季报季后完整更新（全量 + 评分 + 触发器 + 文档生成）
python -m cli quarterly

# 数据同步
python -m cli sync --quarter 2024Q1    # 增量
python -m cli sync-full                  # 全量（慎用，自动创建快照）

# 评分计算
python -m cli score --segment 光模块     # 单环节
python -m cli score --all                # 全部

# 触发器与诊断
python -m cli check-triggers             # 技术面检测
python -m cli validate                   # 配置与数据一致性校验
python -m cli cache-stats                # 缓存命中率

# 新增产业链（交互式引导）
python -m cli add-industry semiconductor
```

### 工作流事务与回滚

`quarterly` 工作流执行前自动创建数据库快照，失败时回滚：

```python
def quarterly():
    backup_path = create_snapshot()       # 1. 创建快照
    run_id = log_workflow_start(backup_path)
    try:
        with transaction():               # 2. 单一事务
            sync_full(); score_all(); check_triggers(); generate_docs()
        log_success(run_id)
    except Exception as e:
        rollback_to(backup_path)          # 3. 失败回滚
        log_failure(run_id, e)
        raise
```

**策略**：`daily` 子步骤独立事务（风险低）；`quarterly` 整体事务+快照回滚；`sync-full` 强制快照。

---

## 9. MVP 优先级

| 优先级 | 功能 | 理由 |
|--------|------|------|
| **P0** | AKShare 适配器 + 本地缓存 | 数据是核心基础 |
| **P0** | 按环节独立阈值财务评分 | 解决"买哪只"的核心问题 |
| **P0** | 关注清单 + 组合看板 | 用户买的是组合不是个股 |
| **P0** | `daily` / `quarterly` 一键工作流 | 降低维护负担 |
| **P0** | 首页仪表盘（数据健康度 + 组合概览） | 建立信任和日常习惯 |
| **P0** | 个股档案页（雷达图 + **行动建议**） | 评分必须能指导决策 |
| **P1** | 多指标估值矩阵（PE/PS/PB自动适配） | 不同行业估值方法不同 |
| **P1** | 关注清单横向对比 | 同环节选股必备 |
| **P1** | 技术面自动检测 + 板块强度 | 解决"什么时候买" |
| **P1** | Interactive 产业地图 | 比静态文档体验好10倍 |
| **P2** | 定性评分（竞争地位/国产替代/客户结构） | 首次录入后极少变更 |
| **P2** | 事件驱动 + 关联标的推荐 | 锦上添花 |
| **P2** | Jinja2 文档生成 + 手动插槽 | 长期维护才需要 |
| **P2** | 完整时序版本化 | 单人场景可延后 |
| **P3** | 新增产业链向导 | 当前2条产业链足够验证 |

---

## 10. 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| 语言 | Python 3.11+ | 主语言 |
| 依赖管理 | Poetry | 包管理 |
| 数据获取 | AKShare | A股财务/行情数据 |
| 数据库 | SQLite | 本地时序存储 |
| ORM | SQLAlchemy | 数据模型 |
| 前端 | Streamlit | 交互式看板 |
| 图表 | Plotly | 产业地图/雷达图 |
| 文档生成 | Jinja2 | Markdown 模板 |
| 配置 | YAML + Pydantic | 配置定义与校验 |
| 测试 | Pytest + fixtures | 单元/集成/E2E测试 |

---

## 11. 扩展性设计

### 新增产业链

1. `config/industries/` 新增 `semiconductor.yml`
2. `config/scoring_rules.yml` 新增该环节评分阈值
3. `config/stocks.yml` 关联股票代码
4. `cli add-industry semiconductor` 交互式引导
5. `cli daily` 自动抓取数据、计算评分

### 新增数据源

实现 `DataAdapter` 抽象基类即可接入：

```python
class TushareAdapter(DataAdapter):
    def fetch(self, stock_code: str) -> pd.DataFrame: ...
```

### 新增触发器类型

在 `config/triggers.yml` 新增模板，`trigger_engine.py` 自动识别。

### 可测试性设计

```
tests/
├── fixtures/                      # 标准测试数据集
│   ├── stock_300308_q1_2024.csv   # 正常数据
│   ├── stock_300308_invalid.csv   # 异常值（毛利率>100%）
│   └── stock_300308_missing.csv   # 缺失值
├── unit/
│   ├── test_scoring_engine.py     # 确定性输入=确定性输出
│   └── test_config_validation.py
├── integration/
│   ├── test_adapters.py           # 降级链路测试
│   └── test_workflows.py          # 回滚测试
└── e2e/
    └── test_dashboard.py          # Playwright
```

**Mock 适配器**：`MockAdapter(fixture_name)` 从 fixtures 加载固定数据，确保测试确定性。

**Streamlit 测试**：所有交互组件添加 `data-testid` 属性，便于 E2E 定位。

---

## 附录 A. 完整数据库 Schema

```sql
-- 财务指标表（支持时点回溯 + 财报修正）
CREATE TABLE stock_financials (
    stock_code       TEXT NOT NULL,
    report_period    TEXT NOT NULL,
    snapshot_date    DATE NOT NULL,
    revenue          REAL,
    revenue_growth   REAL,
    gross_margin     REAL,
    net_margin       REAL,
    roe              REAL,
    net_profit       REAL,
    net_profit_growth REAL,
    pe_ttm           REAL,
    ps_ttm           REAL,
    pb               REAL,
    northbound_pct   REAL,
    fund_hold_pct    REAL,
    data_source      TEXT,
    is_filing        BOOLEAN DEFAULT 0,
    revision_seq     INTEGER DEFAULT 0,
    is_revised       BOOLEAN DEFAULT 0,
    revised_by_snapshot DATE,
    revision_reason  TEXT,
    PRIMARY KEY (stock_code, report_period, snapshot_date)
);

-- 评分结果表（支持历史对比 + 数据血缘）
CREATE TABLE score_results (
    stock_code        TEXT NOT NULL,
    report_period     TEXT NOT NULL,
    scored_at         DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_score       REAL,
    financial_score   REAL,
    qualitative_score REAL,
    breakdown         TEXT,
    raw_values        TEXT,
    benchmarks        TEXT,
    ranking_in_segment INTEGER,
    total_in_segment  INTEGER,
    config_version    TEXT,
    data_source_versions TEXT,
    workflow_run_id   INTEGER,
    PRIMARY KEY (stock_code, report_period, scored_at)
);

-- 事件触发器表
CREATE TABLE trigger_events (
    id              INTEGER PRIMARY KEY,
    template_id     TEXT NOT NULL,
    instance_date   DATE,
    name            TEXT,
    category        TEXT,
    status          TEXT,
    impact_score    INTEGER,
    description     TEXT,
    related_stocks  TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 关注清单表
CREATE TABLE watchlists (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    description     TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE watchlist_items (
    watchlist_id    INTEGER,
    stock_code      TEXT,
    added_at        DATETIME,
    status          TEXT,
    notes           TEXT,
    alert_rules     TEXT,
    PRIMARY KEY (watchlist_id, stock_code)
);

-- 定性评分表（低频更新）
CREATE TABLE qualitative_scores (
    stock_code              TEXT PRIMARY KEY,
    global_ranking          INTEGER,
    localization_potential  INTEGER,
    customer_health         INTEGER,
    tam_usd_billion         REAL,
    current_penetration     REAL,
    catalyst_timeline       TEXT,
    last_updated            DATE,
    update_trigger_note     TEXT
);

-- 配置版本表（数据血缘追踪）
CREATE TABLE config_versions (
    id              INTEGER PRIMARY KEY,
    config_type     TEXT NOT NULL,
    version         TEXT NOT NULL,
    content_hash    TEXT,
    applied_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 工作流执行日志表
CREATE TABLE workflow_runs (
    id              INTEGER PRIMARY KEY,
    workflow_name   TEXT NOT NULL,
    status          TEXT,
    started_at      DATETIME,
    completed_at    DATETIME,
    backup_path     TEXT,
    error_message   TEXT
);

-- 最新有效财务数据视图（排除已被修正的记录）
CREATE VIEW latest_financials AS
SELECT * FROM stock_financials sf1
WHERE is_revised = 0
  AND snapshot_date = (
      SELECT MAX(snapshot_date) FROM stock_financials sf2
      WHERE sf2.stock_code = sf1.stock_code
        AND sf2.report_period = sf1.report_period
        AND sf2.is_revised = 0
  );
```

---

## 附录 B. 完整评分规则配置

```yaml
# config/scoring_rules.yml
version: "2.0"

financial_rules:
  - segment: 光模块
    metrics:
      - name: 毛利率
        weights: {excellent: ">40", good: ">30", fair: ">20", poor: "<20"}
        weight: 0.20
      - name: 净利率
        weights: {excellent: ">15", good: ">10", fair: ">5", poor: "<5"}
        weight: 0.10
      - name: 营收同比增长
        weights: {excellent: ">50", good: ">30", fair: ">10", poor: "<10"}
        weight: 0.15
      - name: 净利润同比增长
        weights: {excellent: ">60", good: ">30", fair: ">10", poor: "<10"}
        weight: 0.15
      - name: ROE
        weights: {excellent: ">20", good: ">15", fair: ">10", poor: "<10"}
        weight: 0.10

  - segment: 服务器代工
    metrics:
      - name: 毛利率
        weights: {excellent: ">12", good: ">8", fair: ">5", poor: "<5"}
        weight: 0.15
      - name: 净利率
        weights: {excellent: ">5", good: ">3", fair: ">1.5", poor: "<1.5"}
        weight: 0.10
      - name: 营收同比增长
        weights: {excellent: ">30", good: ">15", fair: ">5", poor: "<5"}
        weight: 0.20
      - name: 净利润同比增长
        weights: {excellent: ">30", good: ">15", fair: ">5", poor: "<5"}
        weight: 0.15
      - name: ROE
        weights: {excellent: ">15", good: ">12", fair: ">8", poor: "<8"}
        weight: 0.10

  - segment: 减速器
    metrics:
      - name: 毛利率
        weights: {excellent: ">35", good: ">25", fair: ">15", poor: "<15"}
        weight: 0.20
      - name: 净利率
        weights: {excellent: ">15", good: ">10", fair: ">5", poor: "<5"}
        weight: 0.10
      - name: 营收同比增长
        weights: {excellent: ">40", good: ">25", fair: ">10", poor: "<10"}
        weight: 0.15
      - name: 净利润同比增长
        weights: {excellent: ">50", good: ">30", fair: ">10", poor: "<10"}
        weight: 0.15
      - name: ROE
        weights: {excellent: ">20", good: ">15", fair: ">10", poor: "<10"}
        weight: 0.10

  - segment: 默认
    metrics:
      - name: 毛利率
        weights: {excellent: ">30", good: ">20", fair: ">10", poor: "<10"}
        weight: 0.20
      - name: 净利率
        weights: {excellent: ">15", good: ">10", fair: ">5", poor: "<5"}
        weight: 0.10
      - name: ROE
        weights: {excellent: ">20", good: ">15", fair: ">10", poor: "<10"}
        weight: 0.10
      - name: 营收同比增长
        weights: {excellent: ">30", good: ">20", fair: ">10", poor: "<10"}
        weight: 0.15
      - name: 净利润同比增长
        weights: {excellent: ">30", good: ">20", fair: ">10", poor: "<10"}
        weight: 0.15

qualitative_rules:
  - name: 全球竞争地位
    score_guide:
      5: 全球Top 2，技术领先1代以上
      4: 全球Top 3-5，技术同步
      3: 国内Top 1-2，追赶中
      2: 国内二线
      1: 无显著市场地位
    weight: 0.15

  - name: 国产替代空间
    score_guide:
      5: 国产化率<20%，有明确突破
      4: 国产化率20-40%，加速替代
      3: 国产化率40-60%
      2: 国产化率60-80%
      1: 国产化率>80%，空间饱和
    weight: 0.10

  - name: 客户结构健康度
    score_guide:
      5: 客户分散，前五大<30%，均为优质客户
      4: 前五大30-50%，大客户稳定
      3: 前五大50-70%，有一定风险
      2: 高度依赖单一大客户
      1: 客户结构恶化中
    weight: 0.10
```

---

## 附录 C. 产业链分类

### AI 产业链

| 层级 | 环节 | 细分领域 |
|------|------|----------|
| 上游 | 算力底座 | 光模块/CPO、GPU/ASIC芯片、PCB（高端）、服务器、液冷散热 |
| 中游 | 模型平台 | 大模型厂商、数据要素（数据采集标注/存储管理/交易流通）、算法公司 |
| 下游 | 应用落地 | 传媒游戏（AIGC）、办公软件、自动驾驶、AI+医疗、AI+教育 |

### 机器人产业链

| 层级 | 环节 | 细分领域 |
|------|------|----------|
| 上游 | 核心零部件 | 伺服电机、减速器（谐波/RV）、传感器（六维力/视觉）、控制器、丝杠 |
| 中游 | 本体制造 | 整机代工、系统集成 |
| 下游 | 场景落地 | 工业制造、医疗机器人、家用服务机器人 |

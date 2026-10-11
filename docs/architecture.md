# 系统架构与运行时序

> 状态：V1 implemented  
> 目的：说明模块边界、核心状态、一次研究的执行路径，以及当前单实例交付边界。

## 1. 总体架构

```mermaid
flowchart TB
    subgraph Delivery[交付层]
        WEB[React + TypeScript Console]
        CLI[Typer CLI]
        HTTP[FastAPI REST + SSE]
    end

    subgraph Application[应用层]
        RUNS[RunManager]
        LIVE[LiveResearchService]
        EVAL[LiveEvaluationService]
        CHECK[Provider / Extraction Checks]
    end

    subgraph Core[Agent Core]
        ENGINE[ResearchEngine]
        POLICY[ResearchPolicy]
        EXEC[ActionExecutor]
        REDUCER[StateReducer]
        LEDGER[BudgetLedger]
        STATE[ResearchState]
    end

    subgraph Evidence[检索与证据]
        CHUNK[Chunker]
        BM25[BM25 Context Selection]
        METRICS[Evidence Metrics]
        QUALITY[Source Quality]
        GROUND[Report Grounding]
    end

    subgraph Providers[外部 Provider]
        MOONSHOT[Moonshot / Kimi]
        TAVILY[Tavily]
        WEBPAGE[HTTPX + Trafilatura]
    end

    subgraph Persistence[持久化]
        SQLITE[(SQLite)]
        EVENTS[events.jsonl]
        JSON[State / Evidence / Metrics JSON]
        REPORT[report.md]
    end

    WEB --> HTTP
    CLI --> LIVE
    CLI --> EVAL
    HTTP --> RUNS --> LIVE
    LIVE --> ENGINE
    EVAL --> LIVE
    CHECK --> Providers
    ENGINE --> POLICY
    ENGINE --> EXEC
    ENGINE --> REDUCER
    ENGINE --> LEDGER
    REDUCER --> STATE
    EXEC --> MOONSHOT
    EXEC --> TAVILY
    EXEC --> WEBPAGE
    EXEC --> CHUNK --> BM25
    REDUCER --> METRICS
    REDUCER --> QUALITY
    EXEC --> GROUND
    RUNS --> SQLITE
    LIVE --> EVENTS
    LIVE --> JSON
    LIVE --> REPORT
```

## 2. 核心职责

| 模块 | 输入 | 输出 | 不负责 |
|---|---|---|---|
| `ResearchPolicy` | 只读研究状态与剩余预算 | 下一条 Action 或停止 | 网络调用、数据库写入 |
| `ActionExecutor` | Action 与当前状态 | ActionResult 和真实资源消耗 | 决定下一步、修改全局状态 |
| `StateReducer` | State、Action、Result | 新的 ResearchState | 调用 Provider、预算判断 |
| `BudgetLedger` | 资源估算与实际使用量 | 预算快照、超限拒绝 | 研究质量判断 |
| Evidence 模块 | 来源、Chunk、Evidence | 去重证据、指标、质量层级 | 决定研究动作 |
| Grounding 模块 | 报告草稿与 Evidence ID | 通过校验的结构化报告 | 自由补充无证据事实 |
| `RunManager` | API 创建/取消请求 | 后台任务与持久化状态 | Agent 策略逻辑 |

这种拆分让 Fixed 与 Adaptive 只替换 Policy，其他组件保持一致，从而减少评测中的混杂变量。

## 3. 一次研究的时序

```mermaid
sequenceDiagram
    actor User as 用户
    participant UI as React Console
    participant API as FastAPI / RunManager
    participant DB as SQLite
    participant Engine as ResearchEngine
    participant Policy as Policy
    participant Executor as ActionExecutor
    participant Provider as LLM / Search / Web

    User->>UI: 提交问题、策略和预算
    UI->>API: POST /api/v1/runs
    API->>DB: 创建 pending Run
    API-->>UI: 202 + run_id
    API->>Engine: 后台启动 Research Run
    Engine->>DB: 状态改为 running
    UI->>API: 建立 SSE 连接

    loop 直到完成、取消、失败或预算耗尽
        Engine->>Policy: 当前 State + BudgetStatus
        Policy-->>Engine: Action + reason + estimate
        Engine->>Engine: 预算预留
        Engine->>Executor: 执行 Action
        Executor->>Provider: 模型、搜索或页面请求
        Provider-->>Executor: 输出与 usage
        Executor-->>Engine: ActionResult
        Engine->>Engine: 结算预算并 Reduce State
        Engine->>DB: 保存 ActionRecord
        API-->>UI: SSE action event
    end

    Engine->>DB: 保存终态、证据、报告与 usage
    API-->>UI: SSE terminal run event
    UI->>API: 获取 Evidence 与 Report
```

## 4. Adaptive Budget 决策

Adaptive V1 是确定性规则策略，没有额外调用策略 LLM。它读取以下信号：

- `coverage`：Claim Cluster 覆盖与来源多样性的组合；
- `novelty`：新 Claim Cluster 和新来源比例；
- `source_diversity`：唯一来源数相对目标值；
- `source_quality_score`：唯一来源的平均质量；
- `conflict_ratio`：相近但极性相反的 Claim 比例；
- `low_novelty_streak`：连续低新增轮数；
- Token、搜索、页面抓取和剩余时间。

```mermaid
flowchart TD
    START[读取 ResearchState] --> PLAN{已有子问题?}
    PLAN -->|否| MAKE_PLAN[PLAN]
    PLAN -->|是| UNSEARCHED{存在未搜索子问题?}
    UNSEARCHED -->|是| SEARCH[SEARCH]
    UNSEARCHED -->|否| INITIAL{存在未建立初始证据的子问题?}
    INITIAL -->|是| FETCH_OR_EXTRACT[FETCH 或 EXTRACT_EVIDENCE]
    INITIAL -->|否| SUFFICIENT{全部达到证据目标?}
    SUFFICIENT -->|是| WRITE[WRITE_REPORT]
    SUFFICIENT -->|否| RESERVE{需要预留 Writer 预算或时间?}
    RESERVE -->|是| WRITE
    RESERVE -->|否| RANK[按冲突、覆盖、多样性和质量排序弱分支]
    RANK --> CANDIDATE{仍有高价值候选来源?}
    CANDIDATE -->|是| DEEPEN[FETCH / EXTRACT]
    CANDIDATE -->|否| MORE_SEARCH{允许新的搜索轮次?}
    MORE_SEARCH -->|是| SEARCH
    MORE_SEARCH -->|否| WRITE
```

## 5. 证据与报告约束

Evidence 并非模型返回什么就保存什么。系统执行以下检查：

1. Evidence 必须引用本次抓取并进入上下文的来源；
2. `support_span` 必须能在来源正文中回溯；
3. 同来源重复片段、近似 Claim 和重叠支持片段不会重复增加 Coverage；
4. 不同来源的近似 Claim 会进入同一个 Claim Cluster，但保留各自 Evidence；
5. Report assertion 必须绑定存在的 Evidence ID；
6. 渲染前会再次验证 assertion 与证据 Claim 的一致性；
7. 无证据章节会明确标记证据不足。

## 6. 持久化与实时更新

SQLite 是 API 的运行时事实来源，保存 Run、Action、Evidence、Report 和 Usage。每次完整
运行还会生成 JSON、JSONL 与 Markdown 文件，便于不依赖数据库进行审计。

前端在打开活动任务时连接 `/events/stream`：

- `run` 事件更新状态；
- `action` 事件增量更新 Timeline 和实时资源统计；
- 浏览器断线后使用 `Last-Event-ID` 继续读取遗漏事件；
- 终态到达后关闭流并读取 Evidence 与 Report。

取消运行会取消进程内异步任务，将状态保存为 `cancelled`，并从已保存 Action 中汇总取消前
的实际资源。正在执行的单个外部请求可能已经计费，但不会继续安排后续动作。

## 7. 运行状态

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> running
    pending --> cancelled
    running --> completed
    running --> completed_with_limitations
    running --> budget_exhausted
    running --> insufficient_evidence
    running --> failed
    running --> cancelled
    pending --> failed: API 进程重启
    running --> failed: Provider / 校验 / 进程异常
```

## 8. 当前部署边界

V1 面向本地演示和单实例运行：

- SQLite 无需独立数据库服务；
- RunManager 使用 API 进程内任务；
- API 重启会把未完成任务标记为失败，避免产生永远处于 running 的记录；
- SSE 从 SQLite 回放持久化事件。

多实例或生产部署需要把进程内任务迁移到外部队列，并使用 PostgreSQL 与共享事件通道。
这些能力不属于当前 V1。

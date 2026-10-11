# 技术栈与交付架构

> 状态：V1 技术方案 v0.1  
> 目标：确定 Budgeted Research Agent 的工程边界、技术选型、交付形态与开发顺序。  
> 原则：Agent 决策与评测优先，展示层服务于可观测性，不反向绑架核心设计。

## 1. 总体结论

V1 采用以下交付形态：

```text
Agent Core Python Package
    ├── CLI：开发、调试和批量实验
    ├── FastAPI：任务管理、查询与事件流
    └── React Web：运行控制台和实验展示
```

系统从第一天起保持 Core 与交付层解耦：

- CLI、API 和测试调用同一个 Research Engine；
- Web UI 不包含研究策略逻辑；
- Fixed Policy 与 Adaptive Policy 复用同一套执行组件；
- 外部模型、搜索和网页抓取通过 Provider 接口接入；
- 所有重要状态与动作使用 Pydantic 模型表达；
- 所有运行都产生可保存、可回放的事件轨迹。

V1 最终需要 Web 页面，但开发顺序必须是 Core 优先。CLI 闭环未跑通之前不开始正式前端开发。

## 2. 架构总览

```text
┌───────────────────────────────────────────────────────────────┐
│ Delivery                                                      │
│                                                               │
│  CLI / Typer        FastAPI REST + SSE        React Console   │
└───────────────┬───────────────┬───────────────────────┬───────┘
                │               │                       │
                └───────────────▼───────────────────────┘
                        Application Services
                RunService / EvaluationService / Queries
                                │
┌───────────────────────────────▼───────────────────────────────┐
│ Agent Core                                                    │
│                                                               │
│  ResearchEngine → Policy → Action → Executor → StateReducer   │
│         │              │                      │                │
│         ├─ FixedDepthPolicy                  ├─ EvidenceStore  │
│         └─ AdaptiveBudgetPolicy              ├─ BudgetLedger   │
│                                              └─ TraceRecorder  │
└───────────────────────────────┬───────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────┐
│ Providers                                                     │
│                                                               │
│  LLMProvider      SearchProvider      PageFetcher             │
│  Moonshot/Kimi    Tavily first        HTTPX + Trafilatura      │
└───────────────────────────────┬───────────────────────────────┘
                                │
┌───────────────────────────────▼───────────────────────────────┐
│ Persistence and Artifacts                                     │
│                                                               │
│  SQLite / SQLAlchemy     JSONL Traces     Markdown Reports     │
└───────────────────────────────────────────────────────────────┘
```

## 3. Python 与项目管理

### 3.1 Python 版本

V1 使用 Python 3.11。

原因：

- 异步、typing 和 dataclass 能力足够；
- LLM、FastAPI、网页处理和评测生态兼容成熟；
- 与参考实现的运行要求接近；
- 避免为了追求最新解释器增加依赖兼容风险。

### 3.2 依赖和构建

使用：

- `uv`：环境、依赖锁定和命令运行；
- `backend/pyproject.toml`：Python 项目元数据和工具配置；
- `backend/src/` layout：避免测试意外导入工作目录中的未安装代码。

第一版不拆分成多个 Python package，也不采用微服务。Agent Core、API、CLI
和评测代码统一放在 `backend/` 下，通过 Python 模块边界隔离；React 前端单独
放在 `frontend/` 下，避免两套工具链和测试目录相互混杂。

## 4. Agent Core

### 4.1 状态和 Schema

使用 Pydantic v2 定义核心模型，包括但不限于：

```text
ResearchRequest
ResearchBudget
ResearchState
SubQuestion
SearchQuery
SearchResult
SourceDocument
DocumentChunk
EvidenceItem
Claim
Action
ActionRecord
UsageRecord
BudgetLedger
ResearchReport
RunSummary
```

所有跨模块输入输出都使用明确类型，禁止使用任意嵌套字典作为长期核心状态。

### 4.2 编排方式

V1 使用自研的显式异步状态循环：

```python
while not policy.should_stop(state):
    action = policy.next_action(state)
    reservation = budget.reserve(action)
    result = await executor.execute(action)
    state = reducer.apply(state, action, result)
    budget.settle(reservation, result.usage)
    tracer.record(state, action, result)
```

V1 不把 LangGraph 作为核心依赖。

原因：

- 本项目的核心展示点正是状态、动作、预算和停止逻辑；
- 显式循环便于单元测试、消融和回放；
- 避免框架内部状态掩盖 Policy 的真实行为；
- 后续可以基于相同接口提供 LangGraph Adapter，而不改变策略语义。

### 4.3 Policy 边界

Policy 只读取不可变的 State View，并输出下一步 Action 或 Stop Decision；它不直接调用模型、搜索或数据库。

```text
FixedDepthPolicy
    一次性或按阶段产生固定动作

AdaptiveBudgetPolicy
    根据证据状态和预算产生下一动作
```

Action Executor 负责执行动作，State Reducer 负责更新状态，Budget Ledger 负责资源预留和结算。

## 5. LLM Provider

### 5.1 默认服务

V1 暂定使用 Moonshot/Kimi API。官方接口兼容 OpenAI API 格式，因此使用 OpenAI Python SDK 的异步客户端接入：

```python
from openai import AsyncOpenAI

client = AsyncOpenAI(
    api_key=settings.moonshot_api_key,
    base_url=settings.moonshot_base_url,
)
```

默认配置：

```env
LLM_PROVIDER=moonshot
MOONSHOT_API_KEY=
MOONSHOT_BASE_URL=https://api.moonshot.cn/v1
MOONSHOT_MODEL=
```

API Key 只通过环境变量或本地密钥管理提供，不能进入 Git、日志、运行轨迹或前端。

官方接入参考：[Kimi API 快速开始](https://platform.kimi.com/docs/get-api-key)。

### 5.2 模型不写死

具体模型名称保留为配置项。模型选择需要在开发前通过账户实际可用列表和价格确认。

Provider 接口至少支持：

- 普通文本生成；
- JSON/结构化输出；
- 流式输出；
- 超时与重试；
- usage 提取；
- 请求级 metadata；
- 按步骤记录模型、参数和费用。

Planner、Evidence Extractor 和 Writer 的模型配置相互独立。V1 可以先使用同一个模型，完成成本实验后再考虑“强模型规划/写作 + 便宜模型抽取”的分级策略。

### 5.3 Token 与费用统计

模型调用后以 API 返回的 usage 为最终消耗来源，记录：

```text
input_tokens
output_tokens
cached_tokens（如果可用）
total_tokens
latency_ms
model
provider
estimated_cost
actual_cost
```

模型价格保存在版本化配置中，不散落在业务代码。调用前的预算预留使用保守估算，调用后根据真实 usage 结算差额。

### 5.4 不使用内置联网搜索

即使 Kimi 提供联网工具，V1 也不将其作为核心搜索路径，因为黑盒搜索会削弱：

- 搜索次数控制；
- 页面和来源追踪；
- Baseline 与 Adaptive 的公平对比；
- Search Provider 成本统计；
- 测试替身和离线复现。

LLM 只负责规划、结构化抽取、策略辅助判断和报告写作，搜索由独立 SearchProvider 完成。

## 6. Search Provider

### 6.1 接口优先

核心代码依赖自定义协议，而不是具体 SDK：

```python
class SearchProvider(Protocol):
    async def search(self, request: SearchRequest) -> SearchResponse: ...
```

SearchResponse 必须保留：

- query；
- title；
- URL；
- snippet；
- ranking/score；
- published date（如果存在）；
- provider usage；
- request ID；
- 延迟与错误信息。

### 6.2 首个实现

当前优先考虑 Tavily：

- 可以明确控制 `max_results`；
- 可以选择是否返回 raw content；
- 响应包含 URL、内容、分数和 usage；
- GPT Researcher 也将其作为默认搜索服务，便于外部参考。

正式实现前需要确认可访问性、账户额度和实际价格。接口设计必须允许后续增加其他搜索服务。

官方参考：[Tavily Search API](https://docs.tavily.com/documentation/api-reference/endpoint/search)。

### 6.3 离线测试 Provider

必须提供 FixtureSearchProvider：

- 从固定 JSON fixture 返回结果；
- 不访问网络；
- 可模拟空结果、限流、超时和重复 URL；
- 支持离线集成测试和回归测试。

## 7. 网页获取与正文处理

### 7.1 获取

默认使用 `httpx.AsyncClient`：

- 连接池；
- 每请求超时；
- 最大响应体限制；
- Content-Type 检查；
- 重定向限制；
- User-Agent 配置；
- 并发信号量；
- 单次重试。

### 7.2 正文提取

优先使用 Trafilatura 提取正文，BeautifulSoup 作为轻量降级和元数据解析工具。

V1 不默认引入 Playwright。只有当开发期样例表明 JavaScript 页面失败是主要问题时，才增加可选 BrowserFetcher；否则浏览器依赖会显著增加部署和测试复杂度。

### 7.3 安全边界

PageFetcher 必须阻止：

- `file://` 等非 HTTP 协议；
- localhost、私有 IP 和云 metadata 地址；
- 无限重定向；
- 超大页面；
- 非预期二进制文件。

这是公开 Web Agent 必须具备的 SSRF 与资源耗尽防护。

## 8. Context Engineering

### 8.1 Chunking

V1 使用基于 Token 估算的固定 chunk：

```text
chunk_size_tokens = 800
chunk_overlap_tokens = 100
```

每个 chunk 保留 source、URL、标题、位置和 content hash。

### 8.2 排序

Baseline 默认使用 BM25：

- 无额外 API 成本；
- 可复现；
- 不依赖 embedding 模型；
- 便于将研究策略收益与检索模型收益分离。

Embedding 或 reranker 作为后续消融项，不进入最初闭环。

### 8.3 证据优先

Writer 不接收原始网页大上下文，只接收通过 Schema 校验的 EvidenceItem。引用先使用内部 evidence ID，之后由确定性 Citation Renderer 转成链接。

## 9. 数据持久化

### 9.1 默认数据库

V1 使用 SQLite + SQLAlchemy 2.x。

理由：

- 本地一条命令运行；
- 足够支持单用户演示与批量实验；
- 可以查询运行、动作、证据和费用；
- 后续迁移 PostgreSQL 时保留 ORM 边界。

数据库不是 Evidence 语义模型。Domain Model 与 ORM Model 分离，避免业务逻辑直接依赖数据库对象。

### 9.2 初始表

```text
runs
subquestions
sources
document_chunks
evidence_items
actions
usage_records
reports
evaluation_results
```

大段网页正文可以先保存在 artifacts 目录，以路径和 hash 关联数据库，避免 SQLite 被重复正文快速放大。

### 9.3 运行产物

每次运行产生：

```text
runs/{run_id}/
├── request.json
├── events.jsonl
├── state-final.json
├── evidence.json
├── usage.json
├── report.md
└── summary.json
```

`runs/` 已加入 `.gitignore`。精选的离线测试 fixture 单独放在
`backend/tests/fixtures/` 并进入版本控制。

## 10. CLI

使用 Typer 提供开发和实验入口：

```text
bra research "问题" --policy fixed --config configs/dev.yaml
bra run show RUN_ID
bra eval run evals/dev-set.yaml
bra eval compare fixed adaptive
```

CLI 的优先级高于 Web UI，因为它更适合：

- 自动化测试；
- 批量实验；
- CI；
- 日志调试；
- 无前端环境复现。

CLI 必须调用 Application Service，不能复制一套研究流程。

## 11. FastAPI

### 11.1 职责

API 只负责：

- 接收和校验请求；
- 创建研究运行；
- 查询状态、证据和报告；
- 推送运行事件；
- 触发评测；
- 将 Domain 错误映射为 HTTP 错误。

它不负责 Policy 计算或直接操作 Provider。

### 11.2 初始接口

```text
POST /api/v1/runs
GET  /api/v1/runs
GET  /api/v1/runs/{run_id}
GET  /api/v1/runs/{run_id}/events
GET  /api/v1/runs/{run_id}/evidence
GET  /api/v1/runs/{run_id}/report
POST /api/v1/evaluations
GET  /api/v1/evaluations/{evaluation_id}
```

### 11.3 实时事件

使用 Server-Sent Events 推送：

- run status；
- action started/completed/failed；
- budget reserved/settled；
- source discovered/fetched；
- evidence accepted/rejected；
- report section generated；
- run completed/failed。

这里是服务端向浏览器单向推送，SSE 比 WebSocket 更简单。事件必须先持久化，再向前端广播，使断线重连和运行回放使用同一事件源。

FastAPI 官方已提供 SSE 支持：[FastAPI SSE](https://fastapi.tiangolo.com/tutorial/server-sent-events/)。

## 12. Web 前端

### 12.1 技术选择

使用：

- React；
- TypeScript；
- Vite；
- Tailwind CSS；
- TanStack Query；
- 原生 EventSource 或轻量 SSE Client；
- Recharts，用于成本与评测图表。

Vite 官方提供 React TypeScript 模板：[Vite Guide](https://vite.dev/guide/)。

V1 不使用 Next.js。项目不需要 SEO、服务端渲染、复杂认证或 Node 全栈服务；Vite 能以更低复杂度完成单页研究控制台。

Streamlit 只可作为临时调试工具，不作为最终公开 Demo。最终界面需要更清晰地表达 Agent 决策轨迹和证据链。

### 12.2 核心页面

V1 可以由两个路由完成：

```text
/runs/new        创建研究任务
/runs/{run_id}   运行控制台与结果
```

运行控制台包含：

1. 任务与预算摘要；
2. 实时 Action Timeline；
3. Token、费用、搜索和时间预算仪表盘；
4. 子问题及覆盖状态；
5. Evidence Inspector；
6. 最终 Markdown 报告；
7. Fixed 与 Adaptive 对照结果。

### 12.3 不做传统聊天界面

本项目不是聊天机器人。默认视觉中心应是“研究执行与实验”，而不是消息气泡。

UI 必须能回答：

- Agent 当前在研究什么？
- 为什么执行这个动作？
- 花费了多少预算？
- 获得了哪些证据？
- 为什么停止？
- Adaptive 相比 Baseline 攀升或节省在哪里？

## 13. 可观测性

### 13.1 统一事件

Core 通过 EventSink 输出结构化事件，CLI、JSONL、数据库和 SSE 都是 EventSink 的实现或消费者。

```text
DomainEvent
- event_id
- run_id
- sequence
- occurred_at
- event_type
- action_id
- payload
- schema_version
```

### 13.2 日志与轨迹分离

- Log：面向开发者排障；
- Domain Event：面向状态回放和 UI；
- Usage Record：面向预算和实验；
- Evaluation Result：面向质量对比。

不能依靠解析普通日志重建研究状态。

### 13.3 暂不强依赖 SaaS 观测平台

V1 不强制使用 LangSmith 等外部平台。自有事件和成本模型更能展示项目能力，也避免 Demo 依赖第三方账户。后续可以增加可选 exporter。

## 14. 测试与质量

### 14.1 测试框架

- `pytest`：基础测试；
- `pytest-asyncio`：异步流程；
- `respx`：Mock HTTPX；
- FastAPI TestClient/HTTPX ASGI transport：API 测试；
- 前端使用 Vitest + React Testing Library。

### 14.2 测试层次

```text
Unit
  Policy、BudgetLedger、Reducer、URL canonicalization、Citation mapping

Contract
  LLMProvider、SearchProvider、PageFetcher 的请求响应映射

Offline Integration
  Fake LLM + Fixture Search + Fixture Pages 跑完整闭环

Live Smoke
  使用真实 Kimi 和搜索服务跑一个低预算任务

Evaluation
  固定任务集批量比较 Fixed 与 Adaptive
```

默认测试不能依赖真实网络和付费 API。Live 测试使用显式 marker，只有配置密钥后才运行。

### 14.3 静态质量

- Ruff：lint 和 format；
- Pyright：严格类型检查；
- pre-commit：本地提交前检查；
- GitHub Actions：测试、类型、lint 和前端构建。

## 15. 配置管理

配置来源优先级：

```text
CLI 参数 > 环境变量 > YAML 配置 > 默认值
```

敏感信息只来自环境变量。非敏感实验配置写入 YAML，并随每次运行复制到 artifact 中，保证实验可追溯。

建议初始文件：

```text
backend/.env.example
backend/configs/default.yaml
backend/configs/baseline-medium.yaml
backend/configs/dev.yaml
```

## 16. 推荐仓库结构

```text
BudgetedResearchAgent/
├── backend/
│   ├── src/
│   │   └── budgeted_research/
│   │       ├── domain/
│   │       ├── engine/
│   │       ├── policies/
│   │       ├── providers/
│   │       ├── context/
│   │       ├── evidence/
│   │       ├── reporting/
│   │       ├── budgeting/
│   │       ├── tracing/
│   │       ├── storage/
│   │       ├── evaluation/
│   │       ├── application/
│   │       ├── api/
│   │       └── cli/
│   ├── configs/
│   ├── evals/
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   ├── contract/
│   │   └── fixtures/
│   ├── scripts/
│   ├── .env.example
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   ├── tests/
│   └── package.json
├── docs/
├── references/
├── .gitignore
└── README.md
```

这里只提前创建当前阶段需要的目录；其余目录在对应功能开始开发时再增加，
避免产生大量没有职责的空包。

## 17. 开发阶段

### Phase 1：Core Skeleton 与离线闭环

交付：

- Pydantic Domain Models；
- Provider Protocol；
- FixedDepthPolicy；
- BudgetLedger；
- ResearchEngine；
- Fake LLM/Search/Fetcher；
- 一次完整离线运行；
- 单元测试和集成测试。

完成标准：不访问网络即可生成一份带内部 citation ID 的报告和完整 ActionRecord。

### Phase 2：真实 Provider 与 CLI

交付：

- MoonshotLLMProvider；
- 首个真实 SearchProvider；
- HTTP PageFetcher；
- 正文提取、BM25 和 Evidence Extractor；
- Typer CLI；
- usage 与费用统计；
- 一个真实低预算任务。

完成标准：CLI 能生成带 URL 引用的报告、usage 和运行轨迹。

### Phase 3：API、持久化与事件流

交付：

- SQLite/SQLAlchemy；
- FastAPI；
- SSE；
- Run 查询接口；
- 运行恢复和失败状态。

完成标准：通过 API 创建任务并实时观察事件，刷新后仍能查看历史运行。

### Phase 4：Web 控制台

交付：

- 创建任务表单；
- Action Timeline；
- Budget Dashboard；
- Evidence Inspector；
- Markdown Report；
- 基础响应式布局。

完成标准：不了解代码的面试官能够通过页面理解一次运行发生了什么。

### Phase 5：Adaptive Policy 与评测

交付：

- Coverage/Novelty/Conflict 指标；
- AdaptiveBudgetPolicy；
- 统一评测任务集；
- Fixed/Adaptive 对照；
- 质量—成本图表；
- 消融实验。

完成标准：获得真实、可复现并可解释的实验结果，可以写入 README 和简历。

## 18. 明确不进入 V1 的内容

- 用户账号和权限系统；
- 多租户；
- Redis/Celery 分布式任务队列；
- PostgreSQL、ElasticSearch 或向量数据库；
- Kubernetes；
- 默认 Playwright 浏览器集群；
- PDF、图片和视频研究；
- 大型多 Agent 角色团队；
- 强化学习策略；
- 复杂 Prompt 管理 SaaS；
- 手机 App。

这些能力只有在对核心实验或求职展示有明确收益时才增加。

## 19. 风险与降级

| 风险 | V1 处理方式 |
|---|---|
| Kimi 模型或参数变化 | Provider 封装，模型完全配置化 |
| 搜索 API 额度或可用性 | Provider 接口 + FixtureSearchProvider |
| 网页无法抓取 | 明确失败状态，不无限重试；后续可选 BrowserFetcher |
| Token 预估不准确 | 调用前保守预留，调用后按 usage 结算 |
| LLM JSON 不合法 | Schema 校验 + 一次格式修复 + 明确失败 |
| 引用幻觉 | Writer 只使用 evidence ID，确定性渲染 URL |
| 前端拖慢进度 | CLI 闭环完成后再启动正式 UI |
| 框架掩盖核心设计 | V1 使用显式 State/Policy/Action 循环 |

## 20. 开发启动条件

在开始编码前，以下事项已经满足：

- 项目目标与 V1 范围已定义；
- GPT Researcher 参考实现已分析；
- Fixed-depth Baseline 协议已定义；
- 默认 LLM Provider 已暂定为 Moonshot/Kimi；
- 搜索与 LLM 已决定解耦；
- 后端、前端、持久化和测试技术栈已确定；
- 开发阶段和验收路径已确定。

仍未确定的模型 ID、搜索服务账户和价格不会阻塞 Phase 1，因为 Phase 1 使用 Fake Provider 完成离线闭环。

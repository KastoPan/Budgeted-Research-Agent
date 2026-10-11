# 简历与面试讲解材料

本文提供可直接改写的项目描述、口头介绍和常见追问。使用时应根据目标岗位和简历篇幅
压缩，不要把尚未完成的正式 Benchmark 写成已验证结论。

## 1. 项目名称

中文：预算感知深度研究 Agent（Budgeted Research Agent）

一句话：

> 面向技术调研任务的成本感知 Research Agent，在显式 Token、检索、抓取和时间预算内，
> 动态分配研究资源，维护可审计证据链，并生成带引用的结构化报告。

## 2. 简历项目描述

### 推荐版：按 Agent 模块组织

- **Agent 编排与状态管理**：将开放式研究抽象为
  `ResearchState → Policy → Action → Executor → Reducer` 的显式异步状态循环；Planner
  输出结构化子问题，Policy 只负责决策，Tool Executor、状态更新和事件记录独立执行，
  支持 Fixed Depth 与 Adaptive Budget 策略按统一接口替换和对照。
- **预算策略与 Tool 调度**：设计 Budget Ledger，对 Token、搜索、页面抓取、费用和时间执行
  调用前预留、调用后按 Provider Usage 结算；Adaptive Policy 综合 Coverage、Novelty、
  来源多样性、来源质量和冲突比例，动态选择 `SEARCH`、`FETCH`、`EXTRACT_EVIDENCE`
  或 `WRITE_REPORT`。多场景成功配对任务中 Coverage `0.897 → 1.000`、来源多样性
  `0.828 → 1.000`，页面抓取减少 `17.6%`；同时识别 Token 增加 `37.5%` 的成本迁移。
- **Context Engineering 与 Evidence Grounding**：实现 Tavily 检索、HTTPX/Trafilatura
  正文提取、确定性 Chunking 和 BM25 上下文选择；通过支持片段原文回溯、近似 Claim
  聚类、重复 Evidence 过滤和来源质量分层构建证据状态，要求每条 Report Assertion
  绑定有效 Evidence ID 并在渲染前再次校验。
- **Agent 可观测性与评测工程**：使用 EventSink、SQLite 和 JSONL 保存 Action reason、
  Decision Context、预算估算、真实消耗和停止原因，通过 FastAPI/SSE/React 实时回放并支持
  主动取消；构建版本化 Fixed/Adaptive 成对评测，分离 Provider 失败与策略质量，并通过
  资源轨迹定位页面 IO 减少但多轮抽取导致 LLM Token 上升的成本迁移。

### 三条精简版

- **Agent Orchestration / Policy**：自研显式异步 Agent 状态循环，解耦 Planner、Policy、
  Tool Executor、Reducer 与 Budget Ledger；实现 Fixed Depth 与 Adaptive Budget 策略，
  根据证据状态和剩余预算动态选择下一研究动作。
- **Context Engineering / Grounding**：构建搜索、网页正文提取、BM25 上下文选择、Evidence
  去重与 Claim 聚类链路，通过原文支持片段校验和 Evidence ID 绑定保证报告结论可追溯；
  多场景成功配对任务中 Coverage `0.897 → 1.000`、来源多样性 `0.828 → 1.000`。
- **Observability / Evaluation**：使用 FastAPI、SQLite、SSE 和 React 实现实时预算、Action
  Timeline、证据检查、报告回放和主动取消；搭建 Fixed/Adaptive 成对评测体系，量化 Token、
  检索资源、证据指标和运行稳定性。

## 3. 可填写的技术关键词

```text
Python, AsyncIO, FastAPI, Pydantic, SQLAlchemy, SQLite, React, TypeScript,
SSE, LLM Agent, RAG, BM25, Evidence Grounding, Budget Control,
Evaluation, Moonshot/Kimi, Tavily, pytest, Vitest, uv
```

不要为了关键词加入项目中没有使用的 LangGraph、向量数据库、Celery、Redis 或 Kubernetes。

## 4. 30 秒口头介绍

> 我做了一个面向技术调研的预算感知 Research Agent。普通固定深度方案会给所有子问题
> 相同资源，我实现了一套显式状态和规则 Policy，根据证据覆盖、来源多样性、质量、冲突
> 和剩余预算决定继续搜索、抓取、抽取还是写报告。每条报告结论都绑定到经过正文回溯的
> Evidence。项目有 Fixed 基线、真实 Provider、成对评测、FastAPI/SQLite/SSE 后端和
> React 可观测控制台，也保留完整动作原因和资源消耗，便于解释和回放。

## 5. 两分钟讲解结构

### 背景

开放式 Research Agent 容易无限搜索，或者用固定深度导致不同难度分支资源分配不合理。
项目目标是在硬预算内提高证据覆盖与可验证性，同时让停止原因可解释。

### 核心设计

我没有把核心流程交给通用编排框架，而是实现显式异步循环。Policy 只做决策，Executor
负责外部调用，Reducer 更新状态，Ledger 预留和结算资源。Fixed 与 Adaptive 仅替换
Policy，因此可以公平比较。

### 证据可靠性

搜索结果不能直接进入报告。系统先抓取正文、切块、使用 BM25 选择上下文，再让模型输出
Claim、支持片段和来源。支持片段必须存在于原文，重复 Evidence 不增加 Coverage。报告
每条 Assertion 绑定 Evidence ID，渲染前再次校验。

### 工程交付

API 使用 SQLite 保存运行和事件，SSE 将动作推送到 React。任务可以主动取消，取消前已
发生的资源会保留。CLI、API 和前端复用同一套 Agent Core。

### 评测发现

10 类技术调研问题的成对评测中，Fixed 有两次搜索连接故障，因此最终策略比较只使用
双方均成功的配对任务。Adaptive 将内部 Coverage 从 0.897 提升到 1.000、来源多样性从
0.828 提升到 1.000，并减少 17.6% 页面抓取；代价是 Token 增加 37.5%、耗时增加 13.6%。
结论是 Adaptive 更偏向证据完整性，而不是单纯节省 Token。

## 6. 常见面试追问

### 为什么没有直接使用 LangGraph？

项目要研究的正是状态、动作、预算与停止决策。显式循环让策略边界和每次状态转换都能被
测试、记录和做消融。以后可以增加 LangGraph Adapter，但不会让框架内部状态成为核心
实验变量。

### Adaptive 到底自适应在哪里？

它不会预先固定每个子问题的深度。完成最低探索后，Policy 按冲突优先、低覆盖、低多样性
和低质量排序目标；只有存在可用新来源、允许新的搜索轮次且能为 Writer 保留预算时才继续。
达到阈值、低新增持续出现或资源不足时进入报告。

### Coverage 是模型主观打分吗？

不是额外的 LLM Judge。V1 使用确定性代理指标：去重后的 Claim Cluster 数量和唯一来源数
共同形成 Coverage。它便于复现和审计，但不等于事实正确率，所以评测文档明确区分内部
指标和最终质量。

### 如何防止模型编造引用？

Evidence 输出必须包含来源 ID、URL、Claim 和支持片段；系统确认来源属于本次上下文，
并检查支持片段能在抓取正文中找到。报告 Assertion 只能引用已保存的 Evidence ID，渲染
前再检查 Assertion 与对应 Claim 的一致性。失败的 Assertion 被拒绝，不会进入正文。

### 为什么需要调用前预留预算？

模型调用只有完成后才知道真实 Token。如果仅在调用后计数，最后一次请求可能把预算大幅
突破。Ledger 先按动作上界预留，通过后才执行，完成后使用 Provider usage 结算差额。

### 为什么 Adaptive 反而可能使用更多 Token？

减少网页抓取不等于减少模型调用。Adaptive 会在弱分支上多轮抽取和重新评估，Evidence
Extraction 与 Writer 可能成为主要 Token 消耗。完整实验的高方差说明策略还需要更准确的
收益估计和抽取轮次控制。

### SQLite 能用于生产吗？

当前目标是本地演示和单实例服务，SQLite 降低部署复杂度并保留事务与查询能力。多实例时
需要 PostgreSQL、外部任务队列和共享事件通道；仓储层已经通过 SQLAlchemy 与应用逻辑隔离。

### 任务取消是否一定能撤回当前 API 请求？

取消会终止 Agent 后续动作并持久化 `cancelled` 状态。正在执行的单个外部请求可能已经发送
并产生计费，因此 UI 会明确提醒，并保存取消前已经完成动作的资源消耗。

## 7. 项目不足与下一步

可以主动说明以下限制：

- 当前 Coverage 是可解释代理指标，缺少独立的事实正确性与报告完整性盲评；
- 当前来源质量主要依赖 URL 规则，未识别域名默认分可能低估部分官方来源；
- 当前评测每个任务—策略组合只运行一次，跨任务结果不能替代同任务重复统计；
- 词法 Claim 聚类与冲突检测对复杂语义有限；
- 网页抓取不包含浏览器渲染，对重 JavaScript 页面支持有限；
- 单进程后台任务和 SQLite 适合单实例，不支持水平扩展；
- 美元成本依赖用户配置模型单价，现有历史实验没有完整 USD 数据。

后续如继续扩展，可先增加搜索重试和来源质量规则，再引入独立盲评与重复实验；随后优化
抽取轮次和信息增益估计，最后再考虑语义蕴含、Embedding/Reranker 或分布式运行。

## 8. 面试演示建议

优先展示三个画面：

1. 新建任务时的策略和硬预算；
2. 运行中的 SSE 指标与可读 Action reason；
3. 报告引用跳转到 Evidence 支持片段。

如果还有时间，再展示取消记录和评测结果。截图与五分钟脚本见
[演示与截图清单](./demo-guide.md)。

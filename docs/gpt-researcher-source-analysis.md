# GPT Researcher 源码分析

> 分析对象：`assafelovic/gpt-researcher`  
> 分析版本：`0957c301ed06c2a5857b834358c7227c739041d4`  
> 获取方式：`git clone --depth 1`  
> 分析日期：2026-09-28  
> 用途：为 Budgeted Research Agent 提供参考，不作为代码派生基础。

## 1. 结论摘要

GPT Researcher 是一个成熟的深度研究参考实现。它已经覆盖查询规划、搜索、网页抓取、上下文筛选、报告生成、多来源适配、并发执行、成本统计和多 Agent 工作流。

它的核心研究路径仍然主要由预设配置控制研究规模：默认使用 LLM 生成固定上限的子查询，并为每条查询获取固定数量的搜索结果。成本在执行后被累计和展示，但没有成为核心研究循环中的显式约束，也没有根据证据覆盖度、来源冲突、边际信息增益和剩余预算动态选择下一步动作。

这为 Budgeted Research Agent 提供了清晰的差异化方向：

> 从“配置驱动的固定研究流程”转向“证据状态和预算驱动的序贯决策流程”。

## 2. 核心执行路径

### 2.1 单 Agent 核心路径

核心入口是 `GPTResearcher`，它组合了以下职责模块：

- `ResearchConductor`：规划子查询并组织研究；
- `BrowserManager`：抓取网页；
- `ContextManager`：筛选和压缩上下文；
- `SourceCurator`：可选的来源排序；
- `ReportGenerator`：生成带链接的报告；
- Cost utilities：累计模型调用成本。

典型 Web 研究流程为：

```text
原始问题
  ↓
选择 Agent 角色
  ↓
执行一次初始搜索
  ↓
LLM 根据问题和初始结果生成子查询
  ↓
附加原始问题作为额外查询分支
  ↓
并行搜索和抓取各查询分支
  ↓
按查询筛选相关上下文
  ↓
拼接所有上下文
  ↓
可选来源筛选
  ↓
LLM 生成最终报告
```

默认配置中的关键研究规模参数是：

```text
MAX_ITERATIONS = 3
MAX_SEARCH_RESULTS_PER_QUERY = 5
MAX_SUBTOPICS = 3
TOTAL_WORDS = 1200
```

`MAX_ITERATIONS` 实际用于提示 LLM 生成子查询数量。普通报告路径还会追加原始问题，因此一次研究通常包含若干子查询分支和一个原始问题分支。

### 2.2 上下文选择

仓库支持多种上下文过滤方式：

- `jev`：按问题相关的实际有用性为 chunk 评分；
- `keyword`：基于 BM25 的本地关键词排序；
- `embeddings`：向量相似度；
- `none`：不筛选；
- `auto`：根据可用配置选择，并在失败时回退到关键词排序。

值得注意的工程设计包括：

- 内容较少时跳过不必要的压缩；
- 外部评分或 embedding 不可用时自动降级；
- 将网页转换成统一 Document 结构；
- 保留 URL 和标题，用于后续报告引用。

### 2.3 多 Agent 路径

多 Agent 版本通过 LangGraph 组织固定角色和流程：

```text
Browser → Planner → Human Review → Parallel Research
        → Writer → Fact Checker → Visualizer → Publisher
```

部分审核节点具有带最大次数的修订循环。该设计能展示角色分工和流程控制，但研究资源仍主要由预设 section 数量、并行研究任务和最大修订次数决定，不是一个基于全局预算和证据边际收益的调度器。

## 3. 值得借鉴的设计

### 3.1 模块职责分离

搜索、抓取、上下文筛选、写作和成本统计被拆成独立组件。我们应保留这种边界，使 Fixed Policy 和 Adaptive Policy 可以复用同一研究引擎。

### 3.2 I/O 并发

独立查询和网页抓取适合异步并发。我们的策略层负责决定执行哪些动作，执行层可以并发处理同一轮已经批准的动作。

### 3.3 URL 去重

`visited_urls` 在父子研究任务之间共享，避免重复抓取。我们的实现应进一步采用 canonical URL 和 content hash 双重去重。

### 3.4 上下文筛选与可降级性

优先使用便宜、可复现的本地排序，并为外部服务和 embedding 失败提供降级路径。这有助于控制成本并提高演示稳定性。

### 3.5 空证据拒答

当没有获取到研究资料时，报告生成器会拒绝凭空生成带来源外观的报告。我们的 Writer 也必须要求至少存在可引用 EvidenceItem，否则返回不完整或失败状态。

### 3.6 分步骤成本统计

GPT Researcher 记录总成本和部分步骤成本。我们应在此基础上同时记录输入 Token、输出 Token、美元费用、搜索调用、页面抓取和墙钟时间。

## 4. 不直接照搬的设计

### 4.1 不把角色数量等同于 Agent 能力

自动选择角色以及 Browser、Editor、Reviewer、Writer 等大量角色会增加调用成本，但不一定改善预算决策。V1 使用少量职责明确的组件和一个显式 Policy。

### 4.2 不使用拼接字符串作为核心状态

参考实现的核心路径会将多个查询的上下文拼接成大字符串。这样很难准确回答：某个结论来自哪里、哪个子问题还缺证据、两条证据是否重复或冲突。

我们的核心状态应保存结构化对象：

```text
SubQuestion
SourceDocument
EvidenceItem
Claim
Citation
BudgetLedger
ActionRecord
```

### 4.3 不只依靠 Prompt 保证引用正确

参考实现会要求 Writer 添加行内 URL，但核心路径主要依靠 Prompt 约束。我们的报告只能引用 EvidenceStore 中已有的 citation ID，并在报告生成后执行 citation mapping 和支持关系检查。

### 4.4 不把成本统计误认为预算控制

记录“已经花了多少钱”不等于控制“下一步是否值得继续花钱”。Budget Ledger 必须在执行动作之前进行预算预留，在执行后结算实际消耗，并参与 Policy 决策。

### 4.5 不使用固定分支数量作为最终策略

固定子查询和固定结果数适合作为 Baseline，但 Adaptive Policy 应根据覆盖度、证据冲突和信息新增率决定分支深度。

## 5. 我们的差异化设计

| 维度 | GPT Researcher 核心路径 | Budgeted Research Agent |
|---|---|---|
| 研究规模 | 预设子查询和结果上限 | 全局预算与动态动作选择 |
| 核心状态 | 累积上下文 | 结构化问题、证据、claim 和预算账本 |
| 停止方式 | 固定流程完成或配置上限 | 硬预算、覆盖度和边际收益共同触发 |
| 上下文 | 相关内容筛选后拼接 | 按子问题和证据价值分配上下文预算 |
| 引用 | Writer 根据上下文生成 URL | Writer 只能使用证据库中的 citation ID |
| 成本 | 执行后累计 | 执行前预留、执行后结算、策略实时使用 |
| 可观测性 | 日志和总成本 | 完整状态快照、动作原因和资源账本 |
| 评测 | 功能与局部 eval | 固定策略基线、预算扫描和消融实验 |

## 6. 对 V1 的直接影响

源码分析形成以下 V1 决策：

1. 研究引擎和策略必须解耦；
2. Fixed-depth Baseline 与 Adaptive Policy 复用相同组件；
3. V1 使用结构化 EvidenceStore，不以大字符串作为事实来源；
4. 默认使用本地关键词/BM25 做 chunk 初筛，避免把 embedding 成本混入核心实验；
5. 搜索和抓取并发执行，但所有动作必须先经过预算预留；
6. Writer 只能看到选中的 EvidenceItem，而不是完整网页；
7. 无证据时拒绝生成确定性报告；
8. GPT Researcher 作为参考和外部补充对比，我们自己的 Fixed Policy 是主要实验基线。

## 7. 许可与引用

当前参考仓库使用 Apache License 2.0。V1 计划自行实现核心代码，不直接复制参考仓库源码。如果后续复用任何代码片段，必须保留相应版权和许可声明，并在项目文档中明确标注来源。


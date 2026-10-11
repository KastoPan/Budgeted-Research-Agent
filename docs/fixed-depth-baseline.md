# Fixed-depth Baseline 设计

> 状态：V1 Baseline v0.1  
> 目标：定义一个稳定、可复现、非自适应的研究策略，作为 Budgeted Policy 的主要对照组。

## 1. Baseline 的职责

Fixed-depth Baseline 回答的是：

> 如果 Agent 对每个研究分支平均分配固定资源，不观察证据状态并调整策略，它能以多少成本获得怎样的报告质量？

Baseline 必须拥有完整的研究能力，但不能拥有动态预算分配能力。它不是一个刻意做差的系统，而是一个合理、稳定的固定策略。

## 2. 固定执行协议

```text
ResearchRequest
  ↓
Planner：固定生成 4 个子问题
  ↓
每个子问题固定生成 1 条搜索查询
  ↓
每条查询固定获取 Top 5 搜索结果
  ↓
每个子问题固定抓取排名最高的 3 个可用页面
  ↓
固定 chunk 与 BM25 选择
  ↓
每个子问题固定执行 1 次证据抽取
  ↓
Writer 固定执行 1 次报告生成
  ↓
Citation Checker + Metrics Recorder
```

整个研究过程只有一层研究深度，不会根据抽取结果发起第二轮搜索。

## 3. 默认参数

```yaml
policy:
  name: fixed_depth
  subquestion_count: 4
  search_queries_per_subquestion: 1
  search_results_per_query: 5
  pages_to_fetch_per_subquestion: 3
  research_rounds: 1

context:
  chunk_size_tokens: 800
  chunk_overlap_tokens: 100
  selected_chunks_per_subquestion: 6
  ranker: bm25

evidence:
  max_evidence_items_per_subquestion: 5
  require_source_url: true
  require_verbatim_support_span: true

execution:
  subquestion_concurrency: 4
  request_timeout_seconds: 20
  retry_count: 1
```

这些参数在同一实验批次中不可根据任务难度变化。

## 4. 规划输出

Planner 只读取原始研究问题，输出严格的结构化结果：

```json
{
  "subquestions": [
    {
      "id": "sq_01",
      "question": "需要回答的子问题",
      "search_query": "用于搜索服务的查询",
      "rationale": "该子问题与主问题的关系"
    }
  ]
}
```

约束：

- 必须正好生成 4 个子问题；
- 子问题应尽量互补，避免同义重复；
- 不执行初始探索搜索；
- 不根据搜索结果重新规划；
- Planner 输出解析失败时允许一次格式修复，仍失败则任务失败，不静默改变研究规模。

不执行初始探索搜索是有意设计：它消除隐藏的额外检索开销，并使 Baseline 的搜索次数完全可预测。

## 5. 搜索、抓取和去重

每个子问题恰好调用一次搜索服务，获取 Top 5 结果。

处理规则：

1. 规范化 URL，移除常见追踪参数和 fragment；
2. 按 canonical URL 全局去重；
3. 相同页面被多个子问题命中时只抓取一次，但可以被多个子问题引用；
4. 按搜索排名依次抓取，直到当前子问题获得 3 个有效页面；
5. 页面失败后只尝试该查询 Top 5 中的下一条结果；
6. Top 5 用尽后不生成新查询，不扩大搜索范围；
7. 使用 content hash 标记跨 URL 的正文重复。

因此每次运行的上限为：

```text
搜索调用：4 次
搜索候选：20 条
成功抓取页面：最多 12 个唯一页面
```

## 6. 上下文选择

网页正文经过统一清洗和基于 Token 的 chunking。每个子问题使用 BM25 对关联页面的 chunks 排序，固定选择前 6 个。

选择 BM25 作为 Baseline 默认方式的原因：

- 本地运行，没有额外模型费用；
- 可复现，结果稳定；
- 不引入 embedding 模型差异；
- 能建立一个足够合理的 Context Engineering 基线。

Baseline 不根据“当前证据是否足够”改变 chunk 数量。若可用 chunks 少于 6 个，则使用全部可用内容并记录 shortage。

## 7. 证据抽取

每个子问题执行一次 Evidence Extractor 调用，输入该子问题选中的 chunks，最多输出 5 条 EvidenceItem：

```json
{
  "evidence_id": "ev_001",
  "subquestion_id": "sq_01",
  "claim": "由证据直接支持的原子事实",
  "support_span": "来源中的原文片段",
  "source_id": "src_001",
  "source_url": "https://example.com/page",
  "source_title": "Page title",
  "published_at": null,
  "retrieved_at": "2026-09-28T00:00:00Z"
}
```

规则：

- 一个 EvidenceItem 只表达一个尽量原子的 claim；
- `support_span` 必须来自输入 chunk；
- 没有 URL 或支持片段的输出不进入 EvidenceStore；
- 抽取器可以返回少于 5 条证据；
- Baseline 不因证据不足、重复或冲突而补充研究。

去重和格式验证属于研究引擎的公共能力，不属于自适应策略，因此 Baseline 和 Budgeted Agent 都使用它们。

## 8. 报告生成

Writer 只能读取：

- 原始研究问题；
- 4 个子问题；
- 通过验证的 EvidenceItem；
- 固定的报告结构要求。

Writer 不直接读取完整网页，也不能创建 EvidenceStore 中不存在的引用。提示中使用内部 citation ID，例如 `[ev_001]`；生成后由 Citation Renderer 将 ID 转换为 Markdown 链接。

如果没有任何有效 EvidenceItem，系统返回 `INSUFFICIENT_EVIDENCE`，不生成看似确定的研究报告。

## 9. 固定策略与硬预算保护

Baseline 不根据预算动态重新分配资源，但必须服从实验设置的硬上限。

硬预算保护只执行以下操作：

- 在调用前估算是否会超过绝对上限；
- 超过上限时拒绝启动该调用；
- 将运行标记为 `BUDGET_EXHAUSTED`；
- 保留已有证据和不完整报告状态；
- 不把剩余预算转移给其他子问题。

这属于安全约束，不属于智能 Policy。

正式实验应选择足以让默认 Baseline 大多数情况下完整运行的预算，并单独报告预算超限率。

## 10. 预计调用规模

一次正常运行的核心调用规模为：

```text
Planner LLM：1 次
搜索服务：4 次
网页抓取：最多 12 个成功页面
Evidence Extractor LLM：4 次
Writer LLM：1 次
Citation Checker：确定性校验，0 次 LLM
```

默认核心 LLM 调用合计 6 次。模型失败后的格式修复或单次重试必须单独记录，不能隐藏在统计中。

## 11. 与 Budgeted Policy 的公共接口

两种策略共享同一个 Research Engine：

```text
Planner
SearchProvider
PageFetcher
DocumentCleaner
Chunker
ContextRanker
EvidenceExtractor
EvidenceStore
ReportWriter
CitationChecker
UsageMeter
TraceRecorder
```

策略只负责产生动作计划：

```text
FixedDepthPolicy
  → 一次性生成固定 ActionPlan

AdaptiveBudgetPolicy
  → 每轮读取 ResearchState 后生成 NextAction
```

所有模型、Prompt、搜索服务、抓取器和报告生成逻辑保持一致，避免把组件差异误认为策略收益。

## 12. 追踪记录

即使 Baseline 不做动态决策，也必须记录统一的 ActionRecord：

```json
{
  "step": 3,
  "action": "SEARCH",
  "target": "sq_02",
  "policy": "fixed_depth",
  "reason": "fixed protocol: one search per subquestion",
  "estimated_cost": {},
  "actual_cost": {},
  "status": "completed"
}
```

统一轨迹格式使两种策略能够使用相同的调试、可视化和评测工具。

## 13. 实验公平性

主要对比必须控制以下变量：

- 相同研究任务；
- 相同模型及模型参数；
- 相同搜索服务；
- 相同网页抓取和正文清洗；
- 相同 Evidence Extractor；
- 相同 Writer；
- 相同硬预算上限；
- 相同评测器。

唯一关键自变量是 Policy。

后续为了绘制质量—成本曲线，可以增加 Low、Medium、High 三组固定配置。V1 首先实现本文档中的 Medium 默认配置，待端到端 dry run 后再冻结另外两个档位。

## 14. Baseline 验收标准

- 对同一个问题稳定生成 4 个子问题；
- 每个子问题最多发起 1 次搜索；
- 全局最多成功抓取 12 个唯一页面；
- 不会因证据不足或冲突发起补充研究；
- 所有报告引用均能映射到 EvidenceStore；
- 能输出搜索、页面、Token、费用和延迟统计；
- 能输出统一 ActionRecord；
- 触发硬预算时可安全终止并标记原因；
- 固定随机种子和相同外部响应下，执行计划可复现；
- 核心流程具有单元测试和至少一个离线集成测试。

## 15. 尚待技术选型确认

本文档冻结流程协议，但暂不绑定以下实现：

- 具体 LLM 供应商和模型；
- 具体搜索 API；
- 网页正文提取库；
- Tokenizer；
- 持久化数据库；
- 是否使用 LangGraph。

这些选择不应改变 Baseline 的行为语义。


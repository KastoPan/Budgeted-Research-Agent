# Adaptive Budget Policy V1

## 1. 目标

`AdaptiveBudgetPolicy` 与 Fixed-depth Baseline 复用相同的 Planner、搜索、抓取、
BM25、Evidence Extractor、Writer 和硬预算账本。唯一实验变量是 Policy。

V1 是确定性、可解释的规则策略，不使用额外的策略 LLM。它至少完成三类决策：

1. 为每个子问题分配最小探索资源；
2. 选择低覆盖、低来源多样性或存在冲突的子问题继续研究；
3. 在证据充分、边际新增过低、没有可行动作或应保留报告预算时停止。

## 2. 状态指标

每次 Evidence Extraction 后按子问题更新以下指标：

- `evidence_count`：去重后保留的证据数量；
- `claim_cluster_count`：词项高度重合且极性一致的结论簇数量；
- `duplicate_evidence_count`：相同来源中引用相同、claim 近似或支持片段高度重叠的累计重复数量；
- `rejected_evidence_count`：因来源、URL 或逐字引用校验失败而拒绝的累计数量；
- `source_count`：证据覆盖的唯一来源数量；
- `coverage`：`0.7 × claim coverage + 0.3 × source diversity`；
- `novelty`：新 Claim Cluster 比例占 75%，新来源比例占 25%；
- `source_diversity`：唯一来源数相对目标来源数的截断比例；
- `source_quality_score`：按唯一来源计算的平均来源质量分；
- `conflict_ratio`：高词项重合且否定极性相反的 claim 对占比；
- `low_novelty_streak`：连续低于 novelty 阈值的抽取轮数。

同一来源且引用片段相同的 EvidenceItem 不会重复进入 EvidenceStore。同一来源中
claim 高度近似、或支持片段高度重叠的 Evidence 也视为重复。不同来源的近似 claim
会保留各自 EvidenceItem，但归入同一 Claim Cluster，因此能提高来源多样性而不会
重复抬高 Coverage。Novelty 只根据去重后实际接受的 Evidence 计算，拒绝项和重复项
不会贡献新增率。
逐条拒绝的原因保存在 `rejection_reasons_by_subquestion`，便于检查模型输出质量。
冲突检测是 V1 的确定性词法启发式，只作为继续补证信号，不作为事实裁决器。

来源质量同样采用确定性、可审计的 URL 信号，不调用额外 LLM：官方文档、政府、
学术、文档站点、代码仓库、社区发布平台分别获得不同等级。无法识别的域名保持
中性分数，不会被猜测为权威来源。该分数描述来源类型与可审计信号，不代表对内容
真实性的最终裁决。

## 3. 动作选择

### 3.1 Bootstrap

1. Planner 创建候选子问题；
2. 每个子问题获得一次初始搜索；
3. 每个子问题尽量收集两个有效来源，再将其精选 chunks 合并执行第一次证据抽取。

来源多样性目标要求至少两个独立来源，因此单来源抽取通常不可能完成子问题。批量
Bootstrap 避免为这个注定只是中间态的观察额外调用一次 LLM。如果初始候选不足、
抓取失败或页面预算不足，策略会降级为对已有单一来源执行抽取，不会等待到停滞。
该阶段同时避免策略在完全没有观察值时过早把全部预算分配给单一分支。

### 3.2 Adaptive deepen

初始抽取后，候选子问题按以下优先级排序：

1. 冲突率更高；
2. 覆盖度更低；
3. 来源多样性更低；
4. 来源质量更低；
5. 子问题 ID，作为稳定的最终 tie-breaker。

已经同时满足 coverage、来源多样性、来源质量和冲突率目标的子问题会先从候选队列
移除。其他分支仍有缺口时，策略不会重新打开已完成分支，也不会用较低质量的新来源
稀释已经达标的来源质量均值。

被选中的分支优先读取已有搜索结果中的下一来源。新来源到达后立即重新抽取，后续
Extraction 只读取当前子问题尚未抽取的新来源，避免旧页面在跨轮调用中产生换一种
措辞的重复 Evidence，并用实际 novelty 决定是否值得继续。如果候选结果耗尽且仍有搜索预算，则执行一次带
官方文档、主要来源和独立证据缺口提示的补充搜索。同一批未尝试候选中，Adaptive
优先选择来源质量分更高的 URL，再使用搜索相关分与原始排名作为 tie-breaker；Fixed
Baseline 仍严格遵循搜索排名。

当 coverage、来源多样性和冲突率都已达标，只剩来源质量均值未达标时，策略进入
`quality-only` 模式。此时不会继续抓取普通候选，而只接受来源质量至少为 `0.75`、
且按当前唯一证据来源数估算能让质量均值提高至少 `0.03` 的候选。如果已有结果中
没有这种来源，策略最多再发起一次面向官方文档和主要来源的补充搜索；补充搜索仍
找不到合格候选时，直接以 limitations 写报告。这使质量阈值成为“寻找更好来源”的
目标，而不是耗尽页面预算的硬循环条件。

普通深挖仍受每个子问题的来源上限约束；`quality-only` 模式默认只获得 1 个额外的
高质量来源名额。搜索和抓取前还会确认该分支保有抽取轮次与 Writer 之外的 Token
余量，避免下载一个之后无法进入 Evidence Store 的页面。

每个子问题默认以 6 个 Claim Cluster 作为有效结论容量。接近容量后，后续抽取会
缩小 `max_items`，只允许新来源提供少量补强证据，避免在 coverage 已饱和时继续把
报告扩张成结论列表。

## 4. 停止条件

存在有效证据时，任一条件可以触发写报告：

- 所有子问题同时达到 coverage、source diversity、来源质量阈值，且冲突率可接受；
- 只剩来源质量缺口，但补充搜索后没有能带来显著质量增益的候选；
- 剩余 Token 只够保留一次 Writer 和安全余量；
- 剩余时间接近 Writer 所需窗口；
- 页面预算耗尽且没有尚未抽取的新来源；
- 所有分支连续低 novelty 或已达到轮数上限；
- 没有其他具有正预期信息增益的动作。

如果没有任何有效证据，策略停止后由引擎返回 `INSUFFICIENT_EVIDENCE`，不会生成
伪装成完整研究结果的报告。

如果存在有效证据并能生成报告，但 coverage、来源多样性、来源质量或冲突指标仍未
达到门槛，则保留 best-effort 报告并返回 `COMPLETED_WITH_LIMITATIONS`。该状态在 CLI
中属于成功执行，同时逐条输出未满足条件；它与 Provider 异常导致的 `FAILED` 明确
区分。

## 5. 可观测性

每条 `ActionRecord` 记录：

- `policy`；
- 可读的 `reason`；
- 决策时剩余 Token、搜索、页面和时间预算；
- 目标子问题当时的 coverage、novelty、source diversity 和 conflict ratio。

最终状态包含完整预算快照和各子问题指标，并单独输出 `metrics.json` 与
`claim-clusters.json`，用于后续 Fixed/Adaptive 对照、预算扫描、解释和可视化。

## 6. 当前边界

- 冲突检测尚不理解复杂语义否定；
- 补充查询由确定性模板生成，不调用专门的 Query Rewriter；
- 来源质量 V1 只使用 URL 与域名类别信号，尚不理解作者身份、审稿流程和正文质量；
- projected quality gain 假设被抓取来源最终能产出有效证据，因此是偏乐观的抓取前估计；
- V1 按动作串行决策，后续才考虑同轮并发执行。

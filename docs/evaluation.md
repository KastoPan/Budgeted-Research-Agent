# Evaluation Protocol V0.2

## 1. 目标

评测用于回答：在相同任务、Provider、组件和最大预算下，`FixedDepthPolicy` 与
`AdaptiveBudgetPolicy` 分别消耗多少资源、获得怎样的结构化证据状态，并以什么原因
停止。第一版先建立可复现的运行与汇总基础设施，不提前宣称报告事实正确率。

## 2. 公平性约束

每个任务的两种策略必须共享：

- 相同原始问题与硬预算；
- 相同 Moonshot 模型、温度和超时配置；
- 相同 Tavily、PageFetcher、Chunker、BM25、Extractor 和 Writer；
- 相同 Evidence、Grounding 和来源质量规则；
- 同一任务集版本。

允许变化的实验变量仅是 Policy 的动作选择、资源分配和停止决策。V0.1 按顺序执行
策略，避免并发运行引入 Provider 限流差异；不同任务交替 Fixed/Adaptive 的先后顺序，
减少固定由某一策略先运行带来的时间顺序偏差。

V0.2 支持对每个任务—策略组合执行多次真实运行。每次 repetition 内仍顺序执行两种
策略，并在 repetition 和任务之间交替先后顺序，减少某种策略长期固定先运行造成的
时间偏差。每次原始运行都保留独立 run ID 和产物目录。

## 3. 开发任务集

`backend/evals/dev-suite.json` V0.2 包含 10 条技术调研任务，覆盖 Agent 框架、消息系统、
API、数据库、云原生、向量数据库、实时协议、任务队列、RAG 分块和 Python 并发。
当前协议以场景广度优先，每个任务—策略组合默认只运行一次；它仍是开发 Benchmark，
不是事实准确率 Benchmark。任务集包含版本号，每次正式实验都会将原始 suite 快照复制
到评测产物目录。

V0.2 为每个任务统一设置 60,000 Token、8 次搜索、18 次页面抓取和 600 秒硬上限。
正式评测后续再扩展任务数量，并冻结任务版本、预算配置和运行日期。

## 4. 自动指标与波动统计

逐次运行记录：

- Run status 与 Adaptive Evidence Sufficiency；
- Stop reason，包括 Provider、网络和结构校验失败；
- Token、美元费用、搜索、页面抓取和端到端时间；
- Evidence 与 Claim Cluster 数量；
- 平均 Coverage、来源多样性和来源质量；
- 完成率，以及每 10,000 Token 获得的 Coverage；
- 报告 assertion 和 citation 数量；
- 原始运行产物目录。

按策略汇总均值与状态分布。Coverage、来源质量和引用数量是系统内部的可观测代理，
不等于事实正确率、完整性或报告可用性。

`FAILED` 表示运行尝试失败，不会再以零 Coverage、零断言参与策略质量与资源均值。
汇总会分别记录总尝试数、可评测运行数、失败数、失败率，以及包含失败尝试在内的
总 Token/费用。这样 Provider 故障不会伪装成策略质量下降，但可靠性和已经发生的
消耗也不会被隐藏。`INSUFFICIENT_EVIDENCE` 等非 `FAILED` 策略终态仍参与均值，因为
它们属于策略本身的有效结果。

V0.2 同时在单任务和完整评测两个层级计算均值与总体标准差，包括 Token、费用、搜索、
页面抓取、耗时、Coverage、来源多样性、来源质量和报告 assertion 数。标准差只描述
本次真实运行中观察到的波动，不是置信区间；单次运行的标准差固定为 0。
顶层总体标准差会同时包含任务难度差异与同任务运行波动；判断 Provider 随机性时应
优先查看各任务自己的 aggregate。

`coverage_per_10k_tokens` 定义为：

```text
Coverage × 10,000 / Token 消耗
```

它只用于比较系统内部证据覆盖效率，数值越高表示单位 Token 获得的 Coverage 越多；
它不代表事实正确率，也不能脱离完成率、来源质量和失败率单独解读。

## 5. 尚未加入的质量评审

V0.3 将独立定义盲评 rubric，至少覆盖：

- 事实正确性；
- 问题覆盖完整性；
- 引用是否真正支持对应结论；
- 关键限制和不确定性是否表达；
- 最终建议是否由前文证据支撑。

评审可以采用人工双评、LLM Judge 加人工抽检，或者二者结合。Judge 不能读取策略名、
Token 消耗或运行状态，避免把成本信息泄漏给质量评分。

## 6. 运行方式

先运行单任务、两策略的低范围检查：

```bash
cd backend
uv run bra eval run --suite evals/dev-suite.json --limit 1
```

如需专门观察同一任务的随机波动，可以额外执行两次重复：

```bash
uv run bra eval run \
  --suite evals/dev-suite.json \
  --limit 1 \
  --repetitions 2
```

确认 Provider 成本与产物结构后，再去掉 `--limit 1` 运行全部 10 条开发任务：

```bash
uv run bra eval run \
  --suite evals/dev-suite.json \
  --repetitions 1
```

该命令包含 20 次真实 Research Run（10 个问题 × 2 种策略）。重复运行不是本轮
正式对照的必需项；`--repetitions 2` 会增加到 40 次，并近似翻倍 Provider 消耗。

评测产物写入：

```text
evaluations/{evaluation_id}/
├── suite.json
├── summary.json
└── runs/{run_id}/...
```

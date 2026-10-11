# 现有评测结果与结论边界

> 本文记录开发期真实实验，不把 Coverage、来源多样性等内部代理指标解释为报告事实
> 正确率。Moonshot 美元价格未配置，因此 USD 成本不参与结论，资源成本以 Token、搜索、
> 页面抓取和耗时表示。

## 1. 最新 V0.2 开发集评测

最新评测使用 `technical-research-dev@0.2.0`，覆盖 Agent 框架、消息系统、API、数据库、
云原生、向量数据库、实时协议、任务队列、RAG 分块和 Python 并发共 10 类技术调研问题。

- Evaluation ID：`8bd35aec-6fe7-4c60-bf4e-493c2818ac5f`
- 每个问题分别执行 Fixed Depth 与 Adaptive Budget；
- 每个任务—策略组合执行一次，共 20 次 Research Run；
- 单次硬上限为 60,000 Token、8 次搜索、18 次页面抓取和 600 秒；
- 原始产物：
  `backend/evaluations/8bd35aec-6fe7-4c60-bf4e-493c2818ac5f/summary.json`。

### 1.1 运行状态

| Policy | Attempts | Report generated | Failed | Evidence sufficient |
|---|---:|---:|---:|---:|
| Fixed Depth | 10 | 8 | 2 | 不适用 |
| Adaptive Budget | 10 | 10 | 0 | 0 |

Fixed 的两次失败均发生在搜索动作，停止原因为 Tavily/网络层 `ConnectError`；失败运行仅消耗
561 和 591 Token，不能解释为 Fixed 策略本身无法完成研究。Adaptive 的 10 次运行均生成
报告，但状态全部为 `completed_with_limitations`，因此“报告生成率 100%”不能解释为“证据
充分率 100%”。

### 1.2 原始策略汇总

失败运行不参与质量与平均资源指标，但其 Token 会计入总尝试消耗。

| Policy | Evaluated | Mean tokens | Total attempt tokens | Searches | Page fetches | Elapsed | Coverage | Diversity | Source quality | Coverage / 10k tokens |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Fixed Depth | 8/10 | 29,713 | 238,857 | 4.00 | 12.75 | 148.2s | 0.897 | 0.828 | 0.508 | 0.301 |
| Adaptive Budget | 10/10 | 41,498 | 414,982 | 7.30 | 11.00 | 187.1s | 1.000 | 1.000 | 0.542 | 0.245 |

这张表忠实描述全部尝试，但两种策略的平均值来自不同任务集合：Fixed 只包含 8 个成功
任务，Adaptive 包含全部 10 个任务，因此不能直接把两行差异全部归因于 Policy。

### 1.3 成功配对任务比较

为保证可比性，进一步只保留 Fixed 与 Adaptive 都产生可评测结果的 8 个问题：

| Metric | Fixed Depth | Adaptive Budget | Adaptive change |
|---|---:|---:|---:|
| Mean tokens | 29,713 | 40,843 | +37.5% |
| Mean searches | 4.00 | 7.25 | +81.3% |
| Mean page fetches | 12.75 | 10.50 | -17.6% |
| Mean elapsed | 148.2s | 168.4s | +13.6% |
| Coverage | 0.897 | 1.000 | +0.103 |
| Source diversity | 0.828 | 1.000 | +0.172 |
| Source quality | 0.508 | 0.534 | +0.026 |
| Report assertions | 16.38 | 20.88 | +27.5% |
| Coverage / 10k tokens | 0.301 | 0.250 | -17.1% |

配对结果表明，Adaptive 使用更多搜索和 LLM Token，换取更完整、更多样的内部证据，
同时减少页面抓取。它在这一版本中属于“质量优先的动态资源分配”，而不是“更低 Token
消耗”的策略；单位 Token Coverage 也低于 Fixed。

## 2. 来源质量限制

Adaptive 的 10 次运行共有 35 个未满足条件，全部来自来源质量低于阈值 `0.65`：其中
30 个为 `0.50`、4 个为 `0.60`、1 个为 `0.63`。

当前 `SourceQualityEvaluator` 使用确定性 URL 信号，只有少量已登记的官方文档、政府、
教育、文档路径和代码仓库会获得更高分；没有命中规则的域名默认得到 `0.50`。因此该指标
同时反映来源选择和规则覆盖能力，不能直接解释为来源内容不可信。这也解释了 Adaptive
虽然 Coverage 和 Diversity 达到 1.0，仍全部以 `completed_with_limitations` 结束。

## 3. 可支持的工程结论

现有数据支持以下结论：

1. Adaptive 可以在硬预算内对证据不足的分支追加资源，使内部 Coverage 与来源多样性提高；
2. 页面抓取减少不等于总成本下降，多轮搜索、Evidence Extraction 和 Writer 会把成本迁移
   到 LLM Token；
3. 本轮成功配对任务中，Adaptive 的 Coverage 提升 0.103、来源多样性提升 0.172，页面抓取
   减少 17.6%，代价是 Token 增加 37.5%、耗时增加 13.6%；
4. Provider 连接故障必须与 Policy 质量分开统计，失败样本不能以零质量混入策略均值；
5. `completed_with_limitations` 表示生成了可交付报告，但没有达到全部证据阈值；
6. Coverage、来源多样性和来源质量均为可审计的内部代理，不等于事实正确率。

现有数据不支持以下结论：

- Adaptive 在质量和成本上全面优于 Fixed；
- Adaptive 将 Token 或整体 API 成本降低；
- Fixed 的策略失败率为 20%；
- Coverage 1.0 或报告生成率 100% 等于事实准确率 100%。

## 4. 历史探索实验

V0.1 曾对 5 个任务执行重复评测。历史实验暴露了 Adaptive 高方差、Provider 失败以及
失败零值污染质量均值的问题，推动项目加入失败样本分离、总尝试消耗、停止原因和重复
运行统计。旧结果保留在对应 evaluation 产物中，但最终项目描述应优先引用 V0.2 配对数据。

代表性历史产物：

- `c5b756ee-7704-4f21-b0fc-b9addda7709a`：单任务重复对照；
- `457e2e16-5ea9-482a-bad1-a9547b683390`：V0.1 完整开发集；
- `8bd35aec-6fe7-4c60-bf4e-493c2818ac5f`：V0.2 多场景单次成对评测。

## 5. 简历建议表述

推荐写法：

> 构建 Fixed/Adaptive 多场景成对评测体系，从 Token、检索资源、运行状态和证据指标量化
> 策略权衡；在成功配对任务中，Adaptive 将 Coverage 从 0.897 提升至 1.000、来源多样性
> 从 0.828 提升至 1.000，并减少 17.6% 页面抓取，同时识别其 Token 增加 37.5% 的成本迁移。

如果简历空间有限，可以省略 Token 增幅，把成本权衡留到面试中说明，但不能表述为
“Adaptive 降低整体成本”。

## 6. 后续扩展（非当前 V1 必需）

- 为搜索连接故障加入受控重试；
- 扩展并校准来源质量规则；
- 增加事实正确性、完整性和引用支持度的独立盲评；
- 在更高预算允许时增加重复实验和置信区间；
- 配置真实模型单价后补充美元成本与质量—成本 Pareto 分析。

当前结果已经足以展示评测方法、策略权衡和问题诊断，不需要仅为了增加样本数量继续消耗
API 额度。

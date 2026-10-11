# Report Grounding V1

## 目标

最终报告中的每条事实陈述都必须能够追溯到一个或多个已通过来源校验的
`EvidenceItem`。Writer 只负责选择证据和组织章节，不能直接生成最终 Markdown。

## 数据契约

Writer 输出结构化的 `sections` 和 `assertions`。每个 section 只选择已有的
`subquestion_id`，每条 assertion 包含：

- `text`：必须逐字复制输入 Evidence 的 `claim`；
- `evidence_ids`：至少一个 Evidence ID；每一项都必须属于当前子问题，且其 claim 与
  `text` 一致。

报告标题由原始用户问题确定，章节标题由 Planner 的子问题确定，Writer 无权生成或
修改。正文、示例、对比结论和选型建议都必须表示为 assertion，因此不能绕过证据
绑定进入最终报告。

## 确定性校验与渲染

`CitationRenderer` 对每条 assertion 独立执行：

1. 检查 section 引用的子问题是否存在；
2. 检查所有 Evidence ID 是否存在；
3. 检查每条 Evidence 是否属于当前子问题；
4. 对空白字符归一化后，检查正文是否与每条被引用 Evidence claim 完全一致；
5. 去重引用并生成来源链接；
6. 每个章节按 Writer 给出的重要性顺序最多保留 6 条有效 assertion；
7. 仅将通过校验且位于容量内的 assertion 写入最终 Markdown。

不合格 assertion 会被丢弃，原因记录在报告的 `rejection_reasons` 中，同时增加
`rejected_assertion_count`。单条失败不会导致整次研究失败；某章节没有合格结论时，
渲染器只输出固定的“证据不足”提示。

超过章节容量但校验有效的 assertion 不属于错误，会计入
`omitted_assertion_count`，不会计入 rejected。Writer 的提示同样要求每节最多选择
6 条并按重要性排序；渲染器上限是防止 Provider 未遵守提示时继续生成证据堆砌的
确定性保护。

## 取舍与后续方向

V1 采用逐字 claim 约束，优先保证可审计性，因此报告语言可能不如自由生成自然。
后续可以引入受控的语义蕴含判定，允许经过验证的改写；在该判定可靠之前，不开放
自由改写，避免仅凭词项近似把新增事实误判为已有证据支持。

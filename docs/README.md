# Budgeted Research Agent 文档

本目录记录项目目标、架构、策略、证据协议、实验结果和 V1 求职交付材料。

## 文档索引

- [项目章程与 V1 定义](./project-charter.md)：项目目的、任务定义、范围、核心闭环、评测与完成标准。
- [GPT Researcher 源码分析](./gpt-researcher-source-analysis.md)：参考实现的真实执行路径、可借鉴设计与差异化机会。
- [固定深度 Baseline 设计](./fixed-depth-baseline.md)：V1 对照组的执行协议、固定参数、接口边界与验收标准。
- [Adaptive Budget Policy V1](./budget-policy.md)：覆盖度、新增率、冲突、动态加深与停止规则。
- [评测协议 V0.2](./evaluation.md)：版本化任务集、重复运行、波动统计与 Fixed/Adaptive 公平对照。
- [Report Grounding V1](./report-grounding.md)：结构化事实绑定、确定性引用校验与报告渲染。
- [技术栈与交付架构](./technical-stack.md)：后端、Agent Core、模型与搜索接入、持久化、API、前端展示和开发阶段。
- [系统架构与运行时序](./architecture.md)：已实现模块边界、研究时序、Adaptive 决策流、状态流转和部署边界。
- [现有评测结果与结论边界](./evaluation-results.md)：开发期真实数据、失败模式、可用结论和不可过度解读的部分。
- [演示与截图清单](./demo-guide.md)：推荐演示任务、截图文件名、README 替换方式和五分钟演示脚本。
- [简历与面试讲解材料](./resume-and-interview.md)：简历条目、30 秒与两分钟介绍、常见追问和项目不足。
- [V1 发布检查表](./v1-release-checklist.md)：离线验收、截图、密钥和 Git 上传前检查。

`project-charter.md`、`technical-stack.md` 等文档保留设计阶段措辞，用于呈现决策过程；
`architecture.md` 和根目录 `README.md` 代表当前已实现状态。

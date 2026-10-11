# V1 发布检查表

> 代码与文档已进入发布候选状态。以下项目由项目作者在上传 Git 前完成；涉及真实 Provider
> 的步骤均为可选，避免为发布检查额外产生 API 费用。

## 1. 离线验收

- [ ] 后端：`cd backend && uv run pytest`
- [ ] 前端：`cd frontend && npm run test`
- [ ] 前端生产构建：`cd frontend && npm run build`
- [ ] 后端健康检查返回 `{"status":"ok"}`
- [ ] 浏览器控制台无持续报错

当前测试集合应收集 53 个后端测试和 6 个前端测试。最终以本机命令输出为准。

## 2. 功能验收

- [x] CLI 离线闭环可以生成完整产物
- [x] Moonshot 与 Tavily Provider Check 已真实通过
- [x] Fixed Depth Smoke 已真实完成
- [x] Adaptive Budget Smoke 已真实完成
- [x] FastAPI、SQLite 和历史记录读取已真实完成
- [x] React 可以创建任务并展示实时状态
- [x] Evidence、Report 与引用跳转已真实验证
- [x] 用户取消可以保存 `cancelled` 状态与部分资源
- [ ] 时间修复后确认运行时长不再出现额外 480 分钟
- [ ] 时间修复后确认创建时间按北京时间显示

## 3. 文档与截图

- [x] 根目录 README
- [x] 系统架构与运行时序
- [x] Adaptive 与 Grounding 设计说明
- [x] 评测协议和现有结果边界
- [x] 简历与面试讲解材料
- [x] 演示与截图清单
- [x] `01-new-run.png`
- [x] `02-live-run.png`
- [x] `03-evidence-report.png`
- [ ] `04-cancelled-run.png`
- [x] 用真实图片替换 README 截图占位块

## 4. Git 上传前检查

- [ ] `git status --short` 只包含计划提交的源码和文档
- [ ] `.env` 未被跟踪
- [ ] `backend/runs/`、`backend/evaluations/`、`backend/data/` 未被跟踪
- [ ] `frontend/node_modules/` 与 `frontend/dist/` 未被跟踪
- [ ] README 中没有本机绝对路径、用户名或 API Key
- [ ] 截图中没有密钥、账户信息或不希望公开的绝对路径
- [ ] 如果仓库计划公开，选择并添加合适的 `LICENSE`
- [ ] 提交信息能说明 V1 的 Agent Core、API、Web 和文档范围

可以使用以下只读命令检查：

```bash
git status --short
git diff --check
git ls-files | rg '(^|/)\.env$|backend/(runs|evaluations|data)/|frontend/(node_modules|dist)/'
```

最后一条命令没有输出是预期结果。

## 5. 可选真实检查

以下操作会使用外部额度，发布前并非必须：

- [ ] `uv run bra providers-check`
- [ ] 新建一次 Adaptive Smoke 并完整生成报告
- [x] 重新运行完整开发集评测（`technical-research-dev@0.2.0`）

已有真实闭环和历史产物足够用于 V1 演示；完整评测只应在冻结代码、任务集和价格配置后
执行。

## 6. V1 完成定义

满足以下条件即可标记 V1 完成：

1. 后端测试、前端测试和生产构建全部通过；
2. 时间显示修复得到本机确认；
3. README 截图替换完成；
4. Git 检查确认没有密钥与生成产物；
5. README 的启动命令能在全新终端中执行。

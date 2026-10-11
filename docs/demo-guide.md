# 演示与截图清单

本文用于准备 GitHub README、简历附件或面试演示。截图由项目作者在本机放入
`docs/assets/screenshots/`，文档已经预留文件名和展示位置。

## 1. 演示前准备

终端 A：

```bash
cd backend
uv run bra serve --reload
```

终端 B：

```bash
cd frontend
npm run dev
```

浏览器打开 `http://127.0.0.1:5173`。

推荐演示问题：

```text
对比 Python 的 dataclass 和 NamedTuple：它们在可变性、类型定义和适用场景上有什么主要区别？
```

选择 Adaptive Budget、Smoke、50,000 Token、2 次搜索、4 次页面抓取、600 秒。

## 2. 建议截图

### 01 — 新建任务

文件名：`01-new-run.png`

画面应包含：

- 技术调研问题输入框；
- Adaptive 与 Fixed 策略选择；
- Smoke 与 Standard 档位；
- 四类预算配置。

README 位置：项目介绍之后。

> 📷 截图占位：`docs/assets/screenshots/01-new-run.png`

### 02 — 实时运行

文件名：`02-live-run.png`

画面应包含：

- `LIVE STREAM` 状态；
- Token、搜索、抓取和时间实时指标；
- 至少 3 条 Action Timeline；
- “停止运行”按钮。

README 位置：已实现能力之后。

> 📷 截图占位：`docs/assets/screenshots/02-live-run.png`

### 03 — Evidence 与 Report

文件名：`03-evidence-report.png`

画面应包含：

- 至少两张 Evidence 卡片；
- 来源质量等级和支持片段；
- 报告中的 Evidence ID 引用；
- `completed` 或 `completed_with_limitations` 状态。

README 位置：运行详情截图之后。

> 📷 截图占位：`docs/assets/screenshots/03-evidence-report.png`

### 04 — 主动取消

文件名：`04-cancelled-run.png`

画面应包含：

- `已取消` 状态；
- `cancelled by user` 停止原因；
- 取消前已经产生的资源消耗；
- 保留下来的 Action Timeline。

用于面试说明预算控制和运行可靠性，不一定放入首页 README。

> 📷 截图占位：`docs/assets/screenshots/04-cancelled-run.png`

### 05 — 评测命令输出（可选）

文件名：`05-evaluation-cli.png`

可以截取已有 Evaluation 的 CLI 汇总，也可以用文本表格代替。不要为了截图重新运行完整
付费评测。

> 📷 截图占位：`docs/assets/screenshots/05-evaluation-cli.png`

## 3. README 中替换方式

截图完成后，把对应占位块替换为：

```markdown
![创建研究任务](docs/assets/screenshots/01-new-run.png)
```

其他图片同理。建议使用 PNG，宽度保持在 1600–2400 像素之间，截图前关闭包含 API Key、
本机用户名或绝对路径的终端窗口。

## 4. 五分钟演示脚本

1. 用 30 秒说明问题：固定深度会在不同难度分支上浪费或错配预算；
2. 展示新建页，解释问题、策略、档位和硬预算；
3. 创建 Smoke 任务，指出实时预算和每个 Action 的决策原因；
4. 打开 Evidence，说明支持片段必须能回溯到抓取正文；
5. 点击报告中的 Evidence ID，展示引用与证据绑定；
6. 展示一条取消记录，说明任务控制和部分资源结算；
7. 最后展示评测文档，说明 Adaptive 以更多 Token 换取更高证据覆盖，并主动解释 Provider
   连接故障、来源质量阈值和内部代理指标的结论边界。

## 5. 演示失败时的备用材料

真实 Provider 可能超时或断网。演示前保留至少一条已完成历史记录；如果现场网络不可用，
可以：

- 用历史记录展示 Evidence、Report 和 Timeline；
- 运行 `uv run bra offline-demo` 展示确定性闭环；
- 打开 `backend/runs/<run_id>/` 中的 JSONL、Evidence 与 Markdown 产物；
- 使用现有评测结果文档讲解实验设计。

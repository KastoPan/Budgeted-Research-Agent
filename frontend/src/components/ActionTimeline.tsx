import { formatTimestamp } from "../lib/format";
import type { ActionRecord, ActionType } from "../lib/types";

const ACTION_LABELS: Record<ActionType, string> = {
  plan: "规划问题",
  search: "搜索来源",
  fetch: "抓取页面",
  extract_evidence: "提取证据",
  write_report: "撰写报告",
};

export function ActionTimeline({ actions }: { actions: ActionRecord[] }) {
  if (actions.length === 0) {
    return (
      <div className="empty-panel compact">
        <span className="empty-glyph">···</span>
        <p>任务开始后，Agent 的每一步决策会显示在这里。</p>
      </div>
    );
  }

  return (
    <ol className="timeline">
      {actions.map((action) => (
        <li key={`${action.sequence}-${action.action_id}`} className="timeline-item">
          <div className={`timeline-node action-${action.status}`}>
            {String(action.sequence).padStart(2, "0")}
          </div>
          <div className="timeline-content">
            <div className="timeline-heading">
              <strong>{ACTION_LABELS[action.action_type]}</strong>
              <span>{formatTimestamp(action.occurred_at)}</span>
            </div>
            <p>{action.reason}</p>
            <div className="timeline-meta">
              <span>{action.status}</span>
              {action.target && <span>{action.target}</span>}
              {action.actual_resources.tokens !== undefined && (
                <span>{action.actual_resources.tokens} tokens</span>
              )}
            </div>
            {action.error && <div className="action-error">{action.error}</div>}
          </div>
        </li>
      ))}
    </ol>
  );
}

import type { RunStatus } from "../lib/types";

const STATUS_LABELS: Record<RunStatus, string> = {
  pending: "等待中",
  running: "研究中",
  completed: "已完成",
  completed_with_limitations: "有限完成",
  budget_exhausted: "预算耗尽",
  insufficient_evidence: "证据不足",
  cancelled: "已取消",
  failed: "失败",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <span className={`status-badge status-${status}`}>
      <span className="status-dot" aria-hidden="true" />
      {STATUS_LABELS[status]}
    </span>
  );
}

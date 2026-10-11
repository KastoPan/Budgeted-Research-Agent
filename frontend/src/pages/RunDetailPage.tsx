import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ActionTimeline } from "../components/ActionTimeline";
import { EvidenceInspector } from "../components/EvidenceInspector";
import { MetricCard } from "../components/MetricCard";
import { ResearchReportPanel } from "../components/ResearchReportPanel";
import { StatusBadge } from "../components/StatusBadge";
import { isActiveRun, runsApi } from "../lib/api";
import { useRunStream } from "../hooks/useRunStream";
import type { ActionRecord } from "../lib/types";
import {
  formatDuration,
  formatNumber,
  formatTimestamp,
  parseTimestamp,
  shortRunId,
} from "../lib/format";

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const queryClient = useQueryClient();
  const runQuery = useQuery({
    queryKey: ["runs", runId],
    queryFn: () => runsApi.get(runId),
    enabled: Boolean(runId),
  });
  const eventsQuery = useQuery({
    queryKey: ["runs", runId, "events"],
    queryFn: () => runsApi.events(runId),
    enabled: Boolean(runId),
  });
  const evidenceQuery = useQuery({
    queryKey: ["runs", runId, "evidence"],
    queryFn: () => runsApi.evidence(runId),
    enabled: Boolean(runId),
  });
  const canHaveReport =
    runQuery.data?.status === "completed" ||
    runQuery.data?.status === "completed_with_limitations";
  const reportQuery = useQuery({
    queryKey: ["runs", runId, "report"],
    queryFn: () => runsApi.report(runId),
    enabled: Boolean(runId) && canHaveReport,
    retry: false,
  });
  const runIsActive = isActiveRun(runQuery.data);
  const streamState = useRunStream(runId, runIsActive);
  const [clock, setClock] = useState(() => Date.now());
  useEffect(() => {
    if (!runIsActive) return;
    const timer = window.setInterval(() => setClock(Date.now()), 1_000);
    return () => window.clearInterval(timer);
  }, [runIsActive]);
  const cancelMutation = useMutation({
    mutationFn: () => runsApi.cancel(runId),
    onSuccess: (run) => {
      queryClient.setQueryData(["runs", runId], run);
      void queryClient.invalidateQueries({ queryKey: ["runs"] });
      void queryClient.invalidateQueries({ queryKey: ["runs", runId, "events"] });
    },
  });

  function cancelRun() {
    if (window.confirm("确认停止这次研究吗？当前步骤可能已经产生部分 API 消耗。")) {
      cancelMutation.mutate();
    }
  }

  if (runQuery.isLoading) {
    return <PageState title="读取运行记录" message="正在从 SQLite 加载研究状态…" />;
  }
  if (runQuery.isError || !runQuery.data) {
    return (
      <PageState
        title="找不到这次运行"
        message="请确认后端正在运行，或从左侧选择另一条记录。"
        error
      />
    );
  }

  const run = runQuery.data;
  const budget = run.request.budget;
  const liveUsage = sumActionResources(eventsQuery.data ?? []);
  const totalTokens = runIsActive ? liveUsage.tokens : run.total_tokens;
  const searchCount = runIsActive ? liveUsage.searches : run.search_count;
  const pageFetchCount = runIsActive ? liveUsage.page_fetches : run.page_fetch_count;
  const elapsedSeconds = runIsActive
    ? Math.max(0, (clock - parseTimestamp(run.created_at).getTime()) / 1_000)
    : run.elapsed_seconds;
  const tokenProgress = (totalTokens / budget.max_tokens) * 100;
  const searchProgress = (searchCount / budget.max_searches) * 100;
  const fetchProgress = (pageFetchCount / budget.max_page_fetches) * 100;
  const timeProgress = (elapsedSeconds / budget.max_elapsed_seconds) * 100;

  return (
    <div className="page run-detail-page">
      <header className="run-header">
        <div className="run-header-topline">
          <span className="eyebrow">RUN #{shortRunId(run.run_id)}</span>
          <div className="run-controls">
            <StatusBadge status={run.status} />
            {isActiveRun(run) && (
              <button
                className="cancel-run-button"
                type="button"
                disabled={cancelMutation.isPending}
                onClick={cancelRun}
              >
                {cancelMutation.isPending ? "正在停止…" : "停止运行"}
              </button>
            )}
          </div>
        </div>
        <h1>{run.question}</h1>
        <div className="run-meta-row">
          <span>{run.policy === "adaptive_budget" ? "Adaptive Budget" : "Fixed Depth"}</span>
          <span>{run.profile === "smoke" ? "Smoke profile" : "Standard profile"}</span>
          <span>创建于 {formatTimestamp(run.created_at)}</span>
        </div>
      </header>

      {cancelMutation.isError && (
        <div className="inline-error run-control-error" role="alert">
          停止失败：{cancelMutation.error.message}
        </div>
      )}

      {run.stop_reason && !isActiveRun(run) && (
        <div className={`stop-banner stop-${run.status}`}>
          <span>停止原因</span>
          <strong>{run.stop_reason}</strong>
        </div>
      )}

      <section className="dashboard-section" aria-labelledby="budget-heading">
        <div className="section-heading-row">
          <div>
            <span className="section-index">01 / BUDGET</span>
            <h2 id="budget-heading">预算消耗</h2>
          </div>
          {isActiveRun(run) && (
            <span className={`live-indicator stream-${streamState}`}>
              {streamState === "connected"
                ? "LIVE STREAM"
                : streamState === "reconnecting"
                  ? "RECONNECTING"
                  : "CONNECTING"}
            </span>
          )}
        </div>
        <div className="metrics-grid">
          <MetricCard
            label="TOKENS"
            value={formatNumber(totalTokens)}
            detail={`上限 ${formatNumber(budget.max_tokens)}`}
            progress={tokenProgress}
            accent="blue"
          />
          <MetricCard
            label="SEARCHES"
            value={String(searchCount)}
            detail={`上限 ${budget.max_searches}`}
            progress={searchProgress}
            accent="lime"
          />
          <MetricCard
            label="PAGE FETCHES"
            value={String(pageFetchCount)}
            detail={`上限 ${budget.max_page_fetches}`}
            progress={fetchProgress}
            accent="coral"
          />
          <MetricCard
            label="ELAPSED"
            value={formatDuration(elapsedSeconds)}
            detail={`上限 ${formatDuration(budget.max_elapsed_seconds)}`}
            progress={timeProgress}
          />
        </div>
      </section>

      <section className="timeline-section" aria-labelledby="timeline-heading">
        <div className="section-heading-row">
          <div>
            <span className="section-index">02 / TRACE</span>
            <h2 id="timeline-heading">Action Timeline</h2>
          </div>
          <span className="action-count-label">
            {eventsQuery.data?.length ?? run.action_count} ACTIONS
          </span>
        </div>
        {eventsQuery.isError ? (
          <div className="inline-error">动作记录加载失败，请稍后刷新。</div>
        ) : (
          <ActionTimeline actions={eventsQuery.data ?? []} />
        )}
      </section>

      <section className="evidence-section" aria-labelledby="evidence-heading">
        <div className="section-heading-row">
          <div>
            <span className="section-index">03 / EVIDENCE</span>
            <h2 id="evidence-heading">Evidence Inspector</h2>
          </div>
          <span className="action-count-label">
            {evidenceQuery.data?.length ?? 0} VALIDATED
          </span>
        </div>
        {evidenceQuery.isError ? (
          <div className="inline-error">证据记录加载失败，请稍后刷新。</div>
        ) : (
          <EvidenceInspector evidence={evidenceQuery.data ?? []} />
        )}
      </section>

      <section className="report-section" aria-labelledby="report-heading">
        <div className="section-heading-row">
          <div>
            <span className="section-index">04 / REPORT</span>
            <h2 id="report-heading">Research Report</h2>
          </div>
        </div>
        {isActiveRun(run) ? (
          <div className="empty-panel compact">
            <span className="empty-glyph">…</span>
            <p>研究仍在进行，报告会在证据收集与校验完成后生成。</p>
          </div>
        ) : reportQuery.data ? (
          <ResearchReportPanel
            report={reportQuery.data}
            evidence={evidenceQuery.data ?? []}
            markdownUrl={runsApi.reportMarkdownUrl(runId)}
          />
        ) : reportQuery.isLoading ? (
          <div className="empty-panel compact"><p>正在读取研究报告…</p></div>
        ) : (
          <div className="empty-panel compact">
            <span className="empty-glyph">∅</span>
            <p>本次运行没有生成报告。请结合停止原因和动作时间线排查。</p>
          </div>
        )}
      </section>
    </div>
  );
}

function sumActionResources(actions: ActionRecord[]) {
  return actions.reduce(
    (totals, action) => ({
      tokens: totals.tokens + Number(action.actual_resources.tokens ?? 0),
      searches: totals.searches + Number(action.actual_resources.searches ?? 0),
      page_fetches:
        totals.page_fetches + Number(action.actual_resources.page_fetches ?? 0),
    }),
    { tokens: 0, searches: 0, page_fetches: 0 },
  );
}

function PageState({
  title,
  message,
  error = false,
}: {
  title: string;
  message: string;
  error?: boolean;
}) {
  return (
    <div className={`page-state${error ? " error" : ""}`}>
      <span className="state-orbit" aria-hidden="true" />
      <h1>{title}</h1>
      <p>{message}</p>
      {error && <Link to="/runs/new">返回新建任务</Link>}
    </div>
  );
}

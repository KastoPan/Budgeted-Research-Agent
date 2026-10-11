import { useQuery } from "@tanstack/react-query";
import { NavLink, Outlet } from "react-router-dom";

import { formatTimestamp, shortRunId } from "../lib/format";
import { runsApi } from "../lib/api";
import { StatusBadge } from "./StatusBadge";

export function AppShell() {
  const runsQuery = useQuery({
    queryKey: ["runs"],
    queryFn: runsApi.list,
    refetchInterval: 5_000,
  });

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink to="/runs/new" className="brand" aria-label="返回新建任务">
          <span className="brand-mark" aria-hidden="true">
            BR
          </span>
          <span>
            <strong>Budgeted Research</strong>
            <small>Agent Console</small>
          </span>
        </NavLink>

        <NavLink to="/runs/new" className="new-run-link">
          <span aria-hidden="true">＋</span>
          新建研究任务
        </NavLink>

        <div className="sidebar-section-heading">
          <span>最近运行</span>
          <span className="run-count">{runsQuery.data?.length ?? 0}</span>
        </div>

        <nav className="run-list" aria-label="最近运行">
          {runsQuery.isLoading && (
            <div className="sidebar-message">正在读取运行记录…</div>
          )}
          {runsQuery.isError && (
            <div className="sidebar-message error-copy">无法连接后端服务</div>
          )}
          {runsQuery.data?.length === 0 && (
            <div className="sidebar-message">还没有研究记录</div>
          )}
          {runsQuery.data?.map((run) => (
            <NavLink
              key={run.run_id}
              to={`/runs/${run.run_id}`}
              className={({ isActive }) =>
                `run-list-item${isActive ? " active" : ""}`
              }
            >
              <div className="run-list-row">
                <span className="run-id">#{shortRunId(run.run_id)}</span>
                <StatusBadge status={run.status} />
              </div>
              <span className="run-question">{run.question}</span>
              <span className="run-time">{formatTimestamp(run.created_at)}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <span className="connection-dot" aria-hidden="true" />
          FastAPI · SQLite
        </div>
      </aside>
      <main className="main-content">
        <Outlet />
      </main>
    </div>
  );
}

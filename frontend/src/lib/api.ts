import type {
  ActionRecord,
  CreateRunInput,
  EvidenceItem,
  ResearchReport,
  StoredRun,
} from "./types";

const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000/api/v1"
).replace(/\/$/, "");

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const payload = (await response.json()) as { detail?: unknown };
      if (typeof payload.detail === "string") {
        message = payload.detail;
      } else if (payload.detail) {
        message = JSON.stringify(payload.detail);
      }
    } catch {
      // Keep the HTTP fallback when an upstream proxy returns non-JSON.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export const runsApi = {
  list: () => request<StoredRun[]>("/runs"),
  get: (runId: string) => request<StoredRun>(`/runs/${runId}`),
  events: (runId: string) =>
    request<ActionRecord[]>(`/runs/${runId}/events`),
  evidence: (runId: string) =>
    request<EvidenceItem[]>(`/runs/${runId}/evidence`),
  report: (runId: string) =>
    request<ResearchReport>(`/runs/${runId}/report`),
  reportMarkdownUrl: (runId: string) =>
    `${API_BASE_URL}/runs/${runId}/report.md`,
  eventsStreamUrl: (runId: string) =>
    `${API_BASE_URL}/runs/${runId}/events/stream`,
  cancel: (runId: string) =>
    request<StoredRun>(`/runs/${runId}/cancel`, { method: "POST" }),
  create: (input: CreateRunInput) =>
    request<StoredRun>("/runs", {
      method: "POST",
      body: JSON.stringify(input),
    }),
};

export function isActiveRun(run?: StoredRun): boolean {
  return run?.status === "pending" || run?.status === "running";
}

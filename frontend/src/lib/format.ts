export function formatNumber(value: number): string {
  return new Intl.NumberFormat("zh-CN").format(value);
}

export function formatDuration(seconds: number): string {
  if (seconds < 1) return `${Math.round(seconds * 1_000)} ms`;
  if (seconds < 60) return `${seconds.toFixed(1)} s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = Math.round(seconds % 60);
  return `${minutes}m ${remainder}s`;
}

export function formatTimestamp(value: string): string {
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parseTimestamp(value));
}

export function parseTimestamp(value: string): Date {
  const includesTimezone = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value);
  return new Date(includesTimezone ? value : `${value}Z`);
}

export function shortRunId(runId: string): string {
  return runId.slice(0, 8);
}

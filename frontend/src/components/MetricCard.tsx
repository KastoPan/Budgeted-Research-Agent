interface MetricCardProps {
  label: string;
  value: string;
  detail: string;
  progress?: number;
  accent?: "ink" | "lime" | "coral" | "blue";
}

export function MetricCard({
  label,
  value,
  detail,
  progress,
  accent = "ink",
}: MetricCardProps) {
  const normalizedProgress = Math.max(0, Math.min(progress ?? 0, 100));
  return (
    <article className={`metric-card metric-${accent}`}>
      <span className="metric-label">{label}</span>
      <strong className="metric-value">{value}</strong>
      <span className="metric-detail">{detail}</span>
      {progress !== undefined && (
        <div className="metric-track" aria-label={`${label} ${normalizedProgress}%`}>
          <span style={{ width: `${normalizedProgress}%` }} />
        </div>
      )}
    </article>
  );
}

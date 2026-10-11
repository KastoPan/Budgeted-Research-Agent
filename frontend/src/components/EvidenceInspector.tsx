import type { EvidenceItem, SourceQualityTier } from "../lib/types";

const TIER_LABELS: Record<SourceQualityTier, string> = {
  primary: "一手来源",
  authoritative: "权威来源",
  documentation: "官方文档",
  community: "社区来源",
  unknown: "未分类",
};

export function EvidenceInspector({ evidence }: { evidence: EvidenceItem[] }) {
  if (evidence.length === 0) {
    return (
      <div className="empty-panel compact">
        <span className="empty-glyph">∅</span>
        <p>当前运行尚未收集到经过验证的证据。</p>
      </div>
    );
  }

  const groups = groupBySubquestion(evidence);

  return (
    <div className="evidence-groups">
      {groups.map(([subquestionId, items]) => (
        <section className="evidence-group" key={subquestionId}>
          <div className="evidence-group-heading">
            <span>{subquestionId}</span>
            <strong>{items.length} 条证据</strong>
          </div>
          <div className="evidence-list">
            {items.map((item) => (
              <article className="evidence-card" id={`evidence-${item.id}`} key={item.id}>
                <div className="evidence-card-topline">
                  <code>{item.id}</code>
                  <span className={`quality-tier tier-${item.source_quality.tier}`}>
                    {TIER_LABELS[item.source_quality.tier]} · {Math.round(item.source_quality.score * 100)}
                  </span>
                </div>
                <h3>{item.claim}</h3>
                <blockquote>{item.support_span}</blockquote>
                <a href={item.source_url} target="_blank" rel="noreferrer">
                  {item.source_title} <span aria-hidden="true">↗</span>
                </a>
                {item.source_quality.reasons.length > 0 && (
                  <p className="quality-reason">{item.source_quality.reasons.join(" · ")}</p>
                )}
              </article>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function groupBySubquestion(evidence: EvidenceItem[]) {
  const groups = new Map<string, EvidenceItem[]>();
  for (const item of evidence) {
    const group = groups.get(item.subquestion_id) ?? [];
    group.push(item);
    groups.set(item.subquestion_id, group);
  }
  return [...groups.entries()];
}

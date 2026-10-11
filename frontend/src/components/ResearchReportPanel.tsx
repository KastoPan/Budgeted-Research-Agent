import type { EvidenceItem, ResearchReport } from "../lib/types";

export function ResearchReportPanel({
  report,
  evidence,
  markdownUrl,
}: {
  report: ResearchReport;
  evidence: EvidenceItem[];
  markdownUrl: string;
}) {
  const evidenceById = new Map(evidence.map((item) => [item.id, item]));

  return (
    <article className="report-panel">
      <header className="report-panel-header">
        <div>
          <span className="section-index">GROUNDED REPORT</span>
          <h3>{report.title || "研究报告"}</h3>
        </div>
        <a className="markdown-link" href={markdownUrl} target="_blank" rel="noreferrer">
          打开 Markdown ↗
        </a>
      </header>

      <div className="report-stat-row">
        <span>{report.sections.length} 个章节</span>
        <span>{report.citation_ids.length} 条引用</span>
        <span>{report.rejected_assertion_count} 条主张被拒绝</span>
        <span>{report.omitted_assertion_count} 条主张被省略</span>
      </div>

      <div className="report-sections">
        {report.sections.map((section, index) => (
          <section key={`${section.subquestion_id}-${index}`}>
            <span className="report-section-number">{String(index + 1).padStart(2, "0")}</span>
            <div>
              <h4>{section.heading}</h4>
              {section.assertions.length === 0 ? (
                <p className="muted-copy">该章节没有通过证据校验的结论。</p>
              ) : (
                <ul>
                  {section.assertions.map((assertion, assertionIndex) => (
                    <li key={`${section.subquestion_id}-${assertionIndex}`}>
                      <span>{assertion.text}</span>
                      <span className="citation-links">
                        {assertion.evidence_ids.map((evidenceId) => {
                          const item = evidenceById.get(evidenceId);
                          return (
                            <a
                              href={`#evidence-${evidenceId}`}
                              title={item?.source_title ?? evidenceId}
                              key={evidenceId}
                            >
                              [{evidenceId}]
                            </a>
                          );
                        })}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>
        ))}
      </div>

      {report.rejection_reasons.length > 0 && (
        <details className="report-rejections">
          <summary>查看未进入报告的主张</summary>
          <ul>
            {report.rejection_reasons.map((reason, index) => (
              <li key={`${reason}-${index}`}>{reason}</li>
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

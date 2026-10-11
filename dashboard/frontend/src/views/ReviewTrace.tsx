import type { ReactNode } from 'react';
import type { ReviewTrace as Trace } from '../api';
import { Async, Card, SeverityDots, fmt, useApi } from '../components/ui';

const Step = ({ n, title, children }: { n: number; title: string; children: ReactNode }) => (
  <Card>
    <div className="flex gap-3">
      <div className="num font-semibold" style={{ width: 26, height: 26, borderRadius: 13, border: '1px solid var(--axis)', textAlign: 'center', lineHeight: '24px', flex: 'none' }}>{n}</div>
      <div className="min-w-0 flex-1"><h2 className="text-[15px] font-semibold mb-2">{title}</h2>{children}</div>
    </div>
  </Card>
);
const Row = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="grid gap-2 py-1" style={{ gridTemplateColumns: '150px 1fr' }}><div className="ink-2 text-[13.5px]">{label}</div><div className="min-w-0 break-words">{children}</div></div>
);

/** One review followed from its source values through labels and issue to the ranking and the memo. */
export function ReviewTrace({ id }: { id: string }) {
  const state = useApi<Trace>(`/reviews/${encodeURIComponent(id)}`);
  return (
    <Async state={state}>
      {({ review: r, issue, claims_on_this_issue: claims, cited_in_recommendation: cited }) => (
        <div className="grid gap-4">
          <div><h1 className="text-[22px] font-semibold">Review trace</h1><p className="ink-2 mono text-[13px]">{r.review_id}</p></div>
          <Step n={1} title="Source review">
            <p className="text-[16px]" style={{ whiteSpace: 'pre-wrap' }}>{r.review_text || <span className="muted">(empty text)</span>}</p>
            <div className="mt-2">
              <Row label="Posted">{r.review_timestamp} <span className="muted">(timezone not given)</span></Row>
              <Row label="Stars · likes · version">{r.review_rating} · {fmt(Number(r.review_likes))} · {r.app_version || <span className="muted">missing</span>}</Row>
              <Row label="Source row">{fmt(r.row_num)} <span className="muted mono text-[12px]">sha256 {r.source_sha256.slice(0, 16)}…</span></Row>
            </div>
          </Step>
          <Step n={2} title="Classification">
            {r.status === 'completed' ? (
              <>
                <Row label="Topic">{r.topic}</Row>
                <Row label="Intent">{r.intent}</Row>
                <Row label="Severity"><SeverityDots level={r.severity!} /></Row>
                <Row label="Sentiment">{r.sentiment}</Row>
                <Row label="Evidence quote">“{r.evidence_quote}”</Row>
                <Row label="Entities">{r.entities?.length ? r.entities.join(', ') : <span className="muted">none named</span>}</Row>
                <Row label="Flagged for review">{r.needs_review ? 'Yes' : 'No'}</Row>
                {r.cache_source_id && <Row label="Labels reused from">an identical text, <a className="mono" href={`#/reviews/${r.cache_source_id}`}>{r.cache_source_id.slice(0, 8)}</a></Row>}
              </>
            ) : <p>Status <strong>{r.status}</strong>{r.reason && <> · reason <span className="mono">{r.reason}</span></>}. This review was not classified.</p>}
          </Step>
          <Step n={3} title="Issue and ranking">
            {issue ? (
              <>
                <Row label="Issue"><a href={`#/issues/${issue.issue_id}`}>{issue.title}</a> <span className="mono muted">{issue.issue_id}</span></Row>
                <Row label="Rank">#{issue.rank}</Row>
                <Row label="Issue totals">{fmt(issue.complaint_count)} complaints × mean severity {Number(issue.mean_severity).toFixed(2)} = score {fmt(issue.priority_score)}</Row>
                <Row label="This review adds">1 complaint and {r.severity} to the severity sum</Row>
              </>
            ) : <p className="ink-2">Not part of the ranking. Only completed complaint and cancellation reviews are grouped into issues.</p>}
          </Step>
          <Step n={4} title="Recommendation">
            {claims.length ? (
              <>
                <p className="mb-2">{cited ? 'This review is quoted in the recommendation.' : 'This review is not quoted, but its issue is cited in the recommendation.'}</p>
                <div className="flex gap-2 flex-wrap">{claims.map((c) => <span className="chip" key={c.claim_id}>{c.claim_id} · {c.metric.replace(/_/g, ' ')} = {c.value}</span>)}</div>
                <p className="mt-2"><a href="#/recommendation">Open the recommendation</a></p>
              </>
            ) : <p className="ink-2">The recommendation does not cite a number from this review's issue.</p>}
          </Step>
        </div>
      )}
    </Async>
  );
}

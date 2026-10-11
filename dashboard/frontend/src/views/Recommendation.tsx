import type { Recommendation as RecommendationData } from '../api';
import { Markdown } from '../components/Markdown';
import { Async, Card, SeverityDots, Status, TOPIC_LABEL, useApi } from '../components/ui';

export function Recommendation() {
  const state = useApi<RecommendationData>('/recommendation');
  return (
    <Async state={state}>
      {(memo) => {
        const claimIssue = Object.fromEntries(memo.claims.map((c) => [c.claim_id, c.issue_id]));
        // The memo file ends with an appendix of tables; the page shows those from the database instead.
        const body = memo.markdown.split('\n---\n')[0].replace(/^# .*\n+/, '');
        const allMatch = memo.claims.every((c) => c.matches_saved_ranking);
        return (
          <div className="grid gap-4">
            <Card>
              <div className="ink-2 text-[13px]">AI-generated recommendation · written by <span className="mono">{memo.memo_config.split('+')[0]}</span></div>
              <div className="text-[26px] font-semibold leading-tight mt-1 mb-1">Prioritise {TOPIC_LABEL[memo.recommended_priority]?.toLowerCase() ?? memo.recommended_priority}</div>
              <p className="muted text-[13px]">
                The model saw only the saved ranking and a few example reviews. It wrote placeholders, and code filled in every number from the saved
                calculations. Each claim chip opens the issue the number comes from; each review code opens that review.
              </p>
              <Markdown text={body} claimIssue={claimIssue} />
            </Card>
            <Card title="Numbers cited, checked against the saved ranking"
                  note={<Status ok={allMatch}>{allMatch ? `All ${memo.claims.length} cited numbers equal the saved ranking.` : 'Some cited numbers differ from the saved ranking.'}</Status>}>
              <div className="scroll-x"><table className="data">
                <thead><tr><th>Claim</th><th>Issue</th><th>Metric</th><th className="r">Cited</th><th className="r">Saved ranking</th><th>Match</th></tr></thead>
                <tbody>{memo.claims.map((c) => (
                  <tr key={c.claim_id}><td className="mono">{c.claim_id}</td><td><a href={`#/issues/${c.issue_id}`}>{c.title}</a></td><td>{c.metric.replace(/_/g, ' ')}</td>
                    <td className="r">{c.value}</td><td className="r">{c.saved_value}</td><td><Status ok={!!c.matches_saved_ranking}>{c.matches_saved_ranking ? 'Match' : 'Differs'}</Status></td></tr>))}</tbody>
              </table></div>
            </Card>
            <Card title="Reviews cited as evidence" note="Each quote is an exact substring of the review it comes from.">
              <div className="scroll-x"><table className="data">
                <thead><tr><th>Review</th><th>Issue</th><th>Severity</th><th>Evidence quote</th></tr></thead>
                <tbody>{memo.cited_reviews.map((r) => (
                  <tr key={r.review_id}><td><a className="mono" href={`#/reviews/${r.review_id}`}>{r.review_id.slice(0, 8)}</a></td>
                    <td><a href={`#/issues/${r.issue_id}`}>{r.title}</a></td><td><SeverityDots level={r.severity} /></td><td className="ink-2">“{r.quote}”</td></tr>))}</tbody>
              </table></div>
            </Card>
          </div>
        );
      }}
    </Async>
  );
}

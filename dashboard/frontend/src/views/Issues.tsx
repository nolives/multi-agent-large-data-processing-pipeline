import { useState } from 'react';
import type { IssueDetail as IssueDetailData, IssueList } from '../api';
import { LineChart } from '../components/LineChart';
import { Async, BarList, Card, SeverityDots, StatTile, TOPIC_LABEL, fmt, monthLabel, useApi } from '../components/ui';

export function Issues() {
  const state = useApi<IssueList>('/issues');
  const [topic, setTopic] = useState('all');
  return (
    <Async state={state}>
      {(data) => {
        const topics = [...new Set(data.issues.map((i) => i.topic))].sort();
        const rows = data.issues.filter((i) => topic === 'all' || i.topic === topic);
        const max = Math.max(1, ...data.issues.map((i) => i.priority_score));
        return (
          <div className="grid gap-4">
            <div className="flex items-center gap-3 flex-wrap">
              <label className="ink-2 text-[13.5px]" htmlFor="topic">Topic</label>
              <select id="topic" value={topic} onChange={(e) => setTopic(e.target.value)} className="card !py-1.5 !px-3">
                <option value="all">All topics</option>
                {topics.map((t) => <option key={t} value={t}>{TOPIC_LABEL[t] ?? t}</option>)}
              </select>
              <span className="muted text-[13px]">{rows.length} of {data.issues.length} issues · {data.formula}</span>
            </div>
            <Card title="Issue ranking" note="The saved baseline ranking: descending priority score, then issue ID. Ranks are over all topics.">
              <div className="scroll-x"><table className="data">
                <thead><tr><th className="r">Rank</th><th>Issue</th><th>Topic</th><th className="r">Complaints</th><th className="r">Mean severity</th><th style={{ minWidth: 150 }}>Priority score</th></tr></thead>
                <tbody>{rows.map((i) => (
                  <tr key={i.issue_id}>
                    <td className="r">{i.rank}</td>
                    <td><a href={`#/issues/${i.issue_id}`}>{i.title}</a><div className="muted text-[12.5px] mono">{i.issue_id}</div></td>
                    <td>{TOPIC_LABEL[i.topic] ?? i.topic}</td>
                    <td className="r">{fmt(i.complaint_count)}</td>
                    <td className="r">{Number(i.mean_severity).toFixed(2)}</td>
                    <td><div className="flex items-center gap-2"><div className="bar-track flex-1"><div className="bar-fill" style={{ width: `${(100 * i.priority_score) / max}%` }} /></div>
                      <span className="num" style={{ minWidth: 48, textAlign: 'right' }}>{fmt(i.priority_score)}</span></div></td>
                  </tr>))}</tbody>
              </table></div>
            </Card>
          </div>
        );
      }}
    </Async>
  );
}

export function IssueDetail({ id }: { id: string }) {
  const [severity, setSeverity] = useState<number | null>(null);
  const [offset, setOffset] = useState(0);
  const state = useApi<IssueDetailData>(`/issues/${id}?limit=10&offset=${offset}${severity ? `&severity=${severity}` : ''}`);
  return (
    <Async state={state}>
      {({ issue, months, reviews, claims }) => {
        const levels = [1, 2, 3, 4, 5].map((k) => ({ level: k, count: issue[`severity_${k}` as 'severity_1'] }));
        const shown = severity ? levels[severity - 1].count : issue.complaint_count;
        return (
          <div className="grid gap-4">
            <div>
              <a href="#/issues" className="muted text-[13px]">← All issues</a>
              <h1 className="text-[22px] font-semibold mt-1">{issue.title}</h1>
              <p className="ink-2">{issue.description} <span className="mono muted">{issue.issue_id}</span></p>
            </div>
            <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
              <StatTile label="Rank" value={`#${issue.rank}`} sub={`${TOPIC_LABEL[issue.topic] ?? issue.topic} topic`} />
              <StatTile label="Complaints" value={fmt(issue.complaint_count)} sub={`${fmt(issue.cancellation_count)} say they are leaving`} />
              <StatTile label="Mean severity" value={Number(issue.mean_severity).toFixed(2)} sub="on the 1–5 scale" />
              <StatTile label="Priority score" value={fmt(issue.priority_score)} sub="complaints × mean severity" />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Severity of these complaints" note="1 is no reported problem, 5 is stated financial, privacy or data harm.">
                <BarList unit="complaints" data={levels.map((l) => ({ key: String(l.level), label: `Severity ${l.level}`, value: l.count }))} />
              </Card>
              <Card title="Complaints by month" note="Counts in this issue. The first and last months of the window are partial.">
                <LineChart points={months.map((m) => ({ label: monthLabel(m.month), value: m.complaint_count, detail: `severity sum ${fmt(m.severity_sum)}` }))}
                           format={(v) => fmt(Math.round(v))} height={190} />
              </Card>
            </div>
            {claims.length > 0 && (
              <Card title="Numbers the recommendation cites from this issue">
                <div className="flex gap-2 flex-wrap">{claims.map((c) => <span className="chip" key={c.claim_id}>{c.claim_id} · {c.metric.replace(/_/g, ' ')} = {c.value}</span>)}</div>
              </Card>
            )}
            <Card title="Reviews in this issue" note="Most-liked first. Each links to its full trace from source to ranking.">
              <div className="flex items-center gap-2 flex-wrap mb-3">
                <span className="ink-2 text-[13.5px]">Severity</span>
                {[null, 1, 2, 3, 4, 5].map((k) => (
                  <button key={String(k)} className="chip" aria-pressed={severity === k} onClick={() => { setSeverity(k); setOffset(0); }}
                          style={severity === k ? { borderColor: 'var(--ink)', color: 'var(--ink)', fontWeight: 600 } : undefined}>{k ?? 'All'}</button>))}
              </div>
              <div className="scroll-x"><table className="data">
                <thead><tr><th>Review</th><th>Severity</th><th>Evidence quote</th><th className="r">Likes</th></tr></thead>
                <tbody>{reviews.map((r) => (
                  <tr key={r.review_id}>
                    <td style={{ minWidth: 260 }}>{r.review_text}<div className="muted text-[12.5px] mt-1">
                      <a href={`#/reviews/${r.review_id}`} className="mono">{r.review_id.slice(0, 8)}</a> · {r.review_timestamp.slice(0, 10)} · {r.intent}
                      {r.needs_review && ' · flagged for review'}{r.cited && ' · cited in the recommendation'}</div></td>
                    <td><SeverityDots level={r.severity} /></td>
                    <td className="ink-2" style={{ minWidth: 200 }}>“{r.evidence_quote}”</td>
                    <td className="r">{fmt(Number(r.review_likes))}</td>
                  </tr>))}</tbody>
              </table></div>
              {reviews.length === 0 && <p className="muted mt-2">No reviews at this severity.</p>}
              <div className="flex items-center gap-3 mt-3 text-[13.5px]">
                <button className="chip" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 10))}>Previous</button>
                <span className="muted num">{shown ? `${offset + 1}–${Math.min(offset + 10, shown)} of ${fmt(shown)}` : '0'}</span>
                <button className="chip" disabled={offset + 10 >= shown} onClick={() => setOffset(offset + 10)}>Next</button>
              </div>
            </Card>
          </div>
        );
      }}
    </Async>
  );
}

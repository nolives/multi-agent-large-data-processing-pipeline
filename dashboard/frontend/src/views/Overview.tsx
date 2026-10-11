import type { IssueList, Overview as OverviewData, Recommendation } from '../api';
import { LineChart } from '../components/LineChart';
import { Async, BarList, Card, StatTile, TOPIC_LABEL, fmt, monthLabel, pct, share, useApi } from '../components/ui';

export function Overview() {
  const overview = useApi<OverviewData>('/overview');
  const issues = useApi<IssueList>('/issues');
  const memo = useApi<Recommendation>('/recommendation');
  return (
    <Async state={overview}>
      {(o) => {
        const t = o.totals;
        const quarantined = o.status.filter((s) => s.status === 'quarantined').reduce((sum, s) => sum + s.count, 0);
        const pending = o.status.filter((s) => s.status === 'pending').reduce((sum, s) => sum + s.count, 0);
        const areas = issues.data?.priority_areas ?? [];
        const recommended = memo.data?.recommended_priority;
        // The first and last calendar months are partial, so their shares rest on fewer reviews.
        const months = o.months.map((m) => ({ label: monthLabel(m.month), value: m.reviews ? (100 * m.complaints) / m.reviews : 0,
                                              detail: `${fmt(m.complaints)} complaints of ${fmt(m.reviews)} reviews` }));
        return (
          <div className="grid gap-4">
            {recommended && (
              <section className="card">
                <div className="ink-2 text-[13px]">AI-generated recommendation for next quarter</div>
                <div className="text-[30px] font-semibold leading-tight mt-1">Prioritise {TOPIC_LABEL[recommended]?.toLowerCase() ?? recommended}</div>
                <p className="ink-2 mt-2 max-w-[70ch]">
                  Written by a model from the saved ranking and a small evidence pack. Code inserted every number and checked every cited issue and review.{' '}
                  <a href="#/recommendation">Read the full memo with its evidence</a>.
                </p>
              </section>
            )}
            <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
              <StatTile label="Reviews in this run" value={fmt(t.reviews)} sub={`${o.run?.source_file ?? ''} · ${t.first_review.slice(0, 10)} to ${t.last_review.slice(0, 10)}`} />
              <StatTile label="Classified" value={pct(t.completed, t.reviews)} sub={`${fmt(t.completed)} classified · ${fmt(quarantined)} quarantined · ${fmt(pending)} pending`} />
              <StatTile label="Complaints and cancellations" value={fmt(t.complaints)} sub={`${pct(t.complaints, t.completed)} of classified reviews, in ${fmt(t.issues)} issues`} />
              <StatTile label="Independent check, topic agreement" value={o.verification ? share(o.verification.agreement.topic) : 'n/a'}
                        sub={o.verification ? <>on {fmt(o.verification.compared)} sampled texts · <a href="#/quality">quality details</a></> : 'not run'} />
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="The four priority areas" note="Severity sum of complaints (count × mean severity). The recommended area is highlighted.">
                {areas.length ? (
                  <BarList unit="severity sum" data={areas.map((a) => ({
                    key: a.priority, label: TOPIC_LABEL[a.priority] ?? a.priority, value: Number(a.numbers.severity_sum.value.replace(/,/g, '')),
                    display: a.numbers.severity_sum.value, emphasis: a.priority === recommended,
                    detail: `${a.numbers.complaint_count.value} complaints, mean severity ${a.numbers.mean_severity.value}, ${a.numbers.share_of_complaints.value} of complaints`,
                  }))} />
                ) : <p className="muted">Not published for this run.</p>}
                <div className="scroll-x mt-3"><table className="data"><thead><tr><th>Area</th><th className="r">Complaints</th><th className="r">Mean severity</th><th className="r">Share</th></tr></thead>
                  <tbody>{areas.map((a) => <tr key={a.priority}><td>{TOPIC_LABEL[a.priority] ?? a.priority}</td><td className="r">{a.numbers.complaint_count.value}</td>
                    <td className="r">{a.numbers.mean_severity.value}</td><td className="r">{a.numbers.share_of_complaints.value}</td></tr>)}</tbody></table></div>
              </Card>
              <Card title="Top issues by priority score" note={<>Score = complaint count × mean severity. <a href="#/issues">See the full ranking</a>.</>}>
                <BarList unit="priority score" data={(issues.data?.issues ?? []).slice(0, 8).map((i) => ({
                  key: i.issue_id, label: i.title, value: i.priority_score, href: `#/issues/${i.issue_id}`,
                  detail: `${fmt(i.complaint_count)} complaints, mean severity ${Number(i.mean_severity).toFixed(2)}`,
                }))} />
              </Card>
            </div>
            <div className="grid gap-4 lg:grid-cols-2">
              <Card title="Complaint share of reviews, by month" note="Percent of classified reviews that are complaints or cancellations. The first and last months are partial.">
                <LineChart points={months} format={(v) => `${Math.round(v)}%`} partial={[0, months.length - 1]} />
              </Card>
              <Card title="What reviewers are doing" note="Intent of each classified review.">
                <BarList unit="reviews" data={o.intents.map((i) => ({ key: i.intent, label: i.intent[0].toUpperCase() + i.intent.slice(1), value: i.count,
                                                                    display: `${fmt(i.count)} · ${pct(i.count, t.completed, 0)}` }))} />
                <p className="muted text-[13px] mt-3">
                  Cancellation is stated intent in a public review, not observed churn. These are self-selected reviews with no revenue or plan data.
                </p>
              </Card>
            </div>
          </div>
        );
      }}
    </Async>
  );
}

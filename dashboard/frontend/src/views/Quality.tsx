import type { Checks, Overview } from '../api';
import { Async, Card, Status, fmt, pct, share, useApi } from '../components/ui';

export function Quality() {
  const checks = useApi<Checks>('/checks');
  const overview = useApi<Overview>('/overview');
  return (
    <div className="grid gap-4">
      <Async state={checks}>
        {(c) => (
          <Card title="Does the dashboard match the saved calculations?"
                note={<Status ok={c.all_ok}>{c.all_ok ? 'Every check passes.' : 'At least one check fails.'} {c.note}</Status>}>
            <div className="scroll-x"><table className="data">
              <thead><tr><th>Check</th><th className="r">Expected</th><th className="r">Found</th><th>Result</th></tr></thead>
              <tbody>{c.checks.map((x) => <tr key={x.check}><td>{x.check}</td><td className="r">{fmt(x.expected)}</td><td className="r">{fmt(x.actual)}</td>
                <td><Status ok={x.ok}>{x.ok ? 'Pass' : 'Fail'}</Status></td></tr>)}</tbody>
            </table></div>
          </Card>
        )}
      </Async>
      <Async state={overview}>
        {(o) => {
          const g = o.golden?.enricher_vs_human;
          const rows: [string, string][] = [['Topic', 'topic_agreement'], ['Intent', 'intent_agreement'], ['Severity, exact', 'severity_agreement'],
                                            ['Severity, within one level', 'severity_within_one'], ['Topic, intent and severity together', 'all_three_agreement']];
          return (
            <>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="Hand-labeled golden set" note={g ? `${o.golden!.scored} reviews labeled by hand before any model prediction; ${o.golden!.ambiguous_cases} were marked ambiguous.` : 'Not published for this run.'}>
                  {g && (
                    <div className="scroll-x"><table className="data">
                      <thead><tr><th>Agreement with the human label</th><th className="r">All cases</th><th className="r">Non-ambiguous</th></tr></thead>
                      <tbody>{rows.map(([label, key]) => <tr key={key}><td>{label}</td><td className="r">{share(g.all_cases[key])}</td><td className="r">{share(g.non_ambiguous_cases[key])}</td></tr>)}</tbody>
                    </table></div>
                  )}
                  <p className="muted text-[13px] mt-3">Fifty cases are a small diagnostic sample, not a precise accuracy estimate.</p>
                </Card>
                <Card title="Independent verifier" note={o.verification ? `A second model re-labeled ${fmt(o.verification.compared)} sampled texts from the text alone, without seeing the first labels.` : 'Not run.'}>
                  {o.verification && (
                    <div className="scroll-x"><table className="data">
                      <thead><tr><th>Agreement between the two models</th><th className="r">Share</th></tr></thead>
                      <tbody>{[['Topic', 'topic'], ['Intent', 'intent'], ['Severity', 'severity'], ['All three', 'all_three']].map(([label, key]) =>
                        <tr key={key}><td>{label}</td><td className="r">{share(o.verification!.agreement[key])}</td></tr>)}</tbody>
                    </table></div>
                  )}
                  <p className="muted text-[13px] mt-3">Agreement between two models is not accuracy: two versions of the verifier agreed with each other on only about 70% of texts.</p>
                </Card>
              </div>
              <div className="grid gap-4 lg:grid-cols-2">
                <Card title="Coverage" note="Every source review of the run is accounted for.">
                  <div className="scroll-x"><table className="data">
                    <thead><tr><th>Status</th><th>Reason</th><th className="r">Reviews</th></tr></thead>
                    <tbody>{o.status.map((s) => <tr key={s.status + s.reason}><td>{s.status}</td><td className="ink-2">{s.reason ?? ''}</td><td className="r">{fmt(s.count)}</td></tr>)}</tbody>
                  </table></div>
                  <p className="muted text-[13px] mt-3">
                    {fmt(o.totals.reused_from_identical_text)} reviews ({pct(o.totals.reused_from_identical_text, o.totals.reviews)}) reuse the labels of an identical text.{' '}
                    {fmt(o.totals.needs_review)} are flagged for review.
                    {o.source_file_profile && ` The full source file of ${fmt(o.source_file_profile.records)} rows was ingested and profiled.`}
                  </p>
                </Card>
                <Card title="Model calls behind this run" note={o.model_calls ? `Total logged cost $${o.model_calls.total_cost_usd.toFixed(2)}, computed from reported usage.` : undefined}>
                  <div className="scroll-x"><table className="data">
                    <thead><tr><th>Role</th><th>Model</th><th className="r">Calls</th><th className="r">Failed</th><th className="r">Cost</th></tr></thead>
                    <tbody>{(o.model_calls?.by_role ?? []).map((c) => <tr key={c.role + c.model}><td>{c.role}</td><td className="mono">{c.model}</td>
                      <td className="r">{fmt(c.attempts)}</td><td className="r">{fmt(c.failed)}</td><td className="r">${c.cost_usd.toFixed(4)}</td></tr>)}</tbody>
                  </table></div>
                  <p className="muted text-[13px] mt-3 mono break-all">{o.run?.label_config}</p>
                </Card>
              </div>
              <Card title="What this evidence cannot show">
                <ul className="prose list-disc pl-5 ink-2">
                  <li>These are self-selected public app reviews from a fixed historical window, not a sample of all users.</li>
                  <li>There is no revenue, plan tier or confirmed cancellation data. Cancellation language is stated intent, not observed churn.</li>
                  <li>Labels come from an automated classifier. It is weaker on non-English text and can be swayed by text that argues for its own label.</li>
                  <li>The first and last calendar months of the window are partial.</li>
                </ul>
              </Card>
            </>
          );
        }}
      </Async>
    </div>
  );
}

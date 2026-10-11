import express, { type NextFunction, type Request, type Response } from 'express';
import { databaseFromEnv, type Db } from './db.js';

const ISSUE_ID = /^[a-z_]+\.[a-z0-9-]+$/;
const INTENTS = ['cancellation', 'complaint', 'request', 'praise', 'unclear'];
const REVIEW_FIELDS = `review_id, review_text, review_rating, review_likes, app_version, review_timestamp, status, reason, topic, intent,
  sentiment, severity, entities, evidence_quote, needs_review, cache_source_id, issue_id`;

/** Postgres returns COUNT and SUM as strings; the API returns numbers. */
const n = (value: unknown): number => Number(value ?? 0);

async function document(db: Db, key: string): Promise<unknown> {
  const { rows } = await db.query<{ body: unknown }>('SELECT body FROM documents WHERE key = $1', [key]);
  return rows[0]?.body ?? null;
}

/**
 * The dashboard API. Every route reads the published run from Postgres with parameterized SELECTs;
 * nothing here writes, and nothing calls a model. The numbers shown are the pipeline's saved results.
 */
export function createApp(db: Db = databaseFromEnv()) {
  const app = express();
  app.set('trust proxy', 1);
  app.disable('x-powered-by');

  const route = (handler: (req: Request, res: Response) => Promise<void>) =>
    (req: Request, res: Response, next: NextFunction) => handler(req, res).catch(next);

  app.get('/api/health', route(async (_req, res) => {
    const { rows } = await db.query<{ run_id: string; published_at: string }>('SELECT run_id, published_at FROM published_run');
    res.json({ ok: true, database: 'connected', run: rows[0] ?? null });
  }));

  // Overall metrics: coverage, label mix, monthly volume, and the saved quality reports.
  app.get('/api/overview', route(async (_req, res) => {
    const [run, status, intent, topic, months, totals, verify, golden, calls, ingestion] = await Promise.all([
      db.query('SELECT run_id, published_at, label_config, source_file, source_sha256, source_rows FROM published_run'),
      db.query("SELECT status, COALESCE(reason, '') AS reason, COUNT(*) AS count FROM reviews GROUP BY status, reason ORDER BY count DESC"),
      db.query("SELECT intent, COUNT(*) AS count FROM reviews WHERE status = 'completed' GROUP BY intent"),
      db.query(`SELECT topic, COUNT(*) AS reviews, COUNT(issue_id) AS complaints, COALESCE(SUM(severity) FILTER (WHERE issue_id IS NOT NULL), 0) AS severity_sum
                FROM reviews WHERE status = 'completed' GROUP BY topic ORDER BY severity_sum DESC, topic`),
      db.query(`SELECT review_month, COUNT(*) AS reviews, COUNT(issue_id) AS complaints FROM reviews WHERE status = 'completed'
                GROUP BY review_month ORDER BY review_month`),
      db.query(`SELECT COUNT(*) AS reviews, COUNT(*) FILTER (WHERE status = 'completed') AS completed, COUNT(issue_id) AS complaints,
                COUNT(*) FILTER (WHERE needs_review) AS needs_review, COUNT(*) FILTER (WHERE cache_source_id IS NOT NULL) AS reused,
                (SELECT COUNT(*) FROM issues) AS issues, MIN(review_timestamp) AS first_review, MAX(review_timestamp) AS last_review FROM reviews`),
      document(db, 'verify_report'), document(db, 'golden_report'), document(db, 'model_calls'), document(db, 'full_corpus_ingestion'),
    ]);
    const t = totals.rows[0] as Record<string, unknown>;
    const v = verify as { compared: number; agreement: Record<string, number>; verifier_config: string; sample: unknown } | null;
    const g = golden as { scored: number; ambiguous_cases: number; enricher_vs_human: Record<string, unknown> } | null;
    const full = ingestion as { profile?: { counts?: Record<string, number> } } | null;
    res.json({
      run: run.rows[0] ?? null,
      totals: { reviews: n(t.reviews), completed: n(t.completed), complaints: n(t.complaints), needs_review: n(t.needs_review),
                reused_from_identical_text: n(t.reused), issues: n(t.issues), first_review: t.first_review, last_review: t.last_review },
      status: status.rows.map((r) => ({ status: r.status, reason: r.reason || null, count: n(r.count) })),
      intents: INTENTS.map((name) => ({ intent: name, count: n(intent.rows.find((r) => r.intent === name)?.count) })),
      topics: topic.rows.map((r) => ({ topic: r.topic, reviews: n(r.reviews), complaints: n(r.complaints), severity_sum: n(r.severity_sum) })),
      months: months.rows.map((r) => ({ month: r.review_month, reviews: n(r.reviews), complaints: n(r.complaints) })),
      verification: v && { compared: v.compared, agreement: v.agreement, verifier_config: v.verifier_config, sample: v.sample },
      golden: g && { scored: g.scored, ambiguous_cases: g.ambiguous_cases, enricher_vs_human: g.enricher_vs_human },
      model_calls: calls,
      full_corpus: full?.profile?.counts ?? null,
    });
  }));

  // The saved baseline ranking, with the four priority areas the recommendation chooses between.
  app.get('/api/issues', route(async (_req, res) => {
    const [issues, areas] = await Promise.all([
      db.query(`SELECT issue_id, topic, aspect, title, description, rank, complaint_count, severity_sum, mean_severity::text AS mean_severity,
                priority_score, cancellation_count, needs_review_count, severity_1, severity_2, severity_3, severity_4, severity_5
                FROM issues ORDER BY rank`),
      document(db, 'priority_areas'),
    ]);
    res.json({ formula: 'priority_score = complaint_count × mean_severity = severity_sum', issues: issues.rows, priority_areas: areas });
  }));

  // One issue: its saved numbers, its monthly trend, and the reviews behind it.
  app.get('/api/issues/:id', route(async (req, res) => {
    const id = String(req.params.id);
    if (!ISSUE_ID.test(id)) { res.status(400).json({ error: 'Not a valid issue ID.' }); return; }
    const limit = Math.min(Math.max(Number(req.query.limit) || 20, 1), 50);
    const offset = Math.max(Number(req.query.offset) || 0, 0);
    const severity = Number(req.query.severity);
    const filter = Number.isInteger(severity) && severity >= 1 && severity <= 5 ? severity : null;
    const [issue, months, reviews, claims] = await Promise.all([
      db.query(`SELECT issue_id, topic, aspect, title, description, rank, complaint_count, severity_sum, mean_severity::text AS mean_severity,
                priority_score, cancellation_count, needs_review_count, severity_1, severity_2, severity_3, severity_4, severity_5
                FROM issues WHERE issue_id = $1`, [id]),
      db.query('SELECT review_month AS month, complaint_count, severity_sum FROM issue_months WHERE issue_id = $1 ORDER BY review_month', [id]),
      db.query(`SELECT review_id, review_text, review_timestamp, review_likes, intent, severity, evidence_quote, needs_review,
                (SELECT COUNT(*) FROM memo_citations c WHERE c.review_id = r.review_id) AS cited
                FROM reviews r WHERE issue_id = $1 AND ($2::int IS NULL OR severity = $2)
                ORDER BY review_likes::int DESC, row_num LIMIT $3 OFFSET $4`, [id, filter, limit, offset]),
      db.query('SELECT claim_id, metric, value FROM claims WHERE issue_id = $1 ORDER BY claim_id', [id]),
    ]);
    if (!issue.rows[0]) { res.status(404).json({ error: 'No such issue.' }); return; }
    res.json({ issue: issue.rows[0], months: months.rows, claims: claims.rows, limit, offset, severity: filter,
               reviews: reviews.rows.map((r) => ({ ...r, cited: n(r.cited) > 0 })) });
  }));

  // One review traced from source values through labels and issue to the ranking and any memo claim.
  app.get('/api/reviews/:id', route(async (req, res) => {
    const id = String(req.params.id);
    if (id.length > 80) { res.status(400).json({ error: 'Not a valid review ID.' }); return; }
    const { rows } = await db.query<Record<string, unknown>>(`SELECT ${REVIEW_FIELDS}, source_sha256, row_num FROM reviews WHERE review_id = $1`, [id]);
    const review = rows[0];
    if (!review) { res.status(404).json({ error: 'No such review.' }); return; }
    const [issue, claims, citation] = await Promise.all([
      review.issue_id ? db.query(`SELECT issue_id, title, rank, complaint_count, severity_sum, mean_severity::text AS mean_severity, priority_score
                                  FROM issues WHERE issue_id = $1`, [review.issue_id]) : Promise.resolve({ rows: [] }),
      review.issue_id ? db.query('SELECT claim_id, metric, value FROM claims WHERE issue_id = $1 ORDER BY claim_id', [review.issue_id]) : Promise.resolve({ rows: [] }),
      db.query('SELECT quote FROM memo_citations WHERE review_id = $1', [id]),
    ]);
    res.json({ review, issue: issue.rows[0] ?? null, claims_on_this_issue: claims.rows, cited_in_recommendation: citation.rows.length > 0 });
  }));

  // The AI-generated recommendation with every number and review it cites, checked against the saved ranking.
  app.get('/api/recommendation', route(async (_req, res) => {
    const [memo, claims, citations] = await Promise.all([
      db.query('SELECT recommended_priority, markdown, memo_config, checked FROM memo'),
      db.query(`SELECT c.claim_id, c.issue_id, c.metric, c.value, i.title,
                CASE c.metric WHEN 'complaint_count' THEN i.complaint_count::text WHEN 'severity_sum' THEN i.severity_sum::text
                              WHEN 'priority_score' THEN i.priority_score::text WHEN 'mean_severity' THEN i.mean_severity::text END AS saved_value
                FROM claims c JOIN issues i USING (issue_id) ORDER BY c.claim_id`),
      db.query(`SELECT c.review_id, c.issue_id, c.severity, c.quote, i.title FROM memo_citations c JOIN issues i USING (issue_id) ORDER BY i.rank, c.review_id`),
    ]);
    if (!memo.rows[0]) { res.status(404).json({ error: 'No recommendation has been published for this run.' }); return; }
    res.json({ ...memo.rows[0], claims: claims.rows.map((c) => ({ ...c, matches_saved_ranking: c.value === c.saved_value })), cited_reviews: citations.rows });
  }));

  // Recomputes the ranking from the review rows in the database and compares it with the saved tables.
  app.get('/api/checks', route(async (_req, res) => {
    const [issues, order, claims, run] = await Promise.all([
      db.query(`SELECT COUNT(*) AS issues, COUNT(*) FILTER (WHERE r.n = i.complaint_count AND r.s = i.severity_sum AND r.s = i.priority_score
                AND ROUND(r.s::numeric / r.n, 6) = i.mean_severity) AS agree
                FROM issues i LEFT JOIN (SELECT issue_id, COUNT(*) AS n, SUM(severity) AS s FROM reviews WHERE issue_id IS NOT NULL GROUP BY issue_id) r USING (issue_id)`),
      db.query(`SELECT COUNT(*) AS out_of_order FROM (SELECT rank, ROW_NUMBER() OVER (ORDER BY priority_score DESC, issue_id) AS expected FROM issues) x WHERE rank <> expected`),
      db.query(`SELECT COUNT(*) AS claims, COUNT(*) FILTER (WHERE c.value = CASE c.metric WHEN 'complaint_count' THEN i.complaint_count::text
                WHEN 'severity_sum' THEN i.severity_sum::text WHEN 'priority_score' THEN i.priority_score::text WHEN 'mean_severity' THEN i.mean_severity::text END) AS agree
                FROM claims c JOIN issues i USING (issue_id)`),
      db.query(`SELECT p.source_rows, (SELECT COUNT(*) FROM reviews) AS loaded,
                (SELECT COUNT(*) FROM reviews WHERE intent IN ('complaint', 'cancellation') AND status = 'completed' AND issue_id IS NULL) AS ungrouped,
                (SELECT COUNT(*) FROM reviews WHERE status = 'completed' AND POSITION(evidence_quote IN review_text) = 0) AS bad_quotes,
                (SELECT COUNT(*) FROM memo_citations c LEFT JOIN reviews r USING (review_id) WHERE r.review_id IS NULL) AS missing_citations
                FROM published_run p`),
    ]);
    const i = issues.rows[0] as Record<string, unknown>, c = claims.rows[0] as Record<string, unknown>, r = (run.rows[0] ?? {}) as Record<string, unknown>;
    const checks = [
      { check: 'Every source review of the run is in the database', expected: n(r.source_rows), actual: n(r.loaded) },
      { check: 'Issue counts, severity sums, means and scores recomputed from review rows match the saved ranking', expected: n(i.issues), actual: n(i.agree) },
      { check: 'Issues ranked out of order (descending score, then issue ID)', expected: 0, actual: n((order.rows[0] as Record<string, unknown>).out_of_order) },
      { check: 'Numbers cited by the recommendation match the saved ranking', expected: n(c.claims), actual: n(c.agree) },
      { check: 'Completed complaints without an issue', expected: 0, actual: n(r.ungrouped) },
      { check: 'Evidence quotes that are not an exact substring of their review', expected: 0, actual: n(r.bad_quotes) },
      { check: 'Reviews cited by the recommendation that are missing from the database', expected: 0, actual: n(r.missing_citations) },
    ].map((x) => ({ ...x, ok: x.expected === x.actual }));
    res.json({ all_ok: checks.every((x) => x.ok), checks, note: 'Computed by the backend from the database on each request.' });
  }));

  app.use((_req, res) => { res.status(404).json({ error: 'Not found.' }); });
  app.use((error: unknown, _req: Request, res: Response, _next: NextFunction) => {
    // Log server-side; never send driver messages (which can include connection details) to the client.
    console.error('Unhandled error:', error instanceof Error ? error.message : error);
    res.status(500).json({ error: 'The dashboard could not read its database.' });
  });
  return app;
}

/** The single app instance. Vercel's Express integration uses this default export; server.ts listens on it locally. */
const app = createApp();
export default app;

import { readFileSync } from 'node:fs';
import type { AddressInfo } from 'node:net';
import { PGlite } from '@electric-sql/pglite';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { createApp } from './app.js';

/**
 * Runs the real schema and the real route SQL against an in-process Postgres (PGlite) holding a small
 * hand-made run: two issues, five reviews, a memo with two claims and one cited review.
 */
let base: string;
let close: () => Promise<void>;
let pg: PGlite;

const review = (id: string, row: number, text: string, month: string, status: string, labels: string) =>
  `('${id}', ${row}, '${text}', '1', '${row}', '', '${month}-01 00:00:00', '${month}', 'sha-${id}', '${status}', ${labels})`;
const labelled = (topic: string, intent: string, severity: number, quote: string, issue: string | null, source: string | null = null) =>
  `NULL, '${topic}', '${intent}', -0.5, ${severity}, '[]', '${quote}', false, ${source ? `'${source}'` : 'NULL'}, ${issue ? `'${issue}'` : 'NULL'}`;

beforeAll(async () => {
  pg = new PGlite();
  await pg.exec(readFileSync(new URL('../../db/schema.sql', import.meta.url), 'utf8'));
  await pg.exec(`
    INSERT INTO published_run (run_id, label_config, source_file, source_sha256, source_rows) VALUES ('test', 'cfg', 'reviews.csv', 'abc', 5);
    INSERT INTO reviews VALUES
      ${review('r1', 1, 'Too many ads', '2023-01', 'completed', labelled('usability', 'complaint', 2, 'Too many ads', 'usability.ads'))},
      ${review('r2', 2, 'Too many ads', '2023-02', 'completed', labelled('usability', 'complaint', 2, 'Too many ads', 'usability.ads', 'r1'))},
      ${review('r3', 3, 'Cannot log in at all', '2023-02', 'completed', labelled('access', 'cancellation', 4, 'Cannot log in', 'access.login'))},
      ${review('r4', 4, 'Love it', '2023-02', 'completed', labelled('other', 'praise', 1, 'Love it', null))},
      ${review('r5', 5, '', '2023-03', 'quarantined', `'empty_review_text', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL`)};
    INSERT INTO issues VALUES
      ('access.login', 'access', 'login', 'Cannot log in', 'Login fails.', 'model', 1, 1, 4, 4.000000, 4, 1, 0, 0, 0, 0, 1, 0),
      ('usability.ads', 'usability', 'ads', 'Too many ads', 'Ad interruptions.', 'model', 2, 2, 4, 2.000000, 4, 0, 0, 0, 2, 0, 0, 0);
    INSERT INTO issue_months SELECT issue_id, review_month, COUNT(*), SUM(severity) FROM reviews WHERE issue_id IS NOT NULL GROUP BY 1, 2;
    INSERT INTO memo (recommended_priority, markdown, memo_config, checked) VALUES ('access', '## Recommendation', 'memo-cfg', '{"valid": true}');
    INSERT INTO claims VALUES ('C001', 'access.login', 'priority_score', '4'), ('C002', 'usability.ads', 'mean_severity', '2.000000');
    INSERT INTO memo_citations VALUES ('r3', 'access.login', 4, 'Cannot log in');
    INSERT INTO documents VALUES ('verify_report', '{"compared": 3, "agreement": {"topic": 1}, "verifier_config": "v", "sample": {}}'),
      ('priority_areas', '[{"priority": "access"}]');
  `);
  const app = createApp({ query: async (text, params) => ({ rows: (await pg.query(text, params as unknown[])).rows as never[] }) });
  const server = app.listen(0);
  base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  close = () => new Promise((resolve) => server.close(() => resolve()));
});

afterAll(async () => { await close(); await pg.close(); });

const get = async (path: string) => {
  const response = await fetch(base + path);
  return { status: response.status, body: await response.json() };
};

describe('dashboard API', () => {
  it('reports overall metrics from the database', async () => {
    const { body } = await get('/api/overview');
    expect(body.totals).toMatchObject({ reviews: 5, completed: 4, complaints: 3, issues: 2, reused_from_identical_text: 1 });
    expect(body.intents.find((i: { intent: string }) => i.intent === 'complaint').count).toBe(2);
    expect(body.months.map((m: { month: string; complaints: number }) => [m.month, m.complaints])).toEqual([['2023-01', 1], ['2023-02', 2]]);
    expect(body.status).toContainEqual({ status: 'quarantined', reason: 'empty_review_text', count: 1 });
    expect(body.verification.compared).toBe(3);
  });

  it('returns the saved ranking in rank order', async () => {
    const { body } = await get('/api/issues');
    expect(body.issues.map((i: { issue_id: string; mean_severity: string }) => [i.issue_id, i.mean_severity]))
      .toEqual([['access.login', '4.000000'], ['usability.ads', '2.000000']]);
  });

  it('returns an issue with its trend, claims and reviews, and filters by severity', async () => {
    const { body } = await get('/api/issues/usability.ads');
    expect(body.reviews.map((r: { review_id: string }) => r.review_id)).toEqual(['r2', 'r1']);
    expect(body.months).toHaveLength(2);
    expect(body.claims).toEqual([{ claim_id: 'C002', metric: 'mean_severity', value: '2.000000' }]);
    expect((await get('/api/issues/usability.ads?severity=4')).body.reviews).toEqual([]);
    expect((await get('/api/issues/access.login')).body.reviews[0].cited).toBe(true);
  });

  it('traces one review to its issue, rank and claims', async () => {
    const { body } = await get('/api/reviews/r3');
    expect(body.review.evidence_quote).toBe('Cannot log in');
    expect(body.issue).toMatchObject({ issue_id: 'access.login', rank: 1 });
    expect(body.claims_on_this_issue[0].claim_id).toBe('C001');
    expect(body.cited_in_recommendation).toBe(true);
    expect((await get('/api/reviews/r2')).body.review.cache_source_id).toBe('r1');
  });

  it('returns the recommendation with claims checked against the ranking', async () => {
    const { body } = await get('/api/recommendation');
    expect(body.recommended_priority).toBe('access');
    expect(body.claims.every((c: { matches_saved_ranking: boolean }) => c.matches_saved_ranking)).toBe(true);
    expect(body.cited_reviews[0]).toMatchObject({ review_id: 'r3', title: 'Cannot log in' });
  });

  it('confirms the database agrees with the saved ranking, and notices when it does not', async () => {
    expect((await get('/api/checks')).body.all_ok).toBe(true);
    await pg.exec("UPDATE issues SET complaint_count = 3 WHERE issue_id = 'usability.ads'; UPDATE claims SET value = '5' WHERE claim_id = 'C001'");
    const { body } = await get('/api/checks');
    expect(body.all_ok).toBe(false);
    expect(body.checks.filter((c: { ok: boolean }) => !c.ok)).toHaveLength(2);
    await pg.exec("UPDATE issues SET complaint_count = 2 WHERE issue_id = 'usability.ads'; UPDATE claims SET value = '4' WHERE claim_id = 'C001'");
  });

  it('rejects malformed IDs and unknown records', async () => {
    expect((await get("/api/issues/x'; DROP TABLE reviews;--")).status).toBe(400);
    expect((await get('/api/issues/nope.none')).status).toBe(404);
    expect((await get('/api/reviews/unknown')).status).toBe(404);
    expect((await get('/api/overview')).body.totals.reviews).toBe(5);
  });
});

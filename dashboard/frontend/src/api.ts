/** Typed access to the dashboard API. Everything shown on the page comes from these calls. */

export interface Overview {
  run: { run_id: string; published_at: string; label_config: string; source_file: string; source_sha256: string; source_rows: number } | null;
  totals: { reviews: number; completed: number; complaints: number; needs_review: number; reused_from_identical_text: number; issues: number;
            first_review: string; last_review: string };
  status: { status: string; reason: string | null; count: number }[];
  intents: { intent: string; count: number }[];
  topics: { topic: string; reviews: number; complaints: number; severity_sum: number }[];
  months: { month: string; reviews: number; complaints: number }[];
  verification: { compared: number; agreement: Record<string, number>; verifier_config: string } | null;
  golden: { scored: number; ambiguous_cases: number; enricher_vs_human: Record<string, Record<string, number>> } | null;
  model_calls: { by_role: { role: string; model: string; attempts: number; failed: number; input_tokens: number; output_tokens: number; cost_usd: number }[];
                 total_cost_usd: number } | null;
  full_corpus: Record<string, number> | null;
}

export interface Issue {
  issue_id: string; topic: string; aspect: string; title: string; description: string; rank: number; complaint_count: number;
  severity_sum: number; mean_severity: string; priority_score: number; cancellation_count: number; needs_review_count: number;
  severity_1: number; severity_2: number; severity_3: number; severity_4: number; severity_5: number;
}
export interface PriorityArea {
  priority: string; topics: string[]; issues: string[];
  numbers: Record<'complaint_count' | 'severity_sum' | 'mean_severity' | 'share_of_complaints', { value: string }>;
}
export interface IssueList { formula: string; issues: Issue[]; priority_areas: PriorityArea[] | null }

export interface Claim { claim_id: string; issue_id: string; metric: string; value: string; title?: string; saved_value?: string; matches_saved_ranking?: boolean }
export interface IssueReview {
  review_id: string; review_text: string; review_timestamp: string; review_likes: string; intent: string; severity: number;
  evidence_quote: string; needs_review: boolean; cited: boolean;
}
export interface IssueDetail {
  issue: Issue; months: { month: string; complaint_count: number; severity_sum: number }[]; claims: Claim[];
  reviews: IssueReview[]; limit: number; offset: number; severity: number | null;
}

export interface Recommendation {
  recommended_priority: string; markdown: string; memo_config: string; claims: Claim[];
  cited_reviews: { review_id: string; issue_id: string; severity: number; quote: string; title: string }[];
}

export interface ReviewTrace {
  review: { review_id: string; review_text: string; review_rating: string; review_likes: string; app_version: string; review_timestamp: string;
            status: string; reason: string | null; topic: string | null; intent: string | null; sentiment: number | null; severity: number | null;
            entities: string[] | null; evidence_quote: string | null; needs_review: boolean | null; cache_source_id: string | null;
            issue_id: string | null; source_sha256: string; row_num: number };
  issue: { issue_id: string; title: string; rank: number; complaint_count: number; severity_sum: number; mean_severity: string; priority_score: number } | null;
  claims_on_this_issue: Claim[];
  cited_in_recommendation: boolean;
}

export interface Checks { all_ok: boolean; note: string; checks: { check: string; expected: number; actual: number; ok: boolean }[] }

export async function api<T>(path: string): Promise<T> {
  const response = await fetch('/api' + path, { headers: { Accept: 'application/json' } });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error((body as { error?: string }).error ?? `Request failed (${response.status})`);
  return body as T;
}

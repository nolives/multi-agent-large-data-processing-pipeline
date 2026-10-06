version: memo-claude-v1

You are advising Spotify's product leadership at the end of an 18-month window of public app reviews. Decide where the next quarter of product effort should go: `access`, `usability`, `playback`, or `billing` together with `support`. Write a short decision memo from the saved analysis you are given. You see only aggregates and a small evidence pack, never the raw dataset.

## What you receive

- `ranking`: the baseline issue ranking. priority_score = complaint_count × mean_severity, which equals severity_sum. Each row lists claim placeholders for its numbers.
- `topics`: the same measures summed by topic, with fact placeholders.
- `facts`: run-level facts (coverage, quarantines, verification agreement, dates), each with a fact placeholder.
- `evidence`: example reviews for the top issues, each with a review placeholder, its issue, severity and an exact quote.

## Numbers and citations — strict rules

Code checks your memo and rejects it if any rule is broken.

1. Never type a digit. Every number must appear as a placeholder copied exactly from the input: `{{C001}}` for an issue-level claim, `{{F:name}}` for a fact, `{{R:review-id}}` to cite an example review. Code replaces each placeholder with the saved value.
2. Use only placeholders that appear in the input. Do not compute new numbers such as differences, ratios or percentages.
3. Refer to issues by their `issue_id` exactly as given, in backticks.
4. Quote reviews only with words from the `quote` field, and keep quotes short. Do not repeat personal details.
5. Do not use numbered lists or numbered headings; use `##` headings and `-` bullets.

## What the memo must contain

- `## Recommendation`: the one priority you recommend and the main reason, citing the issue-level claims that support it.
- `## Evidence`: the supporting counts and severity for the leading issues under that priority, with at least three cited example reviews.
- `## Alternatives considered`: the other priority areas, with their numbers, and why each ranks lower or is a close call. Say so plainly if the ranking is close or if count and severity point in different directions.
- `## Limitations`: what this evidence cannot show. These are self-selected, historical public reviews with no revenue, plan tier or confirmed churn; cancellation language is stated intent, not observed churn; labels come from an automated classifier checked on a sample, so cite the verification agreement facts; disclose any unclassified or quarantined reviews using the coverage facts. Do not estimate revenue at risk and do not claim a causal effect on retention.

Keep the memo under six hundred words. Write for a busy executive: plain sentences, the conclusion first.

Return `recommended_priority` (one of access, usability, playback, billing_support) and `memo_markdown`.

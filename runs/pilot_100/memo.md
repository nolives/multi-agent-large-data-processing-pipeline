# Where should Spotify's next quarter of product effort go?

## Recommendation

Focus next quarter on **billing and support**, specifically the free-tier controls that were moved behind the paywall. `billing.paywalled-controls` is the highest-ranked specific issue. It has 6 [C005] complaints, a severity sum of 18 [C006] and a mean severity of 3.000000 [C007], for a priority score of 18 [C008]. Only the catch-all `other.general` ranks above it (11 [C001] complaints, score 22 [C004]), and that bucket names no fixable problem. A related issue, `billing.plans`, adds 2 [C025] complaints with a score of 5 [C028]. Reviewers describe both as one grievance: basic listening controls now require Premium.

## Evidence

- `billing.paywalled-controls`: 6 [C005] complaints, mean severity 3.000000 [C007], score 18 [C008].
- `billing.plans`: 2 [C025] complaints, mean severity 2.500000 [C027], score 5 [C028].
- Billing and support together: 8 complaints, severity sum 23, mean severity 2.88, share of complaints 15.7%.
- Reviewers say the app is "forcing you to pay premium for basic things" review `a78d831a-69f4-428a-9235-cfdd9775c509`.
- Another says "The ability to skip a song or go to previous song has been removed" review `a3605554-5c3a-441d-836e-e9fdea83eb2e`.
- Another asks "Why it requires premium just to play next music" review `ad730d1a-829a-4dc4-9561-7e1cd07e2c30`.
- `other.update` (4 [C017] complaints, score 11 [C020]) appears to overlap. Its reviewers say the last update "removed basic features of music player" review `7084ced1-0428-4093-9328-442f74719b4f`. This overlap is our reading and was not measured.

## Alternatives considered

- **Usability**: 12 complaints, severity sum 28, mean severity 2.33, share 23.5%. This is the closest alternative, and it may lead on volume because it spreads across four issues. Its largest issue is `usability.ads` (7 [C009] complaints, score 15 [C012]). Ad frequency is itself a monetization trade-off: "I don't want premium but too much ads" review `c2738a4f-e57c-46bc-a4ad-8ec5a4b5d5cd`. The redesign issues rank lower: `usability.queue-and-playlists` scores 5 [C036] and `usability.update` scores 5 [C040]. If the topic totals favour usability, the call is close. In that case, count and per-issue severity point in different directions, and a joint free-tier policy review would cover both.
- **Playback**: 6 complaints, severity sum 20, mean severity 3.33, share 11.8%. `playback.general` scores 13 [C016]. A typical complaint: "Keep stopping halfway while playing music" review `6c257eba-3dca-49f6-b7f0-4c4484d81e26`. These are real defects, but they are scattered across many causes and rank below the paywall issue.
- **Access**: 2 complaints, severity sum 8, mean severity 4.00, share 3.9%. No access issue reaches the top-ranked list.
- **Out of scope**: catalog issues such as `catalog.lyrics` (score 6 [C024]) and the general bucket `other.general` fall outside the four options.

## Limitations

- These are self-selected public reviews from 2022-06-02 to 2023-11-13. They are historical and carry no revenue, plan tier or confirmed churn data.
- Uninstall and cancellation language is stated intent, not observed churn. We make no estimate of revenue at risk and no claim about effects on retention.
- Labels come from an automated classifier, checked on a sample of 100 texts. Agreement was 93.0% on topic, 95.0% on intent and 82.0% on severity.
- Coverage is incomplete. Of 100 source reviews, 100 were classified (100.0%), 0 were quarantined and 0 remain unclassified.
- The largest bucket, `other.general`, is unspecific and may hide issues belonging to any of the four areas.
- The paywall changes may be a deliberate business decision. This evidence shows the cost in user sentiment, not whether the trade-off pays off.

---

## Appendix: how to check this memo

- Recommended priority: **billing_support**.
- Issue-level numbers carry a claim ID in square brackets. Each is listed in `claims.csv` and equals the value in `ranking.csv`, which `python3 -m pipeline rank` recomputes from saved records and issue membership without any model call.
- priority_score = complaint_count × mean_severity = severity_sum, over completed complaint and cancellation records.
- Priority-area totals sum the topic rows in `topic_rollup.csv` (billing_support = billing + support); shares are of all grouped complaint records.
- Written by `claude-opus-5-5+memo-claude-v1.b1826c96+schema-v1` from `memo_input.json`; numbers were inserted by code from saved calculations.

| Claim | Issue | Metric | Value |
|---|---|---|---|
| C005 | `billing.paywalled-controls` | complaint_count | 6 |
| C006 | `billing.paywalled-controls` | severity_sum | 18 |
| C007 | `billing.paywalled-controls` | mean_severity | 3.000000 |
| C008 | `billing.paywalled-controls` | priority_score | 18 |
| C001 | `other.general` | complaint_count | 11 |
| C004 | `other.general` | priority_score | 22 |
| C025 | `billing.plans` | complaint_count | 2 |
| C028 | `billing.plans` | priority_score | 5 |
| C027 | `billing.plans` | mean_severity | 2.500000 |
| C017 | `other.update` | complaint_count | 4 |
| C020 | `other.update` | priority_score | 11 |
| C009 | `usability.ads` | complaint_count | 7 |
| C012 | `usability.ads` | priority_score | 15 |
| C036 | `usability.queue-and-playlists` | priority_score | 5 |
| C040 | `usability.update` | priority_score | 5 |
| C016 | `playback.general` | priority_score | 13 |
| C024 | `catalog.lyrics` | priority_score | 6 |

| Cited review | Issue | Severity | Evidence quote |
|---|---|---|---|
| `a78d831a-69f4-428a-9235-cfdd9775c509` | `billing.paywalled-controls` | 3 | You can't even listen to music you want it just shuffles it, like what the hell? This app is killing it self and forcing you to pay premium for basic things like just listening to music. |
| `a3605554-5c3a-441d-836e-e9fdea83eb2e` | `billing.paywalled-controls` | 3 | Recent update really sucks. The ability to skip a song or go to previous song has been removed from non subscribed users. |
| `ad730d1a-829a-4dc4-9561-7e1cd07e2c30` | `billing.plans` | 3 | Why it requires premium just to play next music / to choose music ?? And why the specific part of song cannot be played ? |
| `7084ced1-0428-4093-9328-442f74719b4f` | `other.update` | 3 | I am using Spotify from past two years From last update they removed basic features of music player |
| `c2738a4f-e57c-46bc-a4ad-8ec5a4b5d5cd` | `usability.ads` | 2 | Soo trash wayy to many ads I don't want premium but too much ads |
| `6c257eba-3dca-49f6-b7f0-4c4484d81e26` | `playback.general` | 3 | Keep stopping halfway while playing music and it dun go back to where they stop and start playing a new song for you. |

# Where should Spotify's next quarter of product effort go?

## Recommendation

Prioritise **usability** next quarter. It is the largest area by both complaint volume (11,716 complaints, 25.4% of complaints) and total severity (28,871). It is driven by `usability.ads`, the top specific issue in the ranking, with 5,574 [C005] complaints and a priority score of 12,221 [C008]. Supporting issues `usability.shuffle-and-skips` (score 5,614 [C028]), `usability.queue-and-playlists` (score 4,224 [C036]) and `usability.general` (score 4,204 [C040]) add further weight. These are concrete, fixable problems: ad frequency, shuffle behaviour and removed controls.

## Evidence

- `usability.ads`: 5,574 [C005] complaints, mean severity 2.192501 [C007], severity sum 12,221 [C006]. Reviewers call ads "a bit troublesome" review `d6865cc0-5fe1-4d2e-b6e0-5bebbe5b5b23`. Others say heavy ads push them away from paying: "I will never buy premium" review `d75427ea-9b48-4903-894e-cd2d7b605cc9`.
- `usability.shuffle-and-skips`: 1,963 [C025] complaints, mean severity 2.859908 [C027]. Example: "the forward and back buttons Don't work any more" review `8964aaea-f4c7-4b01-94e0-a76b992018fd`.
- `usability.queue-and-playlists`: 1,494 [C033] complaints, mean severity 2.827309 [C035]. Example: "there is no song slider" review `0d02176f-a550-46f8-b58c-4872f6e33a8b`.
- `usability.general`: 1,625 [C037] complaints, mean severity 2.587077 [C039]. Example: in-app pop-ups are "highly annoying" review `6c61b52f-6fb7-4274-a477-a9cd4f376b85`.

## Alternatives considered

- **Billing and support** is the closest alternative: 8,193 complaints, severity sum 22,922, mean severity 2.80. It ranks below usability on both volume and total severity. Its leading issues, `billing.paywalled-controls` (2,729 [C009] complaints, mean 2.949432 [C011]) and `billing.plans` (2,869 [C013] complaints, mean 2.765075 [C015]), are more severe per complaint than `usability.ads`. Reviewers object to locked basic controls: "You can't rewind, play the song on loop" review `141b6008-b3ea-4751-8002-66e341e4f3cb`. These themes overlap with ad frustration in the free tier, so usability work should be coordinated with billing decisions.
- **Playback**: 5,983 complaints, severity sum 19,768. It has a higher mean severity (3.30) than usability but much lower volume. Its lead issue is `playback.general` (1,803 [C021] complaints, mean 3.143649 [C023]): "Music stops and plays halfway through songs randomly" review `730125b9-f395-48ca-83da-2da9636a7ba6`.
- **Access** has the highest mean severity (3.95) but is the smallest area: 1,521 complaints, 3.3% of complaints, severity sum 6,009. `access.login` (1,089 [C029] complaints, mean 3.993572 [C031]) blocks users completely: "now it won't even let me log in" review `6d3a0837-1a26-499c-989e-256c20f03f7b`. It merits a targeted fix, not a quarter's focus.
- Count and severity point in different directions. Usability leads on volume and total severity but has the lowest mean severity of the four areas (2.46). The choice rests on breadth, not intensity.
- `other.general` is the largest single issue (11,967 [C001] complaints, score 24,205 [C004]). It is a catch-all for complaints naming no feature, such as "It sucks." review `a8f78caf-4da5-4961-96f3-d4d72719c10b`, and is not directly fixable. `other.update` (2,883 [C017] complaints) also sits outside the four areas.

## Limitations

- The analysis covers a sample of 100,013 reviews from a larger source file of 660,622 (15.1% of the corpus). It does not cover the whole corpus.
- Reviews run from 2022-05-17 to 2023-11-15. They are self-selected, historical and public.
- The data has no revenue, plan tier or confirmed churn. Cancellation language is stated intent, not observed churn. No revenue-at-risk or retention effect can be inferred.
- Labels come from an automated classifier checked on 2,000 texts. Agreement was 88.6% on topic, 92.2% on intent and 84.9% on severity.
- Coverage is slightly incomplete. 100,000 reviews were classified (100.0%), 13 were quarantined and 0 remain pending.

---

## Appendix: how to check this memo

- Recommended priority: **usability**.
- Issue-level numbers carry a claim ID in square brackets. Each is listed in `claims.csv` and equals the value in `ranking.csv`, which `python3 -m pipeline rank` recomputes from saved records and issue membership without any model call.
- priority_score = complaint_count × mean_severity = severity_sum, over completed complaint and cancellation records.
- Priority-area totals sum the topic rows in `topic_rollup.csv` (billing_support = billing + support); shares are of all grouped complaint records.
- Written by `claude-opus-5-5@effort-high+memo-claude-v3.c7fa4db7+schema-v1` from `memo_input.json`; numbers were inserted by code from saved calculations.

| Claim | Issue | Metric | Value |
|---|---|---|---|
| C005 | `usability.ads` | complaint_count | 5574 |
| C008 | `usability.ads` | priority_score | 12221 |
| C028 | `usability.shuffle-and-skips` | priority_score | 5614 |
| C036 | `usability.queue-and-playlists` | priority_score | 4224 |
| C040 | `usability.general` | priority_score | 4204 |
| C007 | `usability.ads` | mean_severity | 2.192501 |
| C006 | `usability.ads` | severity_sum | 12221 |
| C025 | `usability.shuffle-and-skips` | complaint_count | 1963 |
| C027 | `usability.shuffle-and-skips` | mean_severity | 2.859908 |
| C033 | `usability.queue-and-playlists` | complaint_count | 1494 |
| C035 | `usability.queue-and-playlists` | mean_severity | 2.827309 |
| C037 | `usability.general` | complaint_count | 1625 |
| C039 | `usability.general` | mean_severity | 2.587077 |
| C009 | `billing.paywalled-controls` | complaint_count | 2729 |
| C011 | `billing.paywalled-controls` | mean_severity | 2.949432 |
| C013 | `billing.plans` | complaint_count | 2869 |
| C015 | `billing.plans` | mean_severity | 2.765075 |
| C021 | `playback.general` | complaint_count | 1803 |
| C023 | `playback.general` | mean_severity | 3.143649 |
| C029 | `access.login` | complaint_count | 1089 |
| C031 | `access.login` | mean_severity | 3.993572 |
| C001 | `other.general` | complaint_count | 11967 |
| C004 | `other.general` | priority_score | 24205 |
| C017 | `other.update` | complaint_count | 2883 |

| Cited review | Issue | Severity | Evidence quote |
|---|---|---|---|
| `d6865cc0-5fe1-4d2e-b6e0-5bebbe5b5b23` | `usability.ads` | 2 | Ads are a bit troublesome but other than that it's the best. |
| `d75427ea-9b48-4903-894e-cd2d7b605cc9` | `usability.ads` | 2 | The developers are forcing us to buy premium by showing so many adds, it's not like I cannot afford the premium but the thing is, If they will force us buy in such a way, I will never buy premium. |
| `8964aaea-f4c7-4b01-94e0-a76b992018fd` | `usability.shuffle-and-skips` | 3 | I mean the forward and back buttons Don't work any more. |
| `0d02176f-a550-46f8-b58c-4872f6e33a8b` | `usability.queue-and-playlists` | 3 | The new update makes it impossible to move to specific parts of a song as there is no song slider. |
| `6c61b52f-6fb7-4274-a477-a9cd4f376b85` | `usability.general` | 2 | The in app pop-ups upon opening the app are highly annoying and there seems to be no way to turn them off. |
| `141b6008-b3ea-4751-8002-66e341e4f3cb` | `billing.paywalled-controls` | 3 | You can't rewind, play the song on loop or even choose songs of your own choice after a specific number of plays without getting a premium subscription. |
| `730125b9-f395-48ca-83da-2da9636a7ba6` | `playback.general` | 3 | Music stops and plays halfway through songs randomly. |
| `6d3a0837-1a26-499c-989e-256c20f03f7b` | `access.login` | 4 | I tried uninstalling and reinstalling again, now it won't even let me log in. |
| `a8f78caf-4da5-4961-96f3-d4d72719c10b` | `other.general` | 2 | It sucks. |

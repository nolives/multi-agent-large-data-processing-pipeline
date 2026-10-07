# Where should Spotify's next quarter of product effort go?

## Recommendation

Prioritise **usability** next quarter. It is the largest area on both volume and total severity: 1,220 complaints and a severity sum of 2,990, or 26.1% of complaints. Its lead comes from `usability.ads` (severity sum 1,277 [C006]), the largest specific issue in the ranking. Shuffle, skip, navigation and queue problems add to it. The main reason is breadth: usability touches the most reviewers, and the per-complaint severity is moderate rather than low.

## Evidence

- `usability.ads`: 581 [C005] complaints, mean severity 2.197935 [C007], priority score 1,277 [C008]. Reviewers say there are "WAY too many ads" review `3bfefa06-133c-419b-a435-1fea919d6a44`.
- `usability.shuffle-and-skips`: 184 [C025] complaints, mean severity 2.847826 [C027], score 524 [C028]. One reviewer says "It forces you to shuffle" and they must wait before they "can skip again" review `d4b0a249-e14d-43f2-9711-9cf74cb5b1d6`.
- `usability.general`: 182 [C029] complaints, mean severity 2.554945 [C031], score 465 [C032]. Another reviewer reports "making the UI completely unusable" review `77c8c8a4-7819-412a-8a09-cf83e8cc9c59`.
- `usability.queue-and-playlists`: 146 [C037] complaints, mean severity 2.773973 [C039], score 405 [C040]. One reviewer notes "Player controls disappear now" review `2590181f-b121-4665-884d-0c99026f7c5a`.
- Classifier noise is visible in the sample. One `usability.ads` example is actually about audio quality review `50555133-671b-4fe8-b182-e5bc626f90ec`.

## Alternatives considered

- **Billing and support** ranks second: 854 complaints, severity sum 2,406, mean 2.82, share 18.3%.
  - It is driven by `billing.plans` (score 881 [C012]) and `billing.paywalled-controls` (score 879 [C016]), which carry higher mean severity (2.814696 [C011], 2.949664 [C015]) than the usability issues.
  - This is the closest call. The line between the two areas is blurry: ads and locked shuffle and skip controls are free-tier design choices that appear in both. Reviewers say they need "premium even for shuffle play" review `ebe01dd8-1efd-406a-afa2-17a3753ea391`.
  - Usability work on ads and controls will likely require coordinating with plan decisions.
- **Playback**: 617 complaints, severity sum 2,029, share 13.2%.
  - Its mean severity of 3.29 is higher than usability's 2.45, so count and severity point in different directions.
  - It ranks lower on total impact. `playback.general` scores 570 [C020].
- **Access**: the smallest area, with 159 complaints, severity sum 626 and share 3.4%.
  - It has the highest mean severity, 3.94. `access.login` has mean 3.972727 [C035], because locked-out users "can't log in through Facebook" review `bccc83ff-2c51-40af-97bb-2439aeab2d4e`.
  - It is severe but narrow. It may justify a targeted fix outside the main priority.

## Limitations

- **Self-selected and historical.** These are public reviews dated 2022-05-17 to 2023-11-15. They carry no revenue, plan tier or confirmed churn data.
- **Stated intent only.** Talk of switching apps or cancelling is stated intent, not observed churn. Nothing here estimates revenue at risk or shows a causal effect on retention.
- **Automated labels.** An automated classifier assigned the labels. It was checked on 500 texts, with agreement of 85.0% on topic, 90.0% on intent and 82.4% on severity.
- **Complete coverage.** 10,000 of 10,000 reviews were classified (100.0%). Quarantined reviews were 0 and pending reviews were 0.
- **Catch-all category.** `other.general` is the top-ranked item, with 1,205 [C001] complaints and a score of 2,430 [C004]. It is a catch-all for complaints that name no specific feature, so it is not treated as a fixable problem.
- **Unassigned update complaints.** `other.update` (258 [C021] complaints) likewise sits outside the four areas.

---

## Appendix: how to check this memo

- Recommended priority: **usability**.
- Issue-level numbers carry a claim ID in square brackets. Each is listed in `claims.csv` and equals the value in `ranking.csv`, which `python3 -m pipeline rank` recomputes from saved records and issue membership without any model call.
- priority_score = complaint_count × mean_severity = severity_sum, over completed complaint and cancellation records.
- Priority-area totals sum the topic rows in `topic_rollup.csv` (billing_support = billing + support); shares are of all grouped complaint records.
- Written by `claude-opus-5-5+memo-claude-v2.eae1c86c+schema-v1` from `memo_input.json`; numbers were inserted by code from saved calculations.

| Claim | Issue | Metric | Value |
|---|---|---|---|
| C006 | `usability.ads` | severity_sum | 1277 |
| C005 | `usability.ads` | complaint_count | 581 |
| C007 | `usability.ads` | mean_severity | 2.197935 |
| C008 | `usability.ads` | priority_score | 1277 |
| C025 | `usability.shuffle-and-skips` | complaint_count | 184 |
| C027 | `usability.shuffle-and-skips` | mean_severity | 2.847826 |
| C028 | `usability.shuffle-and-skips` | priority_score | 524 |
| C029 | `usability.general` | complaint_count | 182 |
| C031 | `usability.general` | mean_severity | 2.554945 |
| C032 | `usability.general` | priority_score | 465 |
| C037 | `usability.queue-and-playlists` | complaint_count | 146 |
| C039 | `usability.queue-and-playlists` | mean_severity | 2.773973 |
| C040 | `usability.queue-and-playlists` | priority_score | 405 |
| C012 | `billing.plans` | priority_score | 881 |
| C016 | `billing.paywalled-controls` | priority_score | 879 |
| C011 | `billing.plans` | mean_severity | 2.814696 |
| C015 | `billing.paywalled-controls` | mean_severity | 2.949664 |
| C020 | `playback.general` | priority_score | 570 |
| C035 | `access.login` | mean_severity | 3.972727 |
| C001 | `other.general` | complaint_count | 1205 |
| C004 | `other.general` | priority_score | 2430 |
| C021 | `other.update` | complaint_count | 258 |

| Cited review | Issue | Severity | Evidence quote |
|---|---|---|---|
| `3bfefa06-133c-419b-a435-1fea919d6a44` | `usability.ads` | 2 | WAY too many ads, I used a stopwatch and found that I got 10 minutes of music and 4 of ads, this is ridiculous. The only reasonable premium plans are for multiple people or students. |
| `d4b0a249-e14d-43f2-9711-9cf74cb5b1d6` | `usability.shuffle-and-skips` | 3 | Disappointing. It forces you to shuffle and if you don't find the song you want to listen to, you have to wait through every song until you can skip again. |
| `77c8c8a4-7819-412a-8a09-cf83e8cc9c59` | `usability.shuffle-and-skips` | 3 | edit March 2023 they made it even worse by removing more functionality and making the UI completely unusable. |
| `2590181f-b121-4665-884d-0c99026f7c5a` | `usability.queue-and-playlists` | 3 | Player controls disappear now and sometimes restarting brings them back and sometimes not. |
| `50555133-671b-4fe8-b182-e5bc626f90ec` | `usability.ads` | 2 | Second of all the quality of music, there are other apps which provide better quality, try to give better quality in music. |
| `ebe01dd8-1efd-406a-afa2-17a3753ea391` | `billing.paywalled-controls` | 3 | It was the best app that I had haved but now for everything it display to get premium even for shuffle play or to play the previous song back.Its not good now anymore. |
| `bccc83ff-2c51-40af-97bb-2439aeab2d4e` | `access.login` | 4 | I've just download it and it's not working, I even can't log in through Facebook. A lot of ppl from Croatia have the same issue, don't know why is that. |

# Where should Spotify's next quarter of product effort go?

## Recommendation

Prioritise **usability** next quarter. It leads every option on both volume and total severity: 62 complaints, a severity sum of 148, and 25.5% of complaints. The case rests on two issues. `usability.ads` has 30 [C005] complaints and a severity sum of 65 [C006]. `usability.shuffle-and-skips` has 12 [C021] complaints and a severity sum of 34 [C022]. Both concern the everyday listening experience, especially for free users.

## Evidence

- `usability.ads` is the largest specific issue in the ranking: 30 [C005] complaints, severity sum 65 [C006], mean severity 2.166667 [C007]. Reviewers say "WAY too many ads" review `3bfefa06-133c-419b-a435-1fea919d6a44`. Even satisfied users say "it gives too many ads" and would otherwise rate higher review `5e42046c-b29b-4035-ba83-a8e222789e98`.
- `usability.shuffle-and-skips` has 12 [C021] complaints, severity sum 34 [C022], mean severity 2.833333 [C023]. Reviewers object to "the new drop down menu where it only lets me shuffle" review `f8a85378-c4dd-40e2-b548-beebcdf3b991`. Others write "I just want to listen to one song" review `ebc64fe2-9553-4528-87d5-cb4bb9783be6`. Some report that tapping a liked song may "play a demo" review `0853c56b-0fa1-4d12-9cb9-6817d52233f5`.
- These complaints are lower in severity per review than in other areas, but they are frequent.

## Alternatives considered

- **Billing and support** is the closest call. It has 43 complaints, a severity sum of 123, mean severity 2.86 and a 17.7% share. Its lead issue, `billing.paywalled-controls` (20 [C009] complaints, severity sum 58 [C010], mean 2.900000 [C011]), describes the same free-tier limits on skipping and picking songs as `usability.shuffle-and-skips`. One reviewer says the app is "forcing you to pay premium for basic things" review `a78d831a-69f4-428a-9235-cfdd9775c509`. `billing.plans` adds 15 [C013] complaints (severity sum 44 [C014], mean 2.933333 [C015]). The split between these two areas partly reflects how the classifier labelled one underlying grievance. Any usability work on skips, shuffle and ads should therefore be planned jointly with the billing and plan owners.
- **Playback** has 37 complaints and a severity sum of 123, equal to billing and support. Its mean severity of 3.32 is higher than usability's 2.39. Here count and severity point in different directions: playback problems are fewer but more severe. Examples include `playback.general` (9 [C025] complaints, mean 3.333333 [C027]) and `playback.connection-errors` (7 [C033] complaints, mean 3.285714 [C035]).
- **Access** is the smallest area: 9 complaints and a 3.7% share. It has the highest mean severity, 4.11, and its severity sum is 37. `access.login` (6 [C029] complaints, mean 4.000000 [C031]) is acute for those affected but narrow in reach.

## Limitations

- These are self-selected, historical public reviews from 2022-05-19 to 2023-11-15. They carry no revenue, plan tier or confirmed churn data. Cancellation language, such as "Fastest cancelation of a service" review `a7b7539a-c8d3-4f4e-9edd-d46cd1b1fd12`, is stated intent, not observed churn. This memo estimates no revenue at risk and claims no causal effect on retention.
- Coverage is complete. 500 of 500 reviews were classified (100.0%), with 0 quarantined and 0 pending. There were 243 complaint reviews across 33 ranked issues.
- Labels come from an automated classifier checked on a sample of 200 texts. Agreement was 85.5% on topic, 95.0% on intent and 86.5% on severity. Topic errors could shift the close margins between areas.
- `other.general` is the top-ranked issue (48 [C001] complaints, severity sum 94 [C002]). It is a catch-all for broad verdicts such as "Worst app." review `178c3b49-b689-4fe4-92a2-2257a58e6d95` and is not a fixable problem.
- `other.update` (16 [C017] complaints, severity sum 38 [C018]) falls outside all four areas. It likely overlaps with the paywall and shuffle changes.

---

## Appendix: how to check this memo

- Recommended priority: **usability**.
- Issue-level numbers carry a claim ID in square brackets. Each is listed in `claims.csv` and equals the value in `ranking.csv`, which `python3 -m pipeline rank` recomputes from saved records and issue membership without any model call.
- priority_score = complaint_count × mean_severity = severity_sum, over completed complaint and cancellation records.
- Priority-area totals sum the topic rows in `topic_rollup.csv` (billing_support = billing + support); shares are of all grouped complaint records.
- Written by `claude-opus-5-5@effort-high+memo-claude-v2.eae1c86c+schema-v1` from `memo_input.json`; numbers were inserted by code from saved calculations.

| Claim | Issue | Metric | Value |
|---|---|---|---|
| C005 | `usability.ads` | complaint_count | 30 |
| C006 | `usability.ads` | severity_sum | 65 |
| C021 | `usability.shuffle-and-skips` | complaint_count | 12 |
| C022 | `usability.shuffle-and-skips` | severity_sum | 34 |
| C007 | `usability.ads` | mean_severity | 2.166667 |
| C023 | `usability.shuffle-and-skips` | mean_severity | 2.833333 |
| C009 | `billing.paywalled-controls` | complaint_count | 20 |
| C010 | `billing.paywalled-controls` | severity_sum | 58 |
| C011 | `billing.paywalled-controls` | mean_severity | 2.900000 |
| C013 | `billing.plans` | complaint_count | 15 |
| C014 | `billing.plans` | severity_sum | 44 |
| C015 | `billing.plans` | mean_severity | 2.933333 |
| C025 | `playback.general` | complaint_count | 9 |
| C027 | `playback.general` | mean_severity | 3.333333 |
| C033 | `playback.connection-errors` | complaint_count | 7 |
| C035 | `playback.connection-errors` | mean_severity | 3.285714 |
| C029 | `access.login` | complaint_count | 6 |
| C031 | `access.login` | mean_severity | 4.000000 |
| C001 | `other.general` | complaint_count | 48 |
| C002 | `other.general` | severity_sum | 94 |
| C017 | `other.update` | complaint_count | 16 |
| C018 | `other.update` | severity_sum | 38 |

| Cited review | Issue | Severity | Evidence quote |
|---|---|---|---|
| `3bfefa06-133c-419b-a435-1fea919d6a44` | `usability.ads` | 2 | WAY too many ads, I used a stopwatch and found that I got 10 minutes of music and 4 of ads, this is ridiculous. The only reasonable premium plans are for multiple people or students. |
| `5e42046c-b29b-4035-ba83-a8e222789e98` | `usability.ads` | 2 | Listen to my music almost everyday,this app is great. But the bad thing is that it gives too many ads, i would have hiven it 5 stars. Apart from that this app is great |
| `f8a85378-c4dd-40e2-b548-beebcdf3b991` | `usability.shuffle-and-skips` | 3 | The new drop down menu where it only lets me shuffle. Bad design wrecking me here have a playlist in an order for reason |
| `ebc64fe2-9553-4528-87d5-cb4bb9783be6` | `usability.shuffle-and-skips` | 3 | I just want to listen to one song but nooo I have to go through A HOLE PLAYLIST AND I CAN ONLY SKIP 6 OF THEM 6!!! |
| `0853c56b-0fa1-4d12-9cb9-6817d52233f5` | `usability.shuffle-and-skips` | 3 | This app is so hard to navigate on phone if I click a a song a have liked it goes to didn't song I never heard or it might play a demo of the song that is dumb it should play the song |
| `a78d831a-69f4-428a-9235-cfdd9775c509` | `billing.paywalled-controls` | 3 | You can't even listen to music you want it just shuffles it, like what the hell? This app is killing it self and forcing you to pay premium for basic things like just listening to music. |
| `a7b7539a-c8d3-4f4e-9edd-d46cd1b1fd12` | `billing.plans` | 4 | The very second I signed up for premium it stopped letting me play anything.. lol . Fastest cancelation of a service I've done, ever. Bye bye Spotify. Hello old friend, Bittorrent |
| `178c3b49-b689-4fe4-92a2-2257a58e6d95` | `other.general` | 2 | Worst app. |

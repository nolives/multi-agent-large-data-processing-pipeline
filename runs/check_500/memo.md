# Where should Spotify's next quarter of product effort go?

## Recommendation
Prioritise **billing and support**, focused on the free-tier paywall changes. It has the largest summed severity of the four areas (136), and its weight comes from specific, actionable issues: `billing.plans` (20 [C013] complaints, severity sum 59 [C014]) and `billing.paywalled-controls` (16 [C017] complaints, severity sum 48 [C018]). This is a close call against usability and playback, not a clear win.

## Evidence
- Area total: 47 complaints (19.3% of complaints), mean severity 2.89.
- `billing.plans`: 20 [C013] complaints, mean severity 2.950000 [C015]. One reviewer calls the app "absolutely useless after the latest update" because of premium prompts review `2313bd8e-43bd-4777-bff9-3ae753288f0e`.
- `billing.paywalled-controls`: 16 [C017] complaints, mean severity 3.000000 [C019]. Users say they now "need premium to repeat and skip" review `61e0ddbb-6ec4-4d3a-acd3-41eb5f64afb7` and "can't even pick a certain song" review `d146397f-4a94-4980-be00-ae9212eca3a7`.
- `billing.general`: 8 [C037] complaints, severity sum 20 [C038]: "Paying to use basic festures is just sad" review `82aedd59-debc-4147-9ff4-5a95c3d3a4e4`.
- A new premium subscriber describes the "Fastest cancelation of a service" review `a7b7539a-c8d3-4f4e-9edd-d46cd1b1fd12`. This is stated intent, not observed churn.

## Alternatives considered
- **Usability**: severity sum 134, nearly tied with billing. It has the most complaints (57, 23.5%) but the lowest mean severity (2.35), so count and severity point in different directions. Its lead issue `usability.ads` (29 [C009] complaints, mean severity 2.172414 [C011]) is about free-tier ad load: "WAY too many ads" review `3bfefa06-133c-419b-a435-1fea919d6a44`. Because ad load is also a monetisation decision, it could be reviewed alongside the paywall work.
- **Playback**: severity sum 127, close behind. It has a higher mean severity (3.34) on fewer complaints (38). Its biggest issue, `playback.general` (28 [C005] complaints, severity sum 94 [C006]), is a catch-all bucket that mixes black screens, WiFi failures and audio quality, such as a "Black screen of death" review `065c418e-7f18-42a3-b241-fe693b7a2b0c`. It is not one fixable target and needs triage first. This is a strong runner-up.
- **Access**: the highest mean severity (4.11) but only 9 complaints and a severity sum of 37. `access.login` (6 [C029] complaints, mean severity 4.000000 [C031]) is severe for those affected, for example "Will not except my password" review `de0a9cdf-8974-48bc-802f-331228df4619`. It merits a targeted fix rather than a full quarter.
- `other.general` ranks first overall (52 [C001] complaints, severity sum 100 [C002]). It is a catch-all for general dissatisfaction and support criticism that names no specific feature, so we report it but do not treat it as a fixable problem. `other.update` (16 [C021] complaints) partly overlaps with the paywall complaints.

## Limitations
- These are self-selected, historical public reviews from 2022-05-19 to 2023-11-15. They contain no revenue, plan tier or confirmed churn data. We make no estimate of revenue at risk and no causal claim about retention.
- Cancellation language reflects stated intent only.
- Labels come from an automated classifier checked on a sample of 200 texts. Agreement was 85.5% on topic, 93.0% on intent and 84.5% on severity. The small gaps between the top three areas could shift with labelling error.
- Coverage is complete. 500 of 500 reviews were classified (100.0%), with 0 quarantined and 0 pending. This yielded 243 complaint reviews across 29 ranked issues.

---

## Appendix: how to check this memo

- Recommended priority: **billing_support**.
- Issue-level numbers carry a claim ID in square brackets. Each is listed in `claims.csv` and equals the value in `ranking.csv`, which `python3 -m pipeline rank` recomputes from saved records and issue membership without any model call.
- priority_score = complaint_count × mean_severity = severity_sum, over completed complaint and cancellation records.
- Priority-area totals sum the topic rows in `topic_rollup.csv` (billing_support = billing + support); shares are of all grouped complaint records.
- Written by `claude-opus-5-5+memo-claude-v2.eae1c86c+schema-v1` from `memo_input.json`; numbers were inserted by code from saved calculations.

| Claim | Issue | Metric | Value |
|---|---|---|---|
| C013 | `billing.plans` | complaint_count | 20 |
| C014 | `billing.plans` | severity_sum | 59 |
| C017 | `billing.paywalled-controls` | complaint_count | 16 |
| C018 | `billing.paywalled-controls` | severity_sum | 48 |
| C015 | `billing.plans` | mean_severity | 2.950000 |
| C019 | `billing.paywalled-controls` | mean_severity | 3.000000 |
| C037 | `billing.general` | complaint_count | 8 |
| C038 | `billing.general` | severity_sum | 20 |
| C009 | `usability.ads` | complaint_count | 29 |
| C011 | `usability.ads` | mean_severity | 2.172414 |
| C005 | `playback.general` | complaint_count | 28 |
| C006 | `playback.general` | severity_sum | 94 |
| C029 | `access.login` | complaint_count | 6 |
| C031 | `access.login` | mean_severity | 4.000000 |
| C001 | `other.general` | complaint_count | 52 |
| C002 | `other.general` | severity_sum | 100 |
| C021 | `other.update` | complaint_count | 16 |

| Cited review | Issue | Severity | Evidence quote |
|---|---|---|---|
| `2313bd8e-43bd-4777-bff9-3ae753288f0e` | `billing.plans` | 4 | It is absolutely useless after the latest update. There's nothing I can do without the "try premium" option popping up every damn time. |
| `61e0ddbb-6ec4-4d3a-acd3-41eb5f64afb7` | `billing.paywalled-controls` | 3 | Eyy fodey, charge me for breathing also. You mad or something? Now I need premium to repeat and skip the song to a certain part. |
| `d146397f-4a94-4980-be00-ae9212eca3a7` | `billing.paywalled-controls` | 3 | This was fine till the last update, now you can't even pick a certain song without Spotify premium, and now you can only skip 6 songs, like please just let the songs fit my mood! |
| `82aedd59-debc-4147-9ff4-5a95c3d3a4e4` | `billing.general` | 2 | nah why man, Spotify used to be the best app ever. Paying to use basic festures is just sad and the stupidest thing. |
| `a7b7539a-c8d3-4f4e-9edd-d46cd1b1fd12` | `billing.plans` | 4 | The very second I signed up for premium it stopped letting me play anything.. lol . Fastest cancelation of a service I've done, ever. Bye bye Spotify. Hello old friend, Bittorrent |
| `3bfefa06-133c-419b-a435-1fea919d6a44` | `usability.ads` | 2 | WAY too many ads, I used a stopwatch and found that I got 10 minutes of music and 4 of ads, this is ridiculous. The only reasonable premium plans are for multiple people or students. |
| `065c418e-7f18-42a3-b241-fe693b7a2b0c` | `playback.general` | 4 | Black screen of death. Having to Uninstaller and reinstall after closing and opening app 5x to see if it would work. |
| `de0a9cdf-8974-48bc-802f-331228df4619` | `access.login` | 4 | Will not except my password |

# Where should Spotify's next quarter of product effort go?

## Recommendation

Prioritise **billing and support** next quarter, focused on free-tier controls that now sit behind Premium. `billing.paywalled-controls` is the highest-scoring named issue in the ranking: 6 [C005] complaints, mean severity 2.000000 [C003] for the top row versus 3.000000 [C007] here, and a priority score of 18 [C008]. Only `other.general` scores higher (22 [C004]), and it is a catch-all bucket with no actionable theme. The theme is concentrated and fixable: users say core actions such as skipping, going back and picking a song were removed from the free tier.

## Evidence

- `billing.paywalled-controls`: 6 [C005] complaints, severity sum 18 [C006], mean severity 3.000000 [C007].
- `billing.plans`: 2 [C029] complaints, severity sum 5 [C030], mean severity 2.500000 [C031].
- Billing and support overall: 8 complaints, severity sum 23, mean severity 2.88, share of complaints 15.7%.
- Example reviews:
  - "forcing you to pay premium for basic things" review `a78d831a-69f4-428a-9235-cfdd9775c509`
  - "The ability to skip a song or go to previous song has been removed from non subscribed users" review `a3605554-5c3a-441d-836e-e9fdea83eb2e`
  - "you can't even pick a certain song without Spotify premium" review `d146397f-4a94-4980-be00-ae9212eca3a7`
  - "Why it requires premium just to play next music" review `ad730d1a-829a-4dc4-9561-7e1cd07e2c30`
- The same complaint appears under other labels, such as "they removed basic features of music player" review `7084ced1-0428-4093-9328-442f74719b4f` in `other.update`. That suggests the classifier undercounts this theme.

## Alternatives considered

- **Usability** is the close call. Its topic totals are 13 complaints, severity sum 31, mean severity 2.38, and share 25.5%. Read these against the billing and support totals before committing. Usability spreads its weight across several separate problems: `usability.ads` (7 [C009] complaints, score 15 [C012]), `usability.update` (3 [C021], score 8 [C024]) and `usability.queue-and-playlists` (2 [C037], score 5 [C040]). No single fix addresses all of them. Ads complaints are also free-tier monetisation friction, for example "Soo trash wayy to many ads" review `c2738a4f-e57c-46bc-a4ad-8ec5a4b5d5cd`. Any billing work should be coordinated with ad load.
- **Playback**: 5 complaints, severity sum 17, mean severity 3.40, share 9.8%. `playback.general` scores 13 [C016] on 4 [C013] complaints with mean severity 3.250000 [C015]. Individual reports are serious, such as "Keep stopping halfway while playing music" review `6c257eba-3dca-49f6-b7f0-4c4484d81e26`, but its issue score ranks below paywalled controls. Where its severity is higher, count and severity point in different directions.
- **Access**: 2 complaints, severity sum 8, mean severity 4.00, share 3.9%. No access issue appears in the top-ranked list, and we have no example reviews for it.

## Limitations

- These are self-selected, historical public reviews from 2022-06-02 to 2023-11-13. They carry no revenue, plan tier or confirmed churn data.
- Phrases like "uninstall" express stated intent, not observed churn. We cannot estimate revenue at risk or claim any effect on retention.
- Labels come from an automated classifier checked on 0 sampled texts. Agreement was n/a for topic, n/a for intent and n/a for severity.
- Coverage: 100 of 100 source reviews were classified (100.0%). Another 0 were quarantined and 0 remain unclassified. Results rest on 51 complaint reviews across 17 ranked issues.
- The largest bucket, `other.general` (11 [C001] complaints), is mostly unspecific venting such as "Worst app." review `178c3b49-b689-4fe4-92a2-2257a58e6d95`. It may hide themes we cannot attribute.
- Overlap between the billing, usability and update labels means topic totals are approximate.

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
| C003 | `other.general` | mean_severity | 2.000000 |
| C007 | `billing.paywalled-controls` | mean_severity | 3.000000 |
| C008 | `billing.paywalled-controls` | priority_score | 18 |
| C004 | `other.general` | priority_score | 22 |
| C006 | `billing.paywalled-controls` | severity_sum | 18 |
| C029 | `billing.plans` | complaint_count | 2 |
| C030 | `billing.plans` | severity_sum | 5 |
| C031 | `billing.plans` | mean_severity | 2.500000 |
| C009 | `usability.ads` | complaint_count | 7 |
| C012 | `usability.ads` | priority_score | 15 |
| C021 | `usability.update` | complaint_count | 3 |
| C024 | `usability.update` | priority_score | 8 |
| C037 | `usability.queue-and-playlists` | complaint_count | 2 |
| C040 | `usability.queue-and-playlists` | priority_score | 5 |
| C016 | `playback.general` | priority_score | 13 |
| C013 | `playback.general` | complaint_count | 4 |
| C015 | `playback.general` | mean_severity | 3.250000 |
| C001 | `other.general` | complaint_count | 11 |

| Cited review | Issue | Severity | Evidence quote |
|---|---|---|---|
| `a78d831a-69f4-428a-9235-cfdd9775c509` | `billing.paywalled-controls` | 3 | You can't even listen to music you want it just shuffles it, like what the hell? This app is killing it self and forcing you to pay premium for basic things like just listening to music. |
| `a3605554-5c3a-441d-836e-e9fdea83eb2e` | `billing.paywalled-controls` | 3 | Recent update really sucks. The ability to skip a song or go to previous song has been removed from non subscribed users. |
| `d146397f-4a94-4980-be00-ae9212eca3a7` | `billing.paywalled-controls` | 3 | This was fine till the last update, now you can't even pick a certain song without Spotify premium, and now you can only skip 6 songs, like please just let the songs fit my mood! |
| `ad730d1a-829a-4dc4-9561-7e1cd07e2c30` | `billing.plans` | 3 | Why it requires premium just to play next music / to choose music ?? And why the specific part of song cannot be played ? |
| `7084ced1-0428-4093-9328-442f74719b4f` | `other.update` | 3 | I am using Spotify from past two years From last update they removed basic features of music player |
| `c2738a4f-e57c-46bc-a4ad-8ec5a4b5d5cd` | `usability.ads` | 2 | Soo trash wayy to many ads I don't want premium but too much ads |
| `6c257eba-3dca-49f6-b7f0-4c4484d81e26` | `playback.general` | 3 | Keep stopping halfway while playing music and it dun go back to where they stop and start playing a new song for you. |
| `178c3b49-b689-4fe4-92a2-2257a58e6d95` | `other.general` | 2 | Worst app. |

# Golden-set evaluation

Fifty cases are a small diagnostic sample, not a precise estimate of accuracy on the whole corpus.

- Run `golden_50`, enricher `jev-1.13.0+enrich-jev-v2.22642b2a+schema-v1`.
- 50 of 50 golden reviews scored; 0 missing or quarantined (these count as incorrect).
- 13 cases were marked ambiguous by the labeler.

| Measure | Enricher, all cases | Enricher, non-ambiguous | Verifier, all cases |
|---|---|---|---|
| Cases | 50 | 37 | 50 |
| Topic agreement | 92% | 97% | 94% |
| Intent agreement | 92% | 95% | 92% |
| Severity exact agreement | 84% | 97% | 84% |
| Severity within one level | 98% | 100% | 100% |
| Severity mean absolute error | 0.18 | 0.027 | 0.16 |
| Topic, intent and severity all agree | 76% | 92% | 78% |
| Sentiment within 0.5 | 92% | 92% | 94% |
| Sentiment mean absolute error | 0.13 | 0.1216 | 0.15 |

## Per topic (human label)

| Topic | Human count | Enricher chose the same | Enricher chose this topic in total |
|---|---|---|---|
| billing | 3 | 3 | 4 |
| catalog | 6 | 5 | 5 |
| downloads | 1 | 1 | 1 |
| other | 27 | 26 | 27 |
| playback | 5 | 4 | 5 |
| usability | 8 | 7 | 8 |

## Confusions (human label -> enricher label)

- **topic:** catalog -> other (1); playback -> usability (1); other -> billing (1); usability -> playback (1)
- **intent:** praise -> unclear (1); cancellation -> unclear (1); complaint -> unclear (1); unclear -> complaint (1)
- **severity:** 2 -> 3 (2); 3 -> 4 (2); 3 -> 2 (1); 2 -> 1 (1); 1 -> 2 (1); 3 -> 5 (1)

## Other fields

- **Evidence quote:** 50 of 50 are exact substrings of the source (checked in code); 48 overlap the human's quote.
- **Entities:** the enricher listed an entity the human did not in 14 cases, and missed one the human listed in 15. The enricher's entities come from a fixed lexicon matched against the text, so each one is present in the text; differences are mostly naming and granularity. They are listed per case for inspection.
- **needs_review, as a prediction of the human flag:** the enricher flagged 14, the human 15, both 8 (precision 57%, recall 53%).
- **needs_review, as a prediction of an enricher error:** 8 of 12 wrong records were flagged (recall 67%); 57% of flagged records were wrong.

## Every disagreement on topic, intent or severity

| Review | Ambiguous | Fields | Human | Enricher | Verifier | Enricher flagged | Text |
|---|---|---|---|---|---|---|---|
| `292ce26a` | yes | topic, severity | catalog / complaint / 3 | other / complaint / 2 | catalog / complaint / 2 | yes | Staff must be full of mentally ill kool-aid heads. Banning conservative music that speaks truth. Spotify is doing all they can to protect pedophiles, by banning Christian songs discussing the path the devil leads you down. Pride is a sin. |
| `991b6b3a` | yes | severity | usability / complaint / 2 | usability / complaint / 3 | usability / complaint / 2 | yes | Ads were okay, but limited functionality..it's just too much |
| `723f07de` | yes | severity | playback / complaint / 3 | playback / complaint / 4 | playback / complaint / 4 |  | Update: I reached out to Spotify Support and with some help from Sarah I was able to get the app working again. Old Post:Normally, the app works great, and I use it constantly. I tried to open it today, and it keeps crashing every time. I'v |
| `ac6cd66d` |  | intent | catalog / praise / 1 | catalog / unclear / 1 | catalog / praise / 1 | yes | Lhat ng song nasa spotify |
| `5de7f95b` | yes | intent | other / cancellation / 1 | other / unclear / 1 | other / unclear / 1 |  | We are boycotting Swedish app in our protest against Sweden for their desrecpect & desceration of our holy book Qur'an |
| `36609c5c` |  | intent, severity | other / complaint / 2 | other / unclear / 1 | other / unclear / 1 |  | Bheekhmangon |
| `16d640e9` | yes | severity | billing / complaint / 2 | billing / complaint / 3 | billing / complaint / 3 |  | It's my best music app but now it's not...everything basic features is premium.... |
| `8cc4fad4` | yes | intent, severity | other / unclear / 1 | other / complaint / 2 | other / complaint / 2 | yes | I hate this app and sweden .I love islam |
| `46c0b49f` | yes | topic, severity | playback / complaint / 3 | usability / complaint / 5 | usability / complaint / 2 | yes | Are you out of your mind? This is dangerous! Listening to music in a normal volume and suddenly an add starts and my ears feel like they explode!! Stop this BS, or you're gonna destroy someones ears. |
| `283b5843` |  | topic | other / unclear / 1 | billing / unclear / 1 | billing / unclear / 1 | yes | Beth, we all got to give me a free dollar to go with 3 months, bro I can't be like |
| `dceb14e7` | yes | topic | usability / complaint / 3 | playback / complaint / 3 | usability / complaint / 3 | yes | I gave one star because I can't give any less than that. the new update is sooooooo annoying like I can't even play the songs that I like and I can't rewind songs what the heck |
| `ac4e860a` | yes | severity | downloads / complaint / 3 | downloads / complaint / 4 | downloads / complaint / 3 | yes | paying for subscribing but unable to play in offline mode really? |

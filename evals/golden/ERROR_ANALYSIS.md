# Golden-set error analysis

Draft written from `golden_report.md` and `golden_cases.jsonl` for Nick to review and put in his own words.
The numbers are computed by `tools/golden_eval.py`; the reading of them below is interpretation.

## Setup

- 50 reviews hand-labeled by Nick in two passes, finished before any model prediction for these reviews existed.
- The pipeline ran on `data/golden_50_to_label.csv`, whose label columns are blank. The human labels were never a model input.
- Configuration was frozen before this run: Jev 1.13.0 with the version 2 questions, verified by Claude Haiku 5.5 at low effort.
- Nothing was changed after seeing these results. If the configuration is changed because of them, that must be disclosed
  and checked on fresh held-out cases.
- Five reviews were not in English and were read with a translation tool; their labels carry more uncertainty.

## Headline

| | All 50 | 37 non-ambiguous | 13 ambiguous |
|---|---|---|---|
| Topic agreement | 92% | 97% | 77% |
| Intent agreement | 92% | 95% | 85% |
| Severity exact | 84% | 97% | 46% |
| All three agree | 76% | 92% | 31% |

Severity is within one level of the human label in 49 of 50 cases; mean absolute error is 0.18.
Fifty cases are a small diagnostic sample: one case moves a percentage by two points.

## What the 12 disagreements are

**Nine of the twelve are cases the labeler had already marked ambiguous**, with the alternative label written in the notes
before the model ran. In seven of those nine the enricher chose exactly the alternative the notes name.
Examples: `991b6b3a`, `16d640e9` and `ac4e860a` are severity 2 versus 3 or 3 versus 4 calls on reviews that do not state
how much use remains; `723f07de` is the crash that support later fixed (human 3, both models 4).

**Three are on reviews the labeler considered clear:**

- `ac6cd66d` (Tagalog, "Lhat ng song nasa spotify"): human praise, enricher unclear, verifier praise. The enricher did not
  read a short non-English compliment as praise. It flagged the record for review.
- `36609c5c` (Hindi, a one-word insult): human complaint severity 2, both models unclear severity 1. Neither model
  recognised the word as criticism.
- `283b5843` (garbled English mentioning "a free dollar"): human topic other, both models billing. The models took a money
  reference as a billing subject although no product issue is stated.

Two of these three are non-English. That matches the provider's own warning that Jev is weaker outside English.

**One error is a clear overshoot on severity.** `46c0b49f` complains that a loud ad hurt the reviewer's ears and calls it
"dangerous". The enricher gave severity 5; the human gave 3 and the verifier 2. The shared scale reserves 5 for stated
financial, privacy or data harm, which this review does not claim. The enricher appears to have reacted to alarmed
wording. It did flag the record for review. This matters for the ranking, because severity feeds the priority score.

**Boycott and protest text is unstable.** `5de7f95b` and `8cc4fad4` are protest reviews where the human, enricher and
verifier split between cancellation, complaint and unclear. The labeler marked both ambiguous. These records carry
severity 1 or 2, so their effect on issue scores is small, and the grouping rules place them in `other.boycott-or-protest`.

## Independent verifier

The verifier disagrees with the human on 11 of 50, the enricher on 12. Eight of those are the same reviews.
The verifier is right where the enricher is wrong in four cases, and the enricher is right where the verifier is wrong in three.

- Enricher and verifier are about equally close to the human labels, so this sample gives no evidence that routing
  low-confidence texts to the verifier model as a fallback would improve accuracy. No fallback was added.
- A disagreement between the two models pointed at an enricher error in 6 of the 12 error cases.

## needs_review

- As a prediction of the human flag: enricher flagged 14, human 15, both 8 (precision 57%, recall 53%).
- As a prediction of an enricher error: 8 of the 12 wrong records were flagged (recall 67%), and 57% of flagged records were wrong.

The flag is a useful but weak signal. It is not a correctness guarantee in either direction.

## Evidence quote and entities

- All 50 enricher quotes are exact substrings of the source (checked in code), and 48 overlap the human's quote.
  Forty-six human quotes are the whole review, so overlap is easy to achieve; it shows the quotes are not misplaced, not
  that each one is the best support for its label.
- Entities differ in 14 cases one way and 15 the other. The enricher's entities come from a fixed lexicon matched against
  the text, so none is unsupported by the text. The differences are naming and granularity: the human writes free-form
  names and the lexicon uses fixed ones.

## What this means for the final run

- On clear reviews the enricher's topic, intent and severity agree with the human in 92% of cases together.
- The known weak spots are non-English text, garbled text, protest reviews, and occasional severity inflation from alarmed wording.
- The instructor's private benchmark allows several accepted labels on ambiguous cases, which is where most of these disagreements sit.

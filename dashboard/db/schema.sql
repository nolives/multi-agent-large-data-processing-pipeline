-- Dashboard database: the processed review data, aggregates and analysis outputs of one published pipeline run.
-- Applied by `python3 -m pipeline publish`, which replaces the contents in a single transaction.
-- The backend only ever reads these tables.

DROP TABLE IF EXISTS memo_citations, claims, memo, issue_months, issues, reviews, documents, published_run CASCADE;

CREATE TABLE published_run (
    id            integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    run_id        text NOT NULL,
    published_at  timestamptz NOT NULL DEFAULT now(),
    label_config  text NOT NULL,
    source_file   text NOT NULL,
    source_sha256 text NOT NULL,
    source_rows   integer NOT NULL
);

-- One row per source review ID, with its original values, final status and labels.
CREATE TABLE reviews (
    review_id        text PRIMARY KEY,
    row_num          integer NOT NULL,
    review_text      text NOT NULL,
    review_rating    text NOT NULL,
    review_likes     text NOT NULL,
    app_version      text NOT NULL,
    review_timestamp text NOT NULL,          -- original string; the source gives no timezone
    review_month     text NOT NULL,          -- YYYY-MM, taken from the original string
    source_sha256    text NOT NULL,
    status           text NOT NULL CHECK (status IN ('completed', 'quarantined', 'pending')),
    reason           text,
    topic            text,
    intent           text,
    sentiment        real,
    severity         smallint,
    entities         jsonb,
    evidence_quote   text,
    needs_review     boolean,
    cache_source_id  text,                   -- set when the labels were reused from an identical text
    issue_id         text                    -- set for completed complaint and cancellation records
);
CREATE INDEX reviews_issue ON reviews (issue_id, severity DESC);
CREATE INDEX reviews_month ON reviews (review_month);
CREATE INDEX reviews_intent_topic ON reviews (intent, topic);

-- The saved baseline ranking: priority_score = complaint_count x mean_severity = severity_sum.
CREATE TABLE issues (
    issue_id           text PRIMARY KEY,
    topic              text NOT NULL,
    aspect             text NOT NULL,
    title              text NOT NULL,
    description        text NOT NULL,
    named_by           text NOT NULL,
    rank               integer NOT NULL,
    complaint_count    integer NOT NULL,
    severity_sum       integer NOT NULL,
    mean_severity      numeric(12, 6) NOT NULL,
    priority_score     integer NOT NULL,
    cancellation_count integer NOT NULL,
    needs_review_count integer NOT NULL,
    severity_1 integer NOT NULL, severity_2 integer NOT NULL, severity_3 integer NOT NULL,
    severity_4 integer NOT NULL, severity_5 integer NOT NULL
);

CREATE TABLE issue_months (
    issue_id        text NOT NULL REFERENCES issues,
    review_month    text NOT NULL,
    complaint_count integer NOT NULL,
    severity_sum    integer NOT NULL,
    PRIMARY KEY (issue_id, review_month)
);

-- The AI-generated recommendation, the issue-level numbers it cites, and the reviews it cites.
CREATE TABLE memo (
    id                   integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    recommended_priority text NOT NULL,
    markdown             text NOT NULL,
    memo_config          text NOT NULL,
    checked              jsonb NOT NULL
);
CREATE TABLE claims (
    claim_id text PRIMARY KEY,
    issue_id text NOT NULL REFERENCES issues,
    metric   text NOT NULL,
    value    text NOT NULL
);
CREATE TABLE memo_citations (
    review_id text PRIMARY KEY REFERENCES reviews,
    issue_id  text NOT NULL REFERENCES issues,
    severity  smallint NOT NULL,
    quote     text NOT NULL
);

-- Saved analysis outputs kept as JSON: ingestion profile, verification report, golden evaluation, run and cost summary.
CREATE TABLE documents (
    key  text PRIMARY KEY,
    body jsonb NOT NULL
);

-- The whole simulation in one queryable file.
--
-- The JSON and JSONL files under data/ stay the SOURCE. This database is
-- built from them and can be thrown away and rebuilt at any time, so
-- nothing is ever only in here.
--
--   emails        one row per email the simulation can send, real and fake
--   red_flags     one row per tell, since an email has several
--   people        one row per member of staff, visible facts only
--   hidden_probs  the simulated human's SECRET click chances - see below
--   deliveries    one row per answer: who was sent what, and what they did
--
-- Views at the bottom answer the questions that would otherwise be a nested
-- loop in Python.

CREATE TABLE IF NOT EXISTS emails (
    id                 INTEGER PRIMARY KEY,
    -- what it really is
    label              TEXT NOT NULL CHECK (label IN ('phishing', 'legitimate')),
    is_fake            INTEGER NOT NULL,          -- 1 fake, 0 real
    -- the attack, blank on genuine mail
    cue                TEXT,
    technique          TEXT,
    technique_category TEXT,
    table_row          INTEGER,
    week               INTEGER,
    cia_hit            TEXT,
    address_trick      TEXT,
    key_defense        TEXT,
    -- delivery
    target_role        TEXT,
    difficulty         TEXT,
    -- the message itself
    sender_name        TEXT,
    sender_email       TEXT,
    sender_domain      TEXT,
    reply_to           TEXT,
    subject            TEXT,
    body               TEXT,
    link_text          TEXT,
    link_target        TEXT,
    -- teaching notes
    teaches            TEXT,
    topic              TEXT
);

CREATE TABLE IF NOT EXISTS red_flags (
    email_id INTEGER NOT NULL REFERENCES emails(id),
    position INTEGER NOT NULL,
    flag     TEXT NOT NULL,
    PRIMARY KEY (email_id, position)
);

CREATE TABLE IF NOT EXISTS people (
    id                       TEXT PRIMARY KEY,     -- "P01"
    name                     TEXT NOT NULL,
    job_title                TEXT,
    pillar                   TEXT,
    department               TEXT,
    location                 TEXT,
    age                      INTEGER,
    gender                   TEXT,
    years_in_role            INTEGER,
    years_with_organization  INTEGER,
    -- how they behave, as an observer could describe them
    role_group               TEXT,
    security_awareness       TEXT,
    workload                 TEXT,
    shift                    TEXT
);

-- SEPARATE ON PURPOSE.
--
-- These are the numbers the simulated human rolls against. The twin's whole
-- job is to GUESS them from what it observes, so a query that joins this
-- into a prediction is cheating. It lives here only so the twin can be
-- GRADED afterwards - read it to score, never to predict.
CREATE TABLE IF NOT EXISTS hidden_probs (
    person_id TEXT NOT NULL REFERENCES people(id),
    cue       TEXT NOT NULL,
    p         REAL NOT NULL,
    PRIMARY KEY (person_id, cue)
);

-- One row per answer. This is history_log.jsonl as a table: the log stays
-- the append-only truth, and this is the queryable projection of it.
CREATE TABLE IF NOT EXISTS deliveries (
    rowid_        INTEGER PRIMARY KEY AUTOINCREMENT,
    n             INTEGER,            -- that person's nth answer
    at            TEXT,               -- ISO timestamp
    source        TEXT,               -- "sim" or a real person in the Inbox
    person_id     TEXT REFERENCES people(id),
    email_id      INTEGER,            -- not a FK: built emails are not in emails
    subject       TEXT,
    label         TEXT,
    cue           TEXT,
    cue_key       TEXT,               -- "false_report" on genuine mail
    action        TEXT,               -- click / report / ignore
    said          TEXT,               -- what they called it
    truth         TEXT,               -- what it really was
    correct       INTEGER,
    recognised    INTEGER,
    -- the counters as they stood just after this answer
    running_yes   INTEGER,
    running_no    INTEGER,
    running_all   INTEGER,
    p_before      REAL,
    p_click       REAL
);

CREATE INDEX IF NOT EXISTS idx_label       ON emails (label);
CREATE INDEX IF NOT EXISTS idx_cue         ON emails (cue);
CREATE INDEX IF NOT EXISTS idx_technique   ON emails (technique);
CREATE INDEX IF NOT EXISTS idx_role        ON emails (target_role);
CREATE INDEX IF NOT EXISTS idx_difficulty  ON emails (difficulty);
CREATE INDEX IF NOT EXISTS idx_d_person    ON deliveries (person_id);
CREATE INDEX IF NOT EXISTS idx_d_email     ON deliveries (email_id);
CREATE INDEX IF NOT EXISTS idx_d_cue       ON deliveries (cue_key);
CREATE INDEX IF NOT EXISTS idx_p_awareness ON people (security_awareness);

-- ------------------------------------------------------------------ views

-- How each person is doing overall. Only phishing arrivals count towards
-- the click rate: correctly ignoring genuine mail says nothing about
-- whether someone clicks.
CREATE VIEW IF NOT EXISTS v_person_scores AS
SELECT
    p.id,
    p.name,
    p.job_title,
    p.security_awareness,
    COUNT(*)                                            AS answered,
    SUM(d.correct)                                      AS correct,
    COUNT(*) - SUM(d.correct)                           AS incorrect,
    ROUND(1.0 * SUM(d.correct) / COUNT(*), 3)           AS accuracy,
    SUM(d.label = 'phishing')                           AS phishing_seen,
    SUM(d.label = 'phishing' AND d.action = 'click')    AS clicked,
    SUM(d.label = 'phishing' AND d.action = 'report')   AS reported,
    ROUND(1.0 * SUM(d.label = 'phishing' AND d.action = 'click')
          / NULLIF(SUM(d.label = 'phishing'), 0), 3)    AS click_rate
FROM people p
JOIN deliveries d ON d.person_id = p.id
GROUP BY p.id;

-- How each email performed. "Caught" means flagged when it was phishing,
-- and NOT flagged when it was genuine.
CREATE VIEW IF NOT EXISTS v_email_scores AS
SELECT
    d.email_id,
    d.subject,
    d.label,
    COUNT(*)                                     AS times_sent,
    SUM(d.said = 'spam')                         AS flagged,
    SUM(d.said != 'spam')                        AS trusted,
    ROUND(1.0 * SUM(d.correct) / COUNT(*), 3)    AS caught_rate
FROM deliveries d
-- Grouped by subject as well as id. Built emails have collided with curated
-- ids in the past, and merging those would average two different emails
-- into one row instead of showing that the id was reused.
GROUP BY d.email_id, d.label, d.subject;

-- Which pressure works on whom.
CREATE VIEW IF NOT EXISTS v_cue_rates AS
SELECT
    d.person_id,
    p.name,
    p.security_awareness,
    d.cue_key                                            AS cue,
    COUNT(*)                                             AS answers,
    SUM(d.action = 'click')                              AS clicked,
    ROUND(1.0 * SUM(d.action = 'click') / COUNT(*), 3)   AS click_rate
FROM deliveries d
JOIN people p ON p.id = d.person_id
GROUP BY d.person_id, d.cue_key;

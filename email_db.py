# email_db.py
# The email database: every email the simulation can send, real and fake,
# in a queryable SQLite file.
#
# Why a database rather than the JSON directly:
#   - questions like "hard phishing emails using a forged From line, aimed at
#     billing staff" become one query instead of a nested loop
#   - counts and breakdowns come back without reading every record
#   - it is one file, no server, and sqlite3 ships with Python
#
# data/hospital_emails_mixed.json stays the SOURCE. The database is built
# from it and can be rebuilt at any time:
#
#     python3 email_db.py            rebuild and show what is in it
#
# Two tables:
#   emails     one row per email, flattened
#   red_flags  one row per tell, since an email has several

import json
import os
import sqlite3

DB_PATH = os.path.join("data", "emails.db")
SOURCE_JSON = os.path.join("data", "hospital_emails_mixed.json")

SCHEMA = """
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

CREATE INDEX IF NOT EXISTS idx_label      ON emails (label);
CREATE INDEX IF NOT EXISTS idx_cue        ON emails (cue);
CREATE INDEX IF NOT EXISTS idx_technique  ON emails (technique);
CREATE INDEX IF NOT EXISTS idx_role       ON emails (target_role);
CREATE INDEX IF NOT EXISTS idx_difficulty ON emails (difficulty);
"""


def domain_of(address):
    return address.rsplit("@", 1)[1].lower() if address and "@" in address else ""


class EmailDB:
    """Read-only access to the email database, plus a builder."""

    def __init__(self, path=DB_PATH, build_if_missing=True):
        self.path = path
        if build_if_missing and not os.path.exists(path):
            build(path)
        self.conn = sqlite3.connect(path)
        # Rows come back as dict-like objects rather than bare tuples.
        self.conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------- querying

    def _rows(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params)]

    def all(self):
        """Every email."""
        return self._rows("SELECT * FROM emails ORDER BY id")

    def get(self, email_id):
        """One email by id, with its red flags attached."""
        rows = self._rows("SELECT * FROM emails WHERE id = ?", (email_id,))
        if not rows:
            return None
        email = rows[0]
        email["red_flags"] = self.red_flags(email_id)
        return email

    def red_flags(self, email_id):
        return [r["flag"] for r in self._rows(
            "SELECT flag FROM red_flags WHERE email_id = ? ORDER BY position",
            (email_id,))]

    def find(self, label=None, cue=None, technique=None, difficulty=None,
             address_trick=None, target_role=None, exclude_ids=None):
        """Emails matching whichever filters are given.

        target_role also matches emails addressed to everyone, since those
        reach the person too.
        """
        sql = "SELECT * FROM emails WHERE 1=1"
        params = []

        for column, value in (("label", label), ("cue", cue),
                              ("technique", technique),
                              ("difficulty", difficulty),
                              ("address_trick", address_trick)):
            if value is not None:
                sql += " AND %s = ?" % column
                params.append(value)

        if target_role is not None:
            sql += " AND target_role IN (?, 'all')"
            params.append(target_role)

        if exclude_ids:
            sql += " AND id NOT IN (%s)" % ",".join("?" * len(exclude_ids))
            params.extend(exclude_ids)

        return self._rows(sql + " ORDER BY id", params)

    def fakes(self, **kw):
        return self.find(label="phishing", **kw)

    def real(self, **kw):
        return self.find(label="legitimate", **kw)

    # -------------------------------------------------------------- counting

    def count(self, **kw):
        return len(self.find(**kw))

    def breakdown(self, column):
        """How many emails per value of a column, biggest first."""
        if column not in {"label", "cue", "technique", "technique_category",
                          "difficulty", "address_trick", "target_role",
                          "cia_hit", "week"}:
            raise ValueError("cannot group by %r" % column)
        return self._rows(
            "SELECT %s AS value, COUNT(*) AS n FROM emails "
            "WHERE %s IS NOT NULL AND %s != '' "
            "GROUP BY %s ORDER BY n DESC, value" % ((column,) * 4))

    def close(self):
        self.conn.close()


# ----------------------------------------------------------------- building

def build(path=DB_PATH, source=SOURCE_JSON):
    """(Re)build the database from the JSON source. Safe to run repeatedly."""
    with open(source) as f:
        emails = json.load(f)["emails"]

    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        os.remove(path)

    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)

    for e in emails:
        phishing = e["label"] == "phishing"
        conn.execute(
            "INSERT INTO emails VALUES (:id, :label, :is_fake, :cue, :technique,"
            " :technique_category, :table_row, :week, :cia_hit, :address_trick,"
            " :key_defense, :target_role, :difficulty, :sender_name,"
            " :sender_email, :sender_domain, :reply_to, :subject, :body,"
            " :link_text, :link_target, :teaches, :topic)",
            {
                "id": e["id"],
                "label": e["label"],
                "is_fake": 1 if phishing else 0,
                # The attack columns only mean something on a fake.
                "cue": e.get("cue") if phishing else None,
                "technique": e.get("technique") if phishing else None,
                "technique_category": e.get("technique_category") if phishing else None,
                "table_row": e.get("table_row") if phishing else None,
                "week": e.get("week") if phishing else None,
                "cia_hit": e.get("cia_hit") if phishing else None,
                "address_trick": e.get("address_trick") if phishing else None,
                "key_defense": e.get("key_defense"),
                "target_role": e.get("target_role"),
                "difficulty": e.get("difficulty"),
                "sender_name": e.get("sender_name"),
                "sender_email": e.get("sender_email"),
                "sender_domain": domain_of(e.get("sender_email", "")),
                "reply_to": e.get("reply_to"),
                "subject": e.get("subject"),
                "body": e.get("body"),
                "link_text": e.get("link_text"),
                "link_target": e.get("link_target"),
                "teaches": e.get("teaches"),
                "topic": e.get("topic"),
            })

        for n, flag in enumerate(e.get("red_flags") or e.get("safe_signs") or []):
            conn.execute("INSERT INTO red_flags VALUES (?, ?, ?)", (e["id"], n, flag))

    conn.commit()
    conn.close()
    return path


if __name__ == "__main__":
    path = build()
    db = EmailDB(path, build_if_missing=False)

    print("Built %s\n" % path)
    print("emails: %d   fake: %d   real: %d\n"
          % (db.count(), db.count(label="phishing"), db.count(label="legitimate")))

    for column in ("technique", "cue", "address_trick", "difficulty", "target_role"):
        rows = db.breakdown(column)
        print("%s (%d)" % (column, len(rows)))
        for r in rows:
            print("   %-28s %d" % (r["value"], r["n"]))
        print()

    print("example query - hard fakes from a forged From line:")
    for e in db.fakes(difficulty="hard", address_trick="forged_from"):
        print("   %s  %s" % (e["id"], e["subject"][:52]))
    db.close()

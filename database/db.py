# database/db.py
# Read-only access to the simulation database.
#
# Why a database rather than the JSON and the log directly:
#   - "hard phishing emails using a forged From line, aimed at billing
#     staff" is one query instead of a nested loop
#   - counts and breakdowns come back without reading every record
#   - the 11,000-row history can be grouped without loading it into memory
#   - it is one file, no server, and sqlite3 ships with Python
#
# The files under data/ stay the SOURCE. This is a projection of them, built
# by database/build.py and rebuildable at any time:
#
#     python3 -m database.build      rebuild
#     python3 -m database.db         show what is in it
#
# Everything here reads. Writing is the builder's job, so a query can never
# leave the projection disagreeing with the log it came from.

import os
import sqlite3
import sys

from database.build import DB_PATH, build


class Database:
    """Queries over emails, people and the delivery history."""

    def __init__(self, path=DB_PATH, build_if_missing=True):
        self.path = path
        if build_if_missing and not os.path.exists(path):
            build(path)
        self.conn = sqlite3.connect(path)
        # Rows come back as dict-like objects rather than bare tuples.
        self.conn.row_factory = sqlite3.Row

    def rows(self, sql, params=()):
        """Any query, as a list of dicts. The escape hatch."""
        return [dict(r) for r in self.conn.execute(sql, params)]

    def one(self, sql, params=()):
        got = self.rows(sql, params)
        return got[0] if got else None

    # ------------------------------------------------------------- emails

    def all(self):
        return self.rows("SELECT * FROM emails ORDER BY id")

    def get(self, email_id):
        """One email by id, with its red flags attached."""
        email = self.one("SELECT * FROM emails WHERE id = ?", (email_id,))
        if email:
            email["red_flags"] = self.red_flags(email_id)
        return email

    def red_flags(self, email_id):
        return [r["flag"] for r in self.rows(
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
        return self.rows(sql + " ORDER BY id", params)

    def fakes(self, **kw):
        return self.find(label="phishing", **kw)

    def real(self, **kw):
        return self.find(label="legitimate", **kw)

    # ------------------------------------------------------------- people

    def people(self, awareness=None, role_group=None):
        sql, params = "SELECT * FROM people WHERE 1=1", []
        for column, value in (("security_awareness", awareness),
                              ("role_group", role_group)):
            if value is not None:
                sql += " AND %s = ?" % column
                params.append(value)
        return self.rows(sql + " ORDER BY id", params)

    def person(self, person_id):
        return self.one("SELECT * FROM people WHERE id = ?", (person_id,))

    # --------------------------------------------------------- deliveries

    def deliveries(self, person_id=None, email_id=None, cue=None, limit=None):
        sql, params = "SELECT * FROM deliveries WHERE 1=1", []
        for column, value in (("person_id", person_id),
                              ("email_id", email_id), ("cue_key", cue)):
            if value is not None:
                sql += " AND %s = ?" % column
                params.append(value)
        sql += " ORDER BY at"
        if limit:
            sql += " LIMIT %d" % int(limit)
        return self.rows(sql, params)

    # -------------------------------------------------------------- views

    def person_scores(self):
        return self.rows("SELECT * FROM v_person_scores ORDER BY click_rate DESC")

    def email_scores(self):
        return self.rows("SELECT * FROM v_email_scores ORDER BY caught_rate")

    def cue_rates(self, person_id=None):
        if person_id:
            return self.rows(
                "SELECT * FROM v_cue_rates WHERE person_id = ? ORDER BY cue",
                (person_id,))
        return self.rows("SELECT * FROM v_cue_rates ORDER BY person_id, cue")

    # ----------------------------------------------------------- counting

    def count(self, table="emails", **kw):
        if table == "emails":
            return len(self.find(**kw))
        if table not in {"people", "deliveries", "red_flags", "hidden_probs"}:
            raise ValueError("cannot count %r" % table)
        return self.one("SELECT COUNT(*) AS n FROM %s" % table)["n"]

    def breakdown(self, column, table="emails"):
        """How many rows per value of a column, biggest first."""
        allowed = {
            "emails": {"label", "cue", "technique", "technique_category",
                       "difficulty", "address_trick", "target_role",
                       "cia_hit", "week"},
            "people": {"security_awareness", "workload", "shift",
                       "role_group", "pillar", "department"},
            "deliveries": {"action", "label", "cue_key", "source", "said"},
        }
        if column not in allowed.get(table, ()):
            raise ValueError("cannot group %s by %r" % (table, column))
        return self.rows(
            "SELECT %s AS value, COUNT(*) AS n FROM %s "
            "WHERE %s IS NOT NULL AND %s != '' "
            "GROUP BY %s ORDER BY n DESC, value"
            % (column, table, column, column, column))

    def close(self):
        self.conn.close()


# The email-only name this started as. Kept so the builders that only ever
# wanted emails do not have to care that the database grew.
EmailDB = Database


def main():
    if not os.path.exists(DB_PATH):
        sys.exit("No database yet. Run: python3 -m database.build")
    db = Database(build_if_missing=False)

    print("%s\n" % DB_PATH)
    for table in ("emails", "people", "deliveries", "red_flags"):
        print("   %-12s %6d" % (table, db.count(table)))

    print("\nemails by technique")
    for r in db.breakdown("technique")[:6]:
        print("   %-28s %4d" % (r["value"], r["n"]))

    print("\nanswers by action")
    for r in db.breakdown("action", table="deliveries"):
        print("   %-28s %6d" % (r["value"], r["n"]))

    print("\nmost likely to click")
    for r in db.person_scores()[:5]:
        print("   %-22s %-8s %5.1f%%  (%d phishing seen)"
              % (r["name"], r["security_awareness"],
                 100 * (r["click_rate"] or 0), r["phishing_seen"]))

    print("\nhardest emails to catch")
    for r in db.email_scores()[:5]:
        print("   %4s  %-46s %5.1f%%"
              % (r["email_id"], (r["subject"] or "")[:46],
                 100 * (r["caught_rate"] or 0)))

    print("\nexample query - hard fakes from a forged From line")
    for e in db.fakes(difficulty="hard", address_trick="forged_from"):
        print("   %4d  %s" % (e["id"], e["subject"]))

    db.close()


if __name__ == "__main__":
    main()

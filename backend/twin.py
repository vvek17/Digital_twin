# TwinPredictor: the "digital twin" model.
# Its job is to GUESS how a person will react to an email.
#
# How it learns:
#   The twin keeps simple counters for each person (looked up by person id).
#   It watches what the person actually does (through update()) and slowly
#   builds up a guess. It starts knowing nothing and gets better with data.
#
# The model, straight off the diagram:
#
#       P(click) = a / (a + b)
#
#   where  a = times they clicked (did not recognise the phish)
#          b = times they reported it (recognised it)
#
#   Both counters start at 0, so a person with no history sits at 0.0 and every
#   answer moves the number. Ignoring is neither arrow on the diagram, so it is
#   recorded in the history but does not move a or b.
#
# The twin also keeps a HISTORY: one record per answer. The history is what the
# feedback module reads to tell the person how they are doing on each cue.
#
# IMPORTANT: The twin must NEVER read hidden_probs. Those are the person's
# secret numbers. The twin is only allowed to learn from the actions it sees.


import csv
import json
import os
from datetime import datetime

# Two files, with different jobs.
#
#   HISTORY_LOG  is the record of what happened. One JSON object per line,
#                appended and never rewritten. Past answers cannot change,
#                because nothing ever reopens an old line.
#
#   HISTORY_PATH is a snapshot of the totals, rewritten for convenience.
#                It is DERIVED - delete it and rebuild_from_log() restores it.
#
# The log is the truth; the snapshot is a cache.
HISTORY_LOG = os.path.join("data", "history_log.jsonl")
HISTORY_PATH = os.path.join("data", "people_history.json")

#   HISTORY_CSV  is the same record as the log, flattened into a spreadsheet
#                with the person and the email joined in, so one row answers
#                "who was asked what, what did they say, and were they right".
#                Also append-only. Opens directly in Excel or pandas.
HISTORY_CSV = os.path.join("data", "history.csv")

#   RESULTS_CSV  a short view of the same answers, for reading and sharing:
#                who was asked, which email, did they click it, and what the
#                email actually was.
RESULTS_CSV = os.path.join("data", "results.csv")

#   SCORES_CSV   one row per person: how many they were asked, how many they
#                got right, how many wrong. Rewritten from scratch each save,
#                because it is a summary rather than a record.
SCORES_CSV = os.path.join("data", "scores.csv")

#   EMAILS_CSV   one row per email: how many people were sent it, how many
#                trusted it, how many caught it. Also rewritten each save.
EMAILS_CSV = os.path.join("data", "email_scores.csv")

#   CLICKS_CSV   the plain click tally per account:
#                Clicked + Not Clicked always equals Total Emails.
CLICKS_CSV = os.path.join("data", "click_rates.csv")

#   SUMMARY_CSV  one row per person, numbered 1..N: how many emails they got,
#                how many fakes they fell for, how many genuine ones they got
#                right, and their accuracy.
SUMMARY_CSV = os.path.join("data", "person_summary.csv")

SUMMARY_COLUMNS = [
    "ID", "Person", "Emails Received", "Correct", "Incorrect", "Accuracy (%)",
]

CLICK_COLUMNS = ["ID", "Total Emails", "Clicked", "Not Clicked", "Click Rate (%)"]

EMAIL_SCORES_COLUMNS = [
    "email_id", "subject", "ground_truth", "attack_type", "pressure",
    "difficulty", "times_sent", "trusted", "flagged", "caught_rate",
]

SCORES_COLUMNS = [
    "id", "person_id", "person_name", "job_title", "awareness",
    "emails", "clicked", "not_clicked",
    "correct", "incorrect", "accuracy",
    "spam_trusted", "real_flagged",
]

# The columns, kept deliberately short: who was asked, which email, what it
# really was, what they answered, and the probability after that answer.
# The full record. Plain column names, grouped so it reads left to right:
#   when it happened -> who was asked -> what they were sent -> what they did.
# Nothing here is arithmetic on another column.
CSV_COLUMNS = [
    # when
    "id", "time", "answered_by",
    # who was asked
    "person_id", "person_name", "job_title", "awareness",
    # what they were sent
    "email_id", "subject", "sender", "ground_truth",
    "attack_type", "pressure", "difficulty",
    # what they did about it
    "answer", "clicked", "result",
    # what the model expected beforehand
    "predicted",
]

# The simple view.
RESULTS_COLUMNS = [
    "person_id", "person_name", "email_id", "subject",
    "clicked", "ground_truth",
]


class TwinPredictor:
    def __init__(self, log_path=HISTORY_LOG, csv_path=HISTORY_CSV,
                 results_path=RESULTS_CSV, people_by_id=None):
        # One entry per person id, e.g. "P05".
        self.counters = {}
        # One list of past answers per person id, oldest first.
        self.history = {}
        # Where answers are appended as they happen. None disables logging,
        # which is what tests and throwaway runs want.
        self.log_path = log_path
        self.csv_path = csv_path
        self.results_path = results_path
        # Optional {person_id: Persona}, used to fill the person columns in
        # the CSV. Without it those columns are left blank.
        self.people_by_id = people_by_id or {}
        self.csv_rows = 0

    # ---------------------------------------------------------- append-only

    def _append_log(self, person_id, record):
        """Append one answer to the log. Never rewrites what is already there."""
        if not self.log_path:
            return
        os.makedirs(os.path.dirname(self.log_path) or ".", exist_ok=True)
        line = dict(record)
        line["person_id"] = person_id
        # "a" mode always writes at the end of the file, so an existing line
        # cannot be touched. fsync pushes it to disk before we move on.
        with open(self.log_path, "a") as f:
            f.write(json.dumps(line) + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _append_simple(self, row):
        """Append one row to the short results file."""
        if not self.results_path:
            return
        os.makedirs(os.path.dirname(self.results_path) or ".", exist_ok=True)
        new_file = not os.path.exists(self.results_path)
        with open(self.results_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=RESULTS_COLUMNS,
                                    extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())

    def _append_csv(self, person_id, record, email):
        """Append one flat row, joining the person and the email to the answer."""
        if not self.csv_path:
            return

        os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)
        new_file = not os.path.exists(self.csv_path)

        # Count existing rows once, so "row" keeps counting across restarts.
        if new_file:
            self.csv_rows = 0
        elif not self.csv_rows:
            with open(self.csv_path) as f:
                self.csv_rows = max(sum(1 for _ in f) - 1, 0)
        self.csv_rows += 1

        p = self.people_by_id.get(person_id)
        phishing = email["label"] == "phishing"

        # "clicked" is the plain reading of what they did: they trusted a
        # phishing email and would have followed it.
        clicked = "yes" if record["action"] == "click" else "no"
        ground_truth = "phishing" if phishing else "legitimate"

        if phishing:
            outcome = "caught" if record["correct"] else "missed"
        else:
            outcome = "fine" if record["correct"] else "false alarm"

        row = {
            "id": self.csv_rows,
            "time": record.get("time", ""),
            "answered_by": "a person" if record.get("source") == "app" else "simulation",

            "person_id": person_id,
            "person_name": getattr(p, "name", ""),
            "job_title": getattr(p, "job_title", ""),
            "awareness": getattr(p, "security_awareness", ""),

            "email_id": email["id"],
            "subject": email["subject"],
            "sender": email.get("sender_email", ""),
            "ground_truth": ground_truth,
            "attack_type": email.get("technique", "") if phishing else "",
            "pressure": email.get("cue", "") if phishing else "",
            "difficulty": email.get("difficulty", ""),

            "answer": "spam" if record["said"] == "spam" else "real",
            "clicked": clicked,
            "result": "correct" if record["correct"] else "incorrect",

            "predicted": record["p_before"],
        }

        # The short view of the same answer.
        simple = {
            "person_id": person_id,
            "person_name": getattr(p, "name", ""),
            "email_id": email["id"],
            "subject": email["subject"],
            "clicked": clicked,
            "ground_truth": ground_truth,
        }
        self._append_simple(simple)

        with open(self.csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())

    def rebuild_from_log(self, path=None):
        """Replay the log to reconstruct every counter and every history row.

        This is the recovery path: the snapshot can be deleted or corrupted
        and the full history still comes back from the log alone.
        """
        path = path or self.log_path
        if not path or not os.path.exists(path):
            return 0

        self.counters, self.history = {}, {}
        replayed, damaged = 0, 0

        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    # A half-written final line from a crash. Skip it; every
                    # complete line before it is still good.
                    damaged += 1
                    continue

                pid = rec.get("person_id")
                key = rec.get("key")
                if not pid or not key:
                    damaged += 1
                    continue

                counts = self._counters_for(pid)
                if key in counts:
                    counts[key]["a"] = rec.get("yes", counts[key]["a"])
                    counts[key]["b"] = rec.get("no", counts[key]["b"])
                self.history.setdefault(pid, []).append(rec)
                replayed += 1

        self.damaged_lines = damaged
        return replayed

    @classmethod
    def from_log(cls, path=HISTORY_LOG):
        """A twin rebuilt entirely from the append-only log."""
        twin = cls(log_path=path)
        twin.rebuild_from_log(path)
        return twin

    def _counters_for(self, person_id):
        """Return this person's counters, creating fresh ones the first time."""
        if person_id not in self.counters:
            # Everything starts at 0: no history means no opinion yet.
            self.counters[person_id] = {
                # --- phishing cues: a = clicked, b = reported ---
                "urgency":      {"a": 0, "b": 0},
                "authority":    {"a": 0, "b": 0},
                "it_login":     {"a": 0, "b": 0},
                "hr_payroll":   {"a": 0, "b": 0},
                "billing":      {"a": 0, "b": 0},
                # --- legitimate emails: a = reported by mistake, b = did not ---
                "false_report": {"a": 0, "b": 0},
            }
        return self.counters[person_id]

    def _key_for(self, email):
        """Which counter does this email use?"""
        if email["label"] == "phishing":
            return email["cue"]        # e.g. "urgency"
        else:
            return "false_report"      # a real/safe email

    @staticmethod
    def p_click(a, b):
        """The model straight off the diagram:

               P(click) = a / (a + b)

        where a counts clicks and b counts reports. With no history at all
        (a + b == 0) there is nothing to divide, so the answer starts at 0.
        """
        if a + b == 0:
            return 0.0
        return a / (a + b)

    def predict(self, person_id, email):
        """Return the twin's current guess (0.0 to 1.0) for this person + email."""
        counts = self._counters_for(person_id)
        key = self._key_for(email)
        return self.p_click(counts[key]["a"], counts[key]["b"])

    def update(self, person_id, email, action, source="sim"):
        """After the human acts, move the counters and record the history.

        source says who answered: "app" for a real person clicking in the web
        interface, "sim" for the simulated human. Both land in the same history
        so the counters accumulate, but each event remembers where it came from.
        """
        counts = self._counters_for(person_id)
        key = self._key_for(email)
        before = self.p_click(counts[key]["a"], counts[key]["b"])

        if email["label"] == "phishing":
            # The diagram's two arrows, and only those two:
            #     if click  -> a++        (did not recognise it)
            #     if report -> b++        (recognised it)
            # Ignoring is neither arrow, so it leaves the counters alone.
            if action == "click":
                counts[key]["a"] += 1
            elif action == "report":
                counts[key]["b"] += 1
        else:
            # For a real email the mistake is the false alarm.
            if action == "report":
                counts[key]["a"] += 1
            else:
                counts[key]["b"] += 1

        after = self.p_click(counts[key]["a"], counts[key]["b"])

        yes = counts[key]["a"]          # clicked: did NOT recognise it
        no = counts[key]["b"]           # reported: recognised it

        # Was the judgement right? Calling a phishing email spam is correct;
        # calling a genuine email spam is a false alarm.
        if email["label"] == "phishing":
            correct = action == "report"
        else:
            correct = action != "report"

        self.history.setdefault(person_id, []).append({
            "n": len(self.history.get(person_id, [])) + 1,
            "time": datetime.now().isoformat(timespec="seconds"),
            "source": source,
            "email_id": email["id"],
            "subject": email["subject"],
            "label": email["label"],
            "cue": email["cue"],
            "key": key,
            "action": action,
            # What they pressed, and what the email actually was.
            "said": "spam" if action == "report" else "not spam",
            "truth": "spam email" if email["label"] == "phishing" else "real email",
            "correct": correct,
            "recognised": action == "report",
            # The running totals, in the same words as the answer buttons:
            #   yes = did not recognise, no = recognised, all = yes + no
            #   P(click) = yes / all
            "yes": yes,
            "no": no,
            "all": yes + no,
            "p_before": round(before, 3),
            "p_click": round(after, 3),
        })

        # Write it to the append-only log straight away, so the record exists
        # on disk before anything else can go wrong.
        self._append_log(person_id, self.history[person_id][-1])
        self._append_csv(person_id, self.history[person_id][-1], email)

    def get_history(self, person_id, key=None):
        """Every past answer for this person, newest last.

        Pass key (a cue, or "false_report") to get only that counter's history.
        """
        records = self.history.get(person_id, [])
        if key is None:
            return list(records)
        return [r for r in records if r["key"] == key]

    def get_all_estimates(self, person_id):
        """Return all of the twin's current guesses for this person as a dict."""
        counts = self._counters_for(person_id)
        return {key: self.p_click(pair["a"], pair["b"]) for key, pair in counts.items()}

    # ------------------------------------------------------------ persistence
    #
    # Without this the counters only live as long as the program does, so every
    # run starts from 0 again. Saving lets a person's history build up over many
    # sessions, which is the point of a per-person model.

    def save(self, path=HISTORY_PATH, people_by_id=None):
        """Write every person's totals and events to disk."""
        people = {}
        for pid in sorted(set(self.counters) | set(self.history)):
            entry = {"totals": self.get_totals(pid),
                     "events": self.history.get(pid, [])}
            if people_by_id and pid in people_by_id:
                entry["name"] = people_by_id[pid].name
                entry["role"] = people_by_id[pid].job_title
            people[pid] = entry

        data = {
            "note": ("Accumulated per-person history. yes = clicked (did not "
                     "recognise), no = reported (recognised), all = yes + no, "
                     "p_click = yes / all. Everything starts at 0."),
            "updated": datetime.now().isoformat(timespec="seconds"),
            "people": people,
        }

        # Write to a temp file and rename. os.replace is atomic, so a crash
        # mid-write leaves the previous snapshot intact rather than a
        # half-written file.
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        self.write_scores()
        self.write_click_rates()
        self.write_person_summary()
        return path

    def load(self, path=HISTORY_PATH):
        """Restore totals and events from disk.

        A missing or unreadable file is not an error: it just means nobody has
        any history yet, so every counter stays at 0.
        """
        try:
            with open(path) as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return False

        for pid, entry in data.get("people", {}).items():
            counts = self._counters_for(pid)
            for key, totals in entry.get("totals", {}).items():
                if key in counts:
                    counts[key]["a"] = totals.get("yes", 0)
                    counts[key]["b"] = totals.get("no", 0)
            self.history[pid] = list(entry.get("events", []))
        return True

    @classmethod
    def from_file(cls, path=HISTORY_PATH):
        """A twin that carries on from whatever is already on disk."""
        twin = cls()
        twin.load(path)
        return twin

    def write_scores(self, path=SCORES_CSV):
        """One row per person: asked, right, wrong. Overwritten each time."""
        rows = []
        for pid in sorted(set(self.counters) | set(self.history)):
            sc = self.get_score(pid)
            if not sc["answered"]:
                continue
            p = self.people_by_id.get(pid)
            rows.append({
                "person_id": pid,
                "person_name": getattr(p, "name", ""),
                "job_title": getattr(p, "job_title", ""),
                "awareness": getattr(p, "security_awareness", ""),
                "emails": sc["answered"],
                "clicked": sc["clicked"],
                "not_clicked": sc["not_clicked"],
                "correct": sc["correct"],
                "incorrect": sc["wrong"],
                "accuracy": "%d%%" % round(100 * sc["accuracy"]),
                # The two ways to be wrong, which cost different things.
                "spam_trusted": sc["missed_spam"],
                "real_flagged": sc["false_alarms"],
            })

        rows.sort(key=lambda r: -r["correct"])
        for n, r in enumerate(rows, start=1):
            r["id"] = n

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SCORES_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return path

    def write_person_summary(self, order=None, path=SUMMARY_CSV):
        """One row per person, numbered 1..N in roster order."""
        if order is None:
            order = sorted(self.people_by_id) or sorted(self.history)

        rows = []
        for n, pid in enumerate(order, start=1):
            events = [e for e in self.history.get(pid, []) if "correct" in e]
            if not events:
                continue

            clicked = identified = caught = flagged = 0
            for e in events:
                phishing = e["truth"] == "spam email"
                said_spam = e["said"] == "spam"
                if phishing and said_spam:
                    caught += 1              # right
                elif phishing:
                    clicked += 1             # wrong - trusted a fake
                elif said_spam:
                    flagged += 1             # wrong - false alarm
                else:
                    identified += 1          # right

            p = self.people_by_id.get(pid)
            # Correct: caught a fake, or correctly trusted a genuine email.
            correct_n = caught + identified
            rows.append({
                "ID": n,
                "Person": getattr(p, "name", pid),
                "Emails Received": len(events),
                "Correct": correct_n,
                "Incorrect": len(events) - correct_n,
                "Accuracy (%)": round(100 * correct_n / len(events), 1),
            })

        # Correct and Incorrect must account for every email received.
        for r in rows:
            assert r["Correct"] + r["Incorrect"] == r["Emails Received"], \
                "counts do not add up for ID %s" % r["ID"]

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=SUMMARY_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return path

    def write_click_rates(self, path=CLICKS_CSV):
        """One row per account: total, clicked, not clicked, click rate."""
        rows = []
        for pid in sorted(set(self.counters) | set(self.history)):
            events = [e for e in self.history.get(pid, []) if "correct" in e]
            if not events:
                continue
            total = len(events)
            clicked = sum(1 for e in events if e["action"] == "click")
            # Everything that is not a click. Defined as the remainder, so
            # the two can never fail to add up to the total.
            not_clicked = total - clicked
            rows.append({
                "ID": pid,
                "Total Emails": total,
                "Clicked": clicked,
                "Not Clicked": not_clicked,
                "Click Rate (%)": round(100 * clicked / total, 1),
            })

        rows.sort(key=lambda r: -r["Click Rate (%)"])

        # The invariant the file promises.
        for r in rows:
            assert r["Clicked"] + r["Not Clicked"] == r["Total Emails"], \
                "click counts do not add up for %s" % r["ID"]

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CLICK_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return path

    def write_email_scores(self, emails_by_id, path=EMAILS_CSV):
        """One row per email: who was sent it and how they did on it."""
        tally = {}
        for pid, events in self.history.items():
            for r in events:
                if "correct" not in r:
                    continue
                t = tally.setdefault(r["email_id"],
                                     {"sent": 0, "trusted": 0, "flagged": 0})
                t["sent"] += 1
                if r["said"] == "spam":
                    t["flagged"] += 1
                else:
                    t["trusted"] += 1

        rows = []
        for email_id, t in tally.items():
            e = emails_by_id.get(email_id, {})
            phishing = e.get("label") == "phishing"
            # For a phishing email, "caught" means flagged. For a genuine one,
            # getting it right means NOT flagging it.
            right = t["flagged"] if phishing else t["trusted"]
            rows.append({
                "email_id": email_id,
                "subject": e.get("subject", ""),
                "ground_truth": "phishing" if phishing else "legitimate",
                "attack_type": e.get("technique", "") if phishing else "",
                "pressure": e.get("cue", "") if phishing else "",
                "difficulty": e.get("difficulty", ""),
                "times_sent": t["sent"],
                "trusted": t["trusted"],
                "flagged": t["flagged"],
                "caught_rate": "%d%%" % round(100 * right / t["sent"]) if t["sent"] else "",
            })

        # Hardest first: the phishing emails fewest people caught.
        rows.sort(key=lambda r: (r["ground_truth"] != "phishing",
                                 int(r["caught_rate"].rstrip("%") or 0)))

        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=EMAIL_SCORES_COLUMNS)
            writer.writeheader()
            writer.writerows(rows)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
        return path

    def get_score(self, person_id):
        """How many this person judged, and how many they got right.

        Spam / not spam is a judgement with a right answer, so it can be
        scored directly - unlike the click counters, which only describe
        behaviour.
        """
        events = [e for e in self.history.get(person_id, []) if "correct" in e]
        correct = sum(1 for e in events if e["correct"])

        phishing = [e for e in events if e["truth"] == "spam email"]
        genuine = [e for e in events if e["truth"] == "real email"]

        return {
            "answered": len(events),
            # A click means they trusted a phishing email and followed it.
            "clicked": sum(1 for e in events if e["action"] == "click"),
            "not_clicked": sum(1 for e in events if e["action"] != "click"),
            "correct": correct,
            "wrong": len(events) - correct,
            "accuracy": correct / len(events) if events else 0.0,
            # The two ways to be wrong, which are not equally costly.
            "missed_spam": sum(1 for e in phishing if not e["correct"]),
            "false_alarms": sum(1 for e in genuine if not e["correct"]),
            "spam_seen": len(phishing),
            "genuine_seen": len(genuine),
        }

    def get_totals(self, person_id):
        """The running result per cue, in the same words as the answer buttons.

        yes = did not recognise, no = recognised, all = yes + no,
        p_click = yes / all. Everything starts at 0.
        """
        counts = self._counters_for(person_id)
        totals = {}
        for key, pair in counts.items():
            yes, no = pair["a"], pair["b"]
            totals[key] = {
                "yes": yes,
                "no": no,
                "all": yes + no,
                "p_click": round(self.p_click(yes, no), 3),
            }
        return totals

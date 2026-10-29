# live.py
# A live view of the simulation running by itself.
#
# Emails keep arriving to random staff across the hospital. Every few hundred
# milliseconds the screen redraws showing, right now:
#
#   - the newest arrivals, and whether that person CLICKED or RECOGNISED it
#   - live feedback for each one, from feedback.py
#   - two running boards: who is clicking, and who knows
#
# Run with:
#     python3 live.py                 runs until you press Ctrl-C
#     python3 live.py --rounds 200    stops after 200 emails
#     python3 live.py --speed 0.1     faster (seconds between emails)
#     python3 live.py --plain         no screen clearing, just a scrolling log

import argparse
import random
import sys
import time
from datetime import datetime

from backend.persona import load_people
from backend.generator import EmailGenerator
from backend.human import SimulatedHuman
from backend.twin import TwinPredictor
from backend.feedback import FeedbackModule

# ANSI colours. Kept tiny and in one place.
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"

FEED_LINES = 8        # how many recent arrivals to show
BOARD_LINES = 8       # how many people per board


def bar(fraction, width=12):
    """A tiny text bar."""
    filled = int(round(fraction * width))
    return "#" * filled + "." * (width - filled)


class LiveRun:
    def __init__(self, speed=0.4, plain=False, save_every=25, fresh=False):
        self.people = load_people()
        self.people_by_id = {p.id: p for p in self.people}
        self.generator = EmailGenerator()
        # Carry on from the history already on disk unless asked to start fresh.
        self.twin = TwinPredictor() if fresh else TwinPredictor.from_log()
        self.twin.people_by_id = self.people_by_id
        self.save_every = save_every
        self.feedback = FeedbackModule("detailed")
        self.humans = {p.id: SimulatedHuman(p) for p in self.people}
        self.speed = speed
        self.plain = plain

        # Live tallies, per person.
        self.stats = {
            p.id: {"name": p.name, "role": p.job_title,
                   "awareness": p.security_awareness,
                   "seen": 0, "clicked": 0, "reported": 0, "ignored": 0}
            for p in self.people
        }
        self.feed = []        # most recent arrivals, newest first
        self.rounds = 0
        self.started = time.time()

    # ------------------------------------------------------------- one email

    def step(self):
        # Only ask people who still have unseen emails left.
        available = [p for p in self.people
                     if len({r["email_id"] for r in self.twin.get_history(p.id)})
                     < len(self.generator.emails)]
        if not available:
            return None
        person = random.choice(available)
        seen = {r["email_id"] for r in self.twin.get_history(person.id)}
        email = self.generator.get_unseen(seen)
        if email is None:
            return None

        predicted = self.twin.predict(person.id, email)
        action = self.humans[person.id].respond(email, None)
        self.twin.update(person.id, email, action)

        key = "false_report" if email["label"] == "legitimate" else email["cue"]
        note = self.feedback.give_feedback(
            email, action, self.twin.get_history(person.id, key)
        )

        self.rounds += 1
        s = self.stats[person.id]
        if email["label"] == "phishing":
            s["seen"] += 1
            if action == "click":
                s["clicked"] += 1
            elif action == "report":
                s["reported"] += 1
            else:
                s["ignored"] += 1

        self.feed.insert(0, {
            "time": datetime.now().strftime("%H:%M:%S"),
            "person": person,
            "email": email,
            "action": action,
            "predicted": predicted,
            "feedback": note,
        })
        del self.feed[FEED_LINES:]

    # ---------------------------------------------------------------- render

    def _verdict(self, email, action):
        """Short coloured verdict for the feed."""
        if email["label"] != "phishing":
            if action == "report":
                return YELLOW + "FALSE ALARM" + RESET, "reported a genuine email"
            return DIM + "fine" + RESET, "genuine email, treated as genuine"
        if action == "click":
            return RED + BOLD + "CLICKED" + RESET, "did not recognise it"
        if action == "report":
            return GREEN + BOLD + "RECOGNISED" + RESET, "reported it"
        return DIM + "ignored" + RESET, "did not click, did not report"

    def render(self):
        out = []
        elapsed = int(time.time() - self.started)
        out.append("%sLIVE%s  Ashbrook General phishing simulation    "
                   "%sround %d   %ds elapsed%s"
                   % (BOLD, RESET, DIM, self.rounds, elapsed, RESET))
        out.append("")

        # ---- the feed, with live feedback ----
        out.append(BOLD + "ARRIVING NOW" + RESET)
        for item in self.feed:
            p, e = item["person"], item["email"]
            verdict, _ = self._verdict(e, item["action"])
            out.append("  %s%s%s  %-18s %-5s %-11s %s"
                       % (DIM, item["time"], RESET, p.name[:18],
                          e["id"], e["cue"], verdict))
            fb = item["feedback"]
            if fb:
                out.append("      %s%s%s" % (DIM, fb["headline"], RESET))
                if fb.get("history_note"):
                    out.append("      %s%s%s" % (DIM, fb["history_note"], RESET))
        for _ in range(FEED_LINES - len(self.feed)):
            out.append("")

        out.append("")

        # ---- the two boards ----
        clicked = [s for s in self.stats.values() if s["seen"] >= 3]
        by_click = sorted(clicked, key=lambda s: -s["clicked"] / s["seen"])[:BOARD_LINES]
        by_know = sorted(clicked, key=lambda s: -s["reported"] / s["seen"])[:BOARD_LINES]

        out.append("%s%sWHO CLICKS%s                                   "
                   "%s%sWHO KNOWS%s"
                   % (BOLD, RED, RESET, BOLD, GREEN, RESET))

        for i in range(BOARD_LINES):
            left = right = " " * 44
            if i < len(by_click):
                s = by_click[i]
                rate = s["clicked"] / s["seen"]
                left = "%-18s %3.0f%% %s" % (s["name"][:18], 100 * rate, bar(rate))
            if i < len(by_know):
                s = by_know[i]
                rate = s["reported"] / s["seen"]
                right = "%-18s %3.0f%% %s" % (s["name"][:18], 100 * rate, bar(rate))
            out.append("  %-44s %s" % (left, right))

        out.append("")
        total_seen = sum(s["seen"] for s in self.stats.values())
        total_click = sum(s["clicked"] for s in self.stats.values())
        total_report = sum(s["reported"] for s in self.stats.values())
        if total_seen:
            out.append("  %sacross the hospital: %d phishing emails delivered, "
                       "%.0f%% clicked, %.0f%% reported%s"
                       % (DIM, total_seen, 100 * total_click / total_seen,
                          100 * total_report / total_seen, RESET))
        out.append("  %sCtrl-C to stop%s" % (DIM, RESET))
        return "\n".join(out)

    def render_plain(self):
        """One scrolling line per email, for logging."""
        item = self.feed[0]
        p, e = item["person"], item["email"]
        verdict, why = self._verdict(e, item["action"])
        return "%s  %-18s %-5s %-11s %-22s %s" % (
            item["time"], p.name[:18], e["id"], e["cue"], verdict, why)

    # ------------------------------------------------------------------- run

    def run(self, rounds=None):
        try:
            while rounds is None or self.rounds < rounds:
                if self.step() is None:
                    print("\nEveryone has seen every email - nothing left to ask.")
                    break
                if self.plain:
                    print(self.render_plain(), flush=True)
                else:
                    sys.stdout.write(CLEAR + self.render() + "\n")
                    sys.stdout.flush()
                # Save as we go, so a Ctrl-C never loses the run.
                if self.save_every and self.rounds % self.save_every == 0:
                    self.twin.save(people_by_id=self.people_by_id)

                time.sleep(self.speed)
        except KeyboardInterrupt:
            pass

        if self.save_every:
            path = self.twin.save(people_by_id=self.people_by_id)
            total = sum(len(self.twin.get_history(p.id)) for p in self.people)
            print("\nHistory saved to %s (%d answers on file)" % (path, total))

        self.summary()

    def summary(self):
        print("\n" + BOLD + "Final tally" + RESET)
        print("%-5s %-18s %-10s %-6s %-9s %-10s" %
              ("id", "name", "awareness", "seen", "clicked", "recognised"))
        print("-" * 64)
        rows = sorted(self.stats.items(),
                      key=lambda kv: -(kv[1]["clicked"] / kv[1]["seen"]) if kv[1]["seen"] else 0)
        for pid, s in rows:
            if not s["seen"]:
                continue
            print("%-5s %-18s %-10s %-6d %-9s %-10s" %
                  (pid, s["name"][:18], s["awareness"], s["seen"],
                   "%.0f%%" % (100 * s["clicked"] / s["seen"]),
                   "%.0f%%" % (100 * s["reported"] / s["seen"])))


def main():
    ap = argparse.ArgumentParser(description="Live phishing simulation")
    ap.add_argument("--rounds", type=int, default=None, help="stop after N emails")
    ap.add_argument("--speed", type=float, default=0.4, help="seconds between emails")
    ap.add_argument("--plain", action="store_true", help="scrolling log, no redraw")
    ap.add_argument("--seed", type=int, default=None, help="repeatable run")
    ap.add_argument("--fresh", action="store_true",
                    help="ignore saved history and start every counter at 0")
    ap.add_argument("--no-save", action="store_true",
                    help="run without writing any history")
    args = ap.parse_args()

    if args.seed is not None:
        random.seed(args.seed)

    LiveRun(
        speed=args.speed,
        plain=args.plain,
        fresh=args.fresh,
        save_every=0 if args.no_save else 25,
    ).run(rounds=args.rounds)


if __name__ == "__main__":
    main()

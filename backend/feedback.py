# FeedbackModule: gives feedback to the person after each email.
#
# The feedback is built from TWO things:
#   1. THIS email   -> what it really was, and the tells it carried
#                      (red_flags / safe_signs / key_defense, from the dataset)
#   2. THE HISTORY  -> how this person has done on this cue so far
#
# So the same wrong answer reads differently the first time and the fifth time:
# the history is what turns a single result into a pattern worth naming.
#
# feedback_type controls how much is said:
#   "none"     -> nothing at all (the control group in an experiment)
#   "simple"   -> just right or wrong
#   "detailed" -> right or wrong, the tells, the defense, and the history

CUE_NAMES = {
    "urgency": "urgency",
    "authority": "authority",
    "it_login": "login / IT",
    "hr_payroll": "HR and payroll",
    "billing": "billing",
    "false_report": "legitimate email",
}


class FeedbackModule:
    def __init__(self, feedback_type="detailed"):
        self.feedback_type = feedback_type

    # ---------------------------------------------------------------- verdict

    def _verdict(self, email, action):
        """What happened, in one word plus one sentence."""
        if email["label"] == "phishing":
            if action == "click":
                return ("missed",
                        "That was phishing, and it got you. You did not recognise it.")
            if action == "report":
                return ("caught",
                        "Correct. That was phishing and you recognised it.")
            return ("passive",
                    "That was phishing. You did not fall for it, but you did not "
                    "report it either, so nobody else was warned.")
        else:
            if action == "report":
                return ("false alarm",
                        "That email was genuine. Reporting it is a false alarm - "
                        "no harm done, but it costs someone time to check.")
            return ("fine",
                    "That email was genuine, and you treated it as genuine.")

    # ---------------------------------------------------------------- history

    def _history_note(self, email, history):
        """Turn this person's past answers on this cue into one line."""
        if not history:
            return None

        cue = CUE_NAMES.get(history[0]["key"], history[0]["key"])
        seen = len(history)

        if email["label"] == "phishing":
            caught = sum(1 for h in history if h["action"] == "report")
            missed = sum(1 for h in history if h["action"] == "click")
            note = ("On %s emails you have now seen %d, recognised %d and clicked %d."
                    % (cue, seen, caught, missed))

            # Name a streak only once there is enough history to mean something.
            recent = history[-3:]
            if len(recent) == 3 and all(h["action"] == "click" for h in recent):
                note += " That is three in a row clicked - this is the cue to watch."
            elif len(recent) == 3 and all(h["action"] == "report" for h in recent):
                note += " Three in a row recognised - this cue is working for you."
            return note

        false_alarms = sum(1 for h in history if h["action"] == "report")
        return ("On genuine emails you have now seen %d and reported %d by mistake."
                % (seen, false_alarms))

    # ------------------------------------------------------------------- main

    def give_feedback(self, email, action, history=None):
        """Return a feedback dict for one answer.

        history is this person's past records for THIS email's counter, oldest
        first, including the answer just given (twin.get_history(pid, key)).
        """
        if self.feedback_type == "none":
            return None

        outcome, headline = self._verdict(email, action)
        feedback = {
            "outcome": outcome,
            "headline": headline,
            "was": email["label"],
            "cue": email["cue"],
            "tells": [],
            "defense": None,
            "history_note": None,
        }

        if self.feedback_type == "simple":
            return feedback

        # Detailed: the tells this email carried, straight from the dataset.
        if email["label"] == "phishing":
            feedback["tells"] = list(email.get("red_flags", []))
            feedback["defense"] = email.get("key_defense")
            feedback["technique"] = email.get("technique")
            if email.get("link_target"):
                feedback["hidden_link"] = (email.get("link_text"), email["link_target"])
            if email.get("reply_to"):
                feedback["reply_to"] = email["reply_to"]
        else:
            feedback["tells"] = list(email.get("safe_signs", []))

        feedback["history_note"] = self._history_note(email, history or [])
        return feedback

    # ------------------------------------------------------------ plain text

    def as_text(self, feedback):
        """Render give_feedback() output for a terminal."""
        if not feedback:
            return ""
        lines = [feedback["headline"]]
        if feedback.get("technique"):
            lines.append("Technique: %s" % feedback["technique"])
        for tell in feedback["tells"]:
            lines.append("  - %s" % tell)
        if feedback.get("defense"):
            lines.append("Defense: %s" % feedback["defense"])
        if feedback.get("history_note"):
            lines.append(feedback["history_note"])
        return "\n".join(lines)

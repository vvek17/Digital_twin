# situation.py
# A "situation" is the MOMENT an email arrives.
#
# The person's personality (hidden_probs) never changes, but the situation
# does: it is different for every email. This is the "live" layer that sits
# on top of the fixed personality.
#
# A situation has two parts:
#   - time_of_day: "day", "evening", or "night"
#   - busy_now:    "normal", "busy", or "very busy"  (how slammed they are RIGHT NOW)

import random

TIMES = ["day", "evening", "night"]
BUSY_NOW = ["normal", "busy", "very busy"]


def make_random_situation():
    """Make a random 'moment' for one email delivery."""
    return {
        "time_of_day": random.choice(TIMES),
        "busy_now": random.choice(BUSY_NOW),
    }

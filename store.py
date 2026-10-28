# store.py
# Reading and writing the app's own data files.
#
# This is the only place that knows where these files live or what shape they
# are on disk. The UI asks for emails or responses; it does not open files.
#
# Three things are kept here:
#
#   generated emails  built on the fly during a run, saved so an answer can
#                     still be traced back to the email that caused it
#   human responses   what a real person answered in the Inbox tab
#   archiving         moving the append-only files aside to start fresh
#
# Everything is written to a temp file and renamed. os.replace is atomic, so
# a crash mid-write leaves the previous file intact rather than half of a
# new one.

import json
import os
from datetime import datetime

from twin import HISTORY_LOG, HISTORY_CSV, RESULTS_CSV

GENERATED_PATH = os.path.join("data", "generated_emails.json")
RESPONSES_PATH = os.path.join("data", "responses.json")


def _write_json(path, payload):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


# ------------------------------------------------------- generated emails

def load_generated(path=GENERATED_PATH):
    """Emails built during past runs. A missing file just means none yet."""
    try:
        with open(path) as f:
            return json.load(f)["emails"]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        return []


def save_generated(emails, path=GENERATED_PATH):
    return _write_json(path, {
        "note": "Emails built on the fly during live delivery.",
        "count": len(emails),
        "emails": emails,
    })


# --------------------------------------------------------- human responses

def load_responses(path=RESPONSES_PATH):
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_response(record, path=RESPONSES_PATH):
    """Append one answer a real person gave in the Inbox tab."""
    responses = load_responses(path)
    responses.append(record)
    return _write_json(path, responses)


# ---------------------------------------------------------------- archiving

def archive_log():
    """Move every append-only file aside under one timestamp.

    All three grow by appending, so they must be archived together - leaving
    one behind would mix old answers into the new run.
    """
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = os.path.join("data", "archive", stamp)
    moved = []
    for path in (HISTORY_LOG, HISTORY_CSV, RESULTS_CSV):
        if os.path.exists(path):
            os.makedirs(folder, exist_ok=True)
            os.rename(path, os.path.join(folder, os.path.basename(path)))
            moved.append(os.path.basename(path))
    return "%s (%s)" % (folder, ", ".join(moved)) if moved else None

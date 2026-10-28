# renumber_csvs.py
# Gives each summary CSV a clean sequential ID column: 1, 2, 3 ... with no
# gaps and no duplicates, and keeps every other column as it was.
#
# A NOTE ON MATCHING IDS ACROSS THE TWO FILES
#
# The two files count different things:
#
#     email_scores.csv   one row per EMAIL   (51 rows)
#     click_rates.csv    one row per PERSON  (25 rows)
#
# So row 25 of one is an email and row 25 of the other is a staff member.
# Making the IDs "match" would invent a relationship that does not exist, so
# this script numbers each file within itself and keeps the original key
# column (email_id, person) so nothing is lost.
#
# If you want them joined, the thing that connects them is the history: every
# answer has both a person and an email. data/history.csv already holds that.
#
# Run with:
#     python3 renumber_csvs.py            renumber and report
#     python3 renumber_csvs.py --check    report only, change nothing

import os
import shutil
import sys
from datetime import datetime

import pandas as pd

DATA = "data"
BACKUP = os.path.join(DATA, "backups")

# file -> (the column that identifies a row, what to sort by)
FILES = {
    "email_scores.csv": ("email_id", "email_id"),
    "click_rates.csv": ("ID", "ID"),
    "scores.csv": ("person_id", "person_id"),
    "person_summary.csv": ("Person", "ID"),
}


def backup(path):
    """Copy the original aside with a timestamp before touching it."""
    os.makedirs(BACKUP, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(BACKUP, "%s-%s" % (
        os.path.basename(path).replace(".csv", ""), stamp + ".csv"))
    shutil.copy2(path, dest)
    return dest


def renumber(path, key_column, sort_column, write=True):
    """Add a sequential ID as the first column. Returns a short report."""
    df = pd.read_csv(path)
    before = list(df.columns)

    # Keep the original key under its own name if "ID" would overwrite it.
    if "ID" in df.columns and key_column == "ID" and "person" not in df.columns:
        df = df.rename(columns={"ID": "person"})
        key_column = "person"
    elif "ID" in df.columns:
        # Either a previous numbering, or a first column already saved under
        # its own name by an earlier run. Drop it and renumber from scratch;
        # renaming it a second time would leave two columns with one name.
        if key_column == "ID":
            key_column = "person"
        # An existing ID column is a previous numbering - drop it and
        # renumber from scratch rather than stacking a second one.
        df = df.drop(columns=["ID"])

    # Sort by the natural key. Numeric keys sort numerically, not as text,
    # so 2 comes before 10.
    sort_on = sort_column if sort_column in df.columns else key_column
    if sort_on in df.columns:
        as_numbers = pd.to_numeric(df[sort_on], errors="coerce")
        df = (df.assign(_k=as_numbers.fillna(float("inf")), _t=df[sort_on].astype(str))
                .sort_values(["_k", "_t"])
                .drop(columns=["_k", "_t"]))

    # The sequential ID, 1..N, as the first column.
    df.insert(0, "ID", range(1, len(df) + 1))

    report = {
        "file": os.path.basename(path),
        "rows": len(df),
        "key": key_column,
        "id_min": int(df["ID"].min()) if len(df) else 0,
        "id_max": int(df["ID"].max()) if len(df) else 0,
        "gaps": sorted(set(range(1, len(df) + 1)) - set(df["ID"])),
        "duplicate_ids": int(df["ID"].duplicated().sum()),
        "duplicate_keys": int(df[key_column].duplicated().sum())
                          if key_column in df.columns else 0,
        "columns_before": before,
        "columns_after": list(df.columns),
        "backup": None,
    }

    if write:
        report["backup"] = backup(path)
        df.to_csv(path, index=False)
    return report


def main():
    check_only = "--check" in sys.argv
    reports = []

    for name, (key, sort_on) in FILES.items():
        path = os.path.join(DATA, name)
        if not os.path.exists(path):
            print("skipped %s (not found)" % name)
            continue
        reports.append(renumber(path, key, sort_on, write=not check_only))

    print("%-22s %6s %10s %8s %8s %9s" %
          ("file", "rows", "ID range", "gaps", "dup IDs", "dup keys"))
    print("-" * 70)
    for r in reports:
        print("%-22s %6d %10s %8d %8d %9d" %
              (r["file"], r["rows"], "%d-%d" % (r["id_min"], r["id_max"]),
               len(r["gaps"]), r["duplicate_ids"], r["duplicate_keys"]))

    print()
    for r in reports:
        if r["gaps"]:
            print("%s has gaps at: %s" % (r["file"], r["gaps"][:20]))
        if r["duplicate_keys"]:
            print("%s has %d duplicate %s values - two rows describe the same "
                  "thing" % (r["file"], r["duplicate_keys"], r["key"]))

    if check_only:
        print("\n--check: nothing was written.")
    else:
        print("\nbackups:")
        for r in reports:
            if r["backup"]:
                print("   %s" % r["backup"])

    # The cross-file point from the brief.
    print()
    print("Cross-file note: email_scores.csv is one row per EMAIL and")
    print("click_rates.csv is one row per PERSON, so their IDs describe")
    print("different things and cannot line up. data/history.csv is the file")
    print("that holds both together - one row per answer, with the person and")
    print("the email on it.")


if __name__ == "__main__":
    main()

# ALERT administration

Start the application normally:

```bash
python3 -m streamlit run app.py
```

The sidebar has two main screens: **App** and **Admin**. **Admin** opens the protected `pages/admin.py`
workspace. **App** returns to the practice screen, whose sidebar
switches between Inbox and Training progress. Admin contains Dashboard,
Live, Person, All history, Run, Model, Emails, and System. The existing health,
backup, restore, and cache tools are inside System. Only the selected section
runs, so System can be opened even when malformed research data prevents the
other sections from loading.

The UI lives in `frontend/admin_*.py` and calls `backend/admin.py`. Backend
modules never import Streamlit. `frontend/runtime.py` shares workspace lifecycle;
`backend/training.py` records human practice with the existing twin logic.
Simulation controls and settings, full data downloads, model benchmarks, email
generation, raw counters, and workforce reports are available only in Admin.
The main page shows human training results (`source="app"`) for its selected
fictional persona. These personas are not authenticated private accounts.

Automatic Live and Run answers always use the existing email reader. The old
hidden-probability choice is removed, and stale `use_reader=False` values cannot
enable it through backend service calls. Terminal runners follow the same rule.
Inbox continues to save the user's actual Spam / Not spam choice without an
automatic answerer. Existing saved results and legacy roster fields are retained.

## Assign a manual practice session

In **Person**, select a staff member using the existing searchable sidebar
picker. Enter **Practice emails**, then click **Assign practice**. Counts must
be positive whole numbers, up to the existing Run ceiling of 1,000,000. Return
to **App → Inbox** and select that same fictional person to answer the
assigned emails manually. No real messages are sent. **Run** continues to
produce automatic simulated answers and is unchanged.

The backend rechecks authorization, participant and count under the existing
admin write lock. A stable request ID makes repeated submissions idempotent.
A person can have one unfinished session; completing it allows another.
The service reuses complete generated emails that the person has not answered,
then calls the existing `EmailBuilder` only for the shortfall. Exact duplicate
message text is excluded within the session, using the existing fingerprint
helper and retry limit. If the full requested count cannot be prepared,
assignment fails without saving a shorter session or changing history.

`data/practice_sessions.json` stores each assignment's person ID, requested
count and complete email snapshots in one atomic write. Responses still use
the existing `submit_answer`, twin update, `source="app"` log, feedback and score
calculations. Person ID plus the assigned email IDs identify each session's
answers; no database schema change is required. Session progress appears in
Inbox, while Training progress retains the person's full human-answer history.
People without assignments practice from the saved generated pool. An empty
pool shows an instruction to prepare emails, instead of serving static templates.
Live and Run also reuse generated messages when **Build new emails** is off.
With repeats disabled, an answered message cannot return under a different ID
with identical subject/body text. An empty or exhausted pool skips delivery;
enable building or prepare additional generated messages to continue.

Email Studio now saves its complete generated objects in the shared JSON pool,
in addition to its existing CSV export. The generator's content and similarity
logic are unchanged. Genuine generated messages retain their source teaching notes.
The service allocates integer IDs above those already in
the pool, assignment snapshots, retained history and CSV. Legacy CSV-only rows lack complete
sender/classification/feedback fields and are not reconstructed as new emails.
Matching CSV exports are accepted by integrity checks; conflicting IDs still
produce issues.

Live/Run refresh shared generated-email data before allocating IDs and saving,
preserving unsaved emails in their current workspace as well as new assignments.
The existing simulation loop, answerers and scoring are unchanged. Direct CLI
writers still do not participate in the admin lock; stop those writers when
assigning practice, as with the existing maintenance operations.

Assignments and snapshots are git-ignored and included in health, integrity,
backups and restore. A full-results reset also clears assignments after backing
them up. Existing participant answers and scores are never cleared by assigning
another session. Sessions remain fictional-person practice, not private trainee
accounts or external email delivery.

## Access

Create a local `.streamlit/secrets.toml` with a password you choose:

```toml
admin_password = "replace-with-your-own-long-password"
```

This file is ignored by Git. Do not commit passwords or put them into source
code. For a hosted Streamlit instance, configure the same key through its
secrets settings. A missing, empty, or whitespace-only password locks the
page. Password checks use `hmac.compare_digest`; changing the configured
password invalidates existing admin authentication on the next page run.
`backend/auth.py` issues random, server-held grants after a successful password
check. Grants expire after eight hours and are bound to a session ID and the
configured password. Backend service calls revalidate the grant. Logout revokes
it; a process restart requires a new login. The page reads no research data
before authentication. This does not add trainee accounts or restrict trusted
local command-line/filesystem operators.

## Health and integrity

The page reports file existence, bytes, UTC modification time, record count,
and individual read errors. JSONL record counts include malformed nonblank
lines; the integrity section reports malformed lines separately. JSON
snapshots count person entries. SQLite's file-level record count sums its
five tables; the database section lists each table and view separately.

Integrity checks cover source structure, missing required fields, duplicate
staff/email IDs, collisions across curated and generated stores (including
the on-demand generator CSV), malformed history lines, and unknown history
references. These checks report issues without repairing anything. They do
not establish that an email ID refers to the correct historical subject.

All health queries are read-only. They never create or rebuild the database.
Missing optional runtime files are normal on a new installation.

## Backups and restore

**Create backup** writes a timestamped ZIP under root-level `backups/`. It
contains the known source/runtime data files, any existing audit trail, and a
SHA-256 checksum manifest. It excludes secrets, older backups, and code.
The older `data/backups/` migration directory is not the new backup list.

Select a listed ZIP and type **RESTORE** to restore it. Restore validates
paths, manifest version, checksums, and presence of both authored sources,
then automatically backs up the current files before changing data. Files
absent from the selected backup are removed from the managed set. The current
audit trail is preserved rather than replaced by its older backup copy.

Each rewritten file uses a temporary file and `os.replace`. A caught write
failure triggers rollback from the pre-restore backup. A whole restore spans
multiple files and is not one filesystem transaction: a process or machine
crash can interrupt it. The pre-restore ZIP remains available for recovery.
Restoring history is an explicit administrative recovery operation.

Restore clears caches and discards this session's old simulation state so the
main app reloads the restored files. Other open sessions must be reloaded.
There is also a separate button to clear data/resource caches without changing
saved data. Cache clearing does not discard an existing session's twin.

## Jobs, locks, and audit

Writes are blocked while this session reports an active Live or Run job.
Run's flag clears in `finally`, including on failure. `.admin.lock` serializes
admin writes; it does not coordinate the existing simulation writers.

Stop simulations in **all** browser sessions and command-line processes
before backup, restore, or cache clearing. Also stop training submissions in
other sessions during restore. The page cannot detect those other jobs. SQLite WAL/journal sidecar files also block backup/restore. After a
crash, verify no admin operation is running before removing a stale lock.

Admin writes, including simulated deliveries and email generation, append
`started` and `success`/`failed` entries to
`data/admin_audit.jsonl`, with UTC timestamp, action, target, affected-file
count, and outcome. Audit and backup files are ignored by Git. Counts refer to
files for backup/restore, deliveries for simulations, emails for generation,
and zero for cache clearing or snapshot saves.

## Tests

```bash
pip install -e '.[dev]'
python3 -m pytest -q
```

Write tests use temporary fixtures. Streamlit AppTest also checks login and
read-only page rendering against real project data, verifying that file
sizes/modification times remain unchanged. The test suite never restores or
backs up the real dataset.

Per-person/source-filtered history resets, twin/database rebuilding tools, roster/email editing, persisted
configuration, and additional model management belong to later phases. Moving
existing research views does not implement those new features.

The Model section warns about the existing legitimate-email scoring inversion
and the separate command-line counting-baseline leakage. These research defects
were not silently changed as part of moving the UI. Teaching flags and safe
signs are hydrated from source JSON when loading curated database emails, so
Inbox feedback and instructor previews retain the dataset's explanations.

A full-results reset is available to authorized local operators through
`AdminService.reset_all_results("RESET ALL RESULTS")`. It automatically backs
up current data, stages an empty twin and database projection, atomically
replaces result files, and rolls back caught write failures. It preserves the
roster, original email corpus, secrets, taxonomy catalogue, backups, and audit
trail. The reset audit entry records the cleared history count and backup name.
Stop the app and other writers first, then restart Streamlit to discard stale
session state. This helper is not a per-person/source reset UI.

## Readability and live tables

The centered workspace has a 1340px maximum width and uses shared headers,
cards, spacing and typography from `frontend/layout.py`, `responsive.py` and
`.streamlit/config.toml`. Cards group related controls and results without
forcing equal heights on unrelated content. Inbox and Training progress use
sidebar navigation; only the selected view renders, with existing session state.
Native Streamlit page routes and the authorization boundary remain intact.
`frontend/runtime.py` keeps database paths in session state and opens/closes
queries on the current script thread, so refreshes do not reuse a SQLite
connection created by a previous interaction's thread.

Inbox uses the email reader in `frontend/email_presentation.py`: full sender
and Reply-To addresses, subject, original plain-text body and inspectable
link metadata. Paragraphs and signatures remain intact. Long messages scroll
within the reader, and message text is escaped rather than executed as HTML.
The same reader is used in Training progress.

After a decision, the answered email remains open until **Next email**. The
review shows the saved correctness and classification, original feedback
headline and evidence, optional link/reply details, learning note and history.
Genuine-email learning notes use the existing email's `key_defense` when the
feedback does not include one; missing notes are not invented. Practice
metrics use the same human-only records and calculations as Training progress.
Queued decisions include the displayed persona and email IDs. Buttons are
disabled while saving, reviewed messages cannot be resubmitted in the UI,
and stale clicks cannot answer a new message. The backend's existing
already-answered validation remains unchanged.

Shared panel grids use `auto-fit` and `minmax()` to respond to their actual
available width, including sidebar resizing. Controls, metrics and actions
have their own readable minimum track sizes. This replaces the old global
column overrides based on browser-width breakpoints.

Dashboard's two overview charts use equal-width columns and stack when two
readable panels no longer fit. The Clicked vs recognised card has a compact grouped
chart with horizontal awareness labels, direct percentage values, and a fixed
0–100% scale. Long awareness labels wrap; more than four levels retain a
horizontal scroll area instead of dropping categories or shrinking labels.
The staff chart uses stable person IDs, wrapped names, direct percentages
and a consistent row step, so people with identical names remain separate.
Chart height follows both row count and label length. Long graphics scroll
within a viewport-relative limit while the native toolbar remains outside
the clipping area; small charts retain their natural height. The
pressure breakdown sits below the shorter overview chart to use the column
space. Chart axes and legends use 14px text, headings use
20–28px, and native dataframe text is approximately 15px with the project theme.
The pressure breakdown uses red progress tracks and an aligned percentage
column without redundant axes. Its Cue table remains immediately underneath.
Both charts and the Live probability trace remain connected to the same data.

The per-person judgement table also contains optional delivery columns,
selected under **Choose columns**. This replaces the separate overlapping
workforce table without discarding its values. Phishing rates still use only
phishing arrivals; judgement accuracy still includes both kinds of email.

All tables share automatic row-based height, compact spacing, content-driven
column sizing, and native scrolling/search/sorting. Width inference examines
the complete column, so long names added in the middle are included. Short tables fit their
values; long text receives more width than numbers. Accuracy and rate columns
use compact progress indicators. Long tables use Streamlit's existing
virtualized grid with sticky headers, export, fullscreen and column controls.
Secondary fields remain available through the native columns menu where the
default view is simplified. All history retains its CSV export and optional
per-person summary. System groups file health, database checks, integrity,
backups and cache controls into separate cards. The email catalogue and
email picker include the complete pool rather than only the last 500 records.
Training, Dashboard, Person, All history, Emails, and System refresh their
source-backed displays every 15 seconds while connected. Simulation and model
jobs still run only when explicitly started. No backend calculations changed.

# ALERT

A fictional hospital's staff receive simulated phishing and legitimate emails.
ALERT learns to predict whether each person will click, report or ignore an
email — without ever being allowed to see why they really do it.

Everything is fictional: fake hospital, fake names, `.example` domains only.

GitHub: https://github.com/vvek17/Digital_twin

## The idea in one line

A person answers emails; the twin learns to predict those answers purely by
counting what it observes, and is graded on emails it has never seen.

## Layout

**[docs/STRUCTURE.md](docs/STRUCTURE.md) is the map** — every file with one line
on what it does, a "I want to change X, where do I go" table, and which files
are safe to delete. Start there if you are looking for something.

Everything else written about the project lives in **[docs/](docs/)** — see
[docs/README.md](docs/README.md) for the index.

```
app.py  main.py  live.py  evaluate.py     the things you run
pages/admin.py                           protected instructor workspace
README.md  pyproject.toml                 the front page, and the install

frontend/   training_views Inbox and human training progress
            admin_*        instructor reports, experiments, emails, system tools
            runtime        shared session lifecycle
            layout         shared page headers and cards
            dashboard_charts row-based staff and pressure visualizations
            tables         content-sized, virtualized data tables
            responsive     workspace, typography and responsive grid rules
            theme          palette, chart styling, verdict wording
backend/    auth           server-held admin grants
            admin          authorized research and maintenance operations
            training       shared workspace and human-answer submission
            practice       counted manual sessions and generated-email selection
            engine         one delivery: pick, predict, answer, update
            twin           the counting model, P(click) = yes / (yes + no)
            reader         answers by inspecting the email
            human          compatibility wrapper for the email reader
            store          reading and writing the app's data files
            metrics        history to DataFrames
            benchmark      the ML model against the counting twin
            ml_model       the scikit-learn pipeline
            email_builder  builds new emails from genuine ones
            db_builder     the same, seeded by database query
            entities       swaps reference numbers, wards, days, times
            modifications  the things that make an email phishy
            persona  simulation  feedback  situation  generator
database/   schema.sql  build.py  db.py
scripts/    make_emails  make_people  make_types
tests/      test_persona  test_situation  test_twin  test_twin_all
data/       the sources, and everything built from them
docs/       everything written about the project - no code imports it
```

No file in `backend/`, `database/` or `scripts/` imports `streamlit`. That is
the rule the split is held to: if a module draws, it is frontend; if it
decides, it is backend. Only `app.py`, `pages/`, and `frontend/` know the UI exists.

The workspace is centered with a 1340px maximum width. Related views share
responsive card grids, with compact readable typography. Shared CSS grids use
the space actually available inside each section, including sidebar changes.
Panels use equal-width tracks with a 24rem readable minimum; controls, metrics
and actions use smaller semantic track sizes. Tracks stack when they no longer
fit, rather than relying on browser-width breakpoints. Tables size their columns from content rather than
stretching short values across the page. Large tables retain native
virtualized scrolling, sorting, search, column visibility, export and fullscreen.
See `frontend/layout.py`, `frontend/tables.py` and `frontend/responsive.py`.

## Install

```bash
pip install -e .
```

Editable mode, so `backend`, `frontend` and `database` resolve whichever way a
script is started, and edits take effect without reinstalling.

Dependencies: streamlit, pandas, altair, scikit-learn, numpy.

## Run

```bash
python3 -m streamlit run app.py     # training app and protected Admin page
python3 main.py P09 200             # one person, 200 emails, in the terminal
python3 main.py all 100             # everyone, 100 each
python3 live.py                     # the live loop without the UI
python3 evaluate.py 200             # does the twin transfer to new emails?
```

`main.py` takes `--fresh` (ignore saved history), `--no-save`, and `--repeats`
(let an email arrive twice). Automatic answers always inspect the email.
The old `--reader` flag remains accepted for compatibility.

```bash
python3 -m backend.ml_model         # train and evaluate, print the metrics
python3 -m backend.benchmark 200    # ML model vs counting twin
python3 -m backend.db_builder 1 fake
python3 -m database.build           # rebuild the database
python3 -m database.db              # show what is in it
python3 tests/test_twin_all.py      # all 25 people, per-person accuracy
```

## The app

The main page is for training. **Inbox** lets you judge emails and receive
explained feedback. The email reader preserves the original message and keeps
the answered email open until **Next email**. Its review separates the saved
verdict, source evidence, learning note and human-practice progress.
**Training progress** shows human answers for the selected
fictional persona, with accuracy and answered-email review. Simulated answers
never exhaust the human practice queue. There are no private trainee accounts;
choosing a persona does not establish a real user's identity.

Select **Admin** under **Main screens** and log in to access:

| Section | What it does |
|---|---|
| Dashboard | workforce click rates, awareness comparisons, and scores |
| Live | start/stop simulated delivery, inspect arrivals, speed and session feed |
| Person | assign manual practice, full report card, response sources, counters and history |
| All history | workforce records, filters and CSV download |
| Run | batch the same delivery engine, up to a million deliveries |
| Model | train and compare ML with the counting twin; known scoring issues are flagged |
| Emails | generate, browse and inspect curated/built emails and teaching notes |
| System | file/database health, integrity, backups, restore and cache clearing |

Simulation toggles (new vs saved generated emails, and repeats) live in Admin's
Live and Run sections. Automatic answers always use the existing email reader;
there is no hidden-probability answer mode. Only the selected admin section executes. Leaving Live stops future
bursts; opening training or logging out also stops the session's Live loop.

For manual practice with a custom count, open **Admin → Person**,
select the staff member, enter **Practice emails**, and click **Assign practice**.
Then return to **App → Inbox**, select the same fictional person, and
answer Spam / Not spam. A session contains exactly the requested number of
unique generated emails; existing complete emails are reused before the current
builder creates the shortfall. Only an administrator can assign sessions.
Assignments do not create simulated answers or send real email. Without an
assignment, Inbox uses the saved generated pool. If it is empty, prepare emails
in Admin; opening or refreshing a page never generates messages. **Run** keeps
its automatic simulation workflow. With **Build new emails** off, Live and Run
reuse saved generated messages; they never fall back to static templates.

Set `admin_password` in the git-ignored `.streamlit/secrets.toml`. Missing or
empty credentials lock Admin. Backend service methods require an expiring,
server-held grant bound to the browser session and current password. Hiding a
control is not the authorization mechanism. Local Python/CLI operators remain
trusted filesystem users.

See [docs/ADMIN.md](docs/ADMIN.md) for setup, backup behavior and limitations.
The reorganization does not add per-person history reset, roster editing, or configuration
features from the later admin roadmap.

## How one delivery works

```
   1. pick      a fresh generated email, or a saved generated email
   2. predict   the twin guesses, from its counters alone
   3. answer    the reader inspects the email; Inbox records the user's actual choice
   4. update    the counters move, and the answer is appended to the log
```

Step 2 has to come before step 3. A prediction is only worth something if it
was committed before the outcome existed.

The terminal runners also use the existing builder and retain complete generated
messages alongside their answer history. The static catalogue remains available
for template generation, inspection, and review of previous results. There is no
SMTP service: delivery means arrival inside this fictional simulation.

## The data

**25 staff** across 5 pillars — Patient Care; Diagnostics & Treatment; Nursing
& Clinical Support; Administration & Management; Operations & Infrastructure.
Each has realistic workforce fields plus a `simulation` block holding
`role_group`, `security_awareness`, `workload`, `shift` and `hidden_probs`.

`hidden_probs` contains legacy click chances retained in the original roster and
database. **No answer generator uses these values.** Manual practice records the
user's choices; automatic runs use `RuleReader`, including older scripts that
still import `SimulatedHuman`. Legacy terminal comparison summaries can still
read these fields for grading, but they do not choose answers. **The twin must
never read them to predict.** Existing historical results are preserved.

**51 emails** — 26 phishing, 25 legitimate — built around the HIM 1055 Weeks 7
& 8 taxonomy of attacks and threats. Several genuine emails are deliberate
near-twins of a phishing one, so the difference is the lesson rather than the
vocabulary.

Email ids are one integer sequence. The curated set holds 1–51; anything built
on the fly continues above that, so a generated email can never shadow a
curated one.

### Files under `data/`

Sources, tracked in git:

- `hospital_people.json` — the 25-person workforce
- `hospital_emails_mixed.json` — the 51 emails

Built from them, git-ignored and rebuildable:

- `history_log.jsonl` — every answer, appended and never rewritten. **This is
  the truth.** Each line is fsync'd as it happens.
- `people_history.json` — a snapshot of the totals. Derived; delete it and
  `rebuild_from_log()` restores it.
- `simulation.db` — the queryable projection of all of the above
- `responses.json` — what real people answered in the Inbox tab
- `generated_emails.json` — complete generated messages, including labels,
  sender details, links and teaching notes; retain this with generated-email history
- `history.csv`, `results.csv`, `scores.csv`, `email_scores.csv`,
  `click_rates.csv`, `person_summary.csv` — the exports

The log is the source of truth and the snapshot is a cache. Nothing is ever
only in the database.

`data/practice_sessions.json` stores manual assignments and their complete email
snapshots. It is git-ignored and backed up, but is not a disposable cache: keep
it to retain the exact generated messages associated with practice history.

## The database

`data/simulation.db`, built by `database/build.py` from the JSON and the log.

| Table | Holds |
|---|---|
| `emails` | one row per email, flattened |
| `red_flags` | one row per tell |
| `people` | staff, visible facts only |
| `hidden_probs` | the secrets — separate on purpose |
| `deliveries` | one row per answer |

Three views cover what would otherwise be nested loops: `v_person_scores`,
`v_email_scores`, `v_cue_rates`.

```python
from database.db import Database
db = Database()
db.fakes(difficulty="hard", address_trick="forged_from")
db.person_scores()[:5]
db.cue_rates("P09")
```

The schema lives in `database/schema.sql` as SQL, not as a string inside
Python, so it can be read without reading code.

## What the ML results mean

`backend/ml_model.py` trains four models and holds out **whole emails**, not
random rows — splitting rows at random would put the same email in both halves
and the model would score well by memorising it.

The honest headline: a random forest beats the counting twin by about half a
point. Fifteen features and 200 trees buy very little over dividing two
numbers, and that is a real finding rather than a disappointing one.

**The labels come from the rule reader**, so these models are learning to
reproduce a checklist. A high score means the pipeline works and the rules are
learnable. It is **not** evidence about human behaviour, because no human
generated those labels.

## Known issues

- 49 rows in the history (0.43%) carry a curated email id but a built email's
  subject, all within a two-minute window on 2026-10-26 when the app was
  running during an id migration. `v_email_scores` groups by subject so they
  show up rather than being averaged away.
- The entity swapper changes each value independently, so a generated email can
  say "41% compliance, up from 69%" or sign a Payroll email "Radiology". It
  does not affect the models, which read structure rather than prose, but a
  human reading one spots it.

## Documents

All under [docs/](docs/), indexed in [docs/README.md](docs/README.md). Each one
has a printable version of the same name in [docs/pdf/](docs/pdf/).

| Document | What it is |
|---|---|
| [STRUCTURE.md](docs/STRUCTURE.md) | the map: every file, one line each, plus "I want to change X, where do I go" |
| [PROJECT_MEETING_GUIDE.md](docs/PROJECT_MEETING_GUIDE.md) | the whole project in four pages of plain English |
| [PROJECT_CODE_EXPLANATION.md](docs/PROJECT_CODE_EXPLANATION.md) | what each file does, in four pages |
| [CONNECTION_MAP.md](docs/CONNECTION_MAP.md) | every file and exactly what it imports, as a tree |
| [PROJECT_COMPLETE_EXPLANATION.md](docs/PROJECT_COMPLETE_EXPLANATION.md) | the long one: 84 pages, architecture to the known bugs, 40 questions |
| [prompts.md](docs/prompts.md) | the main prompts used to build the project |

The `.md` file is the original; the PDF beside it in `docs/pdf/` is a printed
copy and does not update by itself.

Slides and earlier hand-outs are in [docs/presentation/](docs/presentation/).

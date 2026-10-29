# What is where

A map of the project. If you are looking for the file that does a
particular thing, start with the table in **"I want to change..."** below.

## The four things you run

| | |
|---|---|
| `app.py` | the website. `python3 -m streamlit run app.py` |
| `main.py` | run the simulation in the terminal for one person or everyone |
| `live.py` | watch deliveries happen, one at a time, without the website |
| `evaluate.py` | does the twin still work on emails it has never seen? |

Everything else is a library that these four use.

## The folders

| Folder | Rule | What is in it |
|---|---|---|
| `frontend/` | how things **look** | colours, chart styling, responsive layout |
| `backend/` | how things **work** | the simulation, the models, the builders |
| `database/` | how things are **stored and queried** | schema, builder, query layer |
| `scripts/` | run **once in a while** | generators and maintenance |
| `tests/` | **check** a piece works | one script per piece |
| `data/` | what is **read and written** | the sources, and everything built from them |
| `docs/` | what is **written about it** | this file, the guides, the slides |

`docs/` is the odd one out: no `.py` file imports anything from it, so it can
be moved or renamed without the application noticing. Everything else is code
the four programs depend on.

The rule the split is held to: **nothing in `backend/`, `database/` or
`scripts/` imports streamlit.** Only `app.py` and `frontend/` know there is a
website at all. If a file draws something it is frontend; if it decides
something it is backend.

## Every file, one line each

### `backend/` — the simulation

**The people and the emails**

| File | What it does |
|---|---|
| `persona.py` | one member of staff, loaded from JSON |
| `generator.py` | decides which email a person gets next |
| `situation.py` | the moment an email arrives (busy? night shift?) |

**Who answers the email** — two different models of a person

| File | What it does |
|---|---|
| `reader.py` | answers by **looking at the email**: sender domain, Reply-To, links, wording |
| `human.py` | answers by **rolling dice** against the person's secret `hidden_probs`, never reads the email |

`reader.py` is the default. `human.py` is the older approach, kept so the two
can be compared.

**The twin and the loop**

| File | What it does |
|---|---|
| `twin.py` | the twin itself: counts answers, predicts `P(click)`, writes the log and the CSVs |
| `engine.py` | **one delivery**: pick an email, predict, answer, update. The Live tab and the Run tab both call this |
| `simulation.py` | runs many deliveries for one person |
| `feedback.py` | explains to the person what they just got wrong |
| `store.py` | reads and writes the app's data files |
| `metrics.py` | turns the history into tables for the charts |

**Building new emails**

| File | What it does |
|---|---|
| `modifications.py` | the catalogue of 17 ways to make an email phishy |
| `entities.py` | swaps ticket numbers, wards, days, times for fresh ones |
| `email_builder.py` | genuine email + modifications = a new email |
| `db_builder.py` | the same, but picks its starting email by database query |
| `email_generator.py` | builds one on demand and rejects it if too similar to an existing one |

**The machine learning**

| File | What it does |
|---|---|
| `ml_model.py` | the scikit-learn pipeline: features, split, train, evaluate |
| `benchmark.py` | the ML model against the counting twin, on brand new emails |

### `frontend/` — how it looks

| File | What it does |
|---|---|
| `theme.py` | the colours, the chart styling, the wording of a verdict |
| `responsive.py` | makes the layout work on a narrow window and a phone |

### `database/` — stored and queried

| File | What it does |
|---|---|
| `schema.sql` | the tables and views, as plain SQL |
| `build.py` | fills the database from the JSON files and the log |
| `db.py` | the queries. `Database()` is what you import |

### `scripts/` — run once in a while

| File | What it does |
|---|---|
| `make_emails.py` | writes `data/hospital_emails_mixed.json`, the 51 emails |
| `make_people.py` | writes `data/hospital_people.json` — **stale, see below** |
| `make_types.py` | writes `data/types.csv`, every category used anywhere |

These **overwrite the source data**. Do not run them casually.

`make_people.py` is out of date with the data it is supposed to produce: it
generates **30** people over four role groups, while
`data/hospital_people.json` holds **25** over five pillars and six role
groups. Running it would replace the roster with an incompatible one. It is
kept as the record of how the dataset was first made, not as a tool to re-run.

`make_person_summary.py` was removed: `twin.write_person_summary()` produces
the same CSV automatically on every save. `renumber_csvs.py` was removed too -
it was a one-time migration, completed on 2026-10-26.

## I want to change...

| ...this | ...go here |
|---|---|
| a colour, or how a chart looks | `frontend/theme.py` |
| how it behaves on a phone | `frontend/responsive.py` |
| the wording or layout of a tab | `app.py` — find the tab by its `with tab_xxx:` block |
| how a person decides spam or not | `backend/reader.py` |
| how the twin predicts | `backend/twin.py` |
| what happens in one delivery | `backend/engine.py` — Live and Run both use it |
| the text or sender of an email | `scripts/make_emails.py`, then rerun it |
| a new way to make an email phishy | `backend/modifications.py` |
| which values get swapped in a new email | `backend/entities.py` |
| the ML features or models | `backend/ml_model.py` |
| a database table, view or column | `database/schema.sql`, then `python3 -m database.build` |
| a new query over the history | `database/db.py` |
| where a file is saved | `backend/store.py` or the paths at the top of `backend/twin.py` |

## The path one email takes

```
  1. generator.py or email_builder.py      pick or build the email
  2. situation.py                          what moment it arrives in
  3. twin.py       predict()               the twin guesses FIRST
  4. reader.py or human.py   respond()     the person answers
  5. twin.py       update()                counters move, answer is logged
  6. feedback.py                           explains what happened
```

Step 3 must come before step 4. A prediction only counts if it was made
before the answer existed.

`backend/engine.py` is the file that runs these six steps in order.

## Which files can I delete?

**Sources — do not delete.** These are tracked in git.

```
data/hospital_people.json          the 25 staff
data/hospital_emails_mixed.json    the 51 emails
```

**The truth — do not delete.** Everything else can be rebuilt from these.

```
data/history_log.jsonl             every simulated answer, appended, never rewritten
data/responses.json                what REAL people answered in the Inbox tab
```

`responses.json` is the one file nothing can regenerate. A person typed it.

**Rebuilt — safe to delete.** They come back on their own.

```
data/people_history.json     a cache of the totals, rebuilt from the log
data/simulation.db           python3 -m database.build
data/*.csv                   written again on the next run
data/generated_emails.*      emails built on the fly
data/db_emails.json          python3 -m backend.db_builder 20
data/types.csv               python3 -m scripts.make_types
```

## Naming

- a **cue** is the pressure an email uses: urgency, authority, it_login,
  hr_payroll, billing
- **false_report** is calling a genuine email spam
- **yes** means clicked, **no** means reported, so `P(click) = yes / (yes + no)`
- a **fake** is a phishing email, a **real** one is legitimate
- **hidden_probs** are the secret numbers the twin is supposed to guess.
  It must never read them.

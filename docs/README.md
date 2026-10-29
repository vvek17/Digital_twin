# Documents

Everything written *about* the project. Nothing here is imported by the code,
so moving or editing these files cannot break the application.

The project [README](../README.md) is deliberately still at the top level,
because that is where GitHub and every other tool looks for it.

```
docs/
  README.md                        this index
  STRUCTURE.md                     the map: every file, one line each
  PROJECT_MEETING_GUIDE.md         the project in 4 pages of plain English
  PROJECT_CODE_EXPLANATION.md      what each file does, in 4 pages
  CONNECTION_MAP.md                every file and what it imports
  PROJECT_COMPLETE_EXPLANATION.md  the long one: 84 pages
  prompts.md                       the prompts used to build it
  pdf/                             the printable copy of each document above
  presentation/                    the slide decks and hand-outs
```

## Start here

| Document | What it is | Read it when |
|---|---|---|
| [STRUCTURE.md](STRUCTURE.md) | The map: every file with one line on what it does, plus a "I want to change X, where do I go" table | You are looking for the file that does a particular thing |
| [PROJECT_MEETING_GUIDE.md](PROJECT_MEETING_GUIDE.md) · [PDF](pdf/PROJECT_MEETING_GUIDE.pdf) | The whole project in **four pages of plain English**: what it does, frontend and backend, a step-by-step walkthrough, and what to say in a meeting | You have an hour and need to be able to explain the project |
| [PROJECT_CODE_EXPLANATION.md](PROJECT_CODE_EXPLANATION.md) · [PDF](pdf/PROJECT_CODE_EXPLANATION.pdf) | **Four pages on the files themselves**: which file belongs to frontend, backend or database, the 18 that matter with what breaks if each is deleted, and the order to open them in | You are asked "what does this file do?" |
| [CONNECTION_MAP.md](CONNECTION_MAP.md) · [PDF](pdf/CONNECTION_MAP.pdf) | Every file and exactly what it imports, drawn as a tree. 3 pages, built to be printed | You want to see what connects to what |
| [PROJECT_COMPLETE_EXPLANATION.md](PROJECT_COMPLETE_EXPLANATION.md) · [PDF](pdf/PROJECT_COMPLETE_EXPLANATION.pdf) | The long one: 84 pages covering architecture, data flow, the machine-learning results, five feature traces, 40 questions with answers, and the known bugs | You want the detail behind any single claim |
| [prompts.md](prompts.md) | The main prompts used to build the project, with what each produced | You are asked which parts were AI-assisted |

## Slides and hand-outs

[presentation/](presentation/):

| File | What it is |
|---|---|
| `phishing_twin_overview.pptx` | The overview deck |
| `project_architecture.pdf` | Architecture and workflow |
| `hospital_workforce_summary.pdf` | The dataset summary |
| `work_today.pptx`, `work_after_feedback.pptx`, `static_vs_dynamic.pptx`, `email_dataset_changes.pptx` | Progress decks from along the way |

## Superseded

[pdf/Project_Meeting_Explanation.pdf](pdf/Project_Meeting_Explanation.pdf) is an
earlier four-page explanation. It has no Markdown source and its figures are out
date: it describes `scripts/` and `tests/` as they were before two dead
scripts and one dead test were removed, and it still calls the project by its
old name. It cannot be reprinted, because there is no Markdown to reprint it
from. `PROJECT_CODE_EXPLANATION.md` replaced it and covers the same ground.
Kept only as a record; safe to delete.

## A note on the PDFs

Each PDF in `pdf/` is generated from the Markdown file of the same name in
`docs/`. If you edit the Markdown, the PDF does not update by itself — it has to
be rebuilt. So treat the `.md` file as the original and the `.pdf` as the
printable copy of it.

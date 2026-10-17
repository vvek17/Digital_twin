# Phishing Digital Twin Simulation

A research/learning project. A fictional hospital's staff receive simulated
phishing and legitimate emails. A "digital twin" model tries to predict whether
each person will click, report, or ignore an email, without ever being allowed
to see the person's hidden behaviour.

All data is fictional: fake hospital, fake names, `.example` email domain.

GitHub: https://github.com/vvek17/Digital_twin

## The idea in one line

A simulated human acts on emails from secret click-probabilities; a digital twin
learns to predict those actions purely by observation, never seeing the secrets.

## Workflow

```
                    DATA (local JSON, the ground truth)
   data/hospital_people.json       -> 25 staff; person.simulation.hidden_probs = SECRET
   data/hospital_emails_mixed.json -> emails {label, cue, subject, body}
            |                                   |
   persona.py load_people()            generator.py get_email()
            v                                   v
   +-----------------------------------------------------------------+
   |                      THE LOOP (one email)                       |
   |   twin.predict(person_id, email)  -> guess 0..1     (twin.py)   |
   |   human.respond(email, situation) -> click/report/ignore       |
   |        uses person.hidden_probs[cue]  (human.py)                |
   |        situation nudges the chance    (situation.py)            |
   |   twin.update(person_id, email, action) -> learns   (twin.py)   |
   +-----------------------------------------------------------------+
        ^                                         |
        |                                         v
   DRIVER A: app.py (Streamlit)        DRIVER B: test_*.py (terminal)
   real person clicks Yes/No           simulated human, scored vs
   -> saves data/responses.json        hidden_probs (test_twin_all.py)

   NOT WIRED (stubs): main.py -> simulation.py -> feedback.py
```

Both drivers run the same loop; the only difference is who clicks: a real person
(the app) or the simulated human (the test scripts).

## The data

The hospital is organized into 5 pillars, with 25 staff (5 per pillar):
Patient Care; Diagnostics & Treatment; Nursing & Clinical Support;
Administration & Management; Operations & Infrastructure.

Each person has realistic workforce fields (job_id, name, age, gender, job_title,
pillar, department, location, inpatient_outpatient, patient_facing, years_in_role,
years_with_organization, responsibilities, skills, reporting_structure,
collaborating_departments) plus a `simulation` block used only by the model:

- `role_group`, `security_awareness`, `workload`, `shift`
- `hidden_probs`: secret click chance per cue (urgency, authority, it_login,
  hr_payroll, billing) plus `false_report` (reporting a real email by mistake)

`hidden_probs` is for the simulated human only. The twin must never read it.

## How to run

The web app (a real person answers Yes/No, the twin learns live):

```bash
python3 -m streamlit run app.py
```

The simulated experiments:

```bash
python3 test_persona.py      # print all 25 people
python3 test_twin.py         # one person: twin guess vs real, per cue
python3 test_twin_all.py     # all 25 people: per-person accuracy
python3 test_situation.py    # how the situation changes click rates
```

## Status

Working:
- `data/hospital_people.json` (25 staff, 5 pillars, simulation blocks)
- `persona.py`, `generator.py`, `human.py`, `situation.py`, `twin.py`
- `app.py` (Streamlit UI) and the `test_*.py` scripts

Not built yet (stubs): `main.py`, `simulation.py`, `feedback.py` are placeholders
for the planned feedback experiment (does feedback reduce clicking over time?).

Stale: `make_people.py` generated the old 30-person schema; do not run it (it would
overwrite the current data).

## Files

- `persona.py` - `Persona` class and `load_people()`.
- `generator.py` - `EmailGenerator`: serves simulated emails.
- `human.py` - `SimulatedHuman`: reacts to emails (click/report/ignore).
- `situation.py` - per-email context (time of day, workload) that nudges behaviour.
- `twin.py` - `TwinPredictor`: predicts behaviour from observed actions only.
- `app.py` - Streamlit web UI; logs answers to `data/responses.json`.
- `test_*.py` - component checks and experiments.
- `feedback.py`, `simulation.py`, `main.py` - stubs for the feedback stage.
- `data/hospital_people.json` - the 25-person workforce + simulation data.
- `data/hospital_emails_mixed.json` - the email set.

## External dependencies

Streamlit and pandas (for the app), plus the Python standard library. No database,
network calls, or external APIs; all data is local JSON. `data/responses.json`
(app output) is git-ignored.

## Presentation material

- `project_architecture.pdf` - full architecture and workflow.
- `demo_walkthrough.pdf` - what to show and say during a live demo.
- `hospital_workforce_summary.pdf` - the dataset summary.
- `phishing_twin_overview.pptx` - overview slide deck.
- `prompts.md` - the main prompts used to build the project.

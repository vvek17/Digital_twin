# Phishing Digital Twin Simulation

A research/learning project. A fictional hospital's staff receive simulated
phishing and legitimate emails. A "digital twin" model tries to predict whether
each person will click, report, or ignore an email, without being allowed to
see the person's hidden behaviour.

All data is fictional: fake hospital, fake names, `.example` email domain.

## Status

Everything below has been run with `python3` and works.

| Script | What it does | Works? |
|---|---|---|
| `make_people.py` | Generates the 30 fake staff into `data/hospital_people.json` | yes |
| `test_persona.py` | Loads and prints all 30 people | yes |
| `test_twin.py` | Runs the twin and compares its guesses to reality | yes |
| `test_generator.py` | Quick check of the email generator | yes |

Not built yet: `simulation.py`, `main.py` (full run), and the feedback stage
(`feedback.py` is still an empty stub).

## What we did, step by step

### Step 1 - The hospital and its people
`make_people.py` creates a fictional hospital (Ashbrook General, 320 beds, 8
departments) and 30 fake staff: 10 nurses, 8 front desk, 6 doctors, 6
admin/billing.

Each person has visible traits (role, department, shift, years of experience,
security awareness, workload) and `hidden_probs`: secret chances of clicking
each type of phishing cue (urgency, authority, it_login, hr_payroll, billing)
plus `false_report` (reporting a real email by mistake).

The hidden chances start from a per-role baseline, then get adjusted for
awareness, workload, and a small random amount. A fixed random seed makes the
output the same every run. Result is saved to `data/hospital_people.json`.

### Step 2 - The persona loader
`persona.py` has a `Persona` class (one person's traits) and `load_people()`,
which reads all 30 people from the JSON file. `hidden_probs` is loaded here but
is meant for the simulated human only, never the twin.

### Step 3 - The simulated human
`human.py` has `SimulatedHuman`. Given an email it returns `"click"`,
`"report"`, or `"ignore"`:
- Phishing email: look up the person's hidden chance for the email's cue, roll a
  random number, and click if the roll is under that chance.
- Legitimate email: use the `false_report` chance to maybe raise a false alarm.

### Step 4 - The digital twin
`twin.py` has `TwinPredictor`. It keeps simple counters per person (clicks vs
not-clicks for each cue, and false-report vs not). `predict()` returns
`a / (a + b)`; `update()` adds to a counter after seeing what the human did;
`get_all_estimates()` returns all current guesses. The twin never reads
`hidden_probs` - it only learns from the actions it observes.

### Step 5 - Tests
- `test_persona.py` prints every person.
- `test_twin.py` sends one person 30 random emails (predict, act, update) and
  prints a table of the twin's guess vs the real hidden chance per cue.

## How to run

```bash
python3 make_people.py      # (re)generate the people file
python3 test_persona.py
python3 test_twin.py
```

## Files

- `make_people.py` - generates the fake hospital staff data.
- `persona.py` - `Persona` class and `load_people()`.
- `generator.py` - `EmailGenerator`: hands out simulated emails.
- `human.py` - `SimulatedHuman`: reacts to emails (click/report/ignore).
- `twin.py` - `TwinPredictor`: predicts behaviour from observed actions only.
- `feedback.py` - `FeedbackModule`: stub, for a later feedback experiment.
- `simulation.py` - stub, will connect everything for a full run.
- `main.py` - stub, entry point.
- `data/hospital_people.json` - generated staff data.
- `data/hospital_emails_mixed.json` - the email set.

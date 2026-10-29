# Prompts used to create this project

Every prompt that produced output, with the result.

---

## Prompt 1 - Rename a file

> change name test.py with test_generator

**Output:** renamed `test.py` to `test_generator.py`.

---

## Prompt 2 - Create the fake hospital staff

> In my phishing_twin project, create fake hospital staff for a phishing simulation.
> Do NOT add feedback groups yet.
>
> 1. Create a script make_people.py that generates data/hospital_people.json with:
>
>    Hospital (fictional):
>    - name: "Ashbrook General Hospital"
>    - email_domain: "ashbrookgeneral.example"
>    - beds: 320
>    - departments: Emergency, Ward 4 (Medical), Surgery, Pediatrics, Radiology,
>      Main Reception, Outpatient Clinic, Finance & Billing
>
>    30 fake people: 10 nurses, 8 front_desk, 6 doctors, 6 admin_billing.
>    Each person has:
>    - id (P01 to P30), fictional name, role, department, shift, years_experience (1-25)
>    - security_awareness: low, medium, or high
>    - workload: normal, busy, or very busy
>    - hidden_probs: secret click chances for these cues:
>      urgency, authority, it_login, hr_payroll, billing
>      plus false_report (chance of reporting a real email by mistake)
>
>    Starting click chances per role:
>    - nurse:         urgency 0.60, authority 0.50, it_login 0.40, hr_payroll 0.70, billing 0.10, false_report 0.15
>    - doctor:        urgency 0.50, authority 0.40, it_login 0.40, hr_payroll 0.30, billing 0.05, false_report 0.10
>    - front_desk:    urgency 0.50, authority 0.50, it_login 0.60, hr_payroll 0.50, billing 0.40, false_report 0.20
>    - admin_billing: urgency 0.40, authority 0.60, it_login 0.40, hr_payroll 0.40, billing 0.60, false_report 0.10
>
>    Adjust each person's click chances based on traits:
>    - awareness: low +0.10, medium 0, high -0.15
>    - workload: normal -0.05, busy 0, very busy +0.08
>    - then add a small random change between -0.10 and +0.10
>    - false_report: low awareness -0.05, high awareness +0.05, plus random -0.05 to +0.05
>    - keep all values between 0.02 and 0.95
>    Use a fixed random seed so results are repeatable.
>
> 2. Fill in persona.py with a Persona class and a function that loads all people
>    from data/hospital_people.json. Add a comment that hidden_probs must only be used
>    by the simulated human, never by the twin predictor.
>
> 3. Create test_persona.py that loads the people and prints each person's
>    name, role, awareness, workload, and hidden_probs.
>
> 4. Run make_people.py, then run test_persona.py with python3, and show me the output.
>
> Keep the code simple and well-commented. I'm a beginner.

**Output:** created `make_people.py`, filled in `persona.py`, created `test_persona.py`.
Running `make_people.py` wrote 30 people to `data/hospital_people.json`.
Running `test_persona.py` printed all 30. First two entries:

```
Loaded 30 people

P01 - Theo Cohen
  role:       nurse
  awareness:  high
  workload:   normal
  hidden_probs: {'urgency': 0.309, 'authority': 0.246, 'it_login': 0.158, 'hr_payroll': 0.416, 'billing': 0.02, 'false_report': 0.16}

P02 - Mia Moreno
  role:       nurse
  awareness:  medium
  workload:   normal
  hidden_probs: {'urgency': 0.524, 'authority': 0.392, 'it_login': 0.303, 'hr_payroll': 0.737, 'billing': 0.08, 'false_report': 0.161}
```

---

## Prompt 3 - Build the simulated human

Built interactively in `human.py`. Given an email, `SimulatedHuman.respond()`
returns `"click"`, `"report"`, or `"ignore"`: phishing uses the person's hidden
chance for the email's cue; a legitimate email uses the `false_report` chance.

**Output (example test):** person P05 with urgency chance 0.628, 10 responses to
a phishing urgency email:

```
['click', 'ignore', 'click', 'ignore', 'click', 'click', 'click', 'ignore', 'click', 'ignore']
```

6 clicks out of 10, close to the 0.63 chance.

---

## Prompt 4 - Create the digital twin

> In my phishing_twin project, fill in twin.py with a TwinPredictor class.
> Keep it simple and well-commented. I'm a beginner.
>
> How it works:
> - The twin keeps separate counters for each person (by person id).
> - For each phishing cue (urgency, authority, it_login, hr_payroll, billing):
>   a = number of clicks, b = number of reports. Both start at 1.
> - For legitimate emails, keep a separate pair of counters for "false_report":
>   a = reported a real email by mistake, b = did not report it. Both start at 1.
>
> Methods:
> - predict(person_id, email): returns the chance as a / (a + b)
>   - if the email is phishing, use the counters for that email's cue
>   - if the email is legitimate, use the false_report counters
> - update(person_id, email, action): after the human acts, add 1 to a or b
> - get_all_estimates(person_id): returns all current guesses for that person
>
> IMPORTANT: The twin must NEVER read hidden_probs. It only learns from the
> actions it sees through update().
>
> Then create test_twin.py that:
> 1. Loads the people (persona.py) and the emails (generator.py)
> 2. Picks one person
> 3. Sends them 30 random emails using human.py
> 4. Each time: twin predicts -> human acts -> twin updates
> 5. At the end, prints a table comparing the twin's guess vs the person's
>    real hidden_probs for each cue, so I can see how close the twin got
>
> Run test_twin.py with python3 and show me the output.
> Don't change persona.py, generator.py, or human.py.

**Output:** created `twin.py` and `test_twin.py`. Running `test_twin.py`:

```
Person: Mason Ivanov (P05)
Role: nurse | awareness: low | workload: busy
Sending 30 random emails...

cue            twin guess   real (hidden)  difference
----------------------------------------------------
urgency        0.50         0.63           0.13
authority      0.40         0.65           0.25
it_login       0.62         0.51           0.12
hr_payroll     0.80         0.85           0.05
billing        0.60         0.19           0.41
false_report   0.27         0.11           0.16
```

---

## Prompt 5 - Add a situational layer

> i want to upgrade like situational

**Output:** created `situation.py` (a per-email "moment": time of day + how busy
the person is now) and upgraded `human.py` so the click chance is nudged by the
situation (night is tiring, an email during your own shift feels expected, being
very busy makes you careless, a billing email to the Finance team looks like
normal work). Created `test_situation.py`. Running it:

```
Person: Mason Ivanov (P05) | shift: night | department: Pediatrics
Email cue: it_login | base hidden chance: 0.51

situation                    click rate
------------------------------------------
(no situation / baseline)    50%
calm (day, normal)           45%
chaotic (night, very busy)   77%
```

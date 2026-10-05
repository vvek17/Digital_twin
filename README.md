# Phishing Digital Twin Simulation

A research project where a twin predictor model guesses whether a simulated human
will click or report a phishing email, comparing different types of feedback.

## Files

- `persona.py` – `Persona` class: traits describing a simulated person.
- `generator.py` – `EmailGenerator` class: creates simulated phishing emails.
- `human.py` – `SimulatedHuman` class: reacts to emails (click, report, ignore).
- `twin.py` – `TwinPredictor` class: predicts how the simulated human will react.
- `feedback.py` – `FeedbackModule` class: gives different types of feedback to the human.
- `simulation.py` – `Simulation` class: connects everything and runs the experiment.
- `main.py` – entry point; run with `python main.py`.

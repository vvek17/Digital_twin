"""Escaped presentation of existing email fields and educational feedback."""

from html import escape

from backend.feedback import CUE_NAMES


def _text(value):
    return escape("" if value is None else str(value))


def email_markup(email):
    """Keep the original plain-text message intact, including all whitespace.

    Dataset text never becomes executable email HTML or remote content. Known
    link metadata is inspectable without navigating away from the exercise.
    """
    sender = email.get("sender_name") or "Unknown sender"
    initials = "".join(word[0] for word in str(sender).split()[:2]).upper()
    reply = ("<div class='alert-mail-detail'><span>Reply-To</span><span>%s</span></div>"
             % _text(email["reply_to"])) if email.get("reply_to") else ""
    link = ""
    if email.get("link_target"):
        link = ("<details class='alert-mail-inspection'><summary>Inspect link destination</summary>"
                "<dl><dt>Link text</dt><dd>%s</dd><dt>Destination</dt><dd>%s</dd></dl></details>"
                % (_text(email.get("link_text") or "No link text supplied"), _text(email["link_target"])))
    return (
        "<article class='alert-mail' aria-label='Email message'>"
        "<h3 class='alert-mail-subject'>%s</h3>"
        "<header class='alert-mail-sender'><span class='alert-mail-avatar' aria-hidden='true'>%s</span>"
        "<div><div class='alert-mail-from'>From</div><div class='alert-mail-name'>%s</div></div></header>"
        "<div class='alert-mail-address'>%s</div>"
        "%s<div class='alert-mail-body' role='document' tabindex='0' aria-label='Message body'>%s</div>"
        "%s</article>"
        % (_text(email.get("subject") or "(No subject)"), _text(initials), _text(sender),
           _text(email.get("sender_email")), reply, _text(email.get("body", "")), link))


def feedback_markup(feedback, record=None, email=None):
    """Display the saved verdict and source evidence, without classifying email."""
    feedback = feedback or {}
    email = email or {}
    outcome = feedback.get("outcome")
    correct = record.get("correct") if record is not None else (
        True if outcome in ("caught", "fine") else False if outcome in ("missed", "false alarm") else None)
    status, tone, symbol = (("Correct answer", "correct", "✓") if correct is True else
                            ("Incorrect answer", "incorrect", "!") if correct is False else
                            ("Answer recorded", "neutral", "✓"))
    label = feedback.get("was") or email.get("label")
    classification = {"phishing": "Phishing email", "legitimate": "Genuine email (not spam)"}.get(
        label, "Classification not supplied")
    facts = "<div><dt>This email was</dt><dd>%s</dd></div>" % _text(classification)
    if record is not None:
        said = {"spam": "Spam", "not spam": "Not spam"}.get(record.get("said"), record.get("said", ""))
        facts = "<div><dt>Your answer</dt><dd>%s</dd></div>" % _text(said) + facts
    tells = feedback.get("tells") or []
    if isinstance(tells, str):
        tells = [tells]
    evidence = ("<ul>%s</ul>" % "".join("<li>%s</li>" % _text(tell) for tell in tells)) if tells else (
        "<p class='alert-feedback-muted'>No additional evidence was supplied for this example.</p>")
    context = []
    if feedback.get("technique"):
        context.append("<div><dt>Attack type</dt><dd>%s</dd></div>" % _text(feedback["technique"]))
    if feedback.get("cue") and label == "phishing":
        cue = feedback["cue"]
        context.append("<div><dt>Pattern</dt><dd>%s</dd></div>" % _text(CUE_NAMES.get(cue, cue)))
    details = "<dl class='alert-feedback-facts'>%s</dl>" % "".join(context) if context else ""
    inspection = ""
    if feedback.get("hidden_link"):
        text, target = feedback["hidden_link"]
        inspection += ("<dt>Displayed link text</dt><dd>%s</dd><dt>Actual destination</dt><dd>%s</dd>"
                       % (_text(text or "No link text supplied"), _text(target)))
    if feedback.get("reply_to"):
        inspection += "<dt>Reply-To address</dt><dd>%s</dd>" % _text(feedback["reply_to"])
    if inspection:
        details += ("<details class='alert-feedback-inspection'><summary>Inspect message details</summary>"
                    "<dl>%s</dl></details>" % inspection)
    takeaway = feedback.get("defense") or email.get("key_defense")
    learning = ("<section class='alert-feedback-section alert-feedback-takeaway'><h4>Learning takeaway</h4>"
                "<p>%s</p></section>" % _text(takeaway)) if takeaway else ""
    history = ("<section class='alert-feedback-section'><h4>Your pattern so far</h4><p>%s</p></section>"
               % _text(feedback["history_note"])) if feedback.get("history_note") else ""
    return (
        "<div class='alert-feedback'><div class='alert-feedback-status alert-feedback-status--%s' "
        "role='status' aria-live='polite'><span class='alert-feedback-symbol' aria-hidden='true'>%s</span>"
        "<strong>%s</strong></div><dl class='alert-feedback-facts'>%s</dl>"
        "<p class='alert-feedback-explanation'>%s</p>"
        "<section class='alert-feedback-section'><h4>Key evidence</h4>%s%s</section>%s%s</div>"
        % (tone, symbol, status, facts, _text(feedback.get("headline", "Your answer has been saved.")),
           evidence, details, learning, history))

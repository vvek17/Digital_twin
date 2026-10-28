# make_emails.py
# Builds data/hospital_emails_mixed.json.
#
# The whole email set is derived from HIM 1055 Weeks 7 & 8, "Comparison of
# Attacks and Threats" (the CIA triad plus the 20-row social-engineering
# table). Every phishing email names the technique it demonstrates and carries
# that row's category, week, CIA hit and key defense, copied from the table.
# Several are built directly on the table's own "Example from class" column.
#
# Everything is fictional: fake hospital, fake staff, .example domains that
# cannot resolve. These are teaching artifacts, not working lures - each one
# ships with the red flags or safe signs needed to explain it afterwards.
#
# The simulation reads only: label, cue, target_role. The cue must stay one of
# the five keys in person.simulation.hidden_probs (urgency, authority,
# it_login, hr_payroll, billing), or "none" for legitimate mail.

import json
from collections import Counter

HOSPITAL = "Ashbrook General Hospital"
REAL_DOMAIN = "ashbrookgeneral.example"
SOURCE = ("HIM 1055 - IT Applications for Health, Weeks 7 & 8: "
          "Comparison of Attacks and Threats")

# ---------------------------------------------------------------------------
# The table, row by row. Only the rows that can arrive in an inbox are here;
# tailgating (15) is physical and vishing (16) is a phone call, so neither has
# an email form. Row numbers match the PDF.
# ---------------------------------------------------------------------------

TAXONOMY = {
    "Malware": {
        "row": 1, "week": 7,
        "category": "Technical (malicious software)",
        "cia_hit": "C, I, A",
        "key_defense": "Spam filters, software updates, don't open unexpected attachments",
    },
    "Ransomware": {
        "row": 2, "week": 7,
        "category": "Technical (malware type)",
        "cia_hit": "A",
        "key_defense": "Patching, MFA, training, reporting quickly",
    },
    "Third-party / supply chain": {
        "row": 9, "week": 7,
        "category": "Organizational risk",
        "cia_hit": "C + A",
        "key_defense": "Vendor oversight, MFA, defense in depth",
    },
    "Phishing": {
        "row": 10, "week": 7,
        "category": "Social engineering (email/web)",
        "cia_hit": "C",
        "key_defense": "Hover before clicking, spam filters, MFA, simulated phishing tests",
    },
    "Spear phishing": {
        "row": 11, "week": 7,
        "category": "Social engineering (targeted)",
        "cia_hit": "C",
        "key_defense": "Training, verify through a second channel",
    },
    "Whaling": {
        "row": 12, "week": 7,
        "category": "Social engineering (executives)",
        "cia_hit": "C",
        "key_defense": "Verify unusual requests, especially urgent ones",
    },
    "Pretexting": {
        "row": 13, "week": 7,
        "category": "Social engineering (false story)",
        "cia_hit": "C",
        "key_defense": "Never verify identity on an incoming request, report it",
    },
    "Baiting": {
        "row": 14, "week": 7,
        "category": "Social engineering (temptation)",
        "cia_hit": "I + C",
        "key_defense": "Never plug in unknown devices, don't open tempting unexpected files",
    },
    "Smishing": {
        "row": 17, "week": 7,
        "category": "Social engineering (text message)",
        "cia_hit": "C",
        "key_defense": "Don't click, report it",
    },
    "Quid pro quo": {
        "row": 18, "week": 8,
        "category": "Social engineering (trade)",
        "cia_hit": "C",
        "key_defense": "Training. A real IT team never trades for your password.",
    },
    "Extortion / blackmail": {
        "row": 20, "week": 8,
        "category": "Social engineering (threat)",
        "cia_hit": "C",
        "key_defense": "Don't pay, don't panic; report it and get help",
    },
    "Legitimate": {
        "row": None, "week": None,
        "category": "Not an attack",
        "cia_hit": "None",
        "key_defense": "If a message feels off, verify on the Staff Portal or call the listed extension",
    },
}


# ---------------------------------------------------------------------------
# How the SENDER ADDRESS itself lies. This is a second axis, independent of the
# social-engineering technique: a whaling email and a mailbox-full email can
# both arrive from a typosquatted domain.
#
# Every address stays inside space that can never resolve. RFC 2606 reserves
# the .example TLD outright, plus example.com / example.net / example.org.
# Endings like .example.info or .example.co are NOT reserved - somebody could
# register them - so they are never used here.
# ---------------------------------------------------------------------------

ADDRESS_TRICKS = {
    "forged_from": (
        "The From line shows the hospital's own address. A From line can be "
        "forged, so it proves nothing on its own - check Reply-To and the link."
    ),
    "lookalike": (
        "Extra words bolted onto the real name: ashbrook-support.example. "
        "Reads right at a glance, owned by someone else."
    ),
    "typosquat": (
        "A character swapped for one that looks identical: an 'i' for an 'l', "
        "or a zero for an 'o'."
    ),
    "subdomain_misdirection": (
        "The hospital name sits at the FRONT as a subdomain, but the real owner "
        "is the LAST domain before the ending. Read a domain right to left."
    ),
    "extra_ending": (
        "The genuine name with a further ending bolted on, so the real "
        "registered domain is not the one you recognise."
    ),
    "display_name_fraud": (
        "The display name is a department you trust; the address behind it is "
        "a machine-generated mailbox somewhere else."
    ),
    "free_provider": (
        "A corporate role sent from a consumer mail provider. Payroll and "
        "managers never write from a personal mail service."
    ),
    "unrelated": (
        "Makes no attempt to look like the hospital - it imitates a supplier, "
        "insurer or authority instead."
    ),
}

# Which address trick each phishing email uses.
ADDRESS_TRICK_BY_ID = {
     1: "forged_from",             2: "typosquat",
     3: "lookalike",               4: "lookalike",
     5: "unrelated",               6: "typosquat",
     7: "forged_from",             8: "free_provider",
     9: "unrelated",              10: "display_name_fraud",
    11: "lookalike",              12: "forged_from",
    13: "subdomain_misdirection", 14: "extra_ending",
    15: "unrelated",              16: "forged_from",
    17: "lookalike",              18: "lookalike",
    19: "free_provider",          20: "subdomain_misdirection",
    21: "lookalike",              22: "unrelated",
    23: "forged_from",            24: "extra_ending",
    25: "lookalike",              51: "forged_from",
}


def body(text):
    """Trim the newlines that come from triple-quoted strings."""
    return text.strip("\n")


# ---------------------------------------------------------------------------
# 1-25 phishing, five per cue so the twin sees each cue equally often.
# 26-50 legitimate. Several legitimate ones are deliberate near-twins of a
# phishing email, so the difference is the lesson rather than the vocabulary.
# ---------------------------------------------------------------------------

EMAILS = [

    # ================= cue: it_login =================

    {
        "id": 1, "label": "phishing", "cue": "it_login",
        "technique": "Phishing", "target_role": "all", "difficulty": "hard",
        "teaches": ("The table's example, 'Your password expires today', but sent from the "
                    "hospital's own address - checking the domain does not save you."),
        "sender_name": "IT Helpdesk",
        "sender_email": "it-helpdesk@ashbrookgeneral.example",
        "reply_to": "helpdesk.support@mail-ashbrook-it.example",
        "link_text": "Renew your password",
        "link_target": "https://ashbrook-support.example/renew",
        "subject": "Your password expires today",
        "body": body("""
Your network password expires today. Staff who do not renew before midnight will
lose access to email and clinical systems until a helpdesk ticket is raised.

Renew your password

This is an automatically generated email, please do not reply.

IT Helpdesk
"""),
        "red_flags": [
            "the From line shows the real hospital domain - a From line can be forged, so it proves nothing",
            "Reply-To goes somewhere else entirely: mail-ashbrook-it.example",
            "hover before clicking: the link reads 'Renew your password' but points to ashbrook-support.example",
            "'do not reply' removes the easiest way to check",
            "IT never renews passwords through an emailed link - compare with E27",
        ],
    },
    {
        "id": 2, "label": "phishing", "cue": "it_login",
        "technique": "Phishing", "target_role": "front_billing", "difficulty": "easy",
        "teaches": "Typosquatting with digits: ashbr00kgeneral uses two zeros in place of the o's.",
        "sender_name": "Mail Administrator",
        "sender_email": "mailbox-admin@ashbr00kgeneral.example",
        "subject": "Your mailbox is full",
        "body": body("""
Your mailbox has reached 99% of its storage limit. New incoming messages are
being held and will be deleted after 24 hours.

Increase storage: https://secure-mail-ashbrook.example/storage

Mail Administrator
"""),
        "red_flags": [
            "typosquatted domain: ashbr00kgeneral.example, with zeros in place of the o's",
            "at a glance it reads as the real domain - that is the entire point",
            "no name, no extension, no department",
            "threatens that mail will be deleted",
            "mailbox size is managed by IT, not by a link in an email",
        ],
    },
    {
        "id": 3, "label": "phishing", "cue": "it_login",
        "technique": "Quid pro quo", "target_role": "all", "difficulty": "hard",
        "teaches": "The trade: a free benefit offered in exchange for your login.",
        "sender_name": "Ashbrook IT Modernisation",
        "sender_email": "upgrades@ashbrook-it-rollout.example",
        "subject": "Free premium licence for staff - 200 seats available",
        "body": body("""
As part of the IT modernisation programme we have 200 free premium office
licences for staff, including installation on your own computer at home.

To claim a seat, sign in with your Ashbrook network account so we can confirm
you are staff and attach the licence to you:

https://ashbrook-it-rollout.example/claim

Seats are allocated in the order claims are received.

Ashbrook IT Modernisation Team
"""),
        "red_flags": [
            "offers you something valuable in exchange for your login",
            "lookalike domain: ashbrook-it-rollout.example",
            "scarcity: 200 seats, first come first served",
            "a real IT team never trades a benefit for your password",
        ],
    },
    {
        "id": 4, "label": "phishing", "cue": "it_login",
        "technique": "Spear phishing", "target_role": "nurse", "difficulty": "hard",
        "teaches": "Targeted: it uses real details - the person's unit and their actual director.",
        "sender_name": "Clinical Systems Team",
        "sender_email": "clinicalsystems@ashbrookgeneral-it.example",
        "subject": "Ward 4 access re-verification before Saturday",
        "body": body("""
Hello,

The patient records system is being upgraded this weekend. Nursing staff on
Carol Mendes's Ward 4 list need to re-verify access before Saturday 6 AM.
Accounts that are not verified will be locked for charting until IT reactivates
them by hand, which can take most of a shift.

Verify access: https://ashbrookgeneral-it.example/verify

Clinical Systems Team
"""),
        "red_flags": [
            "lookalike domain: ashbrookgeneral-it.example",
            "uses real details - your ward and Nursing Director Carol Mendes - to sound informed",
            "fear of being unable to chart",
            "verify through a second channel: call the Service Desk on a number you already know",
        ],
    },
    {
        "id": 5, "label": "phishing", "cue": "it_login",
        "technique": "Third-party / supply chain", "target_role": "all", "difficulty": "hard",
        "teaches": "Riding a vendor breach, the way attackers followed the Change Healthcare disruption.",
        "sender_name": "Claims Portal Security",
        "sender_email": "security@claims-portal-reset.example",
        "subject": "Mandatory password reset after our security incident",
        "body": body("""
As your hospital has been informed, our claims processing platform experienced a
security incident. As a precaution, all hospital user accounts must be reset
before access is restored.

Reset your account: https://claims-portal-reset.example/restore

Accounts not reset within 72 hours will be suspended pending manual review.

Claims Portal Security Team
"""),
        "red_flags": [
            "attackers follow the news - a real breach makes a fake reset believable",
            "domain exists only to host the reset: claims-portal-reset.example",
            "a vendor should never reset your account by emailing staff directly",
            "check with IT Security first; see E45, the real advisory about this breach",
        ],
    },

    # ================= cue: authority =================

    {
        "id": 6, "label": "phishing", "cue": "authority",
        "technique": "Whaling", "target_role": "administration", "difficulty": "hard",
        "teaches": "The table's Main Line Health case: a fake executive requests the staff W-2 file.",
        "sender_name": "Richard Vance, Hospital Administrator",
        "sender_email": "r.vance@ashbrookgenerai.example",
        "subject": "Staff W-2 summary needed for the board pack",
        "body": body("""
Sandra,

The board pack goes out tonight and I need the staff W-2 summary for last year -
names, earnings and tax identifiers - in one file.

Send it straight to me rather than through the usual channel; I'd rather this
didn't circulate before the compensation review is announced.

I'm in meetings until six and can't take calls.

Richard Vance
Hospital Administrator
"""),
        "red_flags": [
            "misspelled domain: ashbrookgenerai.example (an 'i' in place of the 'l')",
            "the whole workforce's tax data in one request",
            "asks you to bypass the usual channel and keep it quiet",
            "claims to be unreachable, so you can't verify",
            "this exact attack sent 11,000 employees' W-2s to an attacker",
        ],
    },
    {
        "id": 7, "label": "phishing", "cue": "authority",
        "technique": "Whaling", "target_role": "physician", "difficulty": "hard",
        "teaches": ("Going after the people with the most access, from an address that "
                    "looks exactly like the one the real notice comes from."),
        "sender_name": "Office of the Chief Medical Officer",
        "sender_email": "cmo.office@ashbrookgeneral.example",
        "reply_to": "cmo.office@ashbrookgeneral-medstaff.example",
        "link_text": "Attest here",
        "link_target": "https://ashbrookgeneral-medstaff.example/attestation",
        "subject": "Mandatory compliance attestation - due Friday",
        "body": body("""
Doctor,

Ahead of next month's accreditation review, all medical staff must complete the
annual compliance attestation by Friday. Incomplete attestations are escalated
to the Chief Medical Officer and recorded in your credentialing file.

Attest here

Office of the Chief Medical Officer
"""),
        "red_flags": [
            "the From line is the genuine hospital domain, so the usual domain check passes",
            "Reply-To and the link both go to ashbrookgeneral-medstaff.example",
            "hover before clicking: 'Attest here' does not go where the From line suggests",
            "an invented accreditation deadline to justify the rush",
            "threatens your credentialing file",
            "verify unusual or urgent requests - E42 is the genuine notice, with a six-week window",
        ],
    },
    {
        "id": 8, "label": "phishing", "cue": "authority",
        "technique": "Spear phishing", "target_role": "nurse", "difficulty": "easy",
        "teaches": "The table's example: an email that names your actual manager and a real meeting.",
        "sender_name": "Carol Mendes",
        "sender_email": "c.mendes.nursing@outlook-mail.example",
        "subject": "The staffing return from Thursday's meeting",
        "body": body("""
Hi,

Following Thursday's ward meeting - I still need the Ward 4 staffing return
before you go off shift. It was due yesterday and it's holding up next month's
rota.

Form here: https://outlook-mail.example/ashbrook/staffing

Thanks,
Carol Mendes
Nursing Director
"""),
        "red_flags": [
            "your Nursing Director's real name, sent from a personal outside address",
            "references a real meeting to prove they know you",
            "pressure to finish before the end of the shift",
            "verify through a second channel - walk to her office or call her known extension",
        ],
    },
    {
        "id": 9, "label": "phishing", "cue": "authority",
        "technique": "Pretexting", "target_role": "all", "difficulty": "hard",
        "teaches": "An invented but believable scenario, posing as someone with authority.",
        "sender_name": "Accreditation Survey Team",
        "sender_email": "survey.team@healthcare-accreditation-review.example",
        "subject": "Pre-survey staff verification - response required today",
        "body": body("""
As part of this week's unannounced accreditation survey, we are verifying that
staff records match the credentials held by the hospital.

Please confirm your full name, date of birth, employee number and the systems
you have access to, using the secure form:

https://healthcare-accreditation-review.example/verify

Surveyors will follow up in person with staff who do not respond today.

Accreditation Survey Team
"""),
        "red_flags": [
            "a believable story that explains why a stranger is asking personal questions",
            "outside domain with an official-sounding name",
            "asks what systems you can access - that is reconnaissance",
            "never verify your identity on an incoming request; report it instead",
        ],
    },
    {
        "id": 10, "label": "phishing", "cue": "authority",
        "technique": "Phishing", "target_role": "front_billing", "difficulty": "easy",
        "teaches": ("Display-name fraud: the name reads 'Front Office Manager', but the "
                    "address behind it is a machine-generated mailbox."),
        "sender_name": "Front Office Manager",
        "sender_email": "user7392@mail-relay-svc.example",
        "subject": "New check-in procedure - acknowledge today",
        "body": body("""
All reception staff must read and acknowledge the new patient check-in procedure
today. Acknowledgements are tracked and reported to department managers.

Read and acknowledge: https://ashbrook-staff.example/procedures/checkin

Front Office Manager
"""),
        "red_flags": [
            "the display name says Front Office Manager; the address is user7392@mail-relay-svc.example",
            "expand the sender before trusting it - the name shown is not the address",
            "a title with no name behind it",
            "implies you are being monitored, to push a fast click",
            "compare with E44, where the real procedure change comes from a named colleague",
        ],
    },

    # ================= cue: urgency =================

    {
        "id": 11, "label": "phishing", "cue": "urgency",
        "technique": "Malware", "target_role": "nurse", "difficulty": "hard",
        "teaches": "The table's example file: Patient_Records_Update.exe, which spreads across the network.",
        "sender_name": "Patient Records Update",
        "sender_email": "records-update@ashbrook-records.example",
        "subject": "Updated patient transfer list - open before handover",
        "body": body("""
The transfer list for this evening's handover has been revised. Four patients
have changed beds since the morning list was printed.

Attached: Patient_Records_Update.exe (2.1 MB)

Run the attached updater on a hospital workstation to refresh your local copy
before handover.

Patient Records Update Service
"""),
        "red_flags": [
            "an .exe attachment is a program, not a document",
            "lookalike domain: ashbrook-records.example",
            "asks you to RUN something - that is how malware reaches other machines",
            "timed for handover, when everyone is rushed",
            "patient lists are never sent as programs to run",
        ],
    },
    {
        "id": 12, "label": "phishing", "cue": "urgency",
        "technique": "Phishing", "target_role": "nurse", "difficulty": "easy",
        "teaches": "Manufactured clinical urgency with a countdown, from the lab's own address.",
        "sender_name": "Laboratory Results",
        "sender_email": "labresults@ashbrookgeneral.example",
        "reply_to": "no-reply@ashbrook-labs-notify.example",
        "link_text": "View result",
        "link_target": "https://ashbrook-labs-notify.example/critical",
        "subject": "URGENT: Critical lab result needs review within 30 minutes",
        "body": body("""
A critical result for a patient on your unit requires review and acknowledgement
within 30 minutes. Unacknowledged critical results are escalated to the
consultant on call.

View result

This is an automatically generated email, please do not reply.

Laboratory Results
"""),
        "red_flags": [
            "the From line is the real lab address, so it passes a quick glance",
            "Reply-To and the link both lead to ashbrook-labs-notify.example",
            "no patient name, no unit, no result reference - a real result identifies the patient",
            "a 30-minute clock plus an escalation threat",
            "critical results are phoned to the ward - Victor Lindqvist's lab team calls, they do not email a link",
        ],
    },
    {
        "id": 13, "label": "phishing", "cue": "urgency",
        "technique": "Phishing", "target_role": "front_billing", "difficulty": "easy",
        "teaches": ("Subdomain misdirection: the hospital's name is only a subdomain. "
                    "The real owner is scheduling-alerts.example, read right to left."),
        "sender_name": "Scheduling Alerts",
        "sender_email": "alerts@ashbrookgeneral.example.scheduling-alerts.example",
        "subject": "Appointment system going offline in 1 hour - action required",
        "body": body("""
The outpatient appointment system goes offline in one hour for emergency
maintenance. Staff must export today's remaining appointments now, or the list
will not be available when the system returns.

Export your list: https://ashbrook-scheduling.example/export

Scheduling Alerts
"""),
        "red_flags": [
            "subdomain misdirection: ashbrookgeneral.example is only a label in front",
            "the domain that actually owns this is scheduling-alerts.example - read right to left",
            "one hour's notice, so you don't stop to check",
            "invents a consequence to force the click",
            "real outages come from the Service Desk with a change reference - see E38",
        ],
    },
    {
        "id": 14, "label": "phishing", "cue": "urgency",
        "technique": "Pretexting", "target_role": "nurse", "difficulty": "hard",
        "teaches": "A false story built from real clinical practice, so hesitating feels unsafe.",
        "sender_name": "Pharmacy Services",
        "sender_email": "pharmacy@ashbrookgeneral.example.net",
        "subject": "Medication recall affecting your unit",
        "body": body("""
Dear Nursing Staff,

A manufacturer has issued an urgent recall for a batch of IV medication stocked
on several units, including yours. Check the affected lot numbers against your
unit stock before the next medication round and confirm the check.

Affected lots: https://ashbrookgeneral.example.net/pharmacy/recall

Pharmacy Services
"""),
        "red_flags": [
            "domain has an extra ending: ashbrookgeneral.example.net",
            "patient-safety framing makes checking first feel irresponsible",
            "a recall would arrive with a phone call to the ward",
            "Dr. Aisha Rahman's pharmacy team can confirm in one call",
        ],
    },
    {
        "id": 15, "label": "phishing", "cue": "urgency",
        "technique": "Extortion / blackmail", "target_role": "all", "difficulty": "easy",
        "teaches": "A threat with a countdown - the goal is panic, not accuracy.",
        "sender_name": "System Notice",
        "sender_email": "notice@secure-review-portal.example",
        "subject": "We have a copy of your activity log",
        "body": body("""
We have obtained a copy of your workstation activity and browsing history from
this hospital's network, along with files from your user folder.

Unless you respond within 48 hours, this material will be sent to your manager
and to the hospital's HR department.

To stop this, open the review portal and follow the instructions:
https://secure-review-portal.example/case

This is your only notice.
"""),
        "red_flags": [
            "a threat with a countdown, designed to cause panic",
            "no name, no department, no reference anyone can look up",
            "a vague claim that would fit literally any employee",
            "don't pay, don't panic - report it and get help",
        ],
    },

    # ================= cue: hr_payroll =================

    {
        "id": 16, "label": "phishing", "cue": "hr_payroll",
        "technique": "Phishing", "target_role": "all", "difficulty": "hard",
        "teaches": ("Sent from payroll@ashbrookgeneral.example - the exact address the real "
                    "payslip notice E26 comes from. Only the content gives it away."),
        "sender_name": "Payroll Services",
        "sender_email": "payroll@ashbrookgeneral.example",
        "reply_to": "payroll.services@ashbrookgeneral-hr.example",
        "link_text": "Confirm details",
        "link_target": "https://ashbrookgeneral-hr.example/payroll/confirm",
        "subject": "Problem with this month's salary payment",
        "body": body("""
A problem was found with this month's salary run and your payment has been held.
Affected staff must confirm their bank details so payment can be released in
this month's cycle.

Confirm details

This is an automatically generated email, please do not reply.

Payroll Services
"""),
        "red_flags": [
            "identical From address to the genuine E26 - the From line is not evidence",
            "Reply-To breaks the illusion: ashbrookgeneral-hr.example",
            "hover before clicking: 'Confirm details' leaves the hospital entirely",
            "asks for bank details, which E26 states payroll will never do by email",
            "nothing is more clickable than a problem with your pay",
            "call Sandra Kim's HR team on extension 4120 instead",
        ],
    },
    {
        "id": 17, "label": "phishing", "cue": "hr_payroll",
        "technique": "Smishing", "target_role": "all", "difficulty": "easy",
        "teaches": "The table's example: 'Your direct deposit failed, click here', pushed to SMS.",
        "sender_name": "Payroll Notifications",
        "sender_email": "no-reply@ashbrook-payroll-alerts.example",
        "subject": "Direct deposit failed - confirm by text or link",
        "body": body("""
Your direct deposit for this period could not be processed and was returned by
the bank.

We have also sent this notice to your mobile. Reply YES to that text message, or
confirm your account here:

https://ashbrook-payroll-alerts.example/deposit

Unconfirmed accounts are removed from the next payment run.

Payroll Notifications
"""),
        "red_flags": [
            "lookalike domain: ashbrook-payroll-alerts.example",
            "moves you to SMS, where links are even harder to inspect",
            "replying confirms your number is live and worth attacking again",
            "threatens removal from the next payment run",
            "don't click, don't reply - report it",
        ],
    },
    {
        "id": 18, "label": "phishing", "cue": "hr_payroll",
        "technique": "Baiting", "target_role": "all", "difficulty": "hard",
        "teaches": "The table's 'Salary Info 2026' bait, as a file instead of a USB stick.",
        "sender_name": "Compensation Review",
        "sender_email": "comp-review@ashbrook-reward.example",
        "subject": "Salary bands 2026 - all staff (confidential)",
        "body": body("""
The 2026 salary bands are attached, covering every grade in the hospital.

Attached: Salary_Info_2026.xlsm

This was circulated to managers in error before the announcement. Please do not
forward it.

Compensation Review
"""),
        "red_flags": [
            "temptation with nothing asked for up front - exactly how baiting works",
            "an .xlsm file runs macros; that is the payload",
            "'sent in error, don't forward' makes you want to open it now",
            "lookalike domain: ashbrook-reward.example",
        ],
    },
    {
        "id": 19, "label": "phishing", "cue": "hr_payroll",
        "technique": "Baiting", "target_role": "front_billing", "difficulty": "easy",
        "teaches": ("A payroll message from a consumer mail provider - HR never writes "
                    "from a personal mail service."),
        "sender_name": "HR Benefits",
        "sender_email": "hr.benefits.dept@mailbox-provider.example",
        "subject": "Overtime bonus approved!",
        "body": body("""
Good news - a discretionary overtime bonus has been approved for your department
for the last quarter.

Your individual amount is shown here: https://ashbrook-benefits.example/bonus

Payments will be made with the next salary run.

HR Benefits
"""),
        "red_flags": [
            "a consumer mail provider, not the hospital: hr.benefits.dept@mailbox-provider.example",
            "a long official-sounding local part does not make an address internal",
            "something tempting, with nothing asked for up front",
            "a bonus nobody mentioned and no manager announced",
            "real bonuses appear on your payslip, not behind a link",
        ],
    },
    {
        "id": 20, "label": "phishing", "cue": "hr_payroll",
        "technique": "Spear phishing", "target_role": "physician", "difficulty": "hard",
        "teaches": ("Targeted detail - right departments, right quarter, a real past query - "
                    "behind a domain whose real owner is oncall-portal.example."),
        "sender_name": "Medical Staffing",
        "sender_email": "medstaff@ashbrookgeneral.example.oncall-portal.example",
        "subject": "On-call schedule and payment summary - Q3",
        "body": body("""
Your Q3 on-call payment summary is ready. It covers the Emergency Medicine and
Surgery rotas and includes the two weekends you queried in August.

View your summary: https://ashbrookgeneral.example.oncall-portal.example/q3

Medical Staffing
"""),
        "red_flags": [
            "subdomain misdirection: the real domain is oncall-portal.example, not the hospital",
            "the hospital's name is only the first label - read the domain right to left",
            "real departments and a real past query, to sound routine",
            "combines rota and pay, the two things worth checking immediately",
            "on-call summaries live on the Staff Portal",
        ],
    },

    {
        "id": 51, "label": "phishing", "cue": "hr_payroll",
        "technique": "Phishing", "target_role": "all", "difficulty": "hard",
        "teaches": ("Modelled on a real captured phish: no name, no detail, no reason - just "
                    "'you have a message' and a Click here. Vagueness is the whole design."),
        "sender_name": "HR Team",
        "sender_email": "hr@ashbrookgeneral.example",
        "reply_to": "hr-notifications@ashbrook-hrportal.example",
        "link_text": "Click here",
        "link_target": "https://ashbrook-hrportal.example/securemessage",
        "subject": "HR Team",
        "body": body("""
Greetings:

You have a message from the HR Department

Click here to view your message

Sincerely,

The Human Resources Talent Acquisition Team

This is an automatically generated email, please do not reply.
"""),
        "red_flags": [
            "'Greetings:' - no name, because it went to everyone at once",
            "says nothing about what the message is or why it exists",
            "the subject is just 'HR Team', which is not a subject",
            "'Click here' hides the destination - hover and it reads ashbrook-hrportal.example",
            "Reply-To is an outside address even though the From line is the hospital's",
            "'Talent Acquisition Team' has no reason to message existing staff",
            "'do not reply' blocks the obvious way to check",
            "real HR mail comes from Sandra Kim with an extension - see E33",
        ],
    },

    # ================= cue: billing =================

    {
        "id": 21, "label": "phishing", "cue": "billing",
        "technique": "Ransomware", "target_role": "front_billing", "difficulty": "hard",
        "teaches": "The delivery email behind a hospital going back to paper charts for days.",
        "sender_name": "Ashbrook Procurement",
        "sender_email": "procurement@ashbrook-procure.example",
        "subject": "Remittance advice - October statement attached",
        "body": body("""
Please find attached the remittance advice for October, covering invoices settled
this month.

Attached: Remittance_October.zip (contains Remittance_October.pdf.exe)

Extract and open the document to reconcile against your ledger. If a security
warning appears, approve it - the archive is password protected, so the scanner
cannot read inside.

Ashbrook Procurement
"""),
        "red_flags": [
            "a double extension: .pdf.exe is a program wearing a document's name",
            "tells you in advance to approve the security warning",
            "password-protected archives exist here to get past the spam filter",
            "report it fast - speed is what limits a ransomware incident",
        ],
    },
    {
        "id": 22, "label": "phishing", "cue": "billing",
        "technique": "Pretexting", "target_role": "front_billing", "difficulty": "easy",
        "teaches": "The table's example: 'Billing' asking someone to verify a patient's SSN.",
        "sender_name": "Claims Processing",
        "sender_email": "claims@health-insure-claims.example",
        "subject": "Patient insurance claim rejected",
        "body": body("""
A claim submitted by your department has been rejected because the patient's
details could not be matched to our records.

To release the claim we need the patient's date of birth and social security
number re-confirmed:

https://health-insure-claims.example/verify

Claims Processing Department
"""),
        "red_flags": [
            "an outside domain pretending to be an insurer",
            "an invented story used to extract patient identifiers",
            "asks for a patient's SSN - never confirm identity on an incoming request",
            "no claim number, no patient reference, no adjuster name",
        ],
    },
    {
        "id": 23, "label": "phishing", "cue": "billing",
        "technique": "Third-party / supply chain", "target_role": "front_billing", "difficulty": "hard",
        "teaches": ("A vendor's compromise becoming your loss. Sent from inside the hospital, "
                    "because the attacker already has a colleague's mailbox."),
        "sender_name": "Vendor Relations",
        "sender_email": "vendor.relations@ashbrookgeneral.example",
        "reply_to": "vendor.relations@ashbrookgeneral-finance.example",
        "link_text": "Updated details",
        "link_target": "https://ashbrookgeneral-finance.example/vendors/update",
        "subject": "Updated bank details for linen supplier",
        "body": body("""
Following a change of banking provider, our linen supplier has issued updated
remittance details. Please apply these to the vendor record before the next
payment run so payments are not returned.

Updated details

Vendor Relations
"""),
        "red_flags": [
            "a genuine internal address - an attacker in a colleague's mailbox sends real internal mail",
            "Reply-To quietly redirects to ashbrookgeneral-finance.example",
            "a changed bank account is the costliest request you can receive",
            "arrives by email rather than through vendor onboarding",
            "call the supplier on the number already on file, never one from the email",
            "E40 is the genuine statement, and says bank details are unchanged",
        ],
    },
    {
        "id": 24, "label": "phishing", "cue": "billing",
        "technique": "Phishing", "target_role": "front_billing", "difficulty": "easy",
        "teaches": "Pressure by invoice: shouting, a countdown and a threat.",
        "sender_name": "MedSupply Partners Accounts",
        "sender_email": "accounts@medsupply-partners.example.net",
        "subject": "Overdue invoice #48213 - FINAL NOTICE",
        "body": body("""
FINAL NOTICE

Invoice #48213 is 60 days overdue. Unless payment is received within 3 working
days, the account passes to a collections agency and further deliveries will be
suspended.

View invoice and pay: https://medsupply-partners.example.net/48213

Accounts Department
"""),
        "red_flags": [
            "an extra ending bolted on: the supplier on file is not on .example.net",
            "check the ending as well as the name - both have to match",
            "shouting FINAL NOTICE to create panic",
            "threatens collections and suspended deliveries",
            "no purchase order number to match it against - see E39",
        ],
    },
    {
        "id": 25, "label": "phishing", "cue": "billing",
        "technique": "Malware", "target_role": "front_billing", "difficulty": "hard",
        "teaches": "Malware through an attachment that looks like ordinary finance paperwork.",
        "sender_name": "Accounts Receivable",
        "sender_email": "ar@ashbrook-billing-docs.example",
        "subject": "Statement of account - action needed on 3 items",
        "body": body("""
Three items on your account need attention this week. The detail is in the
attached statement.

Attached: Statement_Q4_Ashbrook.docm

If the document opens in a protected view, choose Enable Content to see the
item breakdown.

Accounts Receivable
"""),
        "red_flags": [
            "'Enable Content' is the request that runs the macro",
            "a .docm file carries macros; a plain statement never needs them",
            "lookalike domain: ashbrook-billing-docs.example",
            "don't open unexpected attachments, however ordinary they look",
        ],
    },

    # ================= legitimate =================

    {
        "id": 26, "label": "legitimate", "cue": "none", "topic": "payroll",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "The honest version of E16 and E17: it tells you where to go and promises nothing by link.",
        "sender_name": "Payroll",
        "sender_email": "payroll@ashbrookgeneral.example",
        "subject": "Your October payslip is available",
        "body": body("""
Your October payslip is now on the Staff Portal under My Pay.

We never ask for your bank details by email. If anything looks wrong, call
Payroll on extension 4125.

Payroll
"""),
        "safe_signs": [
            "real hospital domain",
            "names where to look instead of linking",
            "states plainly that it will never ask for bank details",
            "a genuine pay email - which is exactly why the fakes work",
        ],
    },
    {
        "id": 27, "label": "legitimate", "cue": "none", "topic": "security_alert",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "What a real IT security warning looks like, including a safe way to report.",
        "sender_name": "IT Security",
        "sender_email": "itsecurity@ashbrookgeneral.example",
        "subject": "Reminder: watch out for fake password emails",
        "body": body("""
Hello,

We have seen fake emails this week asking staff to renew their passwords before
a deadline. IT will never ask you to change your password through an email link.

If you get one, use the Report Phish button in your mail toolbar. If you already
clicked, call us straight away on extension 4410 - reporting quickly is what
limits the damage, and nobody is in trouble for reporting.

Elena Petrova
IT Support, extension 4410
"""),
        "safe_signs": [
            "real hospital domain",
            "no link and no request for credentials",
            "explains how to report and says you will not be blamed",
            "named sender with a real extension",
        ],
    },
    {
        "id": 28, "label": "legitimate", "cue": "none", "topic": "security_training",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "Simulated phishing tests, one of the key defenses the table lists.",
        "sender_name": "IT Security",
        "sender_email": "itsecurity@ashbrookgeneral.example",
        "subject": "Phishing test results - and thank you to the 61 who reported",
        "body": body("""
Last month's simulated phishing test went to all staff. 18% clicked, down from
26% in the spring. 61 people used the Report Phish button, several within a
minute of delivery - that speed is what gives us a chance to act.

If you clicked, you were not named to anyone and you are not in trouble. The one
thing we ask is that you tell us, every time.

Next session dates are on the Staff Portal under Learning.

Elena Petrova
IT Support, extension 4410
"""),
        "safe_signs": [
            "real hospital domain",
            "no link, no sign-in, nothing to claim",
            "reports numbers rather than demanding action",
            "makes reporting safe, which is the point of the exercise",
        ],
    },
    {
        "id": 29, "label": "legitimate", "cue": "none", "topic": "availability",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "A Week 8 availability incident: the portal is flooded, but no data is taken.",
        "sender_name": "IT Service Desk",
        "sender_email": "servicedesk@ashbrookgeneral.example",
        "subject": "Patient portal slow this morning - we know, we're on it",
        "body": body("""
The public patient portal has been slow since about 7 AM. Our provider is
filtering a flood of junk traffic aimed at the portal - the kind that makes a
site crawl without anyone getting in.

No patient data is affected and internal systems are running normally. Patients
who call should be asked to try again later or to book by phone.

Incident reference INC-4471.

IT Service Desk, extension 4400
"""),
        "safe_signs": [
            "real hospital domain",
            "an incident reference you can quote",
            "explains an availability problem instead of asking you to fix it",
            "no link and no sign-in",
        ],
    },
    {
        "id": 30, "label": "legitimate", "cue": "none", "topic": "shadow_it",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "Shadow IT: why the quick workaround is the risk.",
        "sender_name": "IT Security",
        "sender_email": "itsecurity@ashbrookgeneral.example",
        "subject": "Approved apps for sharing patient information",
        "body": body("""
A reminder that patient information must stay in approved systems. Personal
messaging apps, personal email and personal phone cameras are not approved, even
when they are quicker.

If an approved tool is missing something you need, tell us - we would rather fix
the tool than have people work around it.

The approved list is on the Staff Portal under IT Security.

Elena Petrova
IT Support, extension 4410
"""),
        "safe_signs": [
            "real hospital domain",
            "policy reminder with no link and no credentials involved",
            "invites you to raise problems instead of threatening you",
            "named sender with an extension",
        ],
    },
    {
        "id": 31, "label": "legitimate", "cue": "none", "topic": "continuity",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "Practising the paper-charting fallback a ransomware lockout would force.",
        "sender_name": "Emergency Preparedness",
        "sender_email": "preparedness@ashbrookgeneral.example",
        "subject": "Downtime exercise: paper charting, Ward 4, next Wednesday",
        "body": body("""
Next Wednesday, Ward 4 runs a two-hour downtime exercise. Staff will chart on
paper as if the records system were unavailable, as it would be after a serious
IT incident.

Downtime packs are already on the ward. Patient care continues as normal - this
is practice, not a test of individuals.

Carol Mendes will be on the ward for the exercise.

Emergency Preparedness, extension 4320
"""),
        "safe_signs": [
            "real hospital domain",
            "announced in advance, with a named person present",
            "nothing to click and nothing to log into",
            "describes the drill, asks nothing of you personally",
        ],
    },
    {
        "id": 32, "label": "legitimate", "cue": "none", "topic": "vendor_security",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "The real supply-chain advisory that E05 imitates.",
        "sender_name": "IT Security",
        "sender_email": "itsecurity@ashbrookgeneral.example",
        "subject": "One of our suppliers had a breach - what it means for us",
        "body": body("""
A company that processes some of our claims has reported a security incident at
their end. Our own systems are not affected.

You may see claim responses running slowly for a week or two. You may also see
more emails pretending to be from this supplier - attackers follow the news.
Treat any unexpected message about claims, bank details or account resets with
extra suspicion, and report it.

Updates will be posted on the Staff Portal. We will not email you a link to log
in to anything.

IT Security, extension 4410
"""),
        "safe_signs": [
            "real hospital domain",
            "warns you about the phishing that follows a supplier breach",
            "states up front that it will not send login links",
            "updates live on the Staff Portal",
        ],
    },
    {
        "id": 33, "label": "legitimate", "cue": "none", "topic": "benefits",
        "technique": "Legitimate", "target_role": "all", "difficulty": "easy",
        "sender_name": "Human Resources",
        "sender_email": "hr@ashbrookgeneral.example",
        "subject": "Benefits enrollment opens November 1",
        "body": body("""
Hello all,

Annual benefits enrollment opens November 1 and closes November 30. Enroll
through the Staff Portal on the intranet. HR drop-in sessions will be held in
the cafeteria on November 5 and 12.

Sandra Kim
Human Resources Manager, extension 4120
"""),
        "safe_signs": [
            "real hospital domain",
            "a month-long window, no pressure",
            "sends you to the Staff Portal instead of a link",
            "named sender with an extension you can call",
        ],
    },
    {
        "id": 34, "label": "legitimate", "cue": "none", "topic": "safety",
        "technique": "Legitimate", "target_role": "all", "difficulty": "easy",
        "sender_name": "Fire Safety Office",
        "sender_email": "firesafety@ashbrookgeneral.example",
        "subject": "Fire drill - East Wing, Thursday 10 AM",
        "body": body("""
A scheduled fire drill takes place in the East Wing on Thursday at 10 AM.

Clinical areas: follow your usual evacuation procedure. Patient-facing staff
should not interrupt direct care to take part.

Fire Safety Office, extension 4305
"""),
        "safe_signs": [
            "real hospital domain",
            "no link and nothing to click",
            "asks nothing of you",
        ],
    },
    {
        "id": 35, "label": "legitimate", "cue": "none", "topic": "facilities",
        "technique": "Legitimate", "target_role": "all", "difficulty": "easy",
        "sender_name": "Facilities",
        "sender_email": "facilities@ashbrookgeneral.example",
        "subject": "Parking Lot C closed for resurfacing",
        "body": body("""
Parking Lot C is closed from Monday to Wednesday next week for resurfacing.
Please use Lot A or the staff spaces behind the Outpatient entrance.

Night staff: the Lot A barrier stays open from 6 PM.

Facilities, extension 4210
"""),
        "safe_signs": [
            "real hospital domain",
            "an ordinary operational notice",
            "no link, no request, no deadline",
        ],
    },
    {
        "id": 36, "label": "legitimate", "cue": "none", "topic": "quality",
        "technique": "Legitimate", "target_role": "nurse", "difficulty": "easy",
        "sender_name": "Infection Prevention",
        "sender_email": "infectionprevention@ashbrookgeneral.example",
        "subject": "Hand hygiene audit results - great work!",
        "body": body("""
This quarter's hand hygiene audit came back at 94% compliance, up from 88%.
Ward 4 and the Emergency Department both scored above 95%.

Thank you - this is the kind of result that shows up in infection rates.

Infection Prevention Team
"""),
        "safe_signs": [
            "real hospital domain",
            "good news that asks nothing of you",
            "no link, no attachment",
        ],
    },
    {
        "id": 37, "label": "legitimate", "cue": "none", "topic": "rota",
        "technique": "Legitimate", "target_role": "nurse", "difficulty": "hard",
        "teaches": "The honest counterpart to the rota-change phishing pattern.",
        "sender_name": "Scheduling",
        "sender_email": "scheduling@ashbrookgeneral.example",
        "subject": "December rota now published",
        "body": body("""
The December rota is published on the Staff Portal under My Schedule.

Swap requests close on the 20th. Put them through the rota system so they are
recorded - messages sent straight to managers get lost.

Scheduling, extension 4155
"""),
        "safe_signs": [
            "real hospital domain",
            "no link - it names where to look",
            "a reasonable, routine deadline",
            "no threat attached to missing it",
        ],
    },
    {
        "id": 38, "label": "legitimate", "cue": "none", "topic": "it_maintenance",
        "technique": "Legitimate", "target_role": "all", "difficulty": "hard",
        "teaches": "A real outage notice: advance warning, a change reference, no sign-in.",
        "sender_name": "IT Service Desk",
        "sender_email": "servicedesk@ashbrookgeneral.example",
        "subject": "Planned maintenance: records system, Sunday 2-4 AM",
        "body": body("""
The patient records system is unavailable on Sunday between 2 AM and 4 AM for
planned maintenance. Downtime forms are in the usual place on each ward.

Change reference CHG-2291. No sign-in or verification is required before or
after the work.

IT Service Desk, extension 4400
"""),
        "safe_signs": [
            "real hospital domain",
            "a change reference you can look up",
            "says plainly that no sign-in is needed",
            "scheduled ahead in a low-traffic window - unlike E13",
        ],
    },
    {
        "id": 39, "label": "legitimate", "cue": "none", "topic": "billing",
        "technique": "Legitimate", "target_role": "front_billing", "difficulty": "hard",
        "teaches": "The routine approval that E23 and E24 are built to imitate.",
        "sender_name": "Accounts Payable",
        "sender_email": "ap@ashbrookgeneral.example",
        "subject": "Invoice matched to PO 7731 - ready for approval",
        "body": body("""
Hi,

The invoice from our regular linen supplier has been matched to purchase order
7731 and is queued for your approval in the finance system, as usual.

No bank details have changed on this one.

Accounts Payable, extension 4260
"""),
        "safe_signs": [
            "real hospital domain",
            "matches a purchase order you can check",
            "approval happens in the finance system, not by link",
            "says explicitly that bank details are unchanged",
        ],
    },
    {
        "id": 40, "label": "legitimate", "cue": "none", "topic": "vendor",
        "technique": "Legitimate", "target_role": "front_billing", "difficulty": "easy",
        "sender_name": "Clean Linen Services",
        "sender_email": "accounts@cleanlinen.example",
        "subject": "Monthly statement - October",
        "body": body("""
Your October statement is in the supplier portal you already use.

Account: ASH-0094. Terms unchanged, bank details unchanged.

Clean Linen Services, Accounts
"""),
        "safe_signs": [
            "a known supplier with an account number already on file",
            "uses the portal you have, with no new link",
            "explicitly says nothing has changed - compare with E23",
        ],
    },
    {
        "id": 41, "label": "legitimate", "cue": "none", "topic": "clinical_update",
        "technique": "Legitimate", "target_role": "physician", "difficulty": "hard",
        "sender_name": "Laboratory",
        "sender_email": "lab@ashbrookgeneral.example",
        "subject": "New reference ranges for thyroid tests",
        "body": body("""
From the 1st of next month the laboratory adopts new reference ranges for TSH
and free T4, in line with the updated assay.

The ranges are printed on the report itself and summarised in the Lab Handbook
on the intranet. Victor Lindqvist is happy to talk the change through.

Laboratory, extension 4280
"""),
        "safe_signs": [
            "real hospital domain",
            "points to the intranet handbook, not an outside link",
            "names a colleague you can actually find",
            "professional content with no request attached",
        ],
    },
    {
        "id": 42, "label": "legitimate", "cue": "none", "topic": "compliance",
        "technique": "Legitimate", "target_role": "physician", "difficulty": "hard",
        "teaches": "The genuine attestation notice that E07 impersonates.",
        "sender_name": "Medical Staff Office",
        "sender_email": "medstaff@ashbrookgeneral.example",
        "subject": "Compliance attestation window open",
        "body": body("""
The annual compliance attestation window is open until the end of next month.

Complete it on the Staff Portal under Medical Staff. If you already did it as
part of re-credentialing, you can ignore this.

Medical Staff Office, extension 4190
"""),
        "safe_signs": [
            "real hospital domain",
            "a six-week window, not a Friday ultimatum",
            "Staff Portal, no link",
            "no threat to your credentialing file",
        ],
    },
    {
        "id": 43, "label": "legitimate", "cue": "none", "topic": "colleague",
        "technique": "Legitimate", "target_role": "nurse", "difficulty": "easy",
        "sender_name": "Grace Okonkwo",
        "sender_email": "g.okonkwo@ashbrookgeneral.example",
        "subject": "Shift swap Saturday?",
        "body": body("""
Hi,

Any chance you could swap Saturday day for my Sunday night? I have a family
thing I can't move. Happy to take an extra weekend later if that helps.

Let me know either way and I'll put it through the rota system.

Grace
"""),
        "safe_signs": [
            "real hospital domain, real colleague",
            "an ordinary request between staff",
            "no link, no urgency",
            "the change goes through the proper system",
        ],
    },
    {
        "id": 44, "label": "legitimate", "cue": "none", "topic": "procedure",
        "technique": "Legitimate", "target_role": "front_billing", "difficulty": "hard",
        "teaches": "The real procedure change that E10 imitates - named sender, portal, face-to-face.",
        "sender_name": "Lucia Ferraro",
        "sender_email": "l.ferraro@ashbrookgeneral.example",
        "subject": "Updated check-in procedure from next month",
        "body": body("""
Hi all,

The check-in procedure changes from the 1st. The main difference: we confirm the
contact number at check-in now, rather than at discharge.

The updated procedure is on the Staff Portal under Patient Access. I'll go
through it at Monday's huddle - bring questions then.

Lucia
Patient Registration, extension 4140
"""),
        "safe_signs": [
            "real hospital domain, a colleague you know",
            "points to the Staff Portal, no link",
            "offers a face-to-face session instead of tracking your click",
        ],
    },
    {
        "id": 45, "label": "legitimate", "cue": "none", "topic": "training",
        "technique": "Legitimate", "target_role": "nurse", "difficulty": "hard",
        "sender_name": "Education Department",
        "sender_email": "education@ashbrookgeneral.example",
        "subject": "Reminder: annual infection control training",
        "body": body("""
Your annual infection control module is due by the end of next month.

Find it on the Staff Portal under Learning. It takes about 20 minutes and runs on
any ward workstation. Your manager can book protected time if your unit is short.

Education Department, extension 4360
"""),
        "safe_signs": [
            "real hospital domain",
            "a month's notice and no threat",
            "Staff Portal rather than a link",
            "offers help instead of punishment",
        ],
    },
    {
        "id": 46, "label": "legitimate", "cue": "none", "topic": "occupational_health",
        "technique": "Legitimate", "target_role": "all", "difficulty": "easy",
        "sender_name": "Occupational Health",
        "sender_email": "occhealth@ashbrookgeneral.example",
        "subject": "Staff flu vaccine clinics this month",
        "body": body("""
Staff flu vaccine clinics run every weekday this month, 7-9 AM and 1-3 PM, in
the Occupational Health office on Level 2. No appointment needed - bring your
badge.

Night staff clinics: Tuesday and Thursday at 11 PM.

Occupational Health, extension 4340
"""),
        "safe_signs": [
            "real hospital domain",
            "walk-in, nothing to submit",
            "no link and no personal details requested",
        ],
    },
    {
        "id": 47, "label": "legitimate", "cue": "none", "topic": "team",
        "technique": "Legitimate", "target_role": "nurse", "difficulty": "easy",
        "sender_name": "Ward 4 Manager",
        "sender_email": "ward4.manager@ashbrookgeneral.example",
        "subject": "Ward 4 team meeting agenda",
        "body": body("""
Agenda for Thursday's team meeting:

1. Discharge delays - what is actually holding them up
2. The new handover sheet, two weeks in
3. Annual leave over the holidays
4. Any other business

Bring anything you want added. Coffee provided.

Ward 4 Manager
"""),
        "safe_signs": [
            "real hospital domain",
            "specific, ordinary, internal content",
            "no link and no attachment",
        ],
    },
    {
        "id": 48, "label": "legitimate", "cue": "none", "topic": "it_change",
        "technique": "Legitimate", "target_role": "front_billing", "difficulty": "hard",
        "sender_name": "Scheduling Lead",
        "sender_email": "scheduling.lead@ashbrookgeneral.example",
        "subject": "Scheduling system update next Tuesday",
        "body": body("""
The outpatient scheduling system is updated next Tuesday evening after 8 PM. The
booking screen looks slightly different on Wednesday morning - the search box
moves to the top of the page.

No action is needed and no sign-in is required. Drop-in questions at the Patient
Access desk on Wednesday.

Scheduling Lead, extension 4155
"""),
        "safe_signs": [
            "real hospital domain",
            "says explicitly that no action and no sign-in are needed",
            "plenty of notice",
            "reads like E13, but asks for nothing",
        ],
    },
    {
        "id": 49, "label": "legitimate", "cue": "none", "topic": "patient_feedback",
        "technique": "Legitimate", "target_role": "front_billing", "difficulty": "easy",
        "sender_name": "Patient Experience",
        "sender_email": "patientexperience@ashbrookgeneral.example",
        "subject": "Thank-you card from a patient",
        "body": body("""
A patient discharged from the Outpatient Clinic last week sent a card thanking
the reception team by name for how they were treated on a difficult day.

It is on the noticeboard by the staff room. Thought you would like to know.

Patient Experience Team
"""),
        "safe_signs": [
            "real hospital domain",
            "nothing to click and nothing to do",
            "no urgency of any kind",
        ],
    },
    {
        "id": 50, "label": "legitimate", "cue": "none", "topic": "catering",
        "technique": "Legitimate", "target_role": "all", "difficulty": "easy",
        "sender_name": "Catering",
        "sender_email": "catering@ashbrookgeneral.example",
        "subject": "This week's cafeteria menu",
        "body": body("""
This week in the cafeteria:

Monday - chicken casserole, vegetable lasagne
Tuesday - fish pie, bean chilli
Wednesday - roast pork, mushroom risotto
Thursday - curry day
Friday - fish and chips

Night staff: hot options are available until 2 AM.

Catering
"""),
        "safe_signs": [
            "real hospital domain",
            "about as low-stakes as email gets",
            "nothing to click",
        ],
    },
]


def build():
    """Attach the taxonomy columns to each email and write the dataset."""
    records = []
    for e in EMAILS:
        tax = TAXONOMY[e["technique"]]

        rec = {
            "id": e["id"],
            "label": e["label"],
            "cue": e["cue"],
            # --- taxonomy, from the Weeks 7 & 8 comparison table ---
            "technique": e["technique"],
            "technique_category": tax["category"],
            "table_row": tax["row"],
            "week": tax["week"],
            "cia_hit": tax["cia_hit"],
            "key_defense": tax["key_defense"],
            # --- delivery ---
            "target_role": e["target_role"],
            "difficulty": e["difficulty"],
            "sender_name": e["sender_name"],
            "sender_email": e["sender_email"],
            "subject": e["subject"],
            "body": e["body"],
        }
        # Present only when the message hides where it really goes. reply_to is the
        # mismatch you find by looking; link_target is the one you find by hovering.
        for optional in ("reply_to", "link_text", "link_target", "topic", "teaches"):
            if optional in e:
                rec[optional] = e[optional]
        if e["label"] == "phishing":
            trick = ADDRESS_TRICK_BY_ID[e["id"]]
            rec["address_trick"] = trick
            rec["address_trick_note"] = ADDRESS_TRICKS[trick]
            rec["red_flags"] = e["red_flags"]
        else:
            rec["safe_signs"] = e["safe_signs"]

        records.append(rec)

    # Phishing first, then legitimate, each by id.
    records.sort(key=lambda r: (r["label"] != "phishing", r["id"]))

    ids = [r["id"] for r in records]
    assert len(ids) == len(set(ids)), "duplicate email id"

    # Every address must sit in space that can never resolve: the reserved
    # .example TLD, or example.com / example.net / example.org (RFC 2606).
    # Endings like .example.info or .example.co are NOT reserved.
    safe_endings = (".example", ".example.com", ".example.net", ".example.org")
    for r in records:
        domain = r["sender_email"].split("@")[1]
        assert domain.endswith(safe_endings), (
            "sender domain %r in %s could resolve - use reserved space only"
            % (domain, r["id"])
        )
        for field in ("reply_to", "link_target"):
            value = r.get(field)
            if value:
                host = value.split("@")[-1].split("//")[-1].split("/")[0]
                assert host.endswith(safe_endings), (
                    "%s %r in %s could resolve" % (field, value, r["id"]))

    phish = [r for r in records if r["label"] == "phishing"]
    counts = Counter(r["label"] for r in records)

    data = {
        "note": (
            "Fictional training emails for simulation only. Hospital, people, domains "
            "and links are fake (.example domains that cannot resolve). Every email is "
            "tagged with the attack/threat taxonomy from HIM 1055 Weeks 7 & 8 and ships "
            "with the red flags or safe signs needed to explain it afterwards. Some "
            "phishing emails are sent from the hospital's own domain, because a From "
            "line can be forged: where that happens, reply_to and link_target hold the "
            "tells a reader finds by checking the headers and hovering the link."
        ),
        "hospital": HOSPITAL,
        "real_domain": REAL_DOMAIN,
        "taxonomy_source": SOURCE,
        "cia_triad": {
            "C": "Confidentiality - only the right people can see the data",
            "I": "Integrity - the data is accurate and has not been tampered with",
            "A": "Availability - the system and data are there when you need them",
        },
        "counts": {
            "total": len(records),
            "phishing": counts["phishing"],
            "legitimate": counts["legitimate"],
            "by_cue": dict(sorted(Counter(r["cue"] for r in phish).items())),
            "by_technique": dict(sorted(Counter(r["technique"] for r in phish).items())),
            "by_difficulty": dict(sorted(Counter(r["difficulty"] for r in records).items())),
            # Phishing that arrives from the hospital's own domain: the From line
            # looks right, so the tell has to be the Reply-To, the link or the content.
            "phishing_from_real_domain": sum(
                1 for r in phish if r["sender_email"].endswith("@" + REAL_DOMAIN)
            ),
            "phishing_with_hidden_link": sum(1 for r in phish if "link_target" in r),
            "by_address_trick": dict(sorted(Counter(r["address_trick"] for r in phish).items())),
        },
        "address_tricks": ADDRESS_TRICKS,
        "emails": records,
    }

    with open("data/hospital_emails_mixed.json", "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")

    return data


if __name__ == "__main__":
    data = build()
    c = data["counts"]
    print(f"Wrote data/hospital_emails_mixed.json: {c['total']} emails")
    print(f"  phishing   {c['phishing']}")
    print(f"  legitimate {c['legitimate']}")
    print("  phishing by cue:      ", c["by_cue"])
    print("  phishing by technique:")
    for tech, n in sorted(c["by_technique"].items(), key=lambda x: (-x[1], x[0])):
        row = TAXONOMY[tech]["row"]
        print(f"    {n:2}  {tech} (table row {row})")

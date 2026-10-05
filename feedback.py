# FeedbackModule: gives feedback to the human after each email.
# Later this will support different feedback types so we can compare them.


class FeedbackModule:
    def __init__(self, feedback_type):
        # Will store which kind of feedback to use (e.g. "none", "simple", "detailed")
        pass

    def give_feedback(self, email, action):
        # Will return a feedback message based on the email and the human's action
        pass

from generator import EmailGenerator

gen = EmailGenerator()
email = gen.get_email(role="nurse")
print(email["subject"])
print(email["label"])
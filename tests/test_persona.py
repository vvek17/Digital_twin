# test_persona.py
# A quick check: load all the people and print their key traits.
# (hidden_probs are printed here only because this is a test/debug script.)

from backend.persona import load_people


def main():
    people = load_people()
    print("Loaded %d people\n" % len(people))

    for p in people:
        print("%s - %s" % (p.id, p.name))
        print("  role:       %s" % p.role)
        print("  awareness:  %s" % p.security_awareness)
        print("  workload:   %s" % p.workload)
        print("  hidden_probs: %s" % p.hidden_probs)
        print()


if __name__ == "__main__":
    main()

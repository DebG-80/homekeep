# Fixture provenance

Everything under `fixtures/` is synthetic and written for this project.

- **Households and appliances** (`households.json`): invented. Appliances are described only by category, nickname and room. No addresses, phone numbers, emails, invoices or serial numbers are seeded.
- **Identities** (`identities.json`): invented usernames prefixed `hk-`. There are no real people, and no email addresses. Passwords are never stored here: `scripts/seed.py` generates them at random when it creates the Cognito users and prints them once to the operator's terminal.
- **Brand:** "Frostline" (models FL-18i and FL-24x) is a fictional appliance brand. Its catalog content arrives in Slice 2 with its own provenance notes in `catalog_data/`.

No third-party material is included (TDD §2).

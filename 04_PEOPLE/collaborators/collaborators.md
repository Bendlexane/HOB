---
sticker: emoji//1f465
---

Central registry of collaborators and coauthors used for author selection during project creation, as well as for KPI tracking, collaboration analytics, and reporting.

## Schema

- `id`: unique identifier composed of a stable slug and a random 4-character hexadecimal suffix (e.g. john-smith-a3f7)
- `slug`: human-readable identifier derived from display_name
- `display_name`: preferred display format (Surname, Given Names)
- `surname`: family name
- `given_names`: given name(s)
- `canonical_name`: normalized name in the format surname|given, all lowercase (e.g. smith|john)
- `aliases`: alternative name variants, abbreviations, or name spellings (array)
- `affiliations`: list of affiliations (array; use an array even when only one affiliation is available)
- `orcid`: ORCID identifier (optional)
- `email`: contact email address (optional)
- `notes`: free-text notes or additional information

## Workflow

1. During project creation, authors can be selected from a searchable picker populated from this database.
2. If a coauthor is entered manually and no matching record exists, a new record is created automatically.
3. Use ; as the preferred separator when entering multiple coauthors, since commas are already used within the Surname, Given Names format.
4. The database is designed to remain machine-readable, supporting automated KPI generation, collaboration analysis, and reporting.
5

---
sticker: emoji//1f9d1-200d-1f91d-200d-1f9d1
---

Students under supervision and external collaborators. The authoritative coauthor registry (`_people-db.json`) lives here and is read by `new-project.md` at project creation for coauthor selection. New names entered manually at project creation are added to the DB automatically.

| Subfolder | Purpose |
|---|---|
| `students/` | One `LastName_FirstName/` folder per supervised student: `_student.md` (thesis topic, level, period, contacts, project links), `thesis/`, `meetings/`, `outputs/` |
| `collaborators/` | `_people-db.json` (machine-readable registry: display_name, aliases, affiliations, ORCID, tags), `_people-db.md` (schema and governance), optional individual notes |

Do NOT store scientific content here — analyses and manuscripts tied to student work live in the linked `01_PROJECTS/` folder. People pages for taxa, institutions, or places go in `03_KNOWLEDGE/entities/` — not here.

---
sticker: lucide//database-backup
---
The measurement layer. Holds the KPI database and the views built on top of it — data is collected automatically, you don't fill these files by hand.

- `research_kpis.db` — SQLite database, all KPI tables. Written daily by `_scripts/kpi/collector.py`. Gitignored (it's your data).
- `dashboards/` — optional weekly/rendered dashboards on top of the DB.
- `exports/` — on-demand exports for ad-hoc analysis: `python3 _scripts/kpi/database.py export [--from YYYY-MM-DD] [--to YYYY-MM-DD]`.
- `snapshots/` — dated DB copies for rollback, if you choose to script that yourself.

Only what `_scripts/kpi/` actually collects is "live" out of the box (git stats, Zotero reading stats) — everything else here is scaffolding for you to extend.

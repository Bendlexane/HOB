---
type: meta
title: Protocols Index
sticker: emoji//1f9ea
cssclasses: [graph-hide]
---

# Protocols Index

> Every note with `type: protocol`, grouped by the `domain` you give it. Make one subfolder per domain you actually work in, then use the Protocol action to create notes inside it.

## All protocols by domain

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  phase AS Phase,
  reproducibility_status AS Repro,
  last_validated AS "Last validated",
  status AS Status
FROM "03_KNOWLEDGE/protocols"
WHERE type = "protocol"
GROUP BY domain
SORT domain ASC, phase ASC
```

## Due for re-validation (>24 months)

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  last_validated AS "Last validated",
  reproducibility_status AS Status
FROM "03_KNOWLEDGE/protocols"
WHERE type = "protocol" AND last_validated < date(today) - dur(24 months)
SORT last_validated ASC
```

## Deprecated

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  deprecated_reason AS Reason,
  replaced_by AS "Replaced by"
FROM "03_KNOWLEDGE/protocols"
WHERE type = "protocol" AND status = "deprecated"
```

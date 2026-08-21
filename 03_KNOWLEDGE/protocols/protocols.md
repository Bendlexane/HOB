---
type: meta
title: Protocols Index
cssclasses: [graph-hide]
---

# Protocols Index

> Auto-generated table of all protocols by domain, phase, and reproducibility status.

## Phylogenomics — Wet lab

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  reproducibility_status AS Repro,
  last_validated AS "Last validated",
  status AS Status
FROM "03_KNOWLEDGE/protocols/phylogenomics/01_wetlab"
WHERE type = "protocol"
SORT phase ASC
```

## Phylogenomics — Dry lab

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  reproducibility_status AS Repro,
  last_validated AS "Last validated",
  status AS Status
FROM "03_KNOWLEDGE/protocols/phylogenomics/02_drylab"
WHERE type = "protocol"
SORT phase ASC
```

## Morphometry

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  reproducibility_status AS Repro,
  status AS Status
FROM "03_KNOWLEDGE/protocols/morphometry"
WHERE type = "protocol"
```

## Cytogenetics

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  reproducibility_status AS Repro,
  status AS Status
FROM "03_KNOWLEDGE/protocols/cytogenetics"
WHERE type = "protocol"
```

## Herbarium

```dataview
TABLE WITHOUT ID
  file.link AS Protocol,
  reproducibility_status AS Repro,
  status AS Status
FROM "03_KNOWLEDGE/protocols/herbarium"
WHERE type = "protocol"
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

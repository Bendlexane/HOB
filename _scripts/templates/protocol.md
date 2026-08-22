<%*
const name = await tp.system.prompt("Protocol name (kebab-case, e.g. sample-preparation)");
if (!name) return;

// Domains are whatever your field calls them, so offer the ones already in
// use and let anything new be typed in.
const existing = app.vault.getMarkdownFiles()
    .map(f => app.metadataCache.getFileCache(f)?.frontmatter)
    .filter(fm => fm && fm.type === "protocol" && fm.domain)
    .map(fm => String(fm.domain));
const known = [...new Set(existing)].sort();

let domain;
if (known.length) {
    const picked = await tp.system.suggester(
        [...known, "New domain…"],
        [...known, "__new__"]
    );
    if (!picked) return;
    domain = picked === "__new__"
        ? await tp.system.prompt("Domain (kebab-case, e.g. microscopy)")
        : picked;
} else {
    domain = await tp.system.prompt("Domain (kebab-case, e.g. microscopy)");
}
if (!domain) return;

const phase = await tp.system.prompt("Phase, optional (e.g. 01_preparation, or leave blank)", "");

const owner = await tp.system.prompt("Owner (name or lab ID)", "");

const path = phase 
    ? `03_KNOWLEDGE/protocols/${domain}/${phase}/${name}`
    : `03_KNOWLEDGE/protocols/${domain}/${name}`;
// Guard against an existing protocol with the same name: tp.file.move on an
// existing destination throws and leaves the temp file broken (ENOENT).
if (await app.vault.adapter.exists(`${path}.md`)) {
  new Notice(`⚠️ A protocol named "${name}.md" already exists at ${path}.md. Pick a different name.`);
  return;
}
await tp.file.move(path);
%>---
type: protocol
domain: <% domain %>
phase: <% phase || "n/a" %>
name: <% name %>
tools: []
status: draft                  # draft | current | deprecated

# Reproducibility
validated_with:
  software_versions: {}
  environment: ""
  expected_runtime: ""
  test_dataset: ""
reproducibility_status: unknown # validated | partially_validated | deprecated | unknown
last_validated: null
deprecated_reason: null
replaced_by: null

# Governance
owner: <% owner %>
canonical: true
reviewed_by: []
last_curated: <% tp.date.now("YYYY-MM-DD") %>
fork_of: null

taxon_group: null
created: <% tp.date.now("YYYY-MM-DD") %>
---

# <% name %>

## 🎯 Purpose

_What problem does this protocol solve?_

## 📋 Materials

- 

## 🧪 Reagents

- 

## 🔬 Procedure

### Step 1
_Time: _

### Step 2
_Time: _

## ⚠️ Troubleshooting

| Problem | Likely cause | Solution |
|---|---|---|
|  |  |  |

## 📊 Expected results

_What should you see if the protocol went well?_

## 📚 References

- 

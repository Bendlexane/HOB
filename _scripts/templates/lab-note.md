<%*
// Generate a unique 8-char uppercase hex experiment ID and stamp today's date,
// so every note created from this template is uniquely identifiable. Write this
// code on your tubes/gels/photos to retrieve the note via Obsidian search.
const expId = Array.from({ length: 4 }, () =>
  Math.floor(Math.random() * 256).toString(16).padStart(2, "0")
).join("").toUpperCase();
const today = tp.date.now("YYYY-MM-DD");
-%>
---
type: lab-note
experiment_id: <% expId %>
date: <% today %>
project_code: 
activity_type: null            # free text, whatever your field calls the activity
protocol: null
samples_processed: null
success_count: null
material: null                 # free text, what the sample is made of
---

# Lab note <% today %> — ID `<% expId %>`

> 🏷️ **Experiment ID:** `<% expId %>` — write this code on your tubes/gels/photos to retrieve them via Obsidian search.

## 🎯 Goal of the day

## 🧪 Procedure/Protocol

_Link to `[[03_KNOWLEDGE/protocols/...]]` if applicable._

## 📦 Samples/Materials

| Sample ID | Species | Origin | Notes |
|---|---|---|---|
|  |  |  |  |

## 👁️ Observations

## ⚠️ Issues

## 📝 TODO

- [ ] 

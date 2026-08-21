<%*
// When launched from the HOME dashboard, all input is gathered inline *before*
// this template runs (no temp-file churn that re-renders HOME and kills the
// inline prompt) and handed off via window._actionPreset.presetVal. When run
// from the command palette, fall back to native Templater prompts.
const preset = (window._actionPreset && window._actionPreset.presetVal) ? window._actionPreset.presetVal : null;
window._actionPreset = null; // consume

let title, relatedProject, structureChoice;

if (preset && preset.title) {
  title = preset.title;
  relatedProject = preset.project || null;
  structureChoice = preset.structure || 1;
} else {
  title = await tp.system.prompt("Short idea title (kebab-case)");
  if (!title) return;

  // Fetch active projects from 01_PROJECTS/ folder using Obsidian vault API
  const projectsFolder = app.vault.getAbstractFileByPath("01_PROJECTS");
  let activeProjects = [];
  if (projectsFolder && projectsFolder.children) {
    activeProjects = projectsFolder.children
      .filter(f => f.children && f.name && !f.name.startsWith(".") && !f.name.startsWith("_"))
      .map(f => f.name);
  }

  const projectOptions = ["— None", ...activeProjects];
  const selectedProj = await tp.system.suggester(projectOptions, projectOptions);
  relatedProject = selectedProj && selectedProj !== "— None" ? selectedProj : null;

  const structureOptions = [
    "1. Blank — Title and free space",
    "2. Structured — Spark, Research Question, Methodology, Action Plan",
    "3. Simplified — Summary, Next Steps, Status"
  ];
  const selectedStruct = await tp.system.suggester(structureOptions, [1, 2, 3]);
  structureChoice = selectedStruct || 1;
}

// Move file to destination folder. Guard against an existing note with the same
// name first: calling tp.file.move on an existing destination throws "Destination
// file already exists!" and leaves the temp file in a broken state (ENOENT).
const filename = `${tp.date.now("YYYY-MM-DD")}_${title.toLowerCase().replace(/\s+/g, '-')}`;
const destPath = `00_STAGING/ideas/${filename}.md`;
if (await app.vault.adapter.exists(destPath)) {
  new Notice(`⚠️ An idea named "${filename}.md" already exists. Pick a different title.`);
  return;
}
await tp.file.move(`00_STAGING/ideas/${filename}`);
-%>---
type: idea
title: "<% title %>"
status: raw                   # raw | developing | → project
decay: soft                   # never | soft (alert >30d) | aggressive (alert >30d)
created: <% tp.date.now("YYYY-MM-DD") %>
related_projects: <% relatedProject ? `["${relatedProject}"]` : "[]" %>
related_literature: []
---

# <% title %>

<%* if (structureChoice === 1) { %>
_Write your notes here..._

<%* } else if (structureChoice === 2) { %>
#### 💡 Spark

_What came to mind? (origin, context, intuition)_

#### 🎯 Research Question

_If it became a project, what would it answer? (core hypothesis, objective)_

#### 🧪 Methodology & Validation

_Literature to read, data to gather, pilot analysis._

#### 🌱 Action Plan & Status

- [ ] Raw — just noted
- [ ] Developed — preliminary literature read
- [ ] Promoted to project
- [ ] Discarded (reason: ...)

<%* } else if (structureChoice === 3) { %>
#### 📝 Summary

_Brief summary of the idea._

#### 🚀 Next Steps

_Immediate actions to take._

#### 🌱 Status

- [ ] Raw — just noted
- [ ] Developed — preliminary literature read
- [ ] Promoted to project
- [ ] Discarded (reason: ...)
<%* } %>

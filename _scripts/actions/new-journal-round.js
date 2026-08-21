// ============================================================================
//  new-journal-round — add a submission/revision round structure to a project.
//  Migrated from _scripts/templates/new-journal-round.md (now deprecated).
//
//  Resolves the project folder from the open note (under 01_PROJECTS/) or, when
//  launched from the dashboard / with no project note open, via a folder picker.
//  No Templater, no temp file, no window._actionsSourceFile.
// ============================================================================
module.exports = async (ctx) => {
  const { app, ui } = ctx;

  const src = await ctx.requireSourceUnder("01_PROJECTS", "project");
  if (!src) return;
  const projectBase = src.base;

  const journalName = await ui.prompt("New journal name");
  if (!journalName) return;
  const journalFolder = journalName
    .replace(/[^a-zA-Z0-9_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .toLowerCase();

  const folders = [
    `${projectBase}/05_submission/${journalFolder}/01_round`,
    `${projectBase}/05_submission/${journalFolder}/02_round`,
    `${projectBase}/06_correspondence/${journalFolder}/01_round`,
    `${projectBase}/06_correspondence/${journalFolder}/02_round`,
  ];
  for (const f of folders) {
    try { await app.vault.createFolder(f); } catch (e) {}
  }

  ui.notice(`✅ Structure created for ${journalName}`);
};

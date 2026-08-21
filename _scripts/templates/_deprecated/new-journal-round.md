<%*
const activeFile = window._actionsSourceFile || app.workspace.getActiveFile();
delete window._actionsSourceFile;
if (!activeFile) {
    new Notice("❌ No active file — run this template from within a project submission folder.");
    return;
}
const path = activeFile.path;
const projMatch = path.match(/^(01_PROJECTS\/[^/]+)/);
if (!projMatch) {
    new Notice("❌ Active file is not inside a project folder.");
    return;
}
const projectBase = projMatch[1];

const journalName = await tp.system.prompt("New journal name");
if (!journalName) return;
const journalFolder = journalName
    .replace(/[^a-zA-Z0-9_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_|_$/g, "")
    .toLowerCase();

await app.vault.createFolder(`${projectBase}/05_submission/${journalFolder}/01_round`).catch(() => {});
await app.vault.createFolder(`${projectBase}/05_submission/${journalFolder}/02_round`).catch(() => {});
await app.vault.createFolder(`${projectBase}/06_correspondence/${journalFolder}/01_round`).catch(() => {});
await app.vault.createFolder(`${projectBase}/06_correspondence/${journalFolder}/02_round`).catch(() => {});

new Notice(`✅ Structure created for ${journalName}`);
tR += `Created submission + correspondence structure for **${journalName}**:\n`;
tR += `- [[${projectBase}/05_submission/${journalFolder}/01_round]]\n`;
tR += `- [[${projectBase}/05_submission/${journalFolder}/02_round]]\n`;
tR += `- [[${projectBase}/06_correspondence/${journalFolder}/01_round]]\n`;
tR += `- [[${projectBase}/06_correspondence/${journalFolder}/02_round]]\n`;
_%>
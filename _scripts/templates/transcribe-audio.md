<%*
// Template: transcribe-audio  (System & Utilities)
// Transcribe an audio file embedded in the CURRENT note with Whisper + Ollama,
// and stamp the cleaned transcript right under its ![[…]] embed.
//
// Standalone: talks only to _scripts/automation/transcribe_file.py. It does NOT
// use the conference recording server (transcribe_server.py).
// Live progress → Home Notification Center (updates in place). Log → /private/tmp/transcribe_file.log

const vaultPath = app.vault.adapter.basePath;
const script    = `${vaultPath}/_scripts/automation/transcribe_file.py`;
const fs        = require("fs");
const { spawn } = require("child_process");

// ── 1. Resolve the REAL note ──────────────────────────────────────────────────
// Launched via actions.md / Cmd+T, focus shifts to a temp buffer that is then
// deleted — so tp.file.* is useless here. actions.md rewrites the literal
// `window._actionsSourceFile` into a getAbstractFileByPath(...) of the source
// note; a direct run falls back to the active file.
const activeFile = window._actionsSourceFile || app.workspace.getActiveFile();
if (!activeFile) { new Notice("❌ No active note to transcribe."); return; }
const notePath = `${vaultPath}/${activeFile.path}`;
const content  = await app.vault.read(activeFile);

// ── 2. Find embedded audio files ![[name.ext]] ────────────────────────────────
const AUDIO_EXT = /\.(m4a|mp3|wav|aac|ogg|flac|webm|mp4|mov|opus)$/i;
const embedsIn = (txt) => [...(txt || "").matchAll(/!\[\[\s*([^\]|#]+?)\s*(?:[#|][^\]]*)?\]\]/g)]
    .map(m => m[1].trim())
    .filter(name => AUDIO_EXT.test(name));

// Priority: selection / cursor line (only if the visible editor IS this note),
// else the whole note.
let audio = null;
const ed = app.workspace.activeEditor;
if (ed?.editor && ed?.file?.path === activeFile.path) {
    const sel = embedsIn(ed.editor.getSelection());
    if (sel.length) audio = sel[0];
    if (!audio) {
        const line = embedsIn(ed.editor.getLine(ed.editor.getCursor().line));
        if (line.length) audio = line[0];
    }
}
if (!audio) {
    const unique = [...new Set(embedsIn(content))];
    if (unique.length === 0) {
        new Notice("🎙❌ No embedded audio (![[file.m4a]]) found in this note.", 6000);
        return;
    }
    audio = unique.length === 1
        ? unique[0]
        : await tp.system.suggester(unique, unique, false, "Audio file to transcribe");
    if (!audio) { new Notice("Cancelled."); return; }
}

// ── 3. Optional label (used in the callout header + cleanup prompt) ───────────
const stem    = audio.replace(AUDIO_EXT, "");
const session = (await tp.system.prompt("Transcript label", stem, true)) || stem;

// ── 4. Seed the Home Notification Center so feedback is instant ────────────────
// Python then updates this same entry in place (Preparing → Whisper bar → done);
// the Home dashboard polls notifications.json every 5 s and shows the progress.
const NOTI_PATH = "06_PLANNING/kpis/notifications.json";   // kept in sync with transcribe_file.py
try {
    let list = [];
    try { list = JSON.parse(await app.vault.adapter.read(NOTI_PATH)) || []; } catch (e) { list = []; }
    if (!Array.isArray(list)) list = [];
    list = list.filter(n => n.id !== "transcribe_audio");
    list.push({
        id: "transcribe_audio", title: "🎙 Transcription",
        message: `Preparing “${session}”…`,
        timestamp: Date.now(), read: false, sound: false,
    });
    await app.vault.adapter.write(NOTI_PATH, JSON.stringify(list.slice(-20), null, 2));
    if (typeof window.__refreshDashboardNotifications === "function") window.__refreshDashboardNotifications();
} catch (e) {}

// ── 5. Spawn the transcription helper (detached; updates the note + dashboard) ──
let out = "ignore";
try { out = fs.openSync("/private/tmp/transcribe_file.log", "a"); } catch (e) {}
const child = spawn(
    "/usr/bin/python3",
    [script, "--audio", audio, "--note", notePath, "--session", session],
    { cwd: vaultPath, detached: true, stdio: ["ignore", out, out] }
);
child.unref();
// No extra Notice here: the seeded 'transcribe_audio' entry above is the feedback,
// and _HOME mirrors Notices into the same center (would create a duplicate).
%>

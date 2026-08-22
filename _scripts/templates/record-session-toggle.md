<%*
// ══════════════════════════════════════════════════════════════════════
//  RECORD SESSION — TOGGLE
//  Single button: if idle → prompt session name → start recording
//                  if recording → stop + transcribe + append under heading
//
//  The server is auto-started by this button if not already running, and it
//  auto-shuts down after a period of inactivity. No need to launch it manually.
//  (Grant microphone permission to Obsidian the first time macOS asks.)
// ══════════════════════════════════════════════════════════════════════

const _lp = `${app.vault.adapter.basePath}/_scripts/lib/templater-utils.js`;
try { delete require.cache[_lp]; } catch (e) {}
const U = require(_lp);
const env = await U.loadEnv();
const TRANS_SERVER = env.TRANS_SERVER || "http://localhost:11435";
const notePath = tp.file.path(true);

// ── Ensure the transcription server is running; auto-start it if needed. ──
// Launched as a detached child of Obsidian → macOS attributes microphone
// permission to Obsidian (grant once). The server auto-shuts down after a
// period of inactivity, so nothing lingers in the background.
// Shared secret for the server. It writes this file on first run, owner-only,
// so reading it is the proof that we are a local process rather than a web
// page that happens to know the port.
function authToken() {
  try {
    return require("fs")
      .readFileSync(`${app.vault.adapter.basePath}/_scripts/.transcribe_token`, "utf8")
      .trim();
  } catch { return ""; }
}
function authHeaders(extra) {
  return Object.assign({ "X-HOB-Token": authToken() }, extra || {});
}
async function serverHealth() {
  try {
    const res = await fetch(`${TRANS_SERVER}/health`, { headers: authHeaders() });
    // A 403 means the server is up but we read a stale or missing token, which
    // is not "healthy" — treat it as down so the caller reports it.
    if (!res.ok) return null;
    return await res.json();
  } catch { return null; }
}
async function ensureServer() {
  let h = await serverHealth();
  if (h) return h;
  const { spawn } = require("child_process");
  const fs = require("fs");
  const base = app.vault.adapter.basePath;
  const serverPath = `${base}/_scripts/automation/transcribe_server.py`;
  new Notice("⏳ Starting transcription server…");
  let out = "ignore";
  try { out = fs.openSync("/private/tmp/transcribe_server.log", "a"); } catch {}
  const child = spawn("/usr/bin/python3", [serverPath], {
    cwd: base, detached: true, stdio: ["ignore", out, out],
  });
  child.unref();
  for (let i = 0; i < 60; i++) {            // up to ~30s for startup
    await new Promise((r) => setTimeout(r, 500));
    h = await serverHealth();
    if (h) return h;
  }
  return null;
}

try {
  const status = await ensureServer();
  if (!status) {
    new Notice("❌ Could not start the transcription server.\nSee /private/tmp/transcribe_server.log");
    return;
  }

  if (status.recording) {
    const stopRes = await fetch(`${TRANS_SERVER}/record/stop`, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ note_path: notePath }),
    });
    const data = await stopRes.json();
    if (data.status === "idle") {
      new Notice("❌ No active recording to stop.");
      return;
    }
    // ⚠️ Empty recording — microphone was unavailable (lid closed, sleep, no input device).
    // The server recorded 0 frames and returned status "empty".
    if (data.status === "empty") {
      new Notice(
        "🎙❌ No audio recorded\n\n" +
        "The microphone was unavailable when you pressed Stop.\n\n" +
        "Possible causes:\n" +
        "• The computer was closed/asleep when recording started\n" +
        "• No input device selected in System Settings\n\n" +
        "Try again: open the lid, check System Settings → Sound → Input, then press ▶ again.",
        12000   // stay visible 12 s so there's time to read
      );
      return;
    }
    if (data.status !== "ok") {
      new Notice(`⚠️ ${data.message || "unknown error"}`);
      return;
    }
    // Live progress indicator: poll /status and update one persistent Notice
    // through the stages (transcribing → cleaning → done). The transcript is
    // written to the note by the server when finished.
    // NOTE: Obsidian's Notice has no setMessage() — we update the DOM directly.
    const notice = new Notice("🎙 Stopped — starting transcription…", 0);
    const setMsg = (txt) => {
      // Neither notice.messageEl nor notice.hide() exist in this Obsidian build.
      // Update text via raw DOM, fall back to a new Notice if noticeEl is gone.
      if (notice.noticeEl) { notice.noticeEl.textContent = txt; }
      else { new Notice(txt, 4000); }
    };
    const labels = {
      transcribing: "⏳ Whisper: transcribing audio…",
      cleaning:     "🧹 Cleaning up text…",
    };
    const started = Date.now();
    while (Date.now() - started < 240000) {           // safety cap 4 min
      await new Promise((r) => setTimeout(r, 1500));
      let st;
      try { st = await (await fetch(`${TRANS_SERVER}/status`, { headers: authHeaders() })).json(); }
      catch { continue; }
      if (st.stage === "done") {
        setMsg(`✅ Transcript added under "${st.session || data.session_name}"`);
        break;
      }
      if (st.stage === "error") {
        setMsg("❌ Transcription failed — check the server log");
        break;
      }
      setMsg(labels[st.stage] || "⏳ Working…");
    }
    setTimeout(() => notice.noticeEl?.remove(), 4000);
    return;
  }

  let session = await (async () => {
    let cursorLine = null;
    try {
      const c = tp.file.cursor();
      if (c != null && c >= 0) {
        const raw = await tp.file.content;
        cursorLine = raw.substring(0, c).split("\n").length - 1;
      }
    } catch {}
    if (cursorLine == null) {
      const ed = app.workspace.activeEditor?.editor;
      if (ed) cursorLine = ed.getCursor().line;
    }
    if (cursorLine == null) return null;
    let content;
    try { content = await tp.file.content; } catch { content = app.workspace.activeEditor?.editor?.getValue() || ""; }
    const lines = content.split("\n");
    for (let i = cursorLine; i >= 0; i--) {
      const m = lines[i]?.match(/^#### (.+)/);
      if (m) return m[1].trim();
    }
    return null;
  })();
  if (!session) {
    const content = await tp.file.content;
    const talks = [...content.matchAll(/^#### (.+)/gm)].map(m => m[1].trim());
    if (talks.length === 1) {
      session = talks[0];
    } else if (talks.length > 1) {
      session = await tp.system.suggester(talks, talks);
    } else {
      session = await tp.system.prompt("Session name to record under:");
    }
  }
  if (!session) return;

  const startRes = await fetch(`${TRANS_SERVER}/record/start`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ note_path: notePath, session_name: session }),
  });
  const data = await startRes.json();
  if (data.status === "ok") {
    new Notice(`🎙 Recording started for "${session}" — press button again to stop`);
  } else if (data.status === "no_mic") {
    new Notice(
      "🎙❌ Unable to start recording\n\n" +
      "The microphone is not available.\n\n" +
      "Check that the computer is not closed or asleep, and that an input device is active in System Settings → Sound.",
      10000
    );
  } else {
    new Notice(`❌ Error: ${data.message || "unknown"}`);
  }
} catch (e) {
  new Notice("❌ Transcription error: " + (e?.message || e));
}
%>

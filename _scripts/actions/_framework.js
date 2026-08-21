// ============================================================================
//  _framework.js — launcher-agnostic core for the script-first action system
// ----------------------------------------------------------------------------
//  Operational actions live in _scripts/actions/<name>.js as plain async modules:
//
//      module.exports = async (ctx) => { ... };
//
//  where ctx = { app, obsidian, ui, sourceFile, args, + bound helpers }. Action
//  modules NEVER reference QuickAdd or Templater directly — they only touch ctx,
//  the Obsidian API, and the shared lib (templater-utils.js). The trigger layer is
//  swappable: today QuickAdd (see launcher.js) calls launch(); the _HOME.md
//  dashboard calls runScript() with a native UI; a future plugin would do the same.
//
//  The ui contract every launcher must provide:
//      ui.suggester(displayArr, valueArr, placeholder?) -> value | null
//      ui.prompt(header, placeholder?, value?)          -> string | null
//      ui.pickDate(label, default?)                     -> 'YYYY-MM-DD' | null
//      ui.confirm(header, text?)                        -> boolean
//      ui.notice(message)                               -> void
//
//  makeQuickAddUi() is the ONLY QuickAdd-aware code here; makeNativeUi() is fully
//  portable. Everything else is launcher-neutral.
// ============================================================================

function basePath(app) {
  const a = app.vault.adapter;
  return a.basePath || (a.getBasePath ? a.getBasePath() : "");
}

function escapeReg(s) {
  return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Cache-busted require so edits to a module take effect without reloading Obsidian.
function requireFresh(absPath) {
  try { delete require.cache[absPath]; } catch (e) {}
  return require(absPath);
}

function loadUtils(app) {
  return requireFresh(`${basePath(app)}/_scripts/lib/templater-utils.js`);
}

async function loadRegistry(app) {
  try {
    const raw = await app.vault.adapter.read("_scripts/lib/actions-registry.json");
    return JSON.parse(raw).categories;
  } catch (e) {
    return null;
  }
}

// ─── source-file resolution (replaces the fragile window._actionsSourceFile dance) ──
// In the script-first model the action runs inline in the trigger's own context, so
// the active file is reliably the user's note. We still honor an explicit override
// captured by the launcher at trigger time (ctx.sourceFile).
function resolveSourceFile(ctx) {
  if (ctx.sourceFile && ctx.sourceFile.path) return ctx.sourceFile;
  return ctx.app.workspace.getActiveFile();
}

// Resolve the source note and require it to live under `prefix` (e.g. "09_PEER_REVIEWS").
// On no/invalid source, falls back to a folder picker so the action never hard-fails
// for lack of an open note. Returns { file, base } or null (after a Notice).
async function requireSourceUnder(ctx, prefix, label, opts = {}) {
  const file = resolveSourceFile(ctx);
  if (file) {
    const m = file.path.match(new RegExp(`^(${escapeReg(prefix)}\\/[^/]+)`));
    if (m) return { file, base: m[1] };
  }
  const pick = opts.pick || ((c) => pickFolderUnder(c, prefix));
  const base = await pick(ctx);
  if (base) return { file: null, base };
  ctx.ui.notice(`❌ No ${label} selected — open a note under ${prefix}/… or pick a target.`);
  return null;
}

// Suggester over the immediate sub-folders of `prefix` (e.g. 09_PEER_REVIEWS/<MS>).
async function pickFolderUnder(ctx, prefix) {
  const re = new RegExp(`^${escapeReg(prefix)}\\/[^/]+$`);
  const folders = ctx.app.vault.getAllLoadedFiles()
    .filter((f) => f && f.children && re.test(f.path)) // TFolder has .children
    .map((f) => f.path)
    .sort();
  if (!folders.length) { ctx.ui.notice(`No folders found under ${prefix}/`); return null; }
  return await ctx.ui.suggester(folders, folders, `Pick a folder under ${prefix}/`);
}

// ─── dispatch ────────────────────────────────────────────────────────────────
// Run a migrated action module with a fully-built ctx (bound helpers included).
async function runScript(baseCtx, scriptName, args) {
  const { app, ui } = baseCtx;
  const ctx = Object.assign({}, baseCtx, { args: args || {} });
  ctx.resolveSourceFile = () => resolveSourceFile(ctx);
  ctx.requireSourceUnder = (prefix, label, opts) => requireSourceUnder(ctx, prefix, label, opts);
  ctx.pickFolderUnder = (prefix) => pickFolderUnder(ctx, prefix);

  const p = `${basePath(app)}/_scripts/actions/${scriptName}`;
  let mod;
  try { mod = requireFresh(p); }
  catch (e) { ui.notice(`❌ Action module not found: ${scriptName}`); console.error("[actions]", e); return; }

  const fn = (typeof mod === "function") ? mod : mod.run;
  if (typeof fn !== "function") { ui.notice(`❌ ${scriptName} does not export a function.`); return; }
  try { return await fn(ctx); }
  catch (e) { ui.notice(`❌ Action failed: ${e && e.message ? e.message : e}`); console.error("[actions]", e); }
}

// Unmigrated actions reuse the existing, working Templater deep-link (same path the
// dashboard already uses). Lets us migrate one registry entry at a time.
function dispatchLegacy(app, entry) {
  window._actionPreset = { file: entry.file, mode: entry.mode };
  app.commands.executeCommandById("templater-obsidian:_templates/actions.md");
}

async function runEntry(ctx, entry) {
  if (entry.script) return runScript(ctx, entry.script, { mode: entry.mode });
  return dispatchLegacy(ctx.app, entry);
}

// ─── entry point: category → action suggester, then dispatch ──────────────────
async function launch({ app, obsidian, ui }) {
  const sourceFile = app.workspace.getActiveFile(); // capture BEFORE any modal opens
  const categories = await loadRegistry(app);
  if (!categories) { ui.notice("❌ Cannot read action registry."); return; }

  const catKey = await ui.suggester(
    categories.map((c) => c.display),
    categories.map((c) => c.key),
    "What do you want to do?"
  );
  if (!catKey) return;
  const cat = categories.find((c) => c.key === catKey);
  if (!cat) return;

  const entry = await ui.suggester(
    cat.templates.map((t) => t.name),
    cat.templates,
    `${catKey} — choose an action`
  );
  if (!entry) return;

  return runEntry({ app, obsidian, ui, sourceFile }, entry);
}

// ─── UI adapters ──────────────────────────────────────────────────────────────
// QuickAdd-backed UI — the single QuickAdd-aware function in the framework.
function makeQuickAddUi({ quickAddApi, obsidian, app }) {
  const U = loadUtils(app);
  return {
    async suggester(display, values, placeholder) {
      try { const r = await quickAddApi.suggester(display, values); return r === undefined ? null : r; }
      catch (e) { return null; }
    },
    async prompt(header, placeholder, value) {
      try { const r = await quickAddApi.inputPrompt(header, placeholder, value); return r === undefined ? null : r; }
      catch (e) { return null; }
    },
    async pickDate(label, def) { return (await U.pickDate(label, def)) || null; },
    async confirm(header, text) { try { return await quickAddApi.yesNoPrompt(header, text); } catch (e) { return false; } },
    notice(msg) { new obsidian.Notice(msg); },
  };
}

// Portable native-Obsidian UI — used by the dashboard and any non-QuickAdd launcher.
function makeNativeUi({ app, obsidian }) {
  const U = loadUtils(app);
  return {
    suggester(display, values, placeholder) {
      return new Promise((resolve) => {
        let chosen = false;
        class S extends obsidian.SuggestModal {
          getSuggestions(q) {
            const ql = (q || "").toLowerCase();
            return display.map((d, i) => ({ d, i })).filter((o) => o.d.toLowerCase().includes(ql));
          }
          renderSuggestion(o, el) { el.setText(o.d); }
          onChooseSuggestion(o) { chosen = true; resolve(values[o.i]); }
          onClose() { if (!chosen) resolve(null); }
        }
        const m = new S(app);
        if (placeholder) m.setPlaceholder(placeholder);
        m.open();
      });
    },
    prompt(header, placeholder, value) {
      return new Promise((resolve) => {
        let done = false;
        const m = new obsidian.Modal(app);
        m.titleEl.setText(header || "Input");
        const input = m.contentEl.createEl("input", { type: "text" });
        input.style.width = "100%";
        if (placeholder) input.placeholder = placeholder;
        if (value) input.value = value;
        const submit = () => { if (done) return; done = true; const v = input.value; m.close(); resolve(v); };
        input.addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); submit(); } });
        const btn = m.contentEl.createEl("button", { text: "OK" });
        btn.style.marginTop = "0.6rem";
        btn.addEventListener("click", submit);
        const origClose = m.onClose.bind(m);
        m.onClose = () => { origClose(); if (!done) resolve(null); };
        m.open();
        setTimeout(() => input.focus(), 30);
      });
    },
    async pickDate(label, def) { return (await U.pickDate(label, def)) || null; },
    confirm(header, text) {
      return new Promise((resolve) => {
        let done = false;
        const m = new obsidian.Modal(app);
        m.titleEl.setText(header || "Confirm");
        if (text) m.contentEl.createEl("p", { text });
        const row = m.contentEl.createDiv();
        row.style.cssText = "display:flex;gap:.6rem;margin-top:.6rem;";
        const finish = (v) => { if (done) return; done = true; m.close(); resolve(v); };
        const yes = row.createEl("button", { text: "Yes" }); yes.addEventListener("click", () => finish(true));
        const no = row.createEl("button", { text: "No" }); no.addEventListener("click", () => finish(false));
        m.onClose = () => { if (!done) resolve(false); };
        m.open();
      });
    },
    notice(msg) { new obsidian.Notice(msg); },
  };
}

// Dashboard UI — renders into the _HOME.md slot beneath the dashboard via the
// dashboard's own showActionSuggester/showActionPrompt (exposed on window). Falls
// back to the floating native UI if those globals are absent (i.e. not on Home).
function makeDashboardUi({ app, obsidian }) {
  const _sugg = (typeof window !== "undefined") ? window.showActionSuggester : null;
  const _prompt = (typeof window !== "undefined") ? window.showActionPrompt : null;
  if (!_sugg || !_prompt) return makeNativeUi({ app, obsidian });
  const U = loadUtils(app);
  return {
    suggester(display, values, placeholder) {
      return new Promise((resolve) => {
        _sugg({
          title: placeholder || "Select",
          placeholder: placeholder || "Search…",
          items: display.map((d, i) => ({ label: d, value: values[i] })),
          onSelect: (v) => resolve(v),
          onCancel: () => resolve(null),
        });
      });
    },
    prompt(header, placeholder, value) {
      return new Promise((resolve) => {
        _prompt({
          title: header || "Input",
          defaultValue: value || "",
          onSubmit: (v) => resolve(v),
          onCancel: () => resolve(null),
        });
      });
    },
    pickDate(label, def) {
      return new Promise((resolve) => {
        _prompt({
          title: label || "Pick a date",
          defaultValue: def || U.today(),
          inputType: "date",
          onSubmit: (v) => resolve(v || null),
          onCancel: () => resolve(null),
        });
      });
    },
    confirm(header, text) {
      return new Promise((resolve) => {
        _sugg({
          title: header || "Confirm",
          placeholder: text || "",
          items: [{ label: "✅ Yes", value: true }, { label: "❌ No", value: false }],
          onSelect: (v) => resolve(!!v),
          onCancel: () => resolve(false),
        });
      });
    },
    notice(msg) { new obsidian.Notice(msg); },
  };
}

module.exports = {
  launch,
  runScript,
  runEntry,
  dispatchLegacy,
  loadRegistry,
  resolveSourceFile,
  requireSourceUnder,
  pickFolderUnder,
  makeQuickAddUi,
  makeNativeUi,
  makeDashboardUi,
  requireFresh,
  basePath,
};

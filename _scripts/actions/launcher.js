// ============================================================================
//  launcher.js — QuickAdd trigger for the script-first action system
// ----------------------------------------------------------------------------
//  This is the ONLY QuickAdd-specific file. QuickAdd loads it and calls
//  module.exports(params); we build a UI adapter from quickAddApi and hand off to
//  the launcher-agnostic core in _framework.js (loaded fresh each run so edits to
//  the framework / action modules take effect without reloading QuickAdd).
//
//  To replace QuickAdd with another launcher (a custom plugin, Templater, …),
//  reimplement only this file: construct a `ui` and call framework.launch().
//
//  Setup (one-time, in Obsidian):
//    1. QuickAdd settings → set the User Scripts folder to  _scripts/actions
//    2. Add a Macro choice named "Actions" → add a User Script step → launcher.js
//    3. Enable "Add to command palette" on the macro  →  command "QuickAdd: Actions"
//    4. Hotkeys → bind Cmd/Ctrl+T to "QuickAdd: Actions"
//       (and remove it from "Templater: _templates/actions.md")
// ============================================================================
module.exports = async (params) => {
  const app = params.app || window.app;
  const obsidian = params.obsidian || require("obsidian");
  const quickAddApi = params.quickAddApi;

  const base = app.vault.adapter.basePath || app.vault.adapter.getBasePath();
  const fwPath = `${base}/_scripts/actions/_framework.js`;
  try { delete require.cache[fwPath]; } catch (e) {}
  const fw = require(fwPath);

  const ui = fw.makeQuickAddUi({ quickAddApi, obsidian, app });
  return fw.launch({ app, obsidian, ui });
};

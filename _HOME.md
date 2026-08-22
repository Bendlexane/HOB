---
type: home
tags:
  - home
pinned: true
sticker: emoji//1f3e1
cssclasses:
  - home-sky
---


```dataviewjs
// Obsidian's window.localStorage is shared by every vault open in the app,
// so a name or a weather location set here would leak into any other vault.
// Namespace every dashboard key to this vault instead.
const VAULT_NS = `hob:${app.appId ?? app.vault.getName()}:`;
const store = {
  getItem:    k => window.localStorage.getItem(VAULT_NS + k),
  setItem:    (k, v) => window.localStorage.setItem(VAULT_NS + k, v),
  removeItem: k => window.localStorage.removeItem(VAULT_NS + k),
};

// The AI helper talks to whatever Ollama-compatible endpoint .env points at,
// so the model is a setting rather than something baked into this note.
let _envCache = null;
async function vaultEnv(){
  if (_envCache) return _envCache;
  try {
    const base = app.vault.adapter.basePath || app.vault.adapter.getBasePath();
    const U = require(`${base}/_scripts/lib/templater-utils.js`);
    _envCache = (await U.loadEnv()) || {};
  } catch (e) { _envCache = {}; }
  return _envCache;
}
const AI_DEFAULT_HOST  = 'http://localhost:11434';
const AI_DEFAULT_MODEL = 'gpt-oss:120b-cloud';
async function aiConfig(){
  const env = await vaultEnv();
  let host = AI_DEFAULT_HOST;
  if (env.AI_URL) { try { const u = new URL(env.AI_URL); host = u.origin; } catch (e) {} }
  return { host, model: env.AI_MODEL || AI_DEFAULT_MODEL };
}

const NAME_KEY = 'home-user-name';
let NAME = store.getItem(NAME_KEY) ?? 'Researcher';
const DAYS_AHEAD = 45;
const CFG_FILE = '.obsidian/plugins/obsidian-full-calendar/data.json';
const obsidian = require('obsidian');
const { requestUrl } = obsidian;

// Override Obsidian Notice class globally to forward notices to the dashboard Notification Center
if (!window._OriginalNotice) {
  window._OriginalNotice = obsidian.Notice || window.Notice;
  
  const NewNotice = class {
    constructor(message, duration) {
      if (message) {
        const msgStr = String(message).trim();
        // Skip purely transient or internal loading/thinking progress messages and show them natively
        const skipList = ["thinking", "loading", "preview of", "searching for", "cancelled"];
        const shouldSkip = skipList.some(s => msgStr.toLowerCase().includes(s));
        
        if (shouldSkip) {
          return new window._OriginalNotice(message, duration);
        }
        
        let title = "System Alert";
        let cleanMsg = msgStr;
        let sound = true;
        if (msgStr.startsWith("❌")) {
          title = "Error";
          cleanMsg = msgStr.replace(/^❌\s*/, "");
        } else if (msgStr.startsWith("✅")) {
          title = "Success";
          cleanMsg = msgStr.replace(/^✅\s*/, "");
        } else if (msgStr.startsWith("⚠️")) {
          title = "Warning";
          cleanMsg = msgStr.replace(/^⚠️\s*/, "");
        } else if (msgStr.startsWith("⏳")) {
          title = "Progress";
          cleanMsg = msgStr.replace(/^⏳\s*/, "");
          sound = false; // no sound for loading progress
        }
        
        (async () => {
          try {
            const notiPath = "06_PLANNING/kpis/notifications.json";
            let notifications = [];
            try {
              const raw = await app.vault.adapter.read(notiPath);
              notifications = JSON.parse(raw);
              if (!Array.isArray(notifications)) notifications = [];
            } catch(e) {
              notifications = [];
            }
            
            const newNoti = {
              id: String(Date.now() + Math.random()),
              title: title,
              message: cleanMsg,
              timestamp: Date.now(),
              read: false,
              sound: sound
            };
            
            notifications.push(newNoti);
            notifications = notifications.slice(-20);
            
            await app.vault.adapter.write(notiPath, JSON.stringify(notifications, null, 2));
            
            // Trigger a live refresh of the dashboard notifications list if it's currently rendered
            if (typeof window.__refreshDashboardNotifications === 'function') {
              window.__refreshDashboardNotifications();
            }
          } catch (err) {
            console.error("Failed to write Notice to dashboard", err);
          }
        })();
      }
    }
  };
  window.Notice = NewNotice;
  
  // Wrap window.require to return the custom Notice when require('obsidian') is called
  const originalRequire = window.require;
  if (originalRequire && !window._OriginalRequireWrapped) {
    window._OriginalRequireWrapped = true;
    window.require = function(moduleName) {
      const exports = originalRequire(moduleName);
      if (moduleName === 'obsidian' && exports) {
        return new Proxy(exports, {
          get(target, prop, receiver) {
            if (prop === 'Notice') {
              return window.Notice;
            }
            return Reflect.get(target, prop, receiver);
          }
        });
      }
      return exports;
    };
  }
}


const dayNames = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];
const monNames = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
const ymd = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;

const WEATHER_LOC_KEY = 'home-weather-location';
const getLoc = () => store.getItem(WEATHER_LOC_KEY) ?? '';

function greetFor(h) {
  if (h < 6) return 'Good night';
  if (h < 12) return 'Good morning';
  if (h < 18) return 'Good afternoon';
  if (h >= 18 && h < 21) return 'Good evening';
  return 'Good night';
}

// Inject custom styles to hide YAML/Frontmatter and make the page full width only for the home-sky note
let style = document.getElementById('home-custom-layout-styles');
if (!style) {
  style = document.createElement('style');
  style.id = 'home-custom-layout-styles';
  document.head.appendChild(style);
}
style.textContent = `
  .view-content:has(.home-sky) .metadata-container,
  .view-content:has(.home-sky) .frontmatter,
  .view-content:has(.home-sky) .cm-frontmatter,
  .view-content:has(.home-sky) .cm-embed-block:has(.frontmatter),
  .view-content:has(.home-sky) .inline-title,
  .view-content:has(.home-sky) .mk-inline-context,
  .view-content:has(.home-sky) .mk-cover-image-container {
    display: none !important;
  }
  /* In Live Preview, Obsidian wraps the dataviewjs block in an editable
     code-block frame with an "edit source" button. The dashboard is not
     meant to read as a code block, so strip the chrome in both modes. */
  .view-content:has(.home-sky) .cm-embed-block:not(:has(.frontmatter)),
  .view-content:has(.home-sky) .cm-preview-code-block,
  .view-content:has(.home-sky) .block-language-dataviewjs {
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    background: transparent !important;
    padding: 0 !important;
  }
  .view-content:has(.home-sky) .edit-block-button,
  .view-content:has(.home-sky) .cm-embed-block .edit-block-button {
    display: none !important;
  }
  .view-content:has(.home-sky) .markdown-preview-sizer,
  .view-content:has(.home-sky) .cm-sizer {
    max-width: 98% !important;
    width: 98% !important;
  }
  body button.home-quick-action-btn,
  body .home-quick-action-btn {
    display: flex !important;
    align-items: center !important;
    justify-content: center !important;
    gap: .6rem !important;
    padding: .75rem 1.5rem !important;
    border-radius: 12px !important;
    border: 1.5px solid rgba(255,255,255,0.18) !important;
    background: rgba(255,255,255,0.08) !important;
    background-color: rgba(255,255,255,0.08) !important;
    backdrop-filter: var(--vault-blur) !important;
    -webkit-backdrop-filter: var(--vault-blur) !important;
    color: var(--text-normal) !important;
    cursor: pointer !important;
    font-family: var(--font-interface) !important;
    white-space: nowrap !important;
    transition: box-shadow .18s ease, border-color .18s ease, background .18s ease, background-color .18s ease !important;
    box-shadow: none !important;
    flex: 1 !important;
    min-width: 140px !important;
  }
  body button.home-quick-action-btn:hover,
  body .home-quick-action-btn:hover {
    background: rgba(255,255,255,0.16) !important;
    background-color: rgba(255,255,255,0.16) !important;
    border-color: rgba(255,255,255,0.35) !important;
    box-shadow: 0 0 0 2px rgba(255,255,255,0.15) !important;
    color: var(--text-normal) !important;
  }
  body button.home-quick-action-btn:focus,
  body button.home-quick-action-btn:active,
  body .home-quick-action-btn:focus,
  body .home-quick-action-btn:active {
    background: rgba(255,255,255,0.12) !important;
    background-color: rgba(255,255,255,0.12) !important;
    border-color: rgba(255,255,255,0.25) !important;
    box-shadow: none !important;
    outline: none !important;
    color: var(--text-normal) !important;
  }
  
  /* Make Obsidian custom popover menu items more visible */
  body .menu {
    font-size: 0.8rem !important;
    padding: 0.35rem !important;
    border-radius: 10px !important;
  }
  body .menu-item {
    padding: 0.42rem 0.65rem !important;
    border-radius: 6px !important;
  }
  body .menu-item-title {
    font-size: 0.8rem !important;
  }
  /* Tooltip text styling */
  body .tooltip {
    font-size: 0.72rem !important;
    line-height: 1.4 !important;
    max-width: 250px !important;
    padding: 0.45rem 0.65rem !important;
    border-radius: 8px !important;
  }
`;

// Main wrapping container (max-width 100%, centered with padding)
const wrap = dv.container.createDiv();
wrap.style.cssText = 'max-width:100%;padding:0 2rem;margin:0 auto 1.5rem;font-family:var(--font-interface);color:var(--text-normal);';

// ─── TOP HEADER BLOCK (Greeting + Clock + Weather Forecast) ───
const banner = wrap.createDiv();
banner.style.cssText = 'position:relative;overflow:visible;padding:1rem 0;display:flex;flex-direction:column;';

const headerRow = banner.createDiv();
headerRow.style.cssText = 'position:relative;z-index:1;display:flex;align-items:center;justify-content:space-between;gap:1.5rem;flex:0 0 auto;';

// Left: Greeting Title
const leftHeader = headerRow.createDiv();
const title = leftHeader.createDiv();
title.style.cssText = 'font-size:2.2rem;font-weight:700;letter-spacing:-0.02em;margin-bottom:0.3rem;text-shadow:0 1px 8px rgba(0,0,0,0.35);font-family:var(--font-interface), sans-serif;';
const sub = leftHeader.createDiv();
sub.style.cssText = 'opacity:0.85;font-size:0.95rem;text-shadow:0 1px 6px rgba(0,0,0,0.3);cursor:pointer;';
const updateSubText = () => {
  const loc = getLoc();
  const vaultName = app.vault.getName();
  sub.setText(loc ? `${vaultName} · 📍 ${loc}` : `${vaultName} · 📍 Auto-detect`);
};
updateSubText();

title.style.cursor = 'pointer';
title.addEventListener('click', async () => {
  if (typeof window.showActionPrompt === 'function') {
    window.showActionPrompt({
      title: "Your name (shown in greetings)",
      defaultValue: NAME,
      onSubmit: (val) => {
        if (val && val.trim()) {
          NAME = val.trim();
          store.setItem(NAME_KEY, NAME);
        }
      }
    });
  }
});

sub.addEventListener('click', async () => {
  if (typeof window.showActionPrompt === 'function') {
    window.showActionPrompt({
      title: "Enter weather location (e.g. Rome, Paris, Pisa)",
      defaultValue: getLoc(),
      onSubmit: (val) => {
        if (val && val.trim()) {
          store.setItem(WEATHER_LOC_KEY, val.trim());
          updateSubText();
          loadWeather();
          const skyPlugin = app.plugins.getPlugin('sky-background');
          if (skyPlugin && typeof skyPlugin.loadWeather === 'function') {
            skyPlugin.loadWeather();
          }
        }
      }
    });
  }
});

// Right: Lining clock
const rightHeader = headerRow.createDiv();
rightHeader.style.cssText = 'text-align:right;flex:0 0 auto;';
const clock = rightHeader.createDiv();
clock.style.cssText = 'font-size:2.6rem;font-weight:700;font-family:\'Inter\', system-ui, sans-serif;font-variant-numeric:lining-nums tabular-nums;letter-spacing:0.02em;line-height:1;text-shadow:0 1px 8px rgba(0,0,0,0.35);';
const dateline = rightHeader.createDiv();
dateline.style.cssText = 'opacity:0.85;font-size:0.9rem;margin-top:0.35rem;text-shadow:0 1px 6px rgba(0,0,0,0.3);';

// Bottom header row (Weather on left, Notifications on right under the clock)
const headerBottomRow = banner.createDiv();
headerBottomRow.style.cssText = 'position:relative;z-index:1;display:flex;align-items:flex-start;gap:2rem;margin-top:1.25rem;flex-wrap:wrap;';

// Left column: weather, with the sticky notes stacked directly underneath it.
// Keeping them in a column means the notes sit beside the notification panel
// rather than below its full height.
const headerLeftCol = headerBottomRow.createDiv();
headerLeftCol.style.cssText = 'flex:1 1 320px;min-width:0;display:flex;flex-direction:column;';

// Weather cards row (inside bottom row)
const wx = headerLeftCol.createDiv();
wx.style.cssText = 'display:flex;gap:0.75rem;flex-wrap:wrap;flex:0 0 auto;align-items:stretch;';

// Sticky Notes slot (fills the gap between weather and notifications)
const stickySlot = headerLeftCol.createDiv();
stickySlot.className = 'home-banner-sticky-notes';
// Scrolls sideways rather than wrapping, so more notes never push the search
// bar down the page.
stickySlot.style.cssText = 'position:relative;z-index:4;display:none;margin-top:1rem;overflow-x:auto;overflow-y:hidden;padding-bottom:.35rem;';

// Notification Center slot (inside bottom row, float right, max width)
const notiSlot = headerBottomRow.createDiv();
notiSlot.className = 'home-banner-notifications';
notiSlot.style.cssText = 'position:relative;z-index:5;flex:0 1 480px;min-width:280px;max-width:480px;margin-left:auto;display:none;';

// Search Bar slot
const searchSlot = banner.createDiv();
searchSlot.className = 'home-banner-search';
searchSlot.style.cssText = 'position:relative;z-index:5;margin:2rem 0 2.5rem;flex:0 0 auto;';

// Inline AI Ask panel
const askSlot = banner.createDiv();
askSlot.className = 'home-banner-ask';
askSlot.style.cssText = 'position:relative;z-index:5;margin:-0.5rem 0 1.5rem;flex:0 0 auto;display:none;';

// ─── FIRST-RUN SETUP (name + weather location) ───
// Shown once, until the reader saves or skips. Both values live in
// localStorage and stay editable later by clicking the greeting or the
// location line under it.
const ONBOARD_KEY = 'home-onboarded';
if (!store.getItem(ONBOARD_KEY) && !store.getItem(NAME_KEY) && !getLoc()) {
  const ob = banner.createDiv();
  ob.style.cssText = 'position:relative;z-index:6;margin:0 0 1.5rem;background:var(--vault-glass-strong);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:1px solid var(--vault-glass-border);border-radius:16px;padding:1.1rem 1.3rem;box-shadow:0 10px 34px rgba(0,0,0,0.22);';

  const obHead = ob.createDiv();
  obHead.style.cssText = 'display:flex;align-items:center;gap:.5rem;margin-bottom:.35rem;';
  obHead.createSpan({text:'👋'}).style.fontSize = '1.15rem';
  obHead.createSpan({text:'Welcome to HOB'}).style.cssText = 'font-weight:700;font-size:1.05rem;';

  const obSub = ob.createDiv({text:'Two things and the dashboard is yours. You can change both later by clicking your name or the location under it.'});
  obSub.style.cssText = 'font-size:.82rem;color:var(--text-muted);margin-bottom:.85rem;line-height:1.5;';

  const obRow = ob.createDiv();
  obRow.style.cssText = 'display:flex;gap:.6rem;flex-wrap:wrap;align-items:center;';
  const inputCss = 'font-size:.85rem;padding:.45rem .75rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.05);color:var(--text-normal);outline:none;min-width:170px;';

  const obName = obRow.createEl('input');
  obName.setAttr('type','text'); obName.setAttr('placeholder','Your name');
  obName.style.cssText = inputCss;

  const obLoc = obRow.createEl('input');
  obLoc.setAttr('type','text'); obLoc.setAttr('placeholder','Weather location, e.g. Pisa');
  obLoc.style.cssText = inputCss;

  const obSave = obRow.createEl('button', {text:'Save'});
  obSave.style.cssText = 'font-size:.82rem;padding:.45rem 1.1rem;border-radius:9px;border:none;background:var(--interactive-accent);color:var(--text-on-accent);cursor:pointer;font-weight:600;';

  const obSkip = obRow.createEl('button', {text:'Skip'});
  obSkip.style.cssText = 'font-size:.8rem;padding:.45rem .8rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:transparent;color:var(--text-muted);cursor:pointer;';

  const obFoot = ob.createDiv();
  obFoot.style.cssText = 'font-size:.75rem;color:var(--text-faint);margin-top:.7rem;';
  obFoot.createSpan({text:'Next comes a short tour of the dashboard. For the setup commands, Ollama and git included, see '});
  const obLink = obFoot.createEl('a', {text:'GET STARTED'});
  obLink.style.cssText = 'color:var(--text-accent);cursor:pointer;text-decoration:none;';
  obLink.addEventListener('click', (ev) => {
    ev.preventDefault();
    app.workspace.openLinkText('GET STARTED', '', true);
  });
  obFoot.createSpan({text:'.'});

  const finish = () => {
    store.setItem(ONBOARD_KEY, '1');
    ob.remove();
    // The tour is how a new reader learns the dashboard, so lead into it
    // once, right after the two questions.
    if (!store.getItem(TOUR_KEY)) window.setTimeout(startTour, 350);
  };

  obSave.addEventListener('click', () => {
    const n = obName.value.trim();
    const l = obLoc.value.trim();
    if (n) { NAME = n; store.setItem(NAME_KEY, n); }
    if (l) {
      store.setItem(WEATHER_LOC_KEY, l);
      updateSubText();
      try { loadWeather(); } catch (e) {}
      const skyPlugin = app.plugins.getPlugin('sky-background');
      if (skyPlugin && typeof skyPlugin.loadWeather === 'function') skyPlugin.loadWeather();
    }
    finish();
  });

  obSkip.addEventListener('click', finish);
  obName.addEventListener('keydown', e => { if (e.key === 'Enter') obLoc.focus(); });
  obLoc.addEventListener('keydown', e => { if (e.key === 'Enter') obSave.click(); });
}

// ─── QUICK ACTIONS PANEL (Full Width) ───
const act = wrap.createDiv();
act.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:16px;padding:0.8rem 1.2rem;margin:1rem auto 1.5rem;display:flex;align-items:center;justify-content:space-between;gap:1.5rem;flex-wrap:wrap;';

// Action Suggester slot (below the quick actions bar)
const actionSuggesterSlot = wrap.createDiv();
actionSuggesterSlot.className = 'home-banner-action-suggester';
actionSuggesterSlot.style.cssText = 'position:relative;z-index:5;margin:-0.5rem 0 1.5rem;flex:0 0 auto;display:none;';

const actLeft = act.createDiv();
actLeft.style.cssText = 'display:flex;align-items:center;gap:.5rem;';
actLeft.createSpan({text:'⚡'}).style.fontSize = '1.15rem';
const TAGLINES = [
  'What do you want to create today?',
  `Feeling inspired, ${NAME}?`,
  'What shall we grow today?',
  `Ready to start something, ${NAME}?`,
  'What will you discover today?',
  `Where will your curiosity lead, ${NAME}?`,
  'What idea deserves your attention?',
  `Ready to make progress, ${NAME}?`,
  'What challenge will you tackle next?',
  'What knowledge will you build today?',
  `Time to turn ideas into results, ${NAME}.`,
  'What deserves a closer look?',
  `Ready to explore something new, ${NAME}?`,
  'What will move your research forward?',
  'What insight are you chasing?',
  `Where should we begin today, ${NAME}?`,
  'What story is your data telling?',
  `What will you uncover next, ${NAME}?`,
  'Ready to connect the dots?',
  `What breakthrough are you working toward, ${NAME}?`
];
actLeft.createSpan({text: TAGLINES[Math.floor(Math.random()*TAGLINES.length)]}).style.cssText = 'font-weight:600;font-size:0.95rem;white-space:nowrap;';

const actGrid = act.createDiv();
actGrid.style.cssText = 'display:flex;gap:1rem;align-items:center;flex-wrap:wrap;flex:1;justify-content:space-between;max-width:70%;';

// ─── THREE-COLUMN LAYOUT SYSTEM ───
const columnsGrid = wrap.createDiv();
columnsGrid.style.cssText = 'display:grid;grid-template-columns: 0.85fr 1.4fr 0.75fr;gap:1.5rem;align-items:start;margin-top:1rem;';

const col1 = columnsGrid.createDiv();
col1.style.cssText = 'display:flex;flex-direction:column;gap:1.5rem;';

const col2 = columnsGrid.createDiv();
col2.style.cssText = 'display:flex;flex-direction:column;gap:1.5rem;';

const col3 = columnsGrid.createDiv();
col3.style.cssText = 'display:flex;flex-direction:column;gap:1.5rem;';


// ─── COLUMN 1: KPI Analytics Panel ───
const kpiCard = col1.createDiv();
kpiCard.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:16px;padding:1.2rem 1.3rem;';

const kpiHead = kpiCard.createDiv();
kpiHead.style.cssText = 'display:flex;align-items:center;gap:.5rem;margin-bottom:1rem;';
kpiHead.createSpan({text:'📊'}).style.fontSize = '1.2rem';
kpiHead.createSpan({text:'KPI Analytics'}).style.cssText = 'font-weight:700;font-size:1.05rem;';
const kpiSub = kpiHead.createSpan({text:'· loading…'});
kpiSub.style.cssText = 'opacity:.8;font-size:.82rem;margin-left:auto;';

const kpiMetricsGrid = kpiCard.createDiv();
kpiMetricsGrid.style.cssText = 'display:grid;grid-template-columns:repeat(2,1fr);gap:.6rem;margin-bottom:1.2rem;';

const sparklinesContainer = kpiCard.createDiv();
sparklinesContainer.style.cssText = 'display:flex;flex-direction:column;gap:1rem;margin-bottom:1.2rem;border-t:0.5px solid var(--vault-glass-border);padding-top:1rem;';

const topicsContainer = kpiCard.createDiv();
topicsContainer.style.cssText = 'display:flex;flex-direction:column;gap:0.75rem;border-t:0.5px solid var(--vault-glass-border);padding-top:1rem;';





// ─── COLUMN 2: What's New? (RSS feeds) ───
const rssCard = col2.createDiv();
rssCard.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:16px;padding:1.2rem 1.3rem;display:flex;flex-direction:column;';

const rssHead = rssCard.createDiv();
rssHead.style.cssText = 'display:flex;align-items:center;gap:.6rem;margin-bottom:.9rem;';
rssHead.createSpan({text:'📚'}).style.fontSize = '1.4rem';
rssHead.createSpan({text:"What's new?"}).style.cssText = 'font-weight:700;font-size:1.15rem;';
const rssStatus = rssHead.createSpan({text:'· loading…'});
rssStatus.style.cssText = 'opacity:0.8;font-size:.85rem;';
const refreshBtn = rssHead.createEl('button', {text:'↻'});
refreshBtn.setAttr('title','Refresh');
refreshBtn.style.cssText = 'margin-left:auto;font-size:.9rem;padding:.2rem .6rem;border-radius:8px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.08);color:var(--text-normal);cursor:pointer;';

// Keyword search for PubMed
const ctl = rssCard.createDiv();
ctl.style.cssText = 'display:flex;gap:.5rem;align-items:center;margin-bottom:.7rem;';
const kwIcon = ctl.createSpan({text:'🔍'}); kwIcon.style.fontSize='.95rem';
const input = ctl.createEl('input');
input.setAttr('type','text'); input.setAttr('placeholder','PubMed keywords, e.g. your topic…');
input.style.cssText = 'flex:1;font-size:.85rem;padding:.4rem .7rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.04);color:var(--text-normal);outline:none;';
const applyBtn = ctl.createEl('button', {text:'Apply'});
applyBtn.style.cssText = 'font-size:.8rem;padding:.4rem .9rem;border-radius:9px;border:none;background:var(--interactive-accent);color:var(--text-on-accent);cursor:pointer;font-weight:600;';

// Journal toggle chips
const chips = rssCard.createDiv();
chips.style.cssText = 'display:flex;flex-wrap:wrap;gap:.4rem;margin-bottom:.6rem;';

// Add journal form
const addForm = rssCard.createDiv();
addForm.style.cssText = 'display:none;gap:.5rem;align-items:center;margin-bottom:1rem;flex-wrap:wrap;';
const nameIn = addForm.createEl('input');
nameIn.setAttr('type','text'); nameIn.setAttr('placeholder','Journal name');
nameIn.style.cssText = 'font-size:.82rem;padding:.35rem .6rem;border-radius:8px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.04);color:var(--text-normal);';
const issnIn = addForm.createEl('input');
issnIn.setAttr('type','text'); issnIn.setAttr('placeholder','ISSN — e.g. 2055-0278');
issnIn.style.cssText = 'font-size:.82rem;padding:.35rem .6rem;border-radius:8px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.04);color:var(--text-normal);width:120px;';
const addOk = addForm.createEl('button', {text:'Add'});
addOk.style.cssText = 'font-size:.78rem;padding:.35rem .8rem;border-radius:8px;border:none;background:var(--interactive-accent);color:var(--text-on-accent);cursor:pointer;font-weight:600;';
const addHint = addForm.createSpan({text:'Find the ISSN on the journal page (works via Crossref).'});
addHint.style.cssText = 'font-size:.72rem;color:var(--text-muted);display:block;width:100%;';
addOk.addEventListener('click', ()=>{
  const name = nameIn.value.trim(); const issn = issnIn.value.trim();
  if(!name || !/^\d{4}-\d{3}[\dxX]$/.test(issn)){ addHint.setText('Enter a name and a valid ISSN (NNNN-NNNN).'); addHint.style.color='var(--text-error)'; return; }
  const custom = getCustom();
  if(allFeeds().some(f=>f.name===name || f.issn===issn)){ addHint.setText('Already in the list.'); return; }
  const color = CR_PALETTE[custom.length % CR_PALETTE.length];
  custom.push({ name, color, type:'crossref', max:3, issn });
  store.setItem(CUSTOM_KEY, JSON.stringify(custom));
  const e = getEnabled(); e.add(name); store.setItem(ENABLED_KEY, JSON.stringify([...e]));
  nameIn.value=''; issnIn.value=''; addForm.style.display='none';
  renderChips(); run(false);
});

const rssGrid = rssCard.createDiv();
rssGrid.style.cssText = 'display:flex;flex-direction:column;gap:0.75rem;max-height:1160px;overflow-y:auto;padding-right:0.25rem;';


// ─── COLUMN 3: iCloud Calendar Panel ───
const cal = col3.createDiv();
cal.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:16px;padding:1.2rem 1.3rem;display:flex;flex-direction:column;';

const calHead = cal.createDiv();
calHead.style.cssText = 'display:flex;align-items:center;gap:.5rem;margin-bottom:.6rem;flex:0 0 auto;';
calHead.createSpan({text:'📅'}).style.fontSize = '1.2rem';
calHead.createSpan({text:'Calendar'}).style.cssText = 'font-weight:700;font-size:1.05rem;';
const calStatus = calHead.createSpan({text:'· loading…'});
calStatus.style.cssText = 'opacity:.8;font-size:.82rem;';
const calBody = cal.createDiv();
calBody.style.cssText = 'overflow-y:auto;flex:0 0 auto;max-height:360px;padding-right:.3rem;';


// ─── COLUMN 3: Vault Status Stats ───
const statusCard = col3.createDiv();
statusCard.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:16px;padding:1.2rem 1.3rem;';

const statusHead = statusCard.createDiv();
statusHead.style.cssText = 'display:flex;align-items:center;gap:.5rem;margin-bottom:1rem;';
statusHead.createSpan({text:'⚙'}).style.fontSize = '1.2rem';
statusHead.createSpan({text:'Vault Status'}).style.cssText = 'font-weight:700;font-size:1.05rem;';

const statusBody = statusCard.createDiv();
statusBody.style.cssText = 'display:flex;flex-direction:column;gap:0.6rem;';


// ─── COLUMN 3: AI Chatbot Card ───
const chatCard = col3.createDiv();
chatCard.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:16px;padding:1.2rem 1.3rem;display:flex;flex-direction:column;gap:0.75rem;';

const chatHead = chatCard.createDiv();
chatHead.style.cssText = 'display:flex;align-items:center;gap:.5rem;margin-bottom:.25rem;';
chatHead.createSpan({text:'🤖'}).style.fontSize = '1.2rem';
chatHead.createSpan({text:'Vault AI Helper'}).style.cssText = 'font-weight:700;font-size:1.05rem;';

const clearChatBtn = chatHead.createEl('button', {text:'Clear'});
clearChatBtn.style.cssText = 'margin-left:auto;font-size:.7rem;padding:.2rem .5rem;border-radius:6px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.08);color:var(--text-muted);cursor:pointer;';

const chatBody = chatCard.createDiv();
chatBody.style.cssText = 'display:flex;flex-direction:column;gap:0.5rem;max-height:220px;overflow-y:auto;padding-right:.25rem;font-size:0.8rem;';

const chatInputContainer = chatCard.createDiv();
chatInputContainer.style.cssText = 'display:flex;gap:.5rem;align-items:center;';
const chatInput = chatInputContainer.createEl('input');
chatInput.setAttr('type','text');
chatInput.setAttr('placeholder','Ask about implementation...');
chatInput.style.cssText = 'flex:1;font-size:.8rem;padding:.4rem .6rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.04);color:var(--text-normal);outline:none;';

const chatSendBtn = chatInputContainer.createEl('button', {text:'Send'});
chatSendBtn.style.cssText = 'font-size:.78rem;padding:.4rem .8rem;border-radius:9px;border:none;background:var(--interactive-accent);color:var(--text-on-accent);cursor:pointer;font-weight:600;';

// Chatbot functionality
let chatHistory = [];
const homePath = (dv.current() && dv.current().file) ? dv.current().file.path : '';

function appendMessage(role, text) {
  const msgDiv = chatBody.createDiv();
  msgDiv.style.cssText = 'max-width: 85%; padding: 0.5rem 0.75rem; border-radius: 12px; font-size: 0.78rem; line-height: 1.4;';
  
  if (role === 'user') {
    msgDiv.style.background = 'rgba(255,255,255,0.08)';
    msgDiv.style.alignSelf = 'flex-end';
    msgDiv.style.border = '0.5px solid rgba(255,255,255,0.1)';
    msgDiv.style.borderRadius = '12px 12px 0 12px';
    msgDiv.setText(text);
  } else if (role === 'assistant') {
    msgDiv.style.background = 'rgba(255,255,255,0.04)';
    msgDiv.style.alignSelf = 'flex-start';
    msgDiv.style.border = '0.5px solid var(--vault-glass-border)';
    msgDiv.style.borderRadius = '12px 12px 12px 0';
    
    const { MarkdownRenderer } = require('obsidian');
    try {
      MarkdownRenderer.render(app, text, msgDiv, homePath, dv.component);
    } catch(e) {
      msgDiv.setText(text);
    }
  } else if (role === 'system_info') {
    msgDiv.style.color = 'var(--text-muted)';
    msgDiv.style.alignSelf = 'center';
    msgDiv.style.fontSize = '0.72rem';
    msgDiv.style.fontStyle = 'italic';
    msgDiv.setText(text);
  }
  
  chatBody.scrollTo({ top: chatBody.scrollHeight, behavior: 'smooth' });
}

// Initial Greeting
appendMessage('assistant', "Hello! I am the Research Vault assistant. Feel free to ask me anything, I will help you to get thing done!");

async function handleSendMessage() {
  const text = chatInput.value.trim();
  if (!text) return;
  
  chatInput.value = '';
  appendMessage('user', text);
  chatHistory.push({ role: 'user', content: text });
  
  const thinkingDiv = chatBody.createDiv();
  thinkingDiv.style.cssText = 'max-width: 85%; padding: 0.5rem 0.75rem; border-radius: 12px 12px 12px 0; font-size: 0.78rem; align-self: flex-start; background: rgba(255,255,255,0.04); border: 0.5px solid var(--vault-glass-border); font-style: italic; color: var(--text-muted);';
  thinkingDiv.setText("thinking...");
  chatBody.scrollTo({ top: chatBody.scrollHeight, behavior: 'smooth' });
  
  const { host: AI_HOST, model: AI_MODEL } = await aiConfig();
  try {
    // The status document is optional. A vault that has not written one yet
    // should still get a usable assistant, not a failure blamed on Ollama.
    let statusText = '';
    try { statusText = await app.vault.adapter.read("_meta/IMPLEMENTATION_STATUS.md"); } catch (e) {}
    const sysPrompt = statusText
      ? `You are a helpful assistant for this research vault. Use the following implementation status document to answer the user's questions about the software, script execution schedules, and configuration. Respond in the same language as the user. Keep your responses concise, precise, and user-friendly.\n\n${statusText}`
      : `You are a helpful assistant for this research vault, built on the HOB toolkit. Answer questions about the vault's folders, templates, scripts and dashboard. Respond in the same language as the user. Keep your responses concise, precise, and user-friendly.`;

    const response = await requestUrl({
      url: `${AI_HOST}/api/chat`,
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: AI_MODEL,
        messages: [
          { role: 'system', content: sysPrompt },
          ...chatHistory
        ],
        stream: false
      })
    });
    
    thinkingDiv.remove();
    
    const data = JSON.parse(response.text);
    const reply = data.message.content;
    
    appendMessage('assistant', reply);
    chatHistory.push({ role: 'assistant', content: reply });
  } catch (err) {
    thinkingDiv.remove();
    const detail = String(err && (err.message || err));
    let msg;
    if (/ECONNREFUSED|Failed to fetch|net::ERR/i.test(detail)) {
      msg = `⚠️ No AI server answering at ${AI_HOST}.\n\nThe helper needs Ollama running locally. Install it from ollama.com, then run \`ollama pull ${AI_MODEL}\` once and \`ollama serve\`.`;
    } else if (/model|not found|404/i.test(detail)) {
      msg = `⚠️ Ollama is running but does not have the \`${AI_MODEL}\` model.\n\nRun \`ollama pull ${AI_MODEL}\`, or point AI_MODEL in the vault-root .env at a model you already have.`;
    } else {
      msg = `⚠️ The AI helper could not answer.\n\n${detail}`;
    }
    appendMessage('assistant', msg);
    console.error("Chatbot error:", err);
  }
}

chatSendBtn.addEventListener('click', handleSendMessage);
chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    handleSendMessage();
  }
});

clearChatBtn.addEventListener('click', () => {
  chatBody.empty();
  chatHistory = [];
  appendMessage('assistant', "Hello! I am the Research Vault assistant. Feel free to ask me anything, I will help you to get thing done!");
});



// ─── DYNAMIC VAULT STATUS FETCHING ───
function updateVaultStatus() {
  statusBody.empty();
  const totalNotes = app.vault.getMarkdownFiles().length;
  const activePlugins = Object.keys(app.plugins.plugins).length;
  
  let gitStatusVal = "● Error";
  let gitColor = "#eb5757"; // Red
  try {
    if (!navigator.onLine) {
      gitStatusVal = "● Offline";
      gitColor = "#eb5757"; // Red
    } else {
      const { execSync } = require('child_process');
      const vaultRoot = app.vault.adapter.getBasePath();
      try {
        execSync('git rev-parse --is-inside-work-tree', { cwd: vaultRoot, stdio: 'pipe' });
      } catch (notARepo) {
        // A vault downloaded as an archive, or never initialised, has no
        // history at all. Say that rather than showing a stale timestamp.
        gitStatusVal = "● Not versioned";
        gitColor = "#e0a030";
        throw notARepo;
      }
      const gitTime = execSync('git log -1 --format="%cd" --date=relative', { cwd: vaultRoot, stdio: 'pipe' }).toString().trim();
      gitStatusVal = `● ${gitTime}`;
      gitColor = "#27ae60"; // Vibrant Green
    }
  } catch (e) {
    if (gitStatusVal !== "● Not versioned") console.debug("Git status check failed", e);
  }

  let llmWikiStatus = "Never";
  try {
    const fs = require('fs');
    const path = require('path');
    const vaultRoot = app.vault.adapter.getBasePath();
    const configPath = path.join(vaultRoot, '.obsidian/plugins/llm-wiki/data.json');
    if (fs.existsSync(configPath)) {
      const wikiData = JSON.parse(fs.readFileSync(configPath, 'utf8'));
      if (wikiData && wikiData.lastExtractionRunIso) {
        const d = new Date(wikiData.lastExtractionRunIso);
        const diffMs = Date.now() - d.getTime();
        const diffMins = Math.round(diffMs / 60000);
        const diffHours = Math.round(diffMins / 60);
        const diffDays = Math.round(diffHours / 24);
        if (diffMins < 60) {
          llmWikiStatus = `${diffMins}m ago`;
        } else if (diffHours < 24) {
          llmWikiStatus = `${diffHours}h ago`;
        } else {
          llmWikiStatus = `${diffDays}d ago`;
        }
      }
    }
  } catch (e) {
    console.error("Failed to read LLM Wiki last ingest time", e);
  }
  
  const metrics = [
    { label: "Git Sync", value: gitStatusVal, color: gitColor },
    { label: "Total Notes", value: totalNotes.toLocaleString(), color: "var(--chart-3)" },
    { label: "Active Plugins", value: activePlugins.toLocaleString(), color: "var(--chart-4)" },
    { label: "Vault Root", value: "Research", color: "var(--chart-2)" },
    { label: "LLM Ingest", value: llmWikiStatus, color: "var(--chart-5)" }
  ];

  for(const m of metrics) {
    const row = statusBody.createDiv();
    row.style.cssText = 'display:flex;justify-content:space-between;align-items:center;font-size:0.8rem;';
    const lbl = row.createSpan({text: m.label});
    lbl.style.cssText = 'color:var(--text-muted);';
    const val = row.createSpan({text: m.value});
    val.style.cssText = `margin-left:auto;color:${m.color};font-weight:600;font-family:'Inter', sans-serif;font-variant-numeric:lining-nums tabular-nums;`;
  }
}
updateVaultStatus();


// ─── GOOGLE SEARCH & LLM WIKI CONNECTOR ───
(async () => {
  const { MarkdownRenderer, Notice } = require('obsidian');
  try{
    const md = "```search-bar\nonly search bar\nshow starred files\n```";
    const path = (dv.current() && dv.current().file) ? dv.current().file.path
               : (app.workspace.getActiveFile() ? app.workspace.getActiveFile().path : '');
    if (MarkdownRenderer.render) await MarkdownRenderer.render(app, md, searchSlot, path, dv.component);
    else await MarkdownRenderer.renderMarkdown(md, searchSlot, path, dv.component);
  }catch(e){ searchSlot.setText('⚠ search bar unavailable'); searchSlot.style.opacity='0.7'; return; }

  const isQuestion = (q) => {
    q = (q||'').trim(); if(!q) return false;
    if (q.endsWith('?')) return true;
    if (q.split(/\s+/).length >= 5) return true;
    return /^(how|what|why|where|when|who|which|whose|can|could|should|would|will|do|does|did|is|are|explain|summar(y|ise|ize)|come|cosa|che|perch[eé]|quando|dove|chi|quale|quali|qual|posso|puoi|spiega|riassumi)\b/i.test(q);
  };

  const attach = (inputEl) => {
    if (inputEl.dataset.askWired) return;
    inputEl.dataset.askWired = '1';

    let current = null;
    const askQuestion = (question) => {
      const p = app.plugins.plugins['llm-wiki'];
      if (!p || typeof p.queryInline !== 'function') { new Notice('LLM Wiki not available'); return; }
      if (current) { try{ current.cancel(); }catch(e){} current = null; }
      askSlot.empty();
      askSlot.style.display = 'block';

      const card = askSlot.createDiv();
      card.style.cssText = 'background:var(--vault-glass-strong);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:1px solid var(--vault-glass-border);color:var(--text-normal);border-radius:16px;padding:1rem 1.2rem;box-shadow:0 10px 34px rgba(0,0,0,0.22);';
      const head = card.createDiv();
      head.style.cssText = 'display:flex;align-items:center;gap:.5rem;margin-bottom:.55rem;';
      head.createSpan({text:'🔮'}).style.fontSize = '1.05rem';
      const qEl = head.createSpan({text:question});
      qEl.style.cssText = 'font-weight:700;font-size:.95rem;flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
      const statusEl = head.createSpan({text:'thinking…'});
      statusEl.style.cssText = 'font-size:.76rem;color:var(--text-muted);flex:0 0 auto;';
      const closeBtn = head.createEl('button', {text:'×'});
      closeBtn.setAttr('aria-label','Dismiss');
      closeBtn.style.cssText = 'flex:0 0 auto;border:none;background:transparent;color:var(--text-muted);font-size:1.25rem;line-height:1;cursor:pointer;padding:0 .15rem;';
      closeBtn.addEventListener('click', () => {
        if (current) { try{ current.cancel(); }catch(e){} current = null; }
        askSlot.empty(); askSlot.style.display = 'none';
      });
      const bodyEl = card.createDiv();
      bodyEl.style.cssText = 'font-size:.9rem;line-height:1.55;';
      const srcEl = card.createDiv();

      const path = (dv.current() && dv.current().file) ? dv.current().file.path : '';
      const startMs = Date.now();
      let answer = '';
      let rendering = false, dirty = false, timer = null;
      const doRender = async () => {
        if (rendering) { dirty = true; return; }
        rendering = true;
        bodyEl.empty();
        try { await MarkdownRenderer.render(app, answer || '…', bodyEl, path, dv.component); }
        catch(e){ bodyEl.setText(answer); }
        rendering = false;
        if (dirty) { dirty = false; doRender(); }
      };
      const schedule = () => { if (!timer) timer = window.setTimeout(() => { timer = null; doRender(); }, 90); };

      const renderSources = (srcs) => {
        srcEl.empty();
        if (!srcs || !srcs.length) return;
        const det = srcEl.createEl('details');
        det.style.cssText = 'margin-top:.85rem;';
        const sum = det.createEl('summary', {text:`Sources (${srcs.length})`});
        sum.style.cssText = 'cursor:pointer;font-size:.76rem;font-weight:600;color:var(--text-muted);';
        const list = det.createDiv();
        list.style.cssText = 'margin-top:.5rem;display:flex;flex-direction:column;gap:.25rem;';
        for (const s of srcs) {
          const name = (s.id||'').split('/').pop().replace(/\.md$/,'');
          const a = list.createEl('a', {text:name});
          a.style.cssText = 'font-size:.82rem;color:var(--text-accent);text-decoration:none;cursor:pointer;';
          a.addEventListener('click', (e) => { e.preventDefault(); app.workspace.openLinkText(s.id, '', false); });
        }
      };

      current = p.queryInline(question, {
        onChunk: (t) => { answer += t; schedule(); },
        onState: (s) => {
          if (s === 'loading') statusEl.setText('thinking…');
          else if (s === 'streaming') statusEl.setText('streaming…');
          else if (s === 'done') {
            if (timer) { clearTimeout(timer); timer = null; }
            doRender();
            statusEl.setText(`done · ${((Date.now()-startMs)/1000).toFixed(1)}s`);
            current = null;
          } else if (s === 'cancelled') {
            statusEl.setText('cancelled');
          } else if (s === 'error') {
            statusEl.setText('error'); current = null;
          }
        },
        onSources: (srcs) => renderSources(srcs),
        onError: (msg) => { statusEl.setText('error'); bodyEl.setText('⚠ ' + msg); current = null; },
      });

      inputEl.value = '';
      inputEl.dispatchEvent(new Event('input', {bubbles:true}));
    };

    window.__homeAsk = {
      isQuestion,
      ask: (q, el) => { if (el && el.dataset && el.dataset.askWired) askQuestion(q); },
    };

    const relabel = () => {
      const want = isQuestion(inputEl.value) ? '↵ Ask AI' : 'Enter to create';
      searchSlot.querySelectorAll('.suggestion-hotkey').forEach((el) => {
        if (el.textContent !== want) el.textContent = want;
      });
    };
    new MutationObserver(relabel).observe(searchSlot, { childList: true, subtree: true });
    inputEl.addEventListener('input', relabel);
  };

  const existing = searchSlot.querySelector('input');
  if (existing) { attach(existing); return; }
  const obs = new MutationObserver(() => {
    const el = searchSlot.querySelector('input');
    if (el) { obs.disconnect(); attach(el); }
  });
  obs.observe(searchSlot, {childList:true, subtree:true});
  window.setTimeout(() => obs.disconnect(), 10000);
})();


// ─── INLINE ACTION SUGGESTER CONNECTOR ───
function showActionSuggester({ title, placeholder, items, onSelect, onCancel }) {
  const slot = document.querySelector('.home-banner-action-suggester');
  if (!slot) return;
  slot.empty();
  slot.style.display = 'block';

  // Save state globally so we can recover it on Dataview re-render
  if (!window._activeActionState || window._activeActionState.title !== title) {
    window._activeActionState = {
      type: 'suggester',
      title,
      placeholder,
      items,
      onSelect: (val) => {
        window._activeActionState = null;
        window._activeActionStateRestore = null;
        onSelect(val);
      },
      onCancel: () => {
        window._activeActionState = null;
        window._activeActionStateRestore = null;
        if (onCancel) onCancel();
      },
      searchQuery: '',
      selectedIdx: 0
    };
  }

  const state = window._activeActionState;
  
  const card = slot.createDiv();
  card.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);color:var(--text-normal);border-radius:16px;padding:1.2rem 1.4rem;box-shadow:0 10px 34px rgba(0,0,0,0.22);display:flex;flex-direction:column;gap:0.75rem;';
  
  const head = card.createDiv();
  head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;';
  const titleEl = head.createSpan({text: title});
  titleEl.style.cssText = 'font-weight:700;font-size:1.05rem;';
  const closeBtn = head.createEl('button', {text: '×'});
  closeBtn.style.cssText = 'border:none;background:transparent;color:var(--text-muted);font-size:1.35rem;cursor:pointer;line-height:1;padding:0;';
  closeBtn.addEventListener('click', () => {
    slot.empty();
    slot.style.display = 'none';
    state.onCancel();
  });
  
  const searchContainer = card.createDiv();
  searchContainer.style.cssText = 'position:relative;';
  const searchInput = searchContainer.createEl('input');
  searchInput.setAttribute('type', 'text');
  searchInput.setAttribute('placeholder', placeholder);
  searchInput.style.cssText = 'width:100%;font-size:0.9rem;padding:0.55rem 0.8rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.04);color:var(--text-normal);outline:none;';
  searchInput.value = state.searchQuery;
  
  const listContainer = card.createDiv();
  listContainer.style.cssText = 'display:flex;flex-direction:column;gap:0.25rem;max-height:260px;overflow-y:auto;padding-right:0.25rem;margin-top:0.25rem;';
  
  let selectedIdx = state.selectedIdx;
  let filteredItems = items.filter(item => (item.searchText || item.label).toLowerCase().includes(state.searchQuery.toLowerCase()));
  
  function renderList() {
    listContainer.empty();
    if (filteredItems.length === 0) {
      listContainer.createDiv({text: 'No results found'}).style.cssText = 'color:var(--text-faint);font-style:italic;font-size:0.85rem;padding:0.5rem 0;text-align:center;';
      return;
    }
    
    // Safety check for selectedIdx bounds
    if (selectedIdx >= filteredItems.length) {
      selectedIdx = 0;
      state.selectedIdx = 0;
    }

    filteredItems.forEach((item, idx) => {
      const row = listContainer.createDiv();
      row.style.cssText = 'padding:0.5rem 0.75rem;border-radius:8px;font-size:0.85rem;cursor:pointer;transition:background 0.15s;display:flex;align-items:center;justify-content:space-between;';
      
      const lbl = row.createSpan({text: item.label});
      lbl.style.cssText = 'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1;';
      
      if (idx === selectedIdx) {
        row.style.background = 'var(--text-accent)';
        row.style.color = '#fff';
      } else {
        row.style.background = 'rgba(255,255,255,0.03)';
        row.style.color = 'var(--text-normal)';
        row.addEventListener('mouseenter', () => {
          selectedIdx = idx;
          state.selectedIdx = idx;
          renderList();
        });
      }
      
      row.addEventListener('click', () => {
        slot.empty();
        slot.style.display = 'none';
        state.onSelect(item.value);
      });
    });
  }
  
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.toLowerCase().trim();
    state.searchQuery = searchInput.value;
    filteredItems = items.filter(item => (item.searchText || item.label).toLowerCase().includes(q));
    selectedIdx = 0;
    state.selectedIdx = 0;
    renderList();
  });
  
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      selectedIdx = (selectedIdx + 1) % filteredItems.length;
      state.selectedIdx = selectedIdx;
      renderList();
      listContainer.children[selectedIdx]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      selectedIdx = (selectedIdx - 1 + filteredItems.length) % filteredItems.length;
      state.selectedIdx = selectedIdx;
      renderList();
      listContainer.children[selectedIdx]?.scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (filteredItems[selectedIdx]) {
        slot.empty();
        slot.style.display = 'none';
        state.onSelect(filteredItems[selectedIdx].value);
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      slot.empty();
      slot.style.display = 'none';
      state.onCancel();
    }
  });
  
  setTimeout(() => searchInput.focus(), 50);
  renderList();
}
window.showActionSuggester = showActionSuggester;

// ─── INLINE ACTION PROMPT CONNECTOR ───
function showActionPrompt({ title, defaultValue, multiLine, inputType, maxLength, onSubmit, onCancel }) {
  const slot = document.querySelector('.home-banner-action-suggester');
  if (!slot) return;
  slot.empty();
  slot.style.display = 'block';
  
  // Save state globally so we can recover it on Dataview re-render
  if (!window._activeActionState || window._activeActionState.title !== title) {
    window._activeActionState = {
      type: 'prompt',
      title,
      defaultValue,
      multiLine,
      inputType,
      maxLength,
      onSubmit: (val) => {
        window._activeActionState = null;
        window._activeActionStateRestore = null;
        onSubmit(val);
      },
      onCancel: () => {
        window._activeActionState = null;
        window._activeActionStateRestore = null;
        if (onCancel) onCancel();
      },
      searchQuery: defaultValue || ''
    };
  }

  const state = window._activeActionState;

  const card = slot.createDiv();
  card.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);color:var(--text-normal);border-radius:16px;padding:1.2rem 1.4rem;box-shadow:0 10px 34px rgba(0,0,0,0.22);display:flex;flex-direction:column;gap:0.75rem;';
  
  const head = card.createDiv();
  head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;';
  const titleEl = head.createSpan({text: title});
  titleEl.style.cssText = 'font-weight:700;font-size:1.05rem;';
  
  const closeBtn = head.createEl('button', {text: '×'});
  closeBtn.style.cssText = 'border:none;background:transparent;color:var(--text-muted);font-size:1.35rem;cursor:pointer;line-height:1;padding:0;';
  
  const handleCancel = () => {
    slot.empty();
    slot.style.display = 'none';
    state.onCancel();
  };
  closeBtn.addEventListener('click', handleCancel);
  
  const formContainer = card.createDiv();
  formContainer.style.cssText = 'display:flex;flex-direction:column;gap:0.75rem;position:relative;';
  
  let inputEl;
  if (multiLine) {
    inputEl = formContainer.createEl('textarea');
    inputEl.style.cssText = 'width:100%;min-height:100px;font-size:0.9rem;padding:0.55rem 0.8rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.04);color:var(--text-normal);outline:none;resize:vertical;font-family:inherit;';
  } else {
    inputEl = formContainer.createEl('input');
    inputEl.setAttribute('type', state.inputType || 'text');
    inputEl.style.cssText = 'width:100%;font-size:0.9rem;padding:0.55rem 0.8rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.04);color:var(--text-normal);outline:none;';
  }
  
  inputEl.value = state.searchQuery;
  inputEl.setAttribute('placeholder', 'Type here...');
  if (state.maxLength) inputEl.setAttribute('maxlength', String(state.maxLength));

  let counterEl = null;
  if (state.maxLength) {
    counterEl = formContainer.createDiv();
    counterEl.style.cssText = 'align-self:flex-end;font-size:0.72rem;color:var(--text-faint);margin-top:-0.4rem;';
    counterEl.setText(`${inputEl.value.length}/${state.maxLength}`);
  }
  
  // Update searchQuery on typing
  inputEl.addEventListener('input', () => {
    state.searchQuery = inputEl.value;
    if (counterEl) counterEl.setText(`${inputEl.value.length}/${state.maxLength}`);
  });

  const btnContainer = card.createDiv();
  btnContainer.style.cssText = 'display:flex;justify-content:flex-end;gap:0.5rem;';
  
  const submitBtn = btnContainer.createEl('button', {text: 'Submit'});
  submitBtn.style.cssText = 'border:none;background:var(--interactive-accent);color:var(--text-on-accent);font-size:0.85rem;padding:0.4rem 1rem;border-radius:6px;cursor:pointer;font-weight:600;transition:opacity 0.15s;';
  submitBtn.addEventListener('mouseenter', () => submitBtn.style.opacity = '0.9');
  submitBtn.addEventListener('mouseleave', () => submitBtn.style.opacity = '1');
  
  const cancelBtn = btnContainer.createEl('button', {text: 'Cancel'});
  cancelBtn.style.cssText = 'border:1px solid var(--vault-glass-border);background:transparent;color:var(--text-normal);font-size:0.85rem;padding:0.4rem 1rem;border-radius:6px;cursor:pointer;font-weight:600;transition:background 0.15s;';
  cancelBtn.addEventListener('mouseenter', () => cancelBtn.style.background = 'rgba(255,255,255,0.05)');
  cancelBtn.addEventListener('mouseleave', () => cancelBtn.style.background = 'transparent');
  cancelBtn.addEventListener('click', handleCancel);
  
  const submit = () => {
    const val = inputEl.value;
    slot.empty();
    slot.style.display = 'none';
    state.onSubmit(val);
  };
  
  submitBtn.addEventListener('click', submit);
  
  inputEl.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      e.preventDefault();
      handleCancel();
    } else if (e.key === 'Enter') {
      if (multiLine) {
        if (!e.shiftKey) {
          e.preventDefault();
          submit();
        }
      } else {
        e.preventDefault();
        submit();
      }
    }
  });
  
  setTimeout(() => inputEl.focus(), 50);
}
window.showActionPrompt = showActionPrompt;

// Hook into Templater's system modules (suggester and prompt) to show inputs inline under Quick Actions when on Home dashboard
(async () => {
  const templater = app.plugins.plugins['templater-obsidian'];
  if (templater) {
    while (!templater.templater?.functions_generator?.internal_functions?.modules_array) {
      await new Promise(r => setTimeout(r, 50));
    }
    const systemModule = templater.templater.functions_generator.internal_functions.modules_array.find(m => m.name === 'system');
    if (systemModule && systemModule.static_object) {
      // Hook suggester
      if (!systemModule.static_object._suggesterHooked) {
        systemModule.static_object._suggesterHooked = true;
        const originalSuggester = systemModule.static_object.suggester;
        
        systemModule.static_object.suggester = async function(text_items, items, throw_on_cancel, placeholder, limit, default_value) {
          const homeActive = document.querySelector('.home-banner-action-suggester') !== null;
          if (homeActive) {
            return new Promise((resolve, reject) => {
              const mappedItems = items.map((val, idx) => {
                const label = typeof text_items === 'function' ? text_items(val) : text_items[idx];
                return { label: label || String(val), value: val };
              });
              
              const runSuggester = () => {
                if (typeof window.showActionSuggester === 'function') {
                  window.showActionSuggester({
                    title: placeholder || "Select option",
                    placeholder: "Search options...",
                    items: mappedItems,
                    onSelect: (val) => {
                      resolve(val);
                    },
                    onCancel: () => {
                      if (throw_on_cancel) reject(new Error("Cancelled prompt"));
                      else resolve(null);
                    }
                  });
                }
              };
              
              runSuggester();
              
              window._activeActionStateRestore = runSuggester;
            });
          } else {
            return originalSuggester.call(this, text_items, items, throw_on_cancel, placeholder, limit, default_value);
          }
        };
      }

      // Hook prompt
      if (!systemModule.static_object._promptHooked) {
        systemModule.static_object._promptHooked = true;
        const originalPrompt = systemModule.static_object.prompt;
        
        systemModule.static_object.prompt = async function(prompt_text, default_value, throw_on_cancel, multi_line) {
          const homeActive = document.querySelector('.home-banner-action-suggester') !== null;
          if (homeActive) {
            return new Promise((resolve, reject) => {
              const runPrompt = () => {
                if (typeof window.showActionPrompt === 'function') {
                  window.showActionPrompt({
                    title: prompt_text || "Input value",
                    defaultValue: default_value,
                    multiLine: multi_line,
                    onSubmit: (val) => resolve(val),
                    onCancel: () => {
                      if (throw_on_cancel) reject(new Error("Cancelled prompt"));
                      else resolve(null);
                    }
                  });
                }
              };
              
              runPrompt();
              
              window._activeActionStateRestore = runPrompt;
            });
          } else {
            return originalPrompt.call(this, prompt_text, default_value, throw_on_cancel, multi_line);
          }
        };
      }
    }
  }
})();

// ─── DYNAMIC KPI ANALYTICS WIDGET GENERATOR ───
function drawSparklinePath(values, width, height) {
  if (values.length < 2) return '';
  const max = Math.max(...values, 1);
  const points = values.map((val, idx) => {
    const x = (idx / (values.length - 1)) * width;
    const y = height - 2 - (val / max) * (height - 4);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return `M ${points.join(' L ')}`;
}

async function renderKpiWidget() {
  try {
    const raw = await app.vault.adapter.read("06_PLANNING/kpis/kpi_data.json");
    const data = JSON.parse(raw);

    kpiSub.setText(`updated ${data.generated_at}`);

    // Render Stats Grid
    kpiMetricsGrid.empty();
    const metrics = [
      { label: "Papers Added", value: data.summary.total_papers_added, desc: "+30d total", color: "var(--chart-1)" },
      { label: "Annotations", value: data.summary.total_annotations, desc: "+30d total", color: "var(--chart-3)" },
      { label: "Words Written", value: data.summary.total_words_written, desc: "notes text", color: "var(--chart-4)" },
      { label: "Revisited Notes", value: data.summary.total_papers_revisited, desc: "deep study", color: "var(--chart-2)" }
    ];

    for(const m of metrics) {
      const card = kpiMetricsGrid.createDiv();
      card.style.cssText = 'background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:10px;padding:.5rem .7rem;';
      const label = card.createDiv({text: m.label});
      label.style.cssText = 'font-size:.65rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.02em;';
      
      const row = card.createDiv();
      row.style.cssText = 'display:flex;align-items:end;justify-content:space-between;margin-top:.2rem;';
      
      const val = row.createSpan({text: m.value.toLocaleString()});
      val.style.cssText = `font-size:1.35rem;font-weight:700;color:var(--text-normal);line-height:1;font-family:'Inter', sans-serif;font-variant-numeric:lining-nums tabular-nums;`;
      
      const desc = row.createSpan({text: m.desc});
      desc.style.cssText = 'font-size:.58rem;color:var(--text-faint);margin-left:auto;';
    }

    // Render Sparklines
    sparklinesContainer.empty();
    const dailyData = data.daily || [];
    const addedHistory = dailyData.map(d => d.papers_added_zotero || 0);
    const annotHistory = dailyData.map(d => d.annotations_total || 0);

    const charts = [
      { title: "Zotero Papers Added (30 days)", values: addedHistory, color: "var(--chart-1)", label: "Added" },
      { title: "Annotations Made (30 days)", values: annotHistory, color: "var(--chart-3)", label: "Annotations" }
    ];

    for(const c of charts) {
      const item = sparklinesContainer.createDiv();
      item.style.cssText = 'display:flex;flex-direction:column;gap:.25rem;';
      const titleSpan = item.createDiv({text: c.title});
      titleSpan.style.cssText = 'font-size:.75rem;font-weight:600;color:var(--text-muted);';

      const row = item.createDiv();
      row.style.cssText = 'display:flex;align-items:center;gap:.75rem;';

      const chartBox = row.createDiv();
      chartBox.style.cssText = 'flex:1;height:24px;position:relative;';
      
      const width = 200;
      const height = 24;
      const pathData = drawSparklinePath(c.values, width, height);

      const svgHtml = `<svg width="100%" height="100%" viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
        <path d="${pathData}" fill="none" stroke="${c.color}" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      </svg>`;
      chartBox.innerHTML = svgHtml;

      const rightLabel = row.createDiv();
      rightLabel.style.cssText = 'text-align:right;min-width:60px;';
      const sum = c.values.reduce((a,b)=>a+b,0);
      rightLabel.createDiv({text: sum.toLocaleString()}).style.cssText = `font-size:.9rem;font-weight:700;line-height:1;font-family:'Inter', sans-serif;font-variant-numeric:lining-nums tabular-nums;`;
      rightLabel.createDiv({text: c.label}).style.cssText = 'font-size:.58rem;color:var(--text-faint);text-transform:uppercase;';
    }

    // Render Reading Topics (Horizontal Bars)
    topicsContainer.empty();
    const topicsHead = topicsContainer.createDiv({text: "Top Reading Topics"});
    topicsHead.style.cssText = 'font-size:.78rem;font-weight:700;color:var(--text-normal);margin-bottom:.2rem;';

    const topicsList = data.topics || [];
    const maxRead = Math.max(...topicsList.map(t => t.papers_read || 1), 1);

    for(const t of topicsList.slice(0, 4)) {
      const tItem = topicsContainer.createDiv();
      tItem.style.cssText = 'display:flex;flex-direction:column;gap:.2rem;font-size:0.75rem;';
      
      const topInfo = tItem.createDiv();
      topInfo.style.cssText = 'display:flex;justify-content:space-between;color:var(--text-muted);';
      topInfo.createSpan({text: t.category}).style.textTransform = 'capitalize';
      
      const countLabel = topInfo.createSpan({text: `${t.papers_read} papers · ${t.annotations_made} annots`});
      countLabel.style.cssText = `margin-left:auto;font-size:.68rem;font-family:'Inter', sans-serif;font-variant-numeric:lining-nums tabular-nums;`;
      
      const barBg = tItem.createDiv();
      barBg.style.cssText = 'width:100%;height:5px;background:rgba(255,255,255,0.06);border-radius:9px;overflow:hidden;';
      const pct = ((t.papers_read / maxRead) * 100).toFixed(1);
      const barFill = barBg.createDiv();
      barFill.style.cssText = `height:100%;width:${pct}%;background:var(--text-accent);border-radius:9px;`;
    }

  } catch(e) {
    // No collected data yet. This is the expected state on a fresh vault,
    // so explain the next step instead of reporting a failure.
    kpiSub.setText("· nothing to show yet");
    console.debug("KPI card: no data yet", e);
    kpiMetricsGrid.empty();
    const hint = kpiMetricsGrid.createDiv();
    hint.style.cssText = 'font-size:.82rem;color:var(--text-muted);line-height:1.6;';
    hint.createDiv({text: 'Your numbers build up as you work.'}).style.cssText = 'font-weight:600;color:var(--text-normal);margin-bottom:.3rem;';
    hint.createDiv({text: 'This card tracks what you read, annotate and write. It fills in once the vault has a few days of activity to measure, collected nightly by the scheduler.'});
    const how = hint.createDiv();
    how.style.cssText = 'margin-top:.5rem;font-size:.76rem;color:var(--text-faint);';
    how.setText('To collect the first snapshot now, run _scripts/kpi/collector.py from the vault root.');
  }
}
renderKpiWidget();


// ─── VAULT ACTIONS REGISTRY picked loader ───
(async () => {
  const { Menu } = require('obsidian');
  let categories;
  try {
    categories = JSON.parse(await app.vault.adapter.read('_scripts/lib/actions-registry.json')).categories;
  } catch (e) {
    actGrid.setText('⚠ action registry unavailable'); actGrid.style.opacity = '0.7'; return;
  }
  const runAction = (t) => {
    if (t.script) {
      // Migrated action → run the launcher-agnostic module with the dashboard UI
      // (prompts render in the bar beneath the dashboard; no Templater/temp file).
      (async () => {
        const base = app.vault.adapter.basePath || app.vault.adapter.getBasePath();
        const fp = `${base}/_scripts/actions/_framework.js`;
        try { delete require.cache[fp]; } catch (e) {}
        const fw = require(fp);
        const obsidian = require('obsidian');
        const ui = fw.makeDashboardUi({ app, obsidian });
        await fw.runScript({ app, obsidian, ui, sourceFile: app.workspace.getActiveFile() }, t.script, { mode: t.mode });
      })();
      return;
    }
    if (t.file === "sticky-note") {
      if (typeof window.__addStickyNote === 'function') window.__addStickyNote();
      return;
    }
    if (t.file === "file-recover.md" && t.mode) {
      const { exec } = require('child_process');
      const vaultPath = app.vault.adapter.getBasePath();
      const { Notice } = require('obsidian');
      
      if (t.mode === "A") {
        new Notice("Searching deleted files...");
        exec(`git -C "${vaultPath}" log --diff-filter=D --name-only --oneline -80`, (err, stdout) => {
          if (err) { new Notice("Git log failed."); return; }
          const items = [];
          let currentHash = "", currentMsg = "";
          for (const line of stdout.trim().split('\n')) {
            if (!line.trim()) continue;
            if (/^[0-9a-f]{7,12} /.test(line)) {
              currentHash = line.slice(0, 7);
              currentMsg  = line.slice(8).trim();
            } else {
              items.push({ label: `📄 ${line.trim().split('/').pop()}   ←   ${currentHash} — ${currentMsg}`, value: { file: line.trim(), hash: currentHash, message: currentMsg } });
            }
          }
          showActionSuggester({
            title: "Recover Deleted File",
            placeholder: "Search deleted files...",
            items,
            onSelect: (val) => {
              window._actionPreset = { file: "file-recover.md", mode: "A", presetVal: val };
              app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
            }
          });
        });
      } else if (t.mode === "B" || t.mode === "C") {
        const lastFile = app.workspace.getLastOpenFiles().find(p => p !== "_HOME.md" && p !== "_HOME");
        if (!lastFile) { new Notice("❌ No active note found in recent history."); return; }
        const file = app.vault.getAbstractFileByPath(lastFile);
        new Notice(`Loading history for "${file.basename}"...`);
        exec(`git -C "${vaultPath}" log --oneline -40 -- "${lastFile}"`, (err, stdout) => {
          if (err) { new Notice("Git log failed."); return; }
          const commits = stdout.trim().split('\n').filter(Boolean).map(line => ({
            hash: line.slice(0, 7),
            message: line.slice(8).trim()
          }));
          const items = commits.map(c => ({ label: `🕐 ${c.hash} — ${c.message}`, value: c }));
          showActionSuggester({
            title: (t.mode === "B" ? "Restore Past Version" : "Preview Past Version") + ` — ${file.name}`,
            placeholder: "Search backup commits...",
            items,
            onSelect: (val) => {
              window._actionPreset = { file: "file-recover.md", mode: t.mode, presetVal: val, targetFile: lastFile };
              app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
            }
          });
        });
      } else if (t.mode === "D") {
        new Notice("Searching renamed files...");
        exec(`git -C "${vaultPath}" log --diff-filter=R --name-status --oneline -80`, (err, stdout) => {
          if (err) { new Notice("Git log failed."); return; }
          const items = [];
          let currentHash = "", currentMsg = "";
          for (const line of stdout.trim().split('\n')) {
            if (!line.trim()) continue;
            if (/^[0-9a-f]{7,12} /.test(line)) {
              currentHash = line.slice(0, 7);
              currentMsg  = line.slice(8).trim();
            } else if (/^R/.test(line)) {
              const parts = line.split('\t');
              if (parts.length >= 3) {
                items.push({
                  label: `📦 ${parts[1].trim().split('/').pop()} → ${parts[2].trim().split('/').pop()}   (${currentHash} — ${currentMsg})`,
                  value: { oldPath: parts[1].trim(), newPath: parts[2].trim(), hash: currentHash, message: currentMsg }
                });
              }
            }
          }
          showActionSuggester({
            title: "Recover Renamed File",
            placeholder: "Search renamed files...",
            items,
            onSelect: (val) => {
              window._actionPreset = { file: "file-recover.md", mode: "D", presetVal: val };
              app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
            }
          });
        });
      } else if (t.mode === "E") {
        new Notice("Loading backup list...");
        exec(`git -C "${vaultPath}" log --oneline -50`, (err, stdout) => {
          if (err) { new Notice("Git log failed."); return; }
          const commits = stdout.trim().split('\n').filter(Boolean).map(line => ({
            hash: line.slice(0, 7),
            message: line.slice(8).trim()
          }));
          const items = commits.map(c => ({ label: `🕐 ${c.hash} — ${c.message}`, value: c }));
          showActionSuggester({
            title: "Browse Backup Commit",
            placeholder: "Search backups...",
            items,
            onSelect: (val) => {
              window._actionPreset = { file: "file-recover.md", mode: "E", presetVal: val };
              app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
            }
          });
        });
      }
    } else if (t.file === "people-db.md" && t.mode === "edit") {
      const { Notice } = require('obsidian');
      new Notice("Loading collaborators...");
      app.vault.adapter.read("04_PEOPLE/collaborators/_people-db.json").then(raw => {
        const parsed = JSON.parse(raw);
        const items = parsed.people.map(p => ({ label: p.display_name, value: p.id, searchText: [p.display_name, ...(p.aliases || [])].filter(Boolean).join("  ") }));
        showActionSuggester({
          title: "Edit Collaborator",
          placeholder: "Search collaborator...",
          items,
          onSelect: (val) => {
            window._actionPreset = { file: "people-db.md", mode: "edit", presetVal: val };
            app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
          }
        });
      }).catch(e => {
        new Notice("Failed to load people database.");
      });
    } else if (t.file === "view-person.md") {
      const { Notice } = require('obsidian');
      new Notice("Loading collaborators...");
      app.vault.adapter.read("04_PEOPLE/collaborators/_people-db.json").then(raw => {
        const parsed = JSON.parse(raw);
        const items = parsed.people.map(p => ({ label: p.display_name, value: p.id, searchText: [p.display_name, ...(p.aliases || [])].filter(Boolean).join("  ") }));
        showActionSuggester({
          title: "View Collaborator Info",
          placeholder: "Search collaborator...",
          items,
          onSelect: (val) => {
            window._actionPreset = { file: "view-person.md", presetVal: val };
            app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
          }
        });
      }).catch(e => {
        new Notice("Failed to load people database.");
      });
    } else if (t.file === "file-recovery") {
      app.commands.executeCommandById('file-recovery:open');
    } else if (t.file === "idea.md") {
      // Gather all input inline on HOME *before* any template/temp-file runs, so
      // creating the actions temp file can't re-render this dashboard and wipe
      // the inline prompt. Hand off via presetVal — same pattern as the cases above.
      const projectsFolder = app.vault.getAbstractFileByPath("01_PROJECTS");
      let activeProjects = [];
      if (projectsFolder && projectsFolder.children) {
        activeProjects = projectsFolder.children
          .filter(f => f.children && f.name && !f.name.startsWith(".") && !f.name.startsWith("_"))
          .map(f => f.name);
      }
      const projectItems = ["— None", ...activeProjects].map(p => ({ label: p, value: p }));
      const structureItems = [
        { label: "1. Blank — Title and free space", value: 1 },
        { label: "2. Structured — Spark, Research Question, Methodology, Action Plan", value: 2 },
        { label: "3. Simplified — Summary, Next Steps, Status", value: 3 },
      ];

      const askPrompt = (opts) => new Promise((res) => showActionPrompt({ ...opts, onSubmit: res, onCancel: () => res(null) }));
      const askSuggest = (opts) => new Promise((res) => showActionSuggester({ ...opts, onSelect: res }));

      (async () => {
        const title = await askPrompt({ title: "Short idea title (kebab-case)" });
        if (!title) return;
        const proj = await askSuggest({ title: "Link to a project?", placeholder: "Search projects…", items: projectItems });
        const structure = await askSuggest({ title: "Choose a structure", placeholder: "Search layouts…", items: structureItems });
        window._actionPreset = {
          file: "idea.md",
          presetVal: {
            title,
            project: (proj && proj !== "— None") ? proj : null,
            structure: structure || 1,
          },
        };
        app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
      })();
    } else {
      // Guard: a legacy action whose template was removed (e.g. new-grant) must
      // not throw "Template not found" — show a clean notice instead.
      if (t.file && !app.vault.getAbstractFileByPath(`_scripts/templates/${t.file}`)) {
        new (require('obsidian').Notice)(`🚧 ${t.label || t.file} isn't implemented yet.`);
        return;
      }
      window._actionPreset = { file: t.file, mode: t.mode };
      app.commands.executeCommandById('templater-obsidian:_templates/actions.md');
    }
  };

  for (const c of categories) {
    const btn = actGrid.createEl('button');
    btn.className = 'home-quick-action-btn';
    btn.setAttr('title', c.hint || c.label);
    btn.createSpan({text:c.icon}).style.cssText = 'font-size:1rem !important;';
    btn.createSpan({text:c.label}).style.cssText = 'font-weight:500 !important;font-size:.78rem !important;line-height:1 !important;';
    
    btn.addEventListener('click', () => {
      if (c.templates && c.templates.length === 1) {
        runAction(c.templates[0]);
      } else {
        const menu = new Menu();
        menu.setUseNativeMenu(false);
        const { setTooltip } = require('obsidian');
        for (const t of c.templates) {
          menu.addItem((item) => {
            item.setTitle(`${t.icon ? t.icon + '  ' : ''}${t.label}`)
                .onClick(() => runAction(t));
            if (t.desc) {
              const el = item.dom || item.itemEl || item.el;
              if (el) {
                setTooltip(el, t.desc, { delay: 1000 });
              }
            }
          });
          if (t.separator) {
            menu.addSeparator();
          }
        }
        const r = btn.getBoundingClientRect();
        menu.showAtPosition({ x: r.left, y: r.bottom + 4 });
      }
    });
  }
})();


// ─── ZOTERO QUICK LAUNCH ───
const zBtn = actGrid.createEl('button');
zBtn.className = 'home-quick-action-btn';
zBtn.setAttr('title', 'Open Zotero (reference manager)');
const zIcon = zBtn.createEl('span');
zIcon.innerHTML = '<svg viewBox="0 0 32 32" width="30" height="30"><path d="m16.08 2a3.3 3.18 0 00-1.73.42l-9.7 5.41a3.3 3.18 0 00-1.65 2.76v10.82a3.3 3.18 0 001.65 2.76l9.7 5.4a3.3 3.18 0 003.3 0l9.7-5.4a3.3 3.18 0 001.65-2.76v-10.82a3.3 3.18 0 00-1.65-2.76l-9.7-5.4a3.3 3.18 0 00-1.57-.43z" fill="#e4e4e4"/><path d="M10.5 9.4h11l-11 13.1h11" fill="none" stroke="#a81717" stroke-width="3" stroke-linecap="square" stroke-linejoin="round"/></svg>';
zIcon.style.cssText = 'font-size:1.98rem;display:inline-flex;align-items:center;';
zBtn.createSpan({text:'Zotero'}).style.cssText = 'font-weight:500 !important;font-size:.78rem !important;line-height:1 !important;';
zBtn.addEventListener('click', () => {
  const { exec } = require('child_process');
  exec('open -a "Zotero"');
});



// ─── WHAT'S NEW? RSS FEEDS PIPELINE ───
const FEEDS = [
  { name:'bioRxiv · Plant Biology', color:'#e2574c', type:'xml', max:3,
    url:'https://connect.biorxiv.org/biorxiv_xml.php?subject=plant_biology' },
  // One journal ships as a worked example. Add your own with the "+" chip
  // in the What's new? card, or by copying this line with another ISSN.
  { name:'Nature Plants', color:'#3a7d44', type:'crossref', max:3, issn:'2055-0278' },
  // No default query. PubMed searches are topic choices, so anything shipped
  // here would pick a field on the reader's behalf. The feed appears once you
  // type keywords into the box on the card.
  { name:'PubMed', color:'#4a6fa5', type:'pubmed', max:3, query:'' },
];
const TTL_HOURS  = 6;
const CACHE_KEY  = 'home-rss-cache-v2';
const QUERY_KEY  = 'home-rss-query';
const ENABLED_KEY= 'home-rss-enabled';
const CUSTOM_KEY = 'home-rss-custom';
const REMOVED_KEY= 'home-rss-removed';
let CR_MAILTO = '';
try {
  const base = app.vault.adapter.basePath || app.vault.adapter.getBasePath();
  const U = require(`${base}/_scripts/lib/templater-utils.js`);
  const env = await U.loadEnv();
  CR_MAILTO = env.CROSSREF_MAILTO || '';
} catch (e) {}
if (!CR_MAILTO && !window.__crossrefMailtoWarned) {
  window.__crossrefMailtoWarned = true;
  const { Notice } = require('obsidian');
  new Notice('ℹ️ Set CROSSREF_MAILTO in the vault-root .env to enable the Crossref "new papers" feed.');
}
const CR_PALETTE = ['#c0392b','#16a085','#8e44ad','#2980b9','#d35400','#27ae60','#2c3e50','#e84393','#00897b','#5d4037'];
const PUBMED_DEF = (FEEDS.find(f=>f.type==='pubmed')||{}).query || '';
const DAYS_BACK  = 60;
const CUTOFF_MS  = DAYS_BACK*864e5;

const cutoffYMD  = () => { const d=new Date(Date.now()-CUTOFF_MS); return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`; };
const within     = it => { if(!it.date) return false; const t=new Date(it.date).getTime(); return !isNaN(t) && (Date.now()-t) <= CUTOFF_MS; };

const getCustom  = () => { try{ return JSON.parse(store.getItem(CUSTOM_KEY))||[]; }catch(e){ return []; } };
const getRemoved = () => { try{ return new Set(JSON.parse(store.getItem(REMOVED_KEY))); }catch(e){ return new Set(); } };
const allFeeds   = () => FEEDS.filter(f=>!getRemoved().has(f.name) && (f.type!=='crossref' || CR_MAILTO) && (f.type!=='pubmed' || getQuery())).concat(getCustom());
const getQuery   = () => store.getItem(QUERY_KEY) ?? PUBMED_DEF;
const getEnabled = () => { try{ return new Set(JSON.parse(store.getItem(ENABLED_KEY))); }catch(e){ return new Set(allFeeds().map(f=>f.name)); } };
const loadCache  = () => { try{ return JSON.parse(store.getItem(CACHE_KEY))||{}; }catch(e){ return {}; } };
const saveCache  = c => { try{ store.setItem(CACHE_KEY, JSON.stringify(c)); }catch(e){} };
const feedKey    = f => f.type==='pubmed' ? 'pubmed:'+getQuery() : f.type==='crossref' ? 'crossref:'+f.issn : 'xml:'+f.url;

const txt = (el, tag) => { const n = el.getElementsByTagName(tag); return n.length ? (n[0].textContent||'').trim() : ''; };
const txtAll = (el, tag) => Array.from(el.getElementsByTagName(tag)).map(n=>(n.textContent||'').trim()).filter(Boolean);

function relTime(d){
  if(!d || isNaN(d)) return '';
  const diff = (Date.now()-d.getTime())/1000;
  if(diff < 3600) return Math.max(1,Math.round(diff/60))+'m ago';
  if(diff < 86400) return Math.round(diff/3600)+'h ago';
  return Math.round(diff/86400)+'d ago';
}
function clean(s){
  return (s||'').replace(/<[^>]+>/g,'').replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/\s+/g,' ').trim();
}
function fmtName(s){
  s = (s||'').trim(); if(!s) return '';
  if(s.includes(',')){ const [sur,rest=''] = s.split(','); const i=rest.trim()[0]||''; return sur.trim()+(i?` ${i.toUpperCase()}.`:''); }
  const t = s.split(/\s+/);
  if(t.length===1) return t[0];
  const last = t[t.length-1];
  if(/^[A-Za-z]{1,4}$/.test(last) && last===last.toUpperCase()){
    return t.slice(0,-1).join(' ')+` ${last[0].toUpperCase()}.`;
  }
  return last+` ${t[0][0].toUpperCase()}.`;
}
function fmtAuthors(arr){
  if(!arr || !arr.length) return '';
  return fmtName(arr[0]) + (arr.length>1 ? ' et al.' : '');
}
function citation(it){
  const au = fmtAuthors(it.authors);
  let vp = '';
  if(it.volume){ vp = String(it.volume); if(it.issue) vp += `(${it.issue})`; if(it.pages) vp += `: ${it.pages}`; }
  else if(it.pages){ vp = it.pages; }
  const rt = relTime(it.date?new Date(it.date):null);
  const tail = [vp, rt].filter(Boolean).join(' · ');
  return [au, tail].filter(Boolean).join(', ');
}

async function fetchXml(feed){
  const res = await requestUrl({url:feed.url, throw:false});
  if(res.status<200 || res.status>=300) throw new Error('HTTP '+res.status);
  const doc = new DOMParser().parseFromString(res.text, 'text/xml');
  const out = [];
  const entries = doc.getElementsByTagName('entry');
  const items   = doc.getElementsByTagName('item');
  const nodes   = entries.length ? entries : items;
  for(let i=0;i<nodes.length && out.length<feed.max;i++){
    const it = nodes[i];
    const title = txt(it,'title'); if(!title) continue;
    let url = txt(it,'link');
    if(!url){ const l = it.getElementsByTagName('link')[0]; if(l) url = l.getAttribute('href')||''; }
    const dateStr = txt(it,'pubDate') || txt(it,'published') || txt(it,'updated') || txt(it,'date') || txt(it,'dc:date');
    let authors = txtAll(it,'dc:creator');
    if(!authors.length) authors = txtAll(it,'creator');
    if(!authors.length) authors = Array.from(it.getElementsByTagName('author')).map(a=>{ const n=a.getElementsByTagName('name')[0]; return n?n.textContent.trim():a.textContent.trim(); }).filter(Boolean);
    const sp = txt(it,'prism:startingPage'), ep = txt(it,'prism:endingPage');
    const pages = sp ? (sp + (ep?`-${ep}`:'')) : txt(it,'prism:pageRange');
    out.push({ title, url, date:dateStr?new Date(dateStr).toISOString():null, authors,
               volume:txt(it,'prism:volume'), issue:txt(it,'prism:number'), pages });
  }
  return out;
}

async function fetchPubmed(feed){
  const base = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/';
  const q = getQuery();
  const s = await requestUrl({url:`${base}esearch.fcgi?db=pubmed&retmode=json&sort=date&datetype=pdat&reldate=${DAYS_BACK}&retmax=${feed.max}&term=${encodeURIComponent(q)}`, throw:false});
  if(s.status<200||s.status>=300) throw new Error('HTTP '+s.status);
  const ids = (JSON.parse(s.text).esearchresult||{}).idlist||[];
  if(!ids.length) return [];
  const d = await requestUrl({url:`${base}esummary.fcgi?db=pubmed&retmode=json&id=${ids.join(',')}`, throw:false});
  if(d.status<200||d.status>=300) throw new Error('HTTP '+d.status);
  const r = JSON.parse(d.text).result||{};
  return ids.filter(id=>r[id]).map(id=>{
    const a = r[id];
    return { title:clean(a.title||''), url:`https://pubmed.ncbi.nlm.nih.gov/${id}/`,
             date:a.sortpubdate||a.pubdate||null, authors:(a.authors||[]).map(x=>x.name),
             volume:a.volume||'', issue:a.issue||'', pages:a.pages||'' };
  });
}

async function fetchCrossref(feed){
  const url = `https://api.crossref.org/journals/${feed.issn}/works`+
    `?filter=from-created-date:${cutoffYMD()}&sort=created&order=desc&rows=${feed.max}&mailto=${encodeURIComponent(CR_MAILTO)}`+
    `&select=title,author,volume,issue,page,published,created,DOI`;
  const res = await requestUrl({url, throw:false});
  if(res.status<200||res.status>=300) throw new Error('HTTP '+res.status);
  const items = ((JSON.parse(res.text).message||{}).items)||[];
  return items.map(a=>{
    const dp = ((a.published||{})['date-parts']||[[]])[0]||[];
    const cp = ((a.created||{})['date-parts']||[[]])[0]||[];
    const pD = dp.length ? new Date(dp[0],(dp[1]||1)-1,dp[2]||1) : null;
    const cD = cp.length ? new Date(cp[0],(cp[1]||1)-1,cp[2]||1) : null;
    let best = (pD&&cD) ? (pD>cD?pD:cD) : (pD||cD);
    if(best && best.getTime()>Date.now()) best = cD||pD;
    const date = best ? best.toISOString() : null;
    const authors = (a.author||[]).map(x=>`${x.family||''}, ${x.given||''}`.trim()).filter(s=>s!==',');
    return { title:clean((a.title||[''])[0]), url:a.DOI?`https://doi.org/${a.DOI}`:'#',
             date, authors, volume:a.volume||'', issue:a.issue||'', pages:a.page||'' };
  }).filter(it=>it.title);
}

async function getFeedItems(f, force){
  const key = feedKey(f);
  const cache = loadCache();
  if(!force && cache[key] && (Date.now()-cache[key].ts) < TTL_HOURS*3600e3) return cache[key].items.filter(within);
  const items = f.type==='pubmed' ? await fetchPubmed(f)
              : f.type==='crossref' ? await fetchCrossref(f)
              : await fetchXml(f);
  cache[key] = { ts:Date.now(), items };
  saveCache(cache);
  return items.filter(within);
}

function card(g){
  const c = rssGrid.createDiv();
  c.style.cssText = 'background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.07);border-radius:14px;overflow:hidden;margin-bottom:0.75rem;flex-shrink:0;';
  
  const ch = c.createDiv();
  ch.style.cssText = `display:flex;align-items:center;gap:.5rem;padding:.5rem .75rem;font-weight:700;font-size:.82rem;color:${g.color};background:${g.color}14;border-bottom:1px solid ${g.color}22;`;
  const dot = ch.createDiv(); dot.style.cssText = `width:8px;height:8px;border-radius:50%;background:${g.color};flex:0 0 auto;`;
  ch.createSpan({text:g.name});
  
  const list = c.createDiv(); list.style.cssText = 'padding:.3rem .5rem;';
  for(const it of g.items){
    const row = list.createDiv();
    row.style.cssText = 'padding:.4rem .45rem;border-radius:9px;margin-bottom:0.15rem;transition:background 0.2s ease;';
    row.addEventListener('mouseenter',()=>row.style.background='rgba(255,255,255,0.06)');
    row.addEventListener('mouseleave',()=>row.style.background='transparent');
    
    const a = row.createEl('a', {text:it.title, href:it.url||'#'});
    a.setAttr('target','_blank'); a.setAttr('rel','noopener');
    a.style.cssText = 'font-size:.8rem;font-weight:500;line-height:1.25;color:var(--text-normal);text-decoration:none;display:block;font-family:var(--font-interface), sans-serif;';
    
    const meta = row.createDiv({text:citation(it)});
    meta.style.cssText = 'font-size:.7rem;color:var(--text-muted);margin-top:.15rem;font-style:italic;';
  }
}

let runToken = 0;
async function run(force){
  const my = ++runToken;
  rssStatus.setText('· loading…');
  const active = allFeeds().filter(f=>getEnabled().has(f.name));
  let failed = 0;
  const results = await Promise.all(active.map(async f=>{
    try{ const items = await getFeedItems(f, force); return items.length?{name:f.name,color:f.color,items}:null; }
    catch(e){ failed++; return null; }
  }));
  if(my !== runToken) return;
  rssGrid.empty();
  const groups = results.filter(Boolean);
  if(!groups.length){ rssStatus.setText(failed?`· ⚠ ${failed} unavailable`:'· no papers'); rssGrid.createDiv({text:'No recent papers.'}).style.cssText='color:var(--text-muted);font-size:0.8rem;'; return; }
  for(const g of groups) card(g);
  const total = groups.reduce((n,g)=>n+g.items.length,0);
  rssStatus.setText(`· ${total} items · last ${DAYS_BACK}d${failed?`  ⚠ ${failed} unavailable`:''}`);
}

applyBtn.addEventListener('click', ()=>{ store.setItem(QUERY_KEY, input.value.trim()); renderChips(); run(true); });
input.addEventListener('keydown', e=>{ if(e.key==='Enter'){ store.setItem(QUERY_KEY, input.value.trim()); renderChips(); run(true); } });
refreshBtn.addEventListener('click', ()=>run(true));

function renderChips(){
  chips.empty();
  const enabled = getEnabled();
  const customNames = new Set(getCustom().map(f=>f.name));
  for(const f of allFeeds()){
    const on = enabled.has(f.name);
    const isCustom = customNames.has(f.name);
    const chip = chips.createEl('span');
    chip.style.cssText = `display:inline-flex;align-items:center;gap:.35rem;font-size:.7rem;font-weight:600;padding:.2rem .5rem;border-radius:999px;cursor:pointer;border:1.5px solid ${f.color};`+
      (on ? `background:${f.color};color:#fff;` : `background:transparent;color:var(--text-muted);opacity:.7;`);
    const lbl = chip.createSpan({text:f.name});
    lbl.setAttr('title','Click to show/hide');
    lbl.addEventListener('click', ()=>{
      const e = getEnabled();
      if(e.has(f.name)) e.delete(f.name); else e.add(f.name);
      store.setItem(ENABLED_KEY, JSON.stringify([...e]));
      renderChips(); run(false);
    });
    const x = chip.createSpan({text:'×'});
    x.style.cssText = `font-weight:800;font-size:.9rem;line-height:1;opacity:.85;border-radius:50%;padding:0 .12rem;`+(on?'':'color:var(--text-muted);');
    x.setAttr('title', isCustom?'Delete journal':'Remove journal (restorable)');
    x.addEventListener('click', ev=>{
      ev.stopPropagation();
      if(isCustom){
        store.setItem(CUSTOM_KEY, JSON.stringify(getCustom().filter(c=>c.name!==f.name)));
      } else {
        const r = getRemoved(); r.add(f.name); store.setItem(REMOVED_KEY, JSON.stringify([...r]));
      }
      const e = getEnabled(); e.delete(f.name); store.setItem(ENABLED_KEY, JSON.stringify([...e]));
      renderChips(); run(false);
    });
  }
  const add = chips.createEl('span', {text:'➕ Add journal'});
  add.style.cssText = 'font-size:.7rem;font-weight:600;padding:.2rem .55rem;border-radius:999px;cursor:pointer;border:1px dashed var(--background-modifier-border);color:var(--text-muted);';
  add.addEventListener('click', ()=>{ addForm.style.display = addForm.style.display==='none' ? 'flex' : 'none'; });
}
renderChips();
run(false);


// ─── WEATHER FORECAST PARSER ───
function wxEmoji(code){
  code = +code;
  if(code===113) return '☀️';
  if(code===116) return '⛅';
  if([119,122].includes(code)) return '☁️';
  if([143,248,260].includes(code)) return '🌫️';
  if([176,263,266,293,296,353].includes(code)) return '🌦️';
  if([299,302,305,308,356,359].includes(code)) return '🌧️';
  if([179,182,323,326,368,371].includes(code)) return '🌨️';
  if([227,230].includes(code)) return '❄️';
  if([200,386,389,392,395].includes(code)) return '⛈️';
  return '🌡️';
}

async function loadWeather(){
  try{
    const res = await requestUrl({url:`https://wttr.in/${encodeURIComponent(getLoc())}?format=j1`, throw:false});
    if(res.status<200 || res.status>=300) { wxFallback(); return; }
    const data = JSON.parse(res.text);
    wx.empty();
    const cur = data.current_condition && data.current_condition[0];
    
    // Main feels-like card
    if(cur){
      const c = wx.createDiv();
      c.style.cssText = 'display:flex;align-items:center;gap:0.75rem;background:var(--vault-glass-card);border:0.5px solid var(--vault-glass-border);border-radius:14px;padding:0.6rem 1rem;backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);';
      const em = c.createSpan({text:wxEmoji(cur.weatherCode)}); em.style.cssText='font-size:1.8rem;font-family:"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;';
      const box = c.createDiv();
      const tp = box.createDiv({text:`${cur.temp_C}°`});
      tp.style.cssText='font-weight:700;font-size:1.35rem;line-height:1.05;font-family:\'Inter\', system-ui, sans-serif;font-variant-numeric:lining-nums tabular-nums;';
      const ds = box.createDiv({text:`Now · feels ${cur.FeelsLikeC}°`});
      ds.style.cssText='font-size:0.7rem;color:var(--text-muted);font-family:\'Inter\', system-ui, sans-serif;font-variant-numeric:lining-nums tabular-nums;';
    }
    
    // 3 forecast day cards
    (data.weather||[]).slice(0, 3).forEach((d,i)=>{
      const date = new Date(d.date+'T00:00:00');
      const name = i===0 ? 'Today' : date.toLocaleDateString('en-US',{weekday:'short'});
      const code = (d.hourly && (d.hourly[4]||d.hourly[0]) || {}).weatherCode;
      
      const chip = wx.createDiv();
      chip.style.cssText = 'display:flex;flex-direction:column;align-items:center;gap:0.25rem;background:var(--vault-glass);border:0.5px solid var(--vault-glass-border);border-radius:14px;padding:0.55rem 0.85rem;min-width:76px;text-align:center;justify-content:space-between;';
      chip.createDiv({text:name}).style.cssText='font-size:0.7rem;color:var(--text-muted);font-weight:600;';
      chip.createDiv({text:wxEmoji(code)}).style.cssText='font-size:1.25rem;font-family:"Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji", sans-serif;';
      
      const temps = chip.createDiv({text:`${d.maxtempC}° / ${d.mintempC}°`});
      temps.style.cssText='font-size:0.7rem;font-family:\'Inter\', system-ui, sans-serif;font-variant-numeric:lining-nums tabular-nums;color:var(--text-normal);font-weight:600;';
    });
  }catch(e){ wxFallback(); }
}

// The weather service answers by IP when no location is set, but it also
// rate-limits. Either way, say so instead of leaving an empty gap.
function wxFallback(){
  wx.empty();
  const chip = wx.createDiv();
  chip.style.cssText = 'display:flex;align-items:center;gap:.5rem;background:var(--vault-glass);border:0.5px solid var(--vault-glass-border);border-radius:14px;padding:.6rem 1rem;cursor:pointer;';
  chip.createSpan({text:'🌡'}).style.fontSize = '1.1rem';
  const box = chip.createDiv();
  box.createDiv({text: getLoc() ? 'Weather unavailable' : 'Set your location'})
     .style.cssText = 'font-size:.8rem;font-weight:600;';
  box.createDiv({text: getLoc() ? 'Tap to retry' : 'Tap to choose a city'})
     .style.cssText = 'font-size:.68rem;color:var(--text-muted);';
  chip.addEventListener('click', () => { sub.click(); });
}
loadWeather();


// ─── ICLOUD CALDAV CALENDAR FETCH ───
function parseDT(left, val){
  const allDay = /VALUE=DATE\b/.test(left) || /^\d{8}$/.test(val);
  if(allDay) return { date:new Date(+val.slice(0,4), +val.slice(4,6)-1, +val.slice(6,8)), allDay:true };
  const m = val.match(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})(Z)?$/);
  if(!m) return null;
  const [,Y,Mo,D,H,Mi,S,Z] = m;
  const date = Z ? new Date(Date.UTC(+Y,+Mo-1,+D,+H,+Mi,+S)) : new Date(+Y,+Mo-1,+D,+H,+Mi,+S);
  return { date, allDay:false };
}
function parseICS(xml, source, out){
  const text = xml.replace(/&amp;/g,'&').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&#13;/g,'');
  const lines = text.replace(/\r\n[ \t]/g,'').replace(/\n[ \t]/g,'').split(/\r\n|\n|\r/);
  let cur = null;
  for(const line of lines){
    if(line === 'BEGIN:VEVENT'){ cur = {}; continue; }
    if(line === 'END:VEVENT'){
      if(cur && cur.start && cur.summary) out.push({...cur, color:source.color, cal:source.name});
      cur = null; continue;
    }
    if(!cur) continue;
    const idx = line.indexOf(':'); if(idx<0) continue;
    const lft = line.slice(0,idx), val = line.slice(idx+1);
    const key = lft.split(';')[0].toUpperCase();
    if(key==='SUMMARY') cur.summary = val.replace(/\\,/g,',').replace(/\\;/g,';').replace(/\\n/gi,' ');
    else if(key==='DTSTART') cur.start = parseDT(lft,val);
    else if(key==='DTEND') cur.end = parseDT(lft,val);
    else if(key==='LOCATION') cur.location = val.replace(/\\,/g,',');
  }
}

async function loadCalendar(){
  try{
    const cfg = JSON.parse(await app.vault.adapter.read(CFG_FILE));
    const sources = (cfg.calendarSources||[]).filter(s=>s.type==='caldav');
    const start = new Date(); start.setHours(0,0,0,0);
    const end = new Date(start); end.setDate(end.getDate()+DAYS_AHEAD);
    const fmt = d => d.toISOString().replace(/[-:]/g,'').replace(/\.\d{3}/,'');
    const reqBody =
`<?xml version="1.0" encoding="utf-8"?>
<c:calendar-query xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav">
 <d:prop><c:calendar-data><c:expand start="${fmt(start)}" end="${fmt(end)}"/></c:calendar-data></d:prop>
 <c:filter><c:comp-filter name="VCALENDAR"><c:comp-filter name="VEVENT">
  <c:time-range start="${fmt(start)}" end="${fmt(end)}"/>
 </c:comp-filter></c:comp-filter></c:filter>
</c:calendar-query>`;
    const events = [];
    await Promise.all(sources.map(async s => {
      try{
        const res = await requestUrl({
          url: s.homeUrl, method:'REPORT',
          headers:{
            'Authorization':'Basic '+btoa(s.username+':'+s.password),
            'Depth':'1','Content-Type':'application/xml; charset=utf-8'
          },
          body: reqBody, throw:false
        });
        if(res.status>=200 && res.status<300) parseICS(res.text, s, events);
      }catch(e){ /* skip */ }
    }));
    events.sort((a,b)=>a.start.date - b.start.date);
    calStatus.setText(`· ${events.length} events`);
    calBody.empty();
    if(!events.length){ calBody.setText('No events.'); calBody.style.opacity='0.8'; calBody.style.fontSize='0.8rem'; return; }

    const groups = {};
    for(const ev of events){ (groups[ymd(ev.start.date)] ||= []).push(ev); }
    const todayK = ymd(new Date());
    const tm = new Date(); tm.setDate(tm.getDate()+1); const tmK = ymd(tm);

    let first = true;
    for(const key of Object.keys(groups).sort()){
      const d = new Date(key+'T00:00:00');
      let label = `${dayNames[d.getDay()]} ${d.getDate()} ${monNames[d.getMonth()]}`;
      if(key===todayK) label='Today';
      else if(key===tmK) label='Tomorrow';

      const dh = calBody.createDiv();
      dh.style.cssText = `font-weight:700;font-size:.8rem;margin:${first?'0':'.8rem'} 0 .3rem;${key===todayK?'color:var(--text-accent);':'color:currentColor;'}`;
      dh.setText(label);
      first = false;

      for(const ev of groups[key]){
        const row = calBody.createDiv();
        row.style.cssText = 'display:flex;align-items:center;gap:.6rem;padding:.4rem .55rem;border-radius:10px;background:rgba(255,255,255,0.04);margin-bottom:.25rem;border:1px solid rgba(255,255,255,0.03);';
        const dot = row.createDiv();
        dot.style.cssText = `width:7px;height:7px;border-radius:50%;flex:0 0 auto;background:${ev.color||'#bbb'};box-shadow:0 0 6px ${ev.color||'#bbb'};`;
        
        const timeVal = ev.start.allDay ? 'All day' : ev.start.date.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:false});
        const t = row.createSpan({text: timeVal});
        t.style.cssText = 'font-family:\'Inter\', sans-serif;font-variant-numeric:lining-nums tabular-nums;font-size:.75rem;opacity:.8;min-width:60px;';
        
        const ti = row.createSpan({text: ev.summary});
        ti.style.cssText = 'font-size:.8rem;font-weight:600;font-family:var(--font-interface), sans-serif;';
        if(ev.location){
          const loc = row.createSpan({text:'· '+ev.location});
          loc.style.cssText='font-size:.7rem;opacity:.6;margin-left:auto;text-overflow:ellipsis;white-space:nowrap;overflow:hidden;max-width:100px;';
        }
      }
    }
  }catch(err){
    // Never surface err.message here. On a vault with no calendar configured
    // it is an ENOENT carrying the reader's absolute home path.
    console.debug('Calendar not available', err);
    calStatus.setText('· not connected');
    calBody.empty();
    const hint = calBody.createDiv();
    hint.style.cssText = 'font-size:.82rem;color:var(--text-muted);line-height:1.6;';
    hint.createDiv({text: 'No calendar connected yet.'}).style.cssText = 'font-weight:600;color:var(--text-normal);margin-bottom:.3rem;';
    hint.createDiv({text: 'Add your accounts under Settings, Community plugins, Full Calendar. CalDAV works with iCloud, Google and Fastmail.'});
  }
}
loadCalendar();


// ─── DYNAMIC FRONTEND NOTIFICATION CENTER ───
const NOTI_PATH = "06_PLANNING/kpis/notifications.json";
const SOUND_PREF_PATH = "06_PLANNING/kpis/sound_pref.json";
let _soundEnabled = true;

async function _loadSoundPref() {
  try {
    const raw = await app.vault.adapter.read(SOUND_PREF_PATH);
    _soundEnabled = JSON.parse(raw) !== false;
  } catch (e) {
    _soundEnabled = true;
  }
}
_loadSoundPref();

function playChime() {
  try {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) return;
    const ctx = new AudioContext();
    const now = ctx.currentTime;
    
    // Tone 1: High crisp note (E6 - 1318.51 Hz)
    const osc1 = ctx.createOscillator();
    const gain1 = ctx.createGain();
    osc1.type = 'sine';
    osc1.frequency.setValueAtTime(1318.51, now);
    
    // Tone 2: Warm fundamental (A5 - 880 Hz)
    const osc2 = ctx.createOscillator();
    const gain2 = ctx.createGain();
    osc2.type = 'sine';
    osc2.frequency.setValueAtTime(880, now);
    
    gain1.gain.setValueAtTime(0, now);
    gain1.gain.linearRampToValueAtTime(0.12, now + 0.01);
    gain1.gain.exponentialRampToValueAtTime(0.001, now + 0.5);
    
    gain2.gain.setValueAtTime(0, now);
    gain2.gain.linearRampToValueAtTime(0.20, now + 0.02);
    gain2.gain.exponentialRampToValueAtTime(0.001, now + 1.0);
    
    osc1.connect(gain1);
    gain1.connect(ctx.destination);
    
    osc2.connect(gain2);
    gain2.connect(ctx.destination);
    
    osc1.start(now);
    osc2.start(now);
    osc1.stop(now + 0.5);
    osc2.stop(now + 1.0);
  } catch (e) {
    console.error("Failed to play notification chime", e);
  }
}

async function updateNotifications() {
  const { Notice } = require('obsidian');
  try {
    let raw = null;
    try {
      raw = await app.vault.adapter.read(NOTI_PATH);
    } catch (e) {
      notiSlot.empty();
      notiSlot.style.display = 'none';
      return;
    }
    
    const notifications = JSON.parse(raw || "[]");
    const unread = notifications.filter(n => !n.read);
    
    let playSound = false;
    let modified = false;
    for (const n of unread) {
      if (n.sound) {
        playSound = true;
        n.sound = false;
        modified = true;
      }
    }
    
    if (modified) {
      await app.vault.adapter.write(NOTI_PATH, JSON.stringify(notifications, null, 2));
    }
    
    if (playSound && _soundEnabled) {
      playChime();
    }
    
    notiSlot.empty();
    notiSlot.style.display = 'block';
    
    const container = notiSlot.createDiv();
    container.style.cssText = 'background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:16px;padding:1rem 1.2rem;display:flex;flex-direction:column;gap:0.75rem;box-shadow:0 8px 32px rgba(0,0,0,0.15);';
    
    const head = container.createDiv();
    head.style.cssText = 'display:flex;align-items:center;justify-content:space-between;margin-bottom:0.25rem;';
    
    const headLeft = head.createDiv();
    headLeft.style.cssText = 'display:flex;align-items:center;gap:0.5rem;';
    const bellSpan = headLeft.createSpan({text: _soundEnabled ? '🔔' : '🔕'});
    bellSpan.style.cssText = 'font-size:1.15rem;cursor:pointer;transition:opacity 0.15s;';
    bellSpan.title = _soundEnabled ? 'Sound on — click to mute' : 'Sound off — click to enable';
    bellSpan.addEventListener('click', async (e) => {
      e.stopPropagation();
      _soundEnabled = !_soundEnabled;
      bellSpan.setText(_soundEnabled ? '🔔' : '🔕');
      bellSpan.title = _soundEnabled ? 'Sound on — click to mute' : 'Sound off — click to enable';
      await app.vault.adapter.write(SOUND_PREF_PATH, JSON.stringify(_soundEnabled));
    });
    headLeft.createSpan({text:'Notifications'}).style.cssText = 'font-weight:700;font-size:0.95rem;';
    
    if (unread.length > 0) {
      const dismissAllBtn = head.createEl('button', {text:'Dismiss All'});
      dismissAllBtn.style.cssText = 'font-size:0.75rem;padding:0.2rem 0.6rem;border-radius:6px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.08);color:var(--text-muted);cursor:pointer;font-weight:600;transition:all 0.2s;';
      dismissAllBtn.addEventListener('mouseenter', () => dismissAllBtn.style.background = 'rgba(255,255,255,0.15)');
      dismissAllBtn.addEventListener('mouseleave', () => dismissAllBtn.style.background = 'rgba(255,255,255,0.08)');
      dismissAllBtn.addEventListener('click', async () => {
        try {
          const latestRaw = await app.vault.adapter.read(NOTI_PATH);
          const latestNotis = JSON.parse(latestRaw || "[]");
          for (const item of latestNotis) {
            item.read = true;
          }
          await app.vault.adapter.write(NOTI_PATH, JSON.stringify(latestNotis, null, 2));
          updateNotifications();
        } catch (e) {
          console.error("Failed to dismiss all notifications", e);
        }
      });
    }
    
    const list = container.createDiv();
    list.style.cssText = 'display:flex;flex-direction:column;gap:0.5rem;max-height:calc(4 * 85px);overflow-y:auto;';
    
    if (unread.length === 0) {
      const noNoti = list.createDiv({text: 'No notifications'});
      noNoti.style.cssText = 'color:var(--text-faint);font-style:italic;font-size:0.8rem;text-align:center;padding:0.5rem 0;';
    } else {
      for (const n of unread) {
        const card = list.createDiv();
        card.style.cssText = 'background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:10px;padding:0.6rem 0.8rem;display:flex;align-items:center;justify-content:space-between;gap:1rem;';
        
        const content = card.createDiv();
        content.style.cssText = 'display:flex;flex-direction:column;gap:0.15rem;flex:1;';
        
        const titleRow = content.createDiv();
        titleRow.style.cssText = 'display:flex;align-items:center;gap:0.5rem;';
        titleRow.createSpan({text: n.title}).style.cssText = 'font-weight:600;font-size:0.85rem;color:var(--text-normal);';
        
        const timeDiff = Date.now() - n.timestamp;
        let timeLabel = '';
        if (timeDiff < 60000) {
          timeLabel = 'Just now';
        } else if (timeDiff < 3600000) {
          timeLabel = `${Math.floor(timeDiff / 60000)}m ago`;
        } else if (timeDiff < 86400000) {
          timeLabel = `${Math.floor(timeDiff / 3600000)}h ago`;
        } else {
          timeLabel = `${Math.floor(timeDiff / 86400000)}d ago`;
        }
        
        const timeSpan = titleRow.createSpan({text: timeLabel});
        timeSpan.style.cssText = 'font-size:0.7rem;color:var(--text-faint);font-family:\'Inter\', sans-serif;font-variant-numeric:lining-nums tabular-nums;';
        
        content.createDiv({text: n.message}).style.cssText = 'font-size:0.8rem;color:var(--text-muted);line-height:1.3;';
        
        if (n.detailed_log) {
          const details = content.createEl('details');
          details.style.cssText = 'margin-top:0.25rem;';
          const summary = details.createEl('summary', {text:'Show proposed changes'});
          summary.style.cssText = 'font-size:0.75rem;color:var(--text-accent);cursor:pointer;outline:none;';
          const logDiv = details.createDiv();
          logDiv.style.cssText = 'font-size:0.75rem;color:var(--text-muted);white-space:pre-wrap;font-family:var(--font-monospace),monospace;background:rgba(0,0,0,0.15);padding:0.4rem;border-radius:4px;margin-top:0.25rem;max-height:120px;overflow-y:auto;line-height:1.3;';
          logDiv.setText(n.detailed_log);
        }
        
        if (n.approve_cmd || n.reject_cmd) {
          const btnRow = content.createDiv();
          btnRow.style.cssText = 'display:flex;gap:0.4rem;margin-top:0.45rem;';

          const markRead = async (id) => {
            try {
              const latestRaw = await app.vault.adapter.read(NOTI_PATH);
              const latestNotis = JSON.parse(latestRaw || "[]");
              const found = latestNotis.find(x => x.id === id);
              if (found) {
                found.read = true;
                await app.vault.adapter.write(NOTI_PATH, JSON.stringify(latestNotis, null, 2));
                updateNotifications();
              }
            } catch (e) {
              console.error("Failed to mark notification as read", e);
            }
          };

          // Shared runner: exec a command, then mark the notification read on success.
          const runCmd = (cmd, btn, runningLabel, idleLabel, okMsg, failMsg) => {
            btn.disabled = true;
            btn.setText(runningLabel);
            const { exec } = require('child_process');
            const vaultRoot = app.vault.adapter.getBasePath();
            exec(cmd, { cwd: vaultRoot }, async (err, stdout, stderr) => {
              if (err) {
                new Notice(failMsg + " " + (stderr || err.message));
                btn.disabled = false;
                btn.setText(idleLabel);
              } else {
                new Notice(okMsg);
                // Wait 150ms for the notice IIFE to finish writing to the file
                await new Promise(r => setTimeout(r, 150));
                await markRead(n.id);
              }
            });
          };

          if (n.approve_cmd) {
            const approveText = n.approve_label || 'Approve';
            const approveRunningText = n.approve_running_label || 'Running…';
            const approveSuccessText = n.approve_success_msg || "✅ Approved action executed successfully!";
            
            const approveBtn = btnRow.createEl('button', {text: approveText});
            approveBtn.style.cssText = 'font-size:0.75rem;padding:0.25rem 0.6rem;border-radius:6px;border:none;background:var(--interactive-accent);color:var(--text-on-accent);cursor:pointer;font-weight:600;transition:opacity 0.15s;';
            approveBtn.addEventListener('mouseenter', () => approveBtn.style.opacity = '0.9');
            approveBtn.addEventListener('mouseleave', () => approveBtn.style.opacity = '1');
            approveBtn.addEventListener('click', (e) => {
              e.stopPropagation();
              runCmd(n.approve_cmd, approveBtn, approveRunningText, approveText, approveSuccessText, "❌ Action failed:");
            });
          }

          if (n.reject_cmd) {
            const rejectBtn = btnRow.createEl('button', {text:'Reject'});
            rejectBtn.style.cssText = 'font-size:0.75rem;padding:0.25rem 0.6rem;border-radius:6px;border:1px solid var(--vault-glass-border);background:transparent;color:var(--text-muted);cursor:pointer;font-weight:600;transition:all 0.15s;';
            rejectBtn.addEventListener('mouseenter', () => { rejectBtn.style.background = 'rgba(255,80,80,0.12)'; rejectBtn.style.color = 'var(--text-error, #e06c6c)'; });
            rejectBtn.addEventListener('mouseleave', () => { rejectBtn.style.background = 'transparent'; rejectBtn.style.color = 'var(--text-muted)'; });
            rejectBtn.addEventListener('click', (e) => {
              e.stopPropagation();
              runCmd(n.reject_cmd, rejectBtn, 'Rejecting…', 'Reject', "🗑️ Idea discarded.", "❌ Reject failed:");
            });
          }
        }
        
        const closeBtn = card.createEl('button', {text: '×'});
        closeBtn.setAttr('aria-label', 'Dismiss');
        closeBtn.style.cssText = 'border:none;background:transparent;color:var(--text-muted);font-size:1.25rem;line-height:1;cursor:pointer;padding:0.2rem;display:flex;align-items:center;justify-content:center;';
        closeBtn.addEventListener('click', async () => {
          await markRead(n.id);
        });
      }
    }
  } catch (e) {
    console.error("Failed to update notification center", e);
  }
}

window.__refreshDashboardNotifications = updateNotifications;
updateNotifications();
dv.component.registerInterval(window.setInterval(updateNotifications, 5000));


// ─── STICKY NOTES PANEL ───
const STICKY_PATH = "06_PLANNING/kpis/sticky-notes.json";
const STICKY_MAX = 3;
const STICKY_CHAR_LIMIT = 200;
const STICKY_COLS = 3;
const STICKY_CARD_W = 300;
const STICKY_CARD_H = 320;
const STICKY_GAP = 12;

function _formatStickyDate(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  return `${monNames[d.getMonth()]} ${d.getDate()}`;
}

async function _loadStickyNotes() {
  try {
    const raw = await app.vault.adapter.read(STICKY_PATH);
    const notes = JSON.parse(raw || "[]");
    return Array.isArray(notes) ? notes : [];
  } catch (e) {
    return [];
  }
}

async function _saveStickyNotes(notes) {
  try {
    await app.vault.adapter.write(STICKY_PATH, JSON.stringify(notes, null, 2));
  } catch (e) {
    console.error("Failed to save sticky notes", e);
  }
}

async function renderStickyNotes() {
  const notes = await _loadStickyNotes();
  stickySlot.empty();
  if (!notes.length) { stickySlot.style.display = 'none'; return; }
  stickySlot.style.display = 'block';

  const grid = stickySlot.createDiv();
  grid.style.cssText = `display:flex;gap:${STICKY_GAP}px;width:max-content;`;

  for (const note of notes) {
    const card = grid.createDiv();
    card.style.cssText = `background:var(--vault-glass-card);backdrop-filter:var(--vault-blur);-webkit-backdrop-filter:var(--vault-blur);border:0.5px solid var(--vault-glass-border);border-radius:14px;padding:1rem 1.1rem;flex:0 0 ${STICKY_CARD_W}px;height:${STICKY_CARD_H}px;display:flex;flex-direction:column;cursor:pointer;position:relative;box-shadow:0 4px 16px rgba(0,0,0,0.12);`;

    const closeBtn = card.createEl('button', {text:'×'});
    closeBtn.setAttr('aria-label','Delete note');
    closeBtn.style.cssText = 'position:absolute;top:0.3rem;right:0.4rem;border:none;background:transparent;color:var(--text-muted);font-size:1.25rem;line-height:1;cursor:pointer;padding:0.1rem;opacity:0.45;transition:opacity 0.15s;';
    closeBtn.addEventListener('mouseenter', () => closeBtn.style.opacity = '1');
    closeBtn.addEventListener('mouseleave', () => closeBtn.style.opacity = '0.45');
    closeBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      const latest = (await _loadStickyNotes()).filter(n => n.id !== note.id);
      await _saveStickyNotes(latest);
      renderStickyNotes();
    });

    const textEl = card.createDiv({text: note.text});
    textEl.style.cssText = 'font-size:0.9rem;line-height:1.45;white-space:pre-wrap;word-break:break-word;color:var(--text-normal);margin-top:0.3rem;flex:1;overflow-y:auto;padding-right:0.3rem;';

    const dateEl = card.createDiv({text: _formatStickyDate(note.createdAt)});
    dateEl.style.cssText = 'font-size:0.65rem;color:var(--text-faint);align-self:flex-end;';

    card.addEventListener('click', () => {
      if (typeof window.showActionPrompt !== 'function') return;
      window.showActionPrompt({
        title: 'Edit Quick Note',
        defaultValue: note.text,
        multiLine: true,
        maxLength: STICKY_CHAR_LIMIT,
        onSubmit: async (val) => {
          const trimmed = (val || '').trim().slice(0, STICKY_CHAR_LIMIT);
          const latest = await _loadStickyNotes();
          const idx = latest.findIndex(n => n.id === note.id);
          if (idx === -1) return;
          if (!trimmed) {
            latest.splice(idx, 1);
          } else {
            latest[idx].text = trimmed;
          }
          await _saveStickyNotes(latest);
          renderStickyNotes();
        }
      });
    });
  }
}
renderStickyNotes();

async function _pushDashboardNotification(title, message) {
  try {
    let notifications = [];
    try {
      const raw = await app.vault.adapter.read(NOTI_PATH);
      notifications = JSON.parse(raw);
      if (!Array.isArray(notifications)) notifications = [];
    } catch (e) {
      notifications = [];
    }
    notifications.push({
      id: String(Date.now() + Math.random()),
      title,
      message,
      timestamp: Date.now(),
      read: false,
      sound: true
    });
    notifications = notifications.slice(-20);
    await app.vault.adapter.write(NOTI_PATH, JSON.stringify(notifications, null, 2));
    if (typeof window.__refreshDashboardNotifications === 'function') {
      window.__refreshDashboardNotifications();
    }
  } catch (err) {
    console.error("Failed to push dashboard notification", err);
  }
}

async function addStickyNote() {
  const latest = await _loadStickyNotes();
  if (latest.length >= STICKY_MAX) {
    await _pushDashboardNotification("Warning", "Post-it limit reached. Remove some if you want to create another one.");
    return;
  }
  if (typeof window.showActionPrompt !== 'function') return;
  window.showActionPrompt({
    title: 'New Quick Note',
    defaultValue: '',
    multiLine: true,
    maxLength: STICKY_CHAR_LIMIT,
    onSubmit: async (val) => {
      const trimmed = (val || '').trim().slice(0, STICKY_CHAR_LIMIT);
      if (!trimmed) return;
      const current = await _loadStickyNotes();
      if (current.length >= STICKY_MAX) {
        await _pushDashboardNotification("Warning", "Post-it limit reached. Remove some if you want to create another one.");
        return;
      }
      current.push({ id: String(Date.now() + Math.random()), text: trimmed, createdAt: Date.now() });
      await _saveStickyNotes(current);
      renderStickyNotes();
    }
  });
}
window.__addStickyNote = addStickyNote;



// ─── GUIDED TOUR ───
// A first-run walkthrough of the dashboard. Orientation lives here, where the
// thing being explained is on screen; the setup commands stay in GET STARTED,
// where they can be copied.
const TOUR_KEY = 'home-tour-done';

const TOUR_STEPS = [
  { get: () => title, side: 'bottom',
    head: 'Start here',
    body: 'The greeting is clickable. Click your name to change it, and the line underneath to set the city used for weather.' },

  { get: () => document.querySelector('.mk-space-body') || document.querySelector('.nav-files-container'), side: 'right',
    head: 'Folders are stages, not subjects',
    body: 'The numbers order the workflow. A note lives where the work currently is, and moves on as it matures. Click a folder to open its hub note.',
    list: [
      ['00_STAGING',     'The inbox. Daily notes, downloads, raw ideas. Nothing stays here.'],
      ['01_PROJECTS',    'One folder per active project. Where the day-to-day work happens.'],
      ['02_GRANTS',      'Proposals moving through writing, submitted, active, archive.'],
      ['03_KNOWLEDGE',   'Literature, concepts, methods, protocols. What the AI indexes.'],
      ['04_PEOPLE',      'Students, collaborators, and the coauthor registry. No science here.'],
      ['05_ADMIN',       'Bureaucracy, missions, certificates, CV material.'],
      ['06_PLANNING',    'KPIs, monthly plans, annual reports.'],
      ['07_INNOVATION',  'Changes to the system itself. Retrospectives, tech radar.'],
      ['08_TEACHING',    'Courses, seminars, teaching materials.'],
      ['09_PEER_REVIEWS','Reviews you are doing for journals. Gitignored by default.'],
      ['99_ARCHIVE',     'Published projects, moved here automatically.'],
    ] },

  { get: () => searchSlot, side: 'bottom',
    head: 'One bar, two jobs',
    body: 'Type part of a filename to jump straight to it. Type a question and press Enter to ask the AI about your notes instead.' },

  { get: () => act, side: 'bottom',
    head: 'Vault Actions',
    body: 'Each button opens a menu of templates. They do not just create a file, they build the folders, the frontmatter and the links, so the structure stays consistent without you thinking about it.',
    list: [
      ['📓 Notes',       'Post-it, idea, lab note, protocol.'],
      ['📄 Publications','New project, journal submission round, LaTeX abstract.'],
      ['🔍 Peer Review', 'A review workspace, and further rounds on it.'],
      ['💰 Grants',      'A new grant, tracked through its lifecycle.'],
      ['✈️ Missions',    'Conference or fieldwork workspace.'],
      ['⚙️ System',      'PDF to markdown, audio transcription, LaTeX export, file recovery, collaborators.'],
      ['Z Zotero',       'Opens your reference manager.'],
    ] },

  { get: () => kpiCard, side: 'right',
    head: 'KPI Analytics',
    body: 'What you read, annotate and write, collected nightly once the scheduler is installed. Empty until the vault has some activity to measure.' },

  { get: () => rssCard, side: 'top',
    head: "What's new?",
    body: 'Recent papers from bioRxiv, PubMed, and any journal you add by ISSN with the + chip. One journal ships as a worked example.' },

  { get: () => cal, side: 'left',
    head: 'Calendar',
    body: 'Your own calendars, over CalDAV. Add the accounts under Settings, Community plugins, Full Calendar. Nothing is configured out of the box.' },

  { get: () => chatCard, side: 'left',
    head: 'The AI helper',
    body: 'Ask questions about the vault itself. It needs Ollama running locally, which is the one part HOB cannot set up for you. GET STARTED walks through it.' },

  { get: () => statusCard, side: 'left',
    head: 'Vault Status',
    body: 'Whether the automations ran, and whether the vault is under version control. A clone is not versioned until you point it at a remote of your own.' },

  { get: () => null,
    head: 'That is the tour',
    body: 'GET STARTED in the vault root has the setup details, Ollama and git versioning included. You can replay this tour any time from the Vault Status card.' },
];

function startTour(){
  if (document.getElementById('hob-tour')) return;
  let i = 0;

  const ov = document.body.createDiv();
  ov.id = 'hob-tour';
  ov.style.cssText = 'position:fixed;inset:0;z-index:9999;';

  const ring = ov.createDiv();
  ring.style.cssText = 'position:absolute;border-radius:14px;box-shadow:0 0 0 9999px rgba(8,10,20,0.66);pointer-events:none;border:1.5px solid rgba(255,255,255,0.5);';

  const tip = ov.createDiv();
  tip.style.cssText = 'position:absolute;width:360px;max-height:80vh;overflow-y:auto;background:var(--vault-glass-strong, rgba(30,34,52,0.97));backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);border:1px solid var(--vault-glass-border, rgba(255,255,255,0.18));border-radius:16px;padding:1rem 1.15rem;box-shadow:0 16px 48px rgba(0,0,0,0.45);color:var(--text-normal);';

  const finish = () => {
    store.setItem(TOUR_KEY, '1');
    ov.remove();
    window.removeEventListener('keydown', onKey);
    window.removeEventListener('resize', place);
    window.removeEventListener('scroll', place, true);
  };
  const onKey = e => {
    if (e.key === 'Escape') { e.preventDefault(); finish(); }
    else if (e.key === 'ArrowRight' || e.key === 'Enter') { e.preventDefault(); go(i + 1); }
    else if (e.key === 'ArrowLeft') { e.preventDefault(); go(i - 1); }
  };
  window.addEventListener('keydown', onKey);
  // Recompute on every scroll and resize. Measuring once is what puts the
  // highlight on the wrong element when anything moves underneath it.
  window.addEventListener('resize', place);
  window.addEventListener('scroll', place, true);
  ov.addEventListener('click', ev => { if (ev.target === ov) finish(); });

  let target = null;

  function place(){
    const vw = window.innerWidth, vh = window.innerHeight;
    const tw = tip.offsetWidth, th = tip.offsetHeight, gap = 14, pad = 8;

    if (!target || !target.isConnected) {
      ring.style.width = '0px'; ring.style.height = '0px';
      ring.style.top = (vh / 2) + 'px'; ring.style.left = (vw / 2) + 'px';
      tip.style.top = Math.max(10, (vh - th) / 2) + 'px';
      tip.style.left = ((vw - tw) / 2) + 'px';
      return;
    }

    const r = target.getBoundingClientRect();
    ring.style.top    = (r.top - pad) + 'px';
    ring.style.left   = (r.left - pad) + 'px';
    ring.style.width  = (r.width + pad * 2) + 'px';
    ring.style.height = (r.height + pad * 2) + 'px';

    // Try the preferred side, then its opposite, then whatever fits. The card
    // must never sit on top of the thing it is describing.
    const fits = {
      bottom: vh - r.bottom - gap >= th,
      top:    r.top - gap >= th,
      right:  vw - r.right - gap >= tw,
      left:   r.left - gap >= tw,
    };
    const opposite = { bottom:'top', top:'bottom', right:'left', left:'right' };
    const pref = TOUR_STEPS[i].side || 'bottom';
    const side = fits[pref] ? pref
               : fits[opposite[pref]] ? opposite[pref]
               : (['bottom','top','right','left'].find(s => fits[s]) || pref);

    let top, left;
    if (side === 'right')     { left = r.right + gap;    top = r.top; }
    else if (side === 'left') { left = r.left - tw - gap; top = r.top; }
    else if (side === 'top')  { left = r.left; top = r.top - th - gap; }
    else                      { left = r.left; top = r.bottom + gap; }

    tip.style.top  = Math.min(Math.max(top, 10), Math.max(10, vh - th - 10)) + 'px';
    tip.style.left = Math.min(Math.max(left, 10), Math.max(10, vw - tw - 10)) + 'px';
  }

  function go(n){
    if (n < 0) return;
    if (n >= TOUR_STEPS.length) { finish(); return; }
    i = n;
    const step = TOUR_STEPS[i];
    target = (() => { try { return step.get(); } catch (e) { return null; } })();

    tip.empty();
    const h = tip.createDiv({ text: step.head });
    h.style.cssText = 'font-weight:700;font-size:1rem;margin-bottom:.4rem;';
    const b = tip.createDiv({ text: step.body });
    b.style.cssText = 'font-size:.83rem;line-height:1.55;color:var(--text-muted);';

    if (step.list) {
      const ul = tip.createDiv();
      ul.style.cssText = 'display:flex;flex-direction:column;gap:.3rem;margin-top:.7rem;padding-top:.7rem;border-top:1px solid var(--vault-glass-border, rgba(255,255,255,0.14));';
      for (const [label, desc] of step.list) {
        const row = ul.createDiv();
        row.style.cssText = 'font-size:.76rem;line-height:1.45;';
        row.createSpan({ text: label }).style.cssText = 'font-weight:700;color:var(--text-normal);';
        row.createSpan({ text: '  ' + desc }).style.cssText = 'color:var(--text-muted);';
      }
    }

    const bar = tip.createDiv();
    bar.style.cssText = 'display:flex;align-items:center;gap:.5rem;margin-top:.9rem;';
    bar.createSpan({ text: `${i + 1} / ${TOUR_STEPS.length}` })
       .style.cssText = 'font-size:.72rem;color:var(--text-faint);margin-right:auto;';
    const mkBtn = (label, primary) => {
      const btn = bar.createEl('button', { text: label });
      btn.style.cssText = primary
        ? 'font-size:.8rem;padding:.35rem .9rem;border-radius:8px;border:none;background:var(--interactive-accent);color:var(--text-on-accent);cursor:pointer;font-weight:600;'
        : 'font-size:.78rem;padding:.35rem .7rem;border-radius:8px;border:1px solid var(--vault-glass-border, rgba(255,255,255,0.18));background:transparent;color:var(--text-muted);cursor:pointer;';
      return btn;
    };
    mkBtn('Skip').addEventListener('click', finish);
    if (i > 0) mkBtn('Back').addEventListener('click', () => go(i - 1));
    mkBtn(i === TOUR_STEPS.length - 1 ? 'Done' : 'Next', true)
      .addEventListener('click', () => go(i + 1));

    // Jump without animation, then measure on the next two frames, once the
    // browser has settled the new scroll offset and the card's own height.
    if (target && target.scrollIntoView) {
      target.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'auto' });
    }
    window.requestAnimationFrame(() => window.requestAnimationFrame(place));
  }

  go(0);
}

// Clean the overlay up if the note re-renders underneath it.
dv.component.register(() => { const o = document.getElementById('hob-tour'); if (o) o.remove(); });

// A permanent way back in, so the tour is not a one-shot.
const tourBtn = statusCard.createEl('button', {text: '🧭 Take the tour'});
tourBtn.style.cssText = 'margin-top:.9rem;width:100%;font-size:.78rem;padding:.45rem .8rem;border-radius:9px;border:1px solid var(--vault-glass-border);background:rgba(255,255,255,0.06);color:var(--text-muted);cursor:pointer;font-weight:600;';
tourBtn.addEventListener('mouseenter', () => tourBtn.style.background = 'rgba(255,255,255,0.13)');
tourBtn.addEventListener('mouseleave', () => tourBtn.style.background = 'rgba(255,255,255,0.06)');
tourBtn.addEventListener('click', startTour);

// ─── CLOCK UPDATE TICK PIPELINE ───
function tick(){
  const now = new Date();
  title.setText(`${greetFor(now.getHours())}, ${NAME}`);
  clock.setText(now.toLocaleTimeString('en-US',{hour:'2-digit',minute:'2-digit',hour12:false}));
  dateline.setText(now.toLocaleDateString('en-US',{weekday:'long',day:'numeric',month:'long',year:'numeric'}));
}
tick();
dv.component.registerInterval(window.setInterval(tick, 1000));

// ─── RESTORE ACTIVE ACTION ON RE-RENDER ───
if (window._activeActionState && typeof window._activeActionStateRestore === 'function') {
  window._activeActionStateRestore();
}
```

/*
  Sky Background — vault-wide time-of-day sky behind the frosted glass.

  Ported from the dataviewjs banner in _HOME.md. Renders, on a single fixed
  full-window layer:
    - a time-of-day gradient (the "day" mood is muted vs. the old banner)
    - a sun that arcs across, or a moon + twinkling stars at dusk/night
    - real-weather clouds / rain / lightning (wttr.in), as a SYSTEM-level ambient

  The companion snippet `.obsidian/snippets/sky-background.css` keeps the app
  chassis transparent and puts a readable glass card behind the text column,
  so this layer reads as a blurred ambient sky around the text.

  Weather mode is configurable in the plugin settings:
    full   — clouds + rain + lightning, vault-wide (default)
    subtle — a few slow clouds only; no rain/lightning
    home   — full effects, but only while the _HOME note is active
    off    — no weather effects

  Debug: set `window.__skyForceHour = 12` in the console to preview any hour;
  set it back to `null`/`undefined` to resume real time.
*/

const { Plugin, PluginSettingTab, Setting, requestUrl } = require("obsidian");

const ANIM_ID = "sky-bg-anim";
const ANIM_CSS =
  "@keyframes sbTwinkle{0%,100%{opacity:.2}50%{opacity:1}}" +
  "@keyframes sbDrift{from{transform:translateX(-30vw)}to{transform:translateX(120vw)}}" +
  "@keyframes sbFall{from{top:-8%;opacity:0}10%{opacity:1}90%{opacity:1}to{top:104%;opacity:0}}" +
  "@keyframes sbFlash{0%,86%,100%{opacity:0}87%{opacity:.55}88%{opacity:.12}90%{opacity:.6}92%{opacity:0}}" +
  "@keyframes sbShooting{0%{transform:translate(0,0) rotate(-45deg) scaleX(0);opacity:0}10%{transform:translate(-10px,10px) rotate(-45deg) scaleX(1);opacity:1}90%{opacity:1}100%{transform:translate(-300px,300px) rotate(-45deg) scaleX(0);opacity:0}}" +
  "@keyframes sbShootingLTR{0%{transform:translate(0,0) rotate(-135deg) scaleX(0);opacity:0}10%{transform:translate(10px,10px) rotate(-135deg) scaleX(1);opacity:1}90%{opacity:1}100%{transform:translate(300px,300px) rotate(-135deg) scaleX(0);opacity:0}}";

const DEFAULT_SETTINGS = { weatherMode: "full" }; // full | subtle | home | off
const WEATHER_URL = "https://wttr.in/?format=j1";
const WEATHER_REFRESH_MS = 30 * 60 * 1000;

/* ---------- sky scene (ported from _HOME.md; "day" muted) ---------- */
function addStars(layer, n) {
  for (let i = 0; i < n; i++) {
    const s = layer.createDiv();
    const size = Math.random() * 2 + 1;
    s.style.cssText =
      `position:absolute;width:${size}px;height:${size}px;border-radius:50%;background:#fff;` +
      `left:${Math.random() * 100}%;top:${Math.random() * 60}%;` +
      `animation:sbTwinkle ${2 + Math.random() * 3}s ease-in-out ${Math.random() * 3}s infinite;`;
  }
}

function makeDisc(layer, core, glow, size) {
  const d = layer.createDiv();
  d.style.cssText =
    `position:absolute;width:${size}px;height:${size}px;border-radius:50%;` +
    `transform:translate(-50%,-50%);transition:left 1.5s linear,top 1.5s linear;` +
    `background:radial-gradient(circle at 35% 35%, ${core}, ${glow});box-shadow:0 0 70px 22px ${glow}bb;`;
  return d;
}

function scene(now) {
  let h = now.getHours() + now.getMinutes() / 60;
  if (typeof window.__skyForceHour === "number") h = window.__skyForceHour;
  if (h >= 6 && h < 20) {
    const frac = (h - 6) / 14;
    const sunLeft = 8 + frac * 84;
    const sunTop = 30 - Math.sin(frac * Math.PI) * 22;
    let key, grad, core, glow;
    if (h < 8) {
      key = "dawn";
      grad = "linear-gradient(160deg,#4b4e8c 0%,#d98a7b 55%,#ffb88c 100%)";
      core = "#ffe6c0";
      glow = "#ff9e6d";
    } else if (h < 17) {
      // clean daytime sky-blue (readability now handled by the glass card + ink,
      // so it no longer needs to be greyed down — the grey read as a dull veil)
      key = "day";
      grad = "linear-gradient(160deg,#6ba1d8 0%,#a8cff3 100%)";
      core = "#ffffff";
      glow = "#ffd24d";
    } else {
      // muted / desaturated sunset — warm dusk mood without the garish orange
      key = "sunset";
      grad = "linear-gradient(160deg,#b76e63 0%,#cf9a7d 45%,#5d4a78 100%)";
      core = "#e7c39e";
      glow = "#c98a6e";
    }
    return { key, grad, sun: { left: sunLeft, top: sunTop, core, glow } };
  } else if (h >= 20 && h < 22) {
    return { key: "dusk", grad: "linear-gradient(160deg,#2c3e50 0%,#4a3a6b 100%)", moon: true, stars: 14 };
  } else {
    return { key: "night", grad: "linear-gradient(160deg,#0b1026 0%,#1a2151 60%,#2a2d64 100%)", moon: true, stars: 38 };
  }
}

/* ---------- weather fx (ported from _HOME.md) ---------- */
function wxCategory(code) {
  code = +code;
  if ([200, 386, 389, 392, 395].includes(code)) return "storm";
  if ([176, 179, 182, 263, 266, 281, 284, 293, 296, 299, 302, 305, 308, 311, 314, 317, 320, 323, 326, 329, 332, 335, 338, 350, 353, 356, 359, 362, 365, 368, 371, 374, 377].includes(code)) return "rain";
  if ([119, 122, 143, 248, 260].includes(code)) return "cloudy";
  if (code === 116) return "partly";
  return "clear";
}
function makeCloud(layer, { scale = 1, top = 20, dur = 60, delay = 0, opacity = 0.85, rgb = "255,255,255" }) {
  const u = 26 * scale;
  const cloud = layer.createDiv();
  cloud.style.cssText =
    `position:absolute;top:${top}%;left:0;width:${u * 4}px;height:${u * 2}px;` +
    `opacity:${opacity};animation:sbDrift ${dur}s linear ${delay}s infinite;will-change:transform;`;
  const circ = (w, l, t) => {
    const d = cloud.createDiv();
    d.style.cssText = `position:absolute;width:${w}px;height:${w}px;border-radius:50%;background:rgb(${rgb});left:${l}px;top:${t}px;filter:blur(1px);`;
  };
  const bar = cloud.createDiv();
  bar.style.cssText = `position:absolute;left:${u * 0.3}px;top:${u * 1.05}px;width:${u * 3.4}px;height:${u * 0.95}px;border-radius:${u}px;background:rgb(${rgb});filter:blur(1px);`;
  circ(u * 1.6, u * 0.2, u * 0.55);
  circ(u * 1.9, u * 1.05, u * 0.05);
  circ(u * 1.5, u * 2.15, u * 0.5);
  circ(u * 1.2, u * 2.9, u * 0.75);
  return cloud;
}
function addRain(layer, count, rgb) {
  for (let i = 0; i < count; i++) {
    const drop = layer.createDiv();
    const h = 9 + Math.random() * 11;
    drop.style.cssText =
      `position:absolute;left:${Math.random() * 100}%;top:-8%;width:1.6px;height:${h}px;` +
      `background:linear-gradient(to bottom, rgba(${rgb},0), rgba(${rgb},.85));border-radius:1px;` +
      `animation:sbFall ${0.5 + Math.random() * 0.5}s linear ${Math.random() * 2}s infinite;`;
  }
}
function addLightning(layer) {
  [0, 3.5].forEach((d) => {
    const f = layer.createDiv();
    f.style.cssText =
      `position:absolute;inset:0;background:radial-gradient(circle at ${30 + Math.random() * 40}% 25%, rgba(255,255,255,.9), rgba(255,255,255,0) 60%);` +
      `opacity:0;animation:sbFlash ${6 + Math.random() * 3}s linear ${d}s infinite;`;
  });
}

module.exports = class SkyBackgroundPlugin extends Plugin {
  async onload() {
    await this.loadSettings();

    if (!document.getElementById(ANIM_ID)) {
      const st = document.createElement("style");
      st.id = ANIM_ID;
      st.textContent = ANIM_CSS;
      document.head.appendChild(st);
    }

    this.sky = document.body.createDiv({ cls: "sky-bg" });
    this.sky.style.cssText =
      "position:fixed;inset:0;z-index:0;pointer-events:none;overflow:hidden;transition:background 2s linear;";
    this.deco = this.sky.createDiv(); // sun / moon / stars
    this.deco.style.cssText = "position:absolute;inset:0;overflow:hidden;";
    this.fx = this.sky.createDiv(); // weather (above deco, below app content)
    this.fx.style.cssText = "position:absolute;inset:0;overflow:hidden;";

    this.curKey = null;
    this.sunEl = null;
    this.wxCode = null;
    this.curFxState = null;

    const tick = () => this.tick();
    tick();
    this.registerInterval(window.setInterval(tick, 1000));

    this.addSettingTab(new SkySettingTab(this.app, this));

    // home-only mode: re-evaluate when the active note changes
    this.registerEvent(this.app.workspace.on("active-leaf-change", () => this.applyWeatherFx()));

    this.loadWeather();
    this.registerInterval(window.setInterval(() => this.loadWeather(), WEATHER_REFRESH_MS));
  }

  tick() {
    const now = new Date();
    const sc = scene(now);
    this.sky.style.background = sc.grad;
    if (sc.key !== this.curKey) {
      this.curKey = sc.key;
      // dynamic ink: bright sky (dawn/day) → dark text; dim sky → light text
      const bright = sc.key === "dawn" || sc.key === "day";
      document.body.classList.toggle("sky-bright", bright);
      document.body.classList.toggle("sky-dim", !bright);
      // per-period class so CSS can tune surfaces the bright/dim split can't
      // distinguish (e.g. code-block frost: navy works at dawn/sunset but is
      // muddy at day / invisible at night). Class form: sky-dawn|day|sunset|dusk|night
      document.body.classList.remove(
        "sky-dawn", "sky-day", "sky-sunset", "sky-dusk", "sky-night");
      document.body.classList.add("sky-" + sc.key);
      this.deco.empty();
      this.sunEl = null;
      if (sc.stars) addStars(this.deco, sc.stars);
      if (sc.moon) {
        const m = makeDisc(this.deco, "#eef2ff", "#c9d4ff", 54);
        m.style.left = "86%";
        m.style.top = "20%";
      }
      if (sc.sun) this.sunEl = makeDisc(this.deco, sc.sun.core, sc.sun.glow, 82);
      this.curFxState = null; // night/day flip → recolor clouds
    }
    if (sc.sun && this.sunEl) {
      this.sunEl.style.left = sc.sun.left + "%";
      this.sunEl.style.top = sc.sun.top + "%";
      this.sunEl.style.background = `radial-gradient(circle at 35% 35%, ${sc.sun.core}, ${sc.sun.glow})`;
      this.sunEl.style.boxShadow = `0 0 70px 22px ${sc.sun.glow}bb`;
    }
    this.applyWeatherFx();

    // Spawn shooting stars when it is night/dusk and the weather is clear ("sereno")
    const cat = this.wxCode == null ? null : wxCategory(this.wxCode);
    const mode = this.settings.weatherMode;
    const homeActive = this.isHomeActive();
    const weatherDisabled = mode === "off" || (mode === "home" && !homeActive);
    const isClear = weatherDisabled || !cat || cat === "clear";
    if (isClear && (sc.key === "night" || sc.key === "dusk")) {
      if (Math.random() < 0.04) {
        this.spawnShootingStar();
      }
    }
  }

  spawnShootingStar() {
    if (!this.deco) return;
    const ss = this.deco.createDiv();
    const duration = 1 + Math.random() * 1.2; // 1s to 2.2s
    const isLtr = Math.random() < 0.5;
    const left = isLtr ? (10 + Math.random() * 50) : (40 + Math.random() * 50);
    const rotation = isLtr ? "-135deg" : "-45deg";
    const animationName = isLtr ? "sbShootingLTR" : "sbShooting";

    ss.style.cssText =
      `position:absolute;` +
      `left:${left}%;` +
      `top:${Math.random() * 40}%;` +
      `width:${60 + Math.random() * 60}px;` +
      `height:2px;` +
      `background:linear-gradient(90deg, rgba(255,255,255,0.95), rgba(255,255,255,0));` +
      `transform-origin:left center;` +
      `transform:rotate(${rotation}) scaleX(0);` +
      `filter:drop-shadow(0 0 5px #fff);` +
      `opacity:0;` +
      `animation:${animationName} ${duration}s cubic-bezier(0.1, 0.8, 0.3, 1) forwards;`;

    setTimeout(() => {
      if (ss.parentNode) ss.remove();
    }, duration * 1000 + 200);
  }

  isHomeActive() {
    const f = this.app.workspace.getActiveFile();
    return !!f && f.basename === "_HOME";
  }

  applyWeatherFx() {
    const mode = this.settings.weatherMode;
    const homeActive = this.isHomeActive();
    const gateOff = mode === "off" || (mode === "home" && !homeActive);
    const subtle = mode === "subtle";
    let cat = this.wxCode == null ? null : wxCategory(this.wxCode);
    const fw = window.__skyForceWeather;
    if (fw && fw !== "auto") cat = fw;
    const dark = this.curKey === "night" || this.curKey === "dusk";

    const stateKey = `${mode}|${cat}|${dark}|${homeActive}`;
    if (stateKey === this.curFxState) return;
    this.curFxState = stateKey;
    this.fx.empty();
    if (gateOff || !cat || cat === "clear") return;

    // NOTE: no overcast veil — a full-screen grey tint reads as fake glassmorphism
    // and ruins the sky's colour. The clouds alone communicate the weather.

    let count, rgb, op;
    if (subtle) {
      count = cat === "partly" ? 2 : 4;
      op = dark ? 0.4 : 0.6;
      rgb = dark ? "190,196,210" : "248,250,252";
    } else if (cat === "partly") {
      count = 3; op = dark ? 0.45 : 0.7; rgb = dark ? "200,205,220" : "255,255,255";
    } else if (cat === "cloudy") {
      count = 5; op = dark ? 0.5 : 0.85; rgb = dark ? "175,182,198" : "240,242,246";
    } else if (cat === "rain") {
      count = 12; op = dark ? 0.6 : 0.9; rgb = dark ? "150,156,172" : "202,208,219";
    } else {
      count = 21; op = dark ? 0.68 : 0.92; rgb = dark ? "120,126,142" : "168,175,188"; // storm
    }

    const baseDur = 133 + Math.random() * 36;
    for (let i = 0; i < count; i++) {
      makeCloud(this.fx, {
        scale: 0.8 + Math.random() * 0.9,
        top: 1 + Math.random() * 30, // upper band only
        dur: baseDur + Math.random() * 15,
        delay: -((i + Math.random() * 0.5) / count) * baseDur,
        opacity: op * (0.8 + Math.random() * 0.2),
        rgb,
      });
    }

    if (!subtle && cat === "rain") addRain(this.fx, 42, "174,194,224");
    if (!subtle && cat === "storm") {
      addRain(this.fx, 58, "170,188,220");
      addLightning(this.fx);
    }
  }

  async loadWeather() {
    if (this.settings.weatherMode === "off") return;
    try {
      const loc = localStorage.getItem('home-weather-location') || '';
      const url = `https://wttr.in/${encodeURIComponent(loc)}?format=j1`;
      const res = await requestUrl({ url, throw: false });
      if (res.status < 200 || res.status >= 300) return;
      const data = JSON.parse(res.text);
      const cur = data.current_condition && data.current_condition[0];
      if (cur) {
        this.wxCode = +cur.weatherCode;
        this.curFxState = null;
        this.applyWeatherFx();
      }
    } catch (e) {
      /* offline → no weather fx */
    }
  }

  async loadSettings() {
    this.settings = Object.assign({}, DEFAULT_SETTINGS, await this.loadData());
  }
  async saveSettings() {
    await this.saveData(this.settings);
  }

  onunload() {
    if (this.sky) this.sky.remove();
    this.sky = this.deco = this.fx = this.sunEl = null;
    document.body.classList.remove("sky-bright", "sky-dim",
      "sky-dawn", "sky-day", "sky-sunset", "sky-dusk", "sky-night");
    const st = document.getElementById(ANIM_ID);
    if (st) st.remove();
  }
};

class SkySettingTab extends PluginSettingTab {
  constructor(app, plugin) {
    super(app, plugin);
    this.plugin = plugin;
  }
  display() {
    const { containerEl } = this;
    containerEl.empty();
    new Setting(containerEl)
      .setName("Weather effects")
      .setDesc("How real weather (clouds, rain, lightning) appears on the vault sky.")
      .addDropdown((d) =>
        d
          .addOption("full", "Full — clouds, rain & lightning, vault-wide")
          .addOption("subtle", "Subtle — light veil + a few slow clouds")
          .addOption("home", "Home only — effects only on the _HOME note")
          .addOption("off", "Off — clean sky")
          .setValue(this.plugin.settings.weatherMode)
          .onChange(async (v) => {
            this.plugin.settings.weatherMode = v;
            await this.plugin.saveSettings();
            this.plugin.curFxState = null;
            if (v !== "off" && this.plugin.wxCode == null) this.plugin.loadWeather();
            else this.plugin.applyWeatherFx();
          })
      );
  }
}

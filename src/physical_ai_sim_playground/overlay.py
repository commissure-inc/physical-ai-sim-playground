"""Japanese UI over the stock mjswan viewer.

Three things are added to the built ``index.html``:

- a head script that opens the viewer with debug drawings off (``?debug=0``) unless the
  URL says otherwise;
- a script that renames the labels the viewer draws itself, hides the rows an attendee
  does not need (field of view, the policy picker...), and starts the pointer in Push;
- the lesson bar (reset, two counters), a short "how to play" card, a tab that
  switches to the coefficient page at ``physics/`` (see ``physics.py``), and the
  "環境の条件" panel: live sliders for floor friction, payload and gravity, written into
  the running model that the plugin event of ``env.py`` hands to the page.

The swan logo and the About dialog it opens are left untouched, as mjswan asks of
company pages. Nothing here talks to a server; the tally lives in the page.
"""

from __future__ import annotations

from pathlib import Path

TITLE = "フィジカルAI シミュレータ体験"
MARK = "<!-- physical-ai-sim-playground overlay -->"

_HEAD = MARK + """
<script>
(function () {
  try {
    var url = new URL(window.location.href);
    if (!url.searchParams.has("debug")) {
      url.searchParams.set("debug", "0");
      window.history.replaceState(null, "", url);
    }
  } catch (e) {}
})();
</script>"""

_BODY = r"""<nav id="lesson-nav" aria-label="ページの切り替え">
  <span aria-current="page">ロボットで試す</span>
  <a href="./physics/" id="lesson-nav-physics">係数を変える</a>
</nav>
<section id="lesson-env" aria-labelledby="lesson-env-title">
  <button type="button" id="lesson-env-toggle" aria-expanded="true">
    <span id="lesson-env-title">環境の条件</span><span class="lesson-env-caret" aria-hidden="true">▾</span>
  </button>
  <div id="lesson-env-body">
    <label class="lesson-env-row" for="env-friction">
      <span class="lesson-env-name">床の摩擦</span>
      <span class="lesson-env-value" id="env-friction-value">シーンのまま</span>
    </label>
    <input type="range" id="env-friction" min="0.05" max="1.5" step="0.05" value="1">
    <label class="lesson-env-row" for="env-payload">
      <span class="lesson-env-name">荷物の重さ</span>
      <span class="lesson-env-value" id="env-payload-value">なし</span>
    </label>
    <input type="range" id="env-payload" min="0" max="80" step="5" value="0">
    <label class="lesson-env-row" for="env-gravity">
      <span class="lesson-env-name">重力（地球＝1）</span>
      <span class="lesson-env-value" id="env-gravity-value">1.0</span>
    </label>
    <input type="range" id="env-gravity" min="0.2" max="2" step="0.1" value="1">
    <button type="button" id="env-reset" class="lesson-link">シーンのままに戻す</button>
    <p class="lesson-env-note">値を変えると、その場で反映される。「最初から」を押しても、変えた値のまま。状況を切り替えると元に戻る。</p>
  </div>
</section>
<div id="lesson-help" role="dialog" aria-labelledby="lesson-help-title" hidden>
  <div class="lesson-card">
    <h2 id="lesson-help-title">遊び方</h2>
    <ol>
      <li>右のパネルで、ロボットと状況（氷の床、荷物、段差など）を選ぶ。左の「環境の条件」で、床の摩擦、荷物の重さ、重力をその場で変えられる。</li>
      <li>ロボットをクリックすると押せる。押す強さは、パネルの「マウスで触る」で変えられる。</li>
      <li>「自分で操作」を入れると、歩く向きと速さをスライダで決められる。入れないと、ロボットが自分で向きと速さを変える。</li>
      <li>押したあと立て直したか、倒れたかを、下のボタンで数える。倒れたら「最初から」。</li>
    </ol>
    <p class="lesson-note">ロボットの外側をドラッグすると視点が回る。ホイールで寄る。</p>
    <button type="button" id="lesson-help-close">始める</button>
  </div>
</div>
<div id="lesson-bar">
  <button type="button" id="lesson-reset" class="lesson-btn">最初から</button>
  <span class="lesson-sep" aria-hidden="true"></span>
  <button type="button" id="lesson-up" class="lesson-btn lesson-up">立て直した</button>
  <button type="button" id="lesson-down" class="lesson-btn lesson-down">倒れた</button>
  <span id="lesson-tally" data-lesson="tally" aria-live="polite">立て直した 0　倒れた 0</span>
  <button type="button" id="lesson-clear" class="lesson-link">数を0に戻す</button>
  <span class="lesson-sep" aria-hidden="true"></span>
  <button type="button" id="lesson-help-open" class="lesson-link">遊び方</button>
</div>
<style>
  :root {
    --lesson-bg: rgba(17, 20, 26, 0.9);
    --lesson-fg: #f3f1ec;
    --lesson-muted: #b9bec8;
    --lesson-btn: #2b313d;
    --lesson-btn-hover: #3a4252;
    --lesson-up: #2f7d5b;
    --lesson-up-hover: #389069;
    --lesson-down: #a3473f;
    --lesson-down-hover: #b8524a;
    --lesson-card-bg: #ffffff;
    --lesson-card-fg: #1d222b;
    --lesson-accent: #1f6feb;
    --lesson-font: "Hiragino Sans", "Hiragino Kaku Gothic ProN", "Noto Sans JP", "Yu Gothic UI", "Meiryo", sans-serif;
  }
  body, .mantine-Text-root, .mantine-Button-label, .mantine-SegmentedControl-innerLabel {
    font-family: var(--lesson-font);
  }
  #lesson-bar {
    position: fixed;
    z-index: 10000;
    left: 50%;
    bottom: 16px;
    transform: translateX(-50%);
    display: flex;
    flex-wrap: nowrap;
    justify-content: center;
    gap: 8px;
    align-items: center;
    max-width: calc(100vw - 32px);
    box-sizing: border-box;
    padding: 8px 12px;
    border-radius: 12px;
    background: var(--lesson-bg);
    color: var(--lesson-fg);
    font: 15px/1.3 var(--lesson-font);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
  }
  .lesson-btn {
    white-space: nowrap;
    font: inherit;
    font-weight: 600;
    color: inherit;
    background: var(--lesson-btn);
    border: 0;
    border-radius: 8px;
    padding: 8px 14px;
    cursor: pointer;
  }
  .lesson-btn:hover { background: var(--lesson-btn-hover); }
  .lesson-up { background: var(--lesson-up); }
  .lesson-up:hover { background: var(--lesson-up-hover); }
  .lesson-down { background: var(--lesson-down); }
  .lesson-down:hover { background: var(--lesson-down-hover); }
  .lesson-btn:focus-visible, .lesson-link:focus-visible, #lesson-help-close:focus-visible {
    outline: 2px solid #9cc3ff;
    outline-offset: 2px;
  }
  .lesson-link {
    white-space: nowrap;
    font: inherit;
    font-size: 13px;
    color: var(--lesson-muted);
    background: none;
    border: 0;
    padding: 4px 6px;
    cursor: pointer;
    text-decoration: underline;
    text-underline-offset: 3px;
  }
  .lesson-link:hover { color: var(--lesson-fg); }
  .lesson-sep { width: 1px; align-self: stretch; background: rgba(255, 255, 255, 0.15); }
  #lesson-tally {
    padding: 0 4px;
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }
  #lesson-nav {
    position: fixed;
    z-index: 10000;
    top: 16px;
    left: 16px;
    display: flex;
    gap: 2px;
    padding: 3px;
    border-radius: 10px;
    background: var(--lesson-bg);
    font: 600 14px/1.2 var(--lesson-font);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
  }
  #lesson-nav a, #lesson-nav span {
    padding: 7px 12px;
    border-radius: 8px;
    color: var(--lesson-muted);
    text-decoration: none;
    white-space: nowrap;
  }
  #lesson-nav a:hover { color: var(--lesson-fg); background: rgba(255, 255, 255, 0.08); }
  #lesson-nav [aria-current="page"] { color: #fff; background: var(--lesson-accent); }
  #lesson-nav a:focus-visible { outline: 2px solid #9cc3ff; outline-offset: 2px; }
  #lesson-env {
    position: fixed;
    z-index: 10000;
    top: 64px;
    left: 16px;
    width: 280px;
    box-sizing: border-box;
    border-radius: 12px;
    background: var(--lesson-bg);
    color: var(--lesson-fg);
    font: 13px/1.5 var(--lesson-font);
    box-shadow: 0 6px 24px rgba(0, 0, 0, 0.25);
  }
  #lesson-env[hidden] { display: none; }
  #lesson-env-toggle {
    display: flex;
    width: 100%;
    justify-content: space-between;
    align-items: center;
    padding: 10px 14px;
    font: 600 14px/1.3 var(--lesson-font);
    color: inherit;
    background: none;
    border: 0;
    cursor: pointer;
  }
  #lesson-env-toggle[aria-expanded="false"] .lesson-env-caret { transform: rotate(-90deg); }
  #lesson-env-body { padding: 0 14px 12px; }
  #lesson-env-toggle[aria-expanded="false"] + #lesson-env-body { display: none; }
  .lesson-env-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    margin-top: 8px;
    color: var(--lesson-muted);
  }
  .lesson-env-name { color: var(--lesson-fg); }
  .lesson-env-value { font-variant-numeric: tabular-nums; white-space: nowrap; }
  #lesson-env input[type="range"] {
    width: 100%;
    margin: 4px 0 2px;
    accent-color: var(--lesson-accent);
  }
  #lesson-env.is-default-friction #env-friction { opacity: 0.55; }
  .lesson-env-note { margin: 8px 0 0; font-size: 12px; color: var(--lesson-muted); }
  #env-reset { padding: 4px 0; margin-top: 6px; }
  #lesson-help {
    position: fixed;
    inset: 0;
    z-index: 10001;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    background: rgba(0, 0, 0, 0.45);
  }
  #lesson-help[hidden] { display: none; }
  .lesson-card {
    max-width: 520px;
    width: 100%;
    max-height: calc(100vh - 32px);
    overflow: auto;
    padding: 24px 28px;
    border-radius: 14px;
    background: var(--lesson-card-bg);
    color: var(--lesson-card-fg);
    font: 15px/1.7 var(--lesson-font);
    box-shadow: 0 12px 40px rgba(0, 0, 0, 0.3);
  }
  .lesson-card h2 { margin: 0 0 12px; font-size: 20px; }
  .lesson-card ol { margin: 0 0 12px; padding-left: 1.4em; }
  .lesson-card li { margin-bottom: 6px; }
  .lesson-note { margin: 0 0 16px; font-size: 13px; color: #5b6472; }
  #lesson-help-close {
    font: inherit;
    font-weight: 600;
    color: #fff;
    background: var(--lesson-accent);
    border: 0;
    border-radius: 8px;
    padding: 8px 20px;
    cursor: pointer;
  }
  @media (max-width: 760px) {
    #lesson-bar { flex-wrap: wrap; }
    #lesson-env { width: calc(100vw - 32px); max-width: 320px; }
  }
  @media (max-width: 640px) {
    #lesson-bar { bottom: 8px; padding: 6px 8px; gap: 6px; font-size: 14px; }
    .lesson-btn { padding: 7px 10px; }
    .lesson-sep { display: none; }
  }
</style>
<script>
(function () {
  // ---- tally ----
  var up = 0, down = 0;
  var tally = document.getElementById("lesson-tally");
  function paint() { tally.textContent = "立て直した " + up + "　倒れた " + down; }
  document.getElementById("lesson-up").addEventListener("click", function () { up += 1; paint(); });
  document.getElementById("lesson-down").addEventListener("click", function () { down += 1; paint(); });
  document.getElementById("lesson-clear").addEventListener("click", function () { up = 0; down = 0; paint(); });

  // ---- reset: press the viewer's own Reset button ----
  document.getElementById("lesson-reset").addEventListener("click", function () {
    var stock = document.querySelector('button[data-lesson-reset="stock"]');
    if (stock) stock.click();
    else window.dispatchEvent(new KeyboardEvent("keydown", {key: "r", bubbles: true, cancelable: true}));
  });

  // ---- help card ----
  var help = document.getElementById("lesson-help");
  var SEEN = "pasp-help-seen";
  function openHelp() { help.hidden = false; document.getElementById("lesson-help-close").focus(); }
  function closeHelp() {
    help.hidden = true;
    try { window.localStorage.setItem(SEEN, "1"); } catch (e) {}
  }
  document.getElementById("lesson-help-open").addEventListener("click", openHelp);
  document.getElementById("lesson-help-close").addEventListener("click", closeHelp);
  help.addEventListener("click", function (ev) { if (ev.target === help) closeHelp(); });
  document.addEventListener("keydown", function (ev) { if (ev.key === "Escape" && !help.hidden) closeHelp(); });
  var seen = false;
  try { seen = window.localStorage.getItem(SEEN) === "1"; } catch (e) {}
  if (!seen && !/[?&]help=0(&|$)/.test(window.location.search)) openHelp();
  if (/[?&]help=0(&|$)/.test(window.location.search)) {
    document.getElementById("lesson-nav-physics").href = "./physics/?help=0";
  }

  // ---- the viewer's own labels ----
  // [text, where it sits ("LABEL", "SPAN", "DIV"; "" = anywhere), replacement]
  var RENAME = [
    ["Scene", "LABEL", "状況"],
    ["Scene", "DIV", "表示"],
    ["Commands", "", "操作"],
    ["Twist", "DIV", "歩く向きと速さ"],
    ["Camera", "", "カメラ"],
    ["Track camera", "", "追いかける"],
    ["Debug Viz", "", "矢印"],
    ["Enabled", "", "矢印を表示"],
    ["Events", "", "ボール"],
    ["Throw overhead", "", "上から投げる"],
    ["Throw underbody", "", "下から投げる"],
    ["Auto throw", "", "自動で投げる"],
    ["Interact", "", "マウスで触る"],
    ["View", "", "見るだけ"],
    ["Pull", "", "引っ張る"],
    ["Push", "", "押す"],
    ["Grab", "", "つかむ"],
    ["Spring (N/m)", "", "引っ張る強さ (N/m)"],
    ["Impulse (N s)", "", "押す強さ (N·s)"],
    ["Impulse (N·s)", "", "押す強さ (N·s)"],
    ["Softness (s)", "", "つかみの柔らかさ (秒)"],
    ["Torque scale", "", "向きを保つ"],
    ["Zero", "", "止める"],
  ];
  // Rows to hide, by the text of their label.
  var HIDE = ["Policy", "FOV (°)", "All envs", "Twist"];

  function rowOf(el) {
    var flex = el.closest(".mantine-Flex-root");
    return flex ? flex.parentElement : null;
  }

  function apply() {
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var node, todo = [];
    while ((node = walker.nextNode())) {
      var parent = node.parentElement;
      if (!parent || parent.closest("#lesson-bar, #lesson-help, #lesson-nav, #lesson-env, script, style, noscript")) continue;
      todo.push(node);
    }
    todo.forEach(function (n) {
      var text = n.textContent.trim();
      if (!text) return;
      var el = n.parentElement;
      var labelEl = el.closest("label");
      var where = labelEl && !el.closest(".mantine-SegmentedControl-root") ? "LABEL" : el.tagName;
      if (where === "LABEL" && HIDE.indexOf(text) >= 0) {
        var row = rowOf(labelEl);
        if (row) row.style.display = "none";
        return;
      }
      if (text === "Reset") {
        var btn = el.closest("button");
        if (btn) {
          btn.setAttribute("data-lesson-reset", "stock");
          btn.style.display = "none";
        }
        return;
      }
      for (var i = 0; i < RENAME.length; i++) {
        var r = RENAME[i];
        if (r[0] !== text) continue;
        if (r[1] && r[1] !== where) continue;
        n.textContent = n.textContent.replace(text, r[2]);
        break;
      }
    });
  }

  var scheduled = false;
  new MutationObserver(function () {
    if (scheduled) return;
    scheduled = true;
    window.requestAnimationFrame(function () { scheduled = false; apply(); });
  }).observe(document.body, {childList: true, subtree: true, characterData: true});
  apply();

  // ---- start the pointer in Push once the viewer is up ----
  // The "マウスで触る" folder starts collapsed. Open it once, so the attendee sees the
  // modes and the push strength, and select Push.
  var pushed = false;
  var opened = false;
  function openInteract() {
    var root = document.querySelector(".mantine-SegmentedControl-root");
    if (root && root.getBoundingClientRect().height > 0) return true;
    var walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    var n;
    while ((n = walker.nextNode())) {
      if (/^(マウスで触る|Interact)$/.test(n.textContent.trim())) {
        n.parentElement.click();
        return true;
      }
    }
    return false;
  }
  function choosePush() {
    if (!opened) opened = openInteract();
    var spans = document.querySelectorAll(".mantine-SegmentedControl-innerLabel");
    for (var i = 0; i < spans.length; i++) {
      var t = spans[i].textContent.trim();
      if (t === "押す" || t === "Push") {
        var label = spans[i].closest("label");
        if (label) { label.click(); pushed = true; }
        return;
      }
    }
  }
  var tries = 0;
  var timer = window.setInterval(function () {
    tries += 1;
    if (window.__mjswanReady) choosePush();
    if ((pushed && opened) || tries > 240) window.clearInterval(timer);
  }, 500);

  // ---- environment sliders (see env.py) ----
  // window.__paspModel is set by the plugin event on every reset. The values below are
  // written into that model; a new model (another scene) puts the sliders back.
  var envBox = document.getElementById("lesson-env");
  var envToggle = document.getElementById("lesson-env-toggle");
  var fr = document.getElementById("env-friction");
  var pl = document.getElementById("env-payload");
  var gr = document.getElementById("env-gravity");
  var env = {friction: null, payload: 0, gravity: 1};
  var snap = null;
  var TORSO = ["torso_link", "trunk", "base_link", "base"];

  try {
    if (window.localStorage.getItem("pasp-env-closed") === "1" || window.innerWidth < 760) {
      envToggle.setAttribute("aria-expanded", "false");
    }
  } catch (e) {}
  envToggle.addEventListener("click", function () {
    var open = envToggle.getAttribute("aria-expanded") !== "true";
    envToggle.setAttribute("aria-expanded", open ? "true" : "false");
    try { window.localStorage.setItem("pasp-env-closed", open ? "0" : "1"); } catch (e) {}
  });

  function bodyName(m, b) {
    var names = m.names, start = m.name_bodyadr[b], end = start;
    while (end < names.length && names[end] !== 0) end++;
    return new TextDecoder("utf-8").decode(names.subarray(start, end));
  }
  function takeSnapshot(m) {
    var s = {model: m, friction: Float64Array.from(m.geom_friction), mass: Float64Array.from(m.body_mass),
      gravity: Float64Array.from(m.opt.gravity), torso: -1, robotMass: 0, floor: null};
    for (var g = 0; g < m.ngeom; g++) {
      if (m.geom_type[g] === 0) { s.floor = m.geom_friction[3 * g]; break; }
    }
    var found = {};
    for (var b = 1; b < m.nbody; b++) {
      var n = bodyName(m, b).toLowerCase();
      var bare = n.split("/").pop();
      if (TORSO.indexOf(bare) >= 0 && !(bare in found)) found[bare] = b;
    }
    for (var i = 0; i < TORSO.length; i++) {
      if (TORSO[i] in found) { s.torso = found[TORSO[i]]; break; }
    }
    if (s.torso >= 0) {
      var root = m.body_rootid[s.torso];
      for (var k = 1; k < m.nbody; k++) if (m.body_rootid[k] === root) s.robotMass += m.body_mass[k];
    }
    return s;
  }
  function paintEnv() {
    document.getElementById("env-friction-value").textContent = env.friction === null
      ? "シーンのまま" + (snap && snap.floor !== null ? "（" + snap.floor.toFixed(2) + "）" : "")
      : env.friction.toFixed(2);
    envBox.classList.toggle("is-default-friction", env.friction === null);
    var kg = snap && snap.robotMass ? "、約" + (env.payload / 100 * snap.robotMass).toFixed(1) + "kg" : "";
    var hasTorso = !snap || snap.torso >= 0;
    document.getElementById("env-payload-value").textContent = !hasTorso ? "載せられない"
      : env.payload === 0 ? "なし" : "ロボットの" + env.payload + "%" + kg;
    document.getElementById("env-gravity-value").textContent = env.gravity.toFixed(1);
    pl.disabled = !hasTorso;
    pl.title = hasTorso ? "" : "このロボットには荷物を載せる胴がない";
  }
  function envDefaults() {
    env = {friction: null, payload: 0, gravity: 1};
    fr.value = snap && snap.floor !== null ? String(snap.floor) : "1";
    pl.value = "0";
    gr.value = "1";
  }
  function applyEnv() {
    var h = window.__paspModel;
    if (!h || !h.mjModel) return;
    var m = h.mjModel;
    if (!snap || snap.model !== m) { snap = takeSnapshot(m); envDefaults(); }
    var f = m.geom_friction;
    for (var g = 0; g < m.ngeom; g++) f[3 * g] = env.friction === null ? snap.friction[3 * g] : env.friction;
    if (snap.torso >= 0) {
      m.body_mass[snap.torso] = snap.mass[snap.torso] + (env.payload / 100) * snap.robotMass;
      if (h.mujoco && h.mjData && h.mujoco.mj_setConst) h.mujoco.mj_setConst(m, h.mjData);
    }
    var gv = m.opt.gravity;
    for (var a = 0; a < 3; a++) gv[a] = snap.gravity[a] * env.gravity;
    paintEnv();
  }
  window.__paspApply = applyEnv;
  window.__paspEnv = function () { return {env: env, snap: snap}; };
  fr.addEventListener("input", function () { env.friction = parseFloat(fr.value); applyEnv(); });
  pl.addEventListener("input", function () { env.payload = parseInt(pl.value, 10); applyEnv(); });
  gr.addEventListener("input", function () { env.gravity = parseFloat(gr.value); applyEnv(); });
  document.getElementById("env-reset").addEventListener("click", function () { envDefaults(); applyEnv(); });
  paintEnv();
  if (window.__paspModel) applyEnv();

  // ---- page title ----
  function title() { if (document.title !== "__TITLE__") document.title = "__TITLE__"; }
  title();
  new MutationObserver(title).observe(document.head, {childList: true, subtree: true, characterData: true});
})();
</script>
""".replace("__TITLE__", TITLE)


def inject(index: Path) -> None:
    """Add the head script, the lesson bar and the help card to a built ``index.html``."""
    html = index.read_text()
    if MARK in html:
        return
    if "<head>" not in html or "</body>" not in html:
        raise RuntimeError(f"{index} has no <head> or </body> to attach the lesson bar to.")
    html = html.replace("<head>", "<head>\n    " + _HEAD, 1)
    if "<title>" in html:
        start = html.index("<title>")
        end = html.index("</title>", start)
        html = html[:start] + f"<title>{TITLE}</title>" + html[end + len("</title>"):]
    html = html.replace("</body>", _BODY + "\n  </body>", 1)
    index.write_text(html)

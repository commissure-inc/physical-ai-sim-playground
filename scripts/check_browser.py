"""Open every scene in a built site and wait until the viewer reports ready.

The server is a plain static file server. GitHub Pages does not send
COOP/COEP headers, and neither does this script.

    uvx --from playwright python scripts/check_browser.py dist

Uses Google Chrome when `channel="chrome"` can launch it, otherwise Playwright's
Chromium. Exits 1 when any project does not become ready.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import json
import socketserver
import sys
import tempfile
import threading
import time
from pathlib import Path

READY_TIMEOUT_MS = 180_000

# Counts the viewer's control-loop wake-ups for the step-rate measurement. Injected by
# this check only; the shipped page does not carry it.
_STEP_PROBE = """
window.__stepProbe = {messages: 0, waits: 0};
(function () {
  var Orig = window.MessageChannel;
  window.MessageChannel = function () {
    var channel = new Orig();
    var post = channel.port2.postMessage.bind(channel.port2);
    channel.port2.postMessage = function () {
      window.__stepProbe.messages += 1;
      return post.apply(channel.port2, arguments);
    };
    return channel;
  };
  var origTimeout = window.setTimeout;
  window.setTimeout = function (fn, ms) {
    if (typeof ms === "number" && ms >= 1 && ms < 80) window.__stepProbe.waits += 1;
    return origTimeout.apply(window, arguments);
  };
})();
"""
SETTLE_SECONDS = 3

# Scenes of the coefficient page (physics/src/experiments.js SCENES). The first four
# are experiments and must show a reading at the bottom left.
PHYSICS_SCENES = ("ramp", "bounce", "mass", "timestep", "mug", "hand", "cloth", "humanoid")
PHYSICS_EXPERIMENTS = PHYSICS_SCENES[:4]


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("site", type=Path, help="directory written by `uv run build`")
    parser.add_argument(
        "--base-path",
        default=None,
        help="URL prefix the site was built for (default: read it from index.html)",
    )
    args = parser.parse_args()
    site = args.site.resolve()
    manifest = json.loads((site / "manifest.json").read_text())
    projects = manifest.get("projects") or []
    if not projects:
        print("manifest.json has no projects", file=sys.stderr)
        raise SystemExit(1)
    base = args.base_path or _base_path((site / "index.html").read_text())

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    with tempfile.TemporaryDirectory() as root:
        served = Path(root)
        if base.strip("/"):
            mount = served.joinpath(*base.strip("/").split("/"))
            mount.parent.mkdir(parents=True, exist_ok=True)
            mount.symlink_to(site, target_is_directory=True)
        else:
            served = site
        handler = functools.partial(_Quiet, directory=str(served))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            threading.Thread(target=server.serve_forever, daemon=True).start()
            origin = f"http://127.0.0.1:{server.server_address[1]}{base}"
            print(f"serving {site} at {origin}")
            with sync_playwright() as playwright:
                browser = _launch(playwright)
                failed = False
                first = True
                for project in projects:
                    scenes = project.get("scenes") or [None]
                    for scene in scenes:
                        problem = _check(
                            browser,
                            origin,
                            project,
                            PlaywrightError,
                            scene=scene,
                            exercise_lesson=first,
                            measure=_is_pacman(project),
                        )
                        first = False
                        failed = failed or problem is not None
                for scene_id in PHYSICS_SCENES:
                    problem = _check_physics(browser, origin, scene_id, PlaywrightError)
                    failed = failed or problem is not None
                browser.close()
            server.shutdown()
    raise SystemExit(1 if failed else 0)


def _launch(playwright):
    flags = ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"]
    try:
        return playwright.chromium.launch(channel="chrome", headless=True, args=flags)
    except Exception as exc:
        print(f"Chrome channel unavailable ({exc}); launching Playwright Chromium")
        return playwright.chromium.launch(headless=True, args=flags)


def _is_pacman(project: dict) -> bool:
    text = f"{project.get('id', '')} {project.get('name', '')}".lower()
    return "pac" in text


def _check(
    browser,
    origin: str,
    project: dict,
    playwright_error: type,
    *,
    scene: dict | None,
    exercise_lesson: bool,
    measure: bool,
) -> str | None:
    project_id = project["id"]
    scene_id = scene["id"] if scene else None
    scene_name = scene.get("name", "") if scene else ""
    errors: list[str] = []
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    if measure:
        page.add_init_script(_STEP_PROBE)
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )
    failed: list[str] = []
    page.on("response", lambda response: _note_http(response, failed))
    start = time.monotonic()
    query = f"?help=0&project={project_id}"
    if scene_id:
        query += f"&scene={scene_id}"
    page.goto(f"{origin}{query}")
    state = "timed out"
    try:
        page.wait_for_function(
            "() => window.__mjswanReady || window.__mjswanError",
            timeout=READY_TIMEOUT_MS,
        )
        error = page.evaluate("() => !!window.__mjswanError")
        state = "reported an error" if error else "ready"
    except playwright_error:
        pass
    if exercise_lesson and state == "ready":
        _exercise_lesson(page, errors)
    rate = None
    if measure and state == "ready":
        rate = _step_rate(page, float(scene.get("control_dt") or 0) if scene else 0)
    else:
        page.wait_for_timeout(SETTLE_SECONDS * 1000)
    opened = page.evaluate("() => new URLSearchParams(location.search).get('project')")
    opened_scene = page.evaluate("() => new URLSearchParams(location.search).get('scene')")
    seconds = time.monotonic() - start
    page.close()

    problem = None
    if state != "ready":
        problem = state
    elif opened != project_id:
        problem = f"opened {opened!r}"
    elif scene_id and opened_scene != scene_id:
        problem = f"opened scene {opened_scene!r}"
    elif errors:
        problem = errors[0]
    elif failed:
        problem = failed[0]
    label = "FAIL" if problem else "ok"
    title = f"{project_id}/{scene_id or '-'}"
    print(f"{label:<5}{title:<42}{seconds:6.1f}s  {scene_name}  {problem or 'ready'}")
    if rate is not None:
        print(
            f"      control {rate['hz']:.1f}/s over {rate['seconds']:.1f}s "
            f"(target {rate['target']:.1f}/s, messages {rate['messages']}, waits {rate['waits']})"
        )
    for error in errors[1:8]:
        print(f"      {error}")
    for item in failed[:8]:
        print(f"      {item}")
    return problem


def _check_physics(browser, origin: str, scene_id: str, playwright_error: type) -> str | None:
    errors: list[str] = []
    failed: list[str] = []
    page = browser.new_page(viewport={"width": 1280, "height": 800})
    page.on("pageerror", lambda exc: errors.append(str(exc)))
    page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
    page.on("response", lambda response: _note_http(response, failed))
    start = time.monotonic()
    page.goto(f"{origin}physics/?help=0&scene={scene_id}")
    state = "timed out"
    try:
        page.wait_for_function("() => window.__physicsReady", timeout=READY_TIMEOUT_MS)
        state = "ready"
    except playwright_error:
        pass
    reading = ""
    if state == "ready":
        page.wait_for_timeout(SETTLE_SECONDS * 1000)
        reading = page.inner_text("#readout").strip()
        lesson = page.inner_text("#lesson-text").strip()
        body = page.inner_text("body")
        if not lesson:
            errors.append("lesson text is empty")
        if scene_id in PHYSICS_EXPERIMENTS and not reading:
            errors.append("no reading at the bottom left")
        for english in ("Simulation", "Example Scene", "Pause Simulation", "Noise"):
            if english in body:
                errors.append(f"English label still shown: {english}")
        if page.evaluate("() => !document.getElementById('loading').hidden"):
            errors.append("loading message still shown")
        if scene_id == PHYSICS_SCENES[0]:
            # The tab back to the robot page resolves inside the site.
            href = page.evaluate("() => document.querySelector('#lesson-nav a').href")
            if not href.startswith(origin):
                errors.append(f"tab back points outside the site: {href}")
    seconds = time.monotonic() - start
    page.close()
    problem = state if state != "ready" else (errors[0] if errors else (failed[0] if failed else None))
    label = "FAIL" if problem else "ok"
    title = f"physics/{scene_id}"
    print(f"{label:<5}{title:<42}{seconds:6.1f}s  {reading[:40]}  {problem or 'ready'}")
    for error in errors[1:8]:
        print(f"      {error}")
    return problem


def _exercise_lesson(page, errors: list[str]) -> None:
    page.wait_for_timeout(1500)
    body = page.inner_text("body")
    for japanese in ("状況", "マウスで触る", "自分で操作", "係数を変える"):
        if japanese not in body:
            errors.append(f"Japanese label missing: {japanese}")
    for english in ("lin_vel_x", "Interact", "Debug Viz", "FOV", "Max lin_vel_x"):
        if english in body:
            errors.append(f"English label still shown: {english}")
    push = page.evaluate(
        "() => [...document.querySelectorAll('.mantine-SegmentedControl-root label')]"
        ".some(l => l.textContent.trim() === '押す' && (l.getAttribute('data-active') !== null"
        " || (l.previousElementSibling && l.previousElementSibling.checked)))"
    )
    if not push:
        errors.append("pointer mode did not start in 押す")
    # Environment sliders (env.py): a slider move must reach the running model.
    written = page.evaluate(
        "() => { const e = document.getElementById('env-friction'); e.value = '0.1';"
        " e.dispatchEvent(new Event('input')); const h = window.__paspModel;"
        " return h && h.mjModel ? h.mjModel.geom_friction[0] : null; }"
    )
    if written is None or abs(written - 0.1) > 1e-6:
        errors.append(f"friction slider did not reach the model: {written}")
    page.click("#env-reset")
    for japanese in ("環境の条件", "床の摩擦", "荷物の重さ", "ロボットで試す"):
        if japanese not in page.inner_text("body"):
            errors.append(f"Japanese label missing: {japanese}")
    page.click("#lesson-up")
    page.click("#lesson-down")
    text = page.inner_text("#lesson-tally")
    if "立て直した 1" not in text or "倒れた 1" not in text:
        errors.append(f"tally did not count: {text}")
    page.click("#lesson-reset")
    page.wait_for_timeout(500)


def _step_rate(page, control_dt: float) -> dict:
    before = page.evaluate(
        "() => ({messages: window.__stepProbe.messages, waits: window.__stepProbe.waits, t: performance.now()})"
    )
    page.wait_for_timeout(5000)
    after = page.evaluate(
        "() => ({messages: window.__stepProbe.messages, waits: window.__stepProbe.waits, t: performance.now()})"
    )
    seconds = max(0.001, (after["t"] - before["t"]) / 1000)
    messages = after["messages"] - before["messages"]
    waits = after["waits"] - before["waits"]
    # On time, the loop waits with setTimeout. Behind, it yields twice on a MessageChannel.
    steps = messages / 2 + waits
    return {
        "hz": steps / seconds,
        "seconds": seconds,
        "messages": messages,
        "waits": waits,
        "target": (1 / control_dt) if control_dt else 0,
    }


def _note_http(response, failed: list[str]) -> None:
    if response.status >= 400 and not response.url.endswith("/favicon.ico"):
        failed.append(f"HTTP {response.status} {response.url}")


def _base_path(index_html: str) -> str:
    marker = "/assets/"
    start = index_html.find('src="')
    if start < 0:
        return "/"
    rest = index_html[start + 5 :]
    assets = rest.find(marker)
    if assets <= 0 or not rest.startswith("/"):
        return "/"
    return rest[:assets] + "/"


if __name__ == "__main__":
    main()

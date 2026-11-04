"""Build, serve, and check the static playground.

Tasks come from mjswan_playground's builders. One task is one process, matching
that project's site command: a failure is reported and the other tasks still build.
The swan icon and the dialog it opens are mjswan's stock viewer; this package does
not replace them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

# Order is the order they appear in the viewer. The first project opens by default.
# microduck and the LAFAN1 dance are not here: their terms are non-commercial.
TASKS = ("unitreerl", "booster", "luwu", "pacman", "leap")

PAGES_REPOSITORY = "physical-ai-sim-playground"


def project_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    return Path.cwd()


def build() -> None:
    parser = argparse.ArgumentParser(
        prog="build",
        description=(
            "Build the walking lessons, luwu, pacman, and leap into one static site at dist/."
        ),
    )
    parser.add_argument(
        "--base-path",
        default=os.environ.get("MJSWAN_BASE_PATH", "/"),
        help="URL prefix baked into the viewer (default: $MJSWAN_BASE_PATH or /).",
    )
    args = parser.parse_args()
    raise SystemExit(run_build(args.base_path))


def serve() -> None:
    parser = argparse.ArgumentParser(
        prog="serve",
        description="Serve dist/ the way mjswan serve does, including COOP/COEP headers.",
    )
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8080")))
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Do not open a browser tab.",
    )
    args = parser.parse_args()
    raise SystemExit(run_serve(args.host, args.port, open_browser=not args.no_open))


def verify() -> None:
    parser = argparse.ArgumentParser(
        prog="verify",
        description=(
            "Request index, the swan logo, wasm, onnx, and scene files from dist/. "
            "Uses a plain static server, which is how GitHub Pages serves the site. "
            "Also refuses a shipped asset whose terms are non-commercial, no-derivatives, "
            "GPL, CERN-OHL, or missing."
        ),
    )
    parser.add_argument(
        "dist",
        nargs="?",
        type=Path,
        default=None,
        help="Site directory (default: <repo>/dist).",
    )
    args = parser.parse_args()
    root = project_root()
    dist = (args.dist or root / "dist").resolve()
    raise SystemExit(run_verify(dist))


def run_build(base_path: str) -> int:
    base_path = _check_base(base_path)
    root = project_root()
    work = root / "build" / "tasks"
    if work.exists():
        _rmtree(work)
    work.mkdir(parents=True)

    print(f"python {sys.version.split()[0]}  base_path={base_path}", flush=True)
    print(f"tasks: {', '.join(TASKS)}", flush=True)

    built: list[Path] = []
    failed: list[tuple[str, str]] = []
    env = os.environ.copy()
    env.setdefault("MUJOCO_GL", "disable")
    env.setdefault("GIT_TERMINAL_PROMPT", "0")
    env["PYTHONUNBUFFERED"] = "1"

    for task in TASKS:
        dest = (work / task).resolve()
        command = [
            sys.executable,
            "-m",
            "physical_ai_sim_playground.build_task",
            task,
            str(dest),
        ]
        print(f"\n=== {task} ===", flush=True)
        print("$ " + " ".join(command), flush=True)
        proc = subprocess.run(command, cwd=root, env=env)
        manifest = dest / "manifest.json"
        if proc.returncode != 0 or not manifest.is_file():
            why = f"exit {proc.returncode}"
            if proc.returncode == 0:
                why = "exit 0 but manifest.json was not written"
            failed.append((task, why))
            print(f"=== {task} failed ({why}); continuing with the other tasks ===", flush=True)
            continue
        built.append(dest)
        print(f"=== {task} ok ===", flush=True)

    if not built:
        print("\nNo task produced a manifest. dist/ was not written.", file=sys.stderr)
        _print_failures(failed)
        return 1

    from mjswan_playground._site import SIZE_LIMIT, SiteError, install_engine, merge, size

    site = root / "dist"
    try:
        projects = merge(built, site)
        install_engine(site, base_path)
    except SiteError as exc:
        print(f"\nCould not assemble the site: {exc}", file=sys.stderr)
        _print_failures(failed)
        return 1

    from physical_ai_sim_playground.localize import localize
    from physical_ai_sim_playground.overlay import inject

    localize(site)
    projects = json.loads((site / "manifest.json").read_text())["projects"]
    inject(site / "index.html")
    print("\n=== site ===", flush=True)
    for project in projects:
        nbytes = size(site / project["id"])
        scenes = ", ".join(
            scene.get("name", scene.get("id", "?")) for scene in project.get("scenes", [])
        )
        print(f"{project['id']:<28} {nbytes / 1e6:8.1f} MB  {scenes}", flush=True)
        for scene in project.get("scenes", []):
            scene_dir = site / project["id"] / scene["id"]
            if scene_dir.is_dir():
                print(f"  {scene['id']:<32} {size(scene_dir) / 1e6:8.1f} MB", flush=True)
    site_bytes = size(site)
    print(f"{'dist/, engine included':<28} {site_bytes / 1e6:8.1f} MB", flush=True)
    print(f"wrote {site}", flush=True)
    from physical_ai_sim_playground.licenses import problems

    license_problems = problems(site)
    if license_problems:
        print("\nlicense scan failed:", file=sys.stderr)
        for problem in license_problems:
            print(f"  {problem}", file=sys.stderr)
        _print_failures(failed)
        return 1
    if site_bytes > SIZE_LIMIT:
        print("GitHub Pages serves at most 1 GB.", file=sys.stderr)
        _print_failures(failed)
        return 1
    if failed:
        _print_failures(failed)
        print("dist/ contains only the tasks that built.", file=sys.stderr)
        return 1
    return 0


def run_serve(host: str, port: int, *, open_browser: bool) -> int:
    dist = project_root() / "dist"
    if not (dist / "index.html").is_file():
        print(f"{dist / 'index.html'} is missing. Run `uv run build` first.", file=sys.stderr)
        return 1
    from mjswan.app import MjswanApp

    print(f"serving {dist} at http://{host}:{port}/", flush=True)
    MjswanApp.from_document(dist).launch(host=host, port=port, open_browser=open_browser)
    return 0


def run_verify(dist: Path) -> int:
    index = dist / "index.html"
    if not index.is_file():
        print(f"{index} is missing. Run `uv run build` first.", file=sys.stderr)
        return 1

    problems: list[str] = []
    logo = dist / "logo.svg"
    engine_logo = _engine_logo()
    if not logo.is_file():
        problems.append("dist/logo.svg is missing (mjswan's swan icon)")
    elif engine_logo is not None and _sha256(logo) != _sha256(engine_logo):
        problems.append(
            f"dist/logo.svg differs from mjswan's {engine_logo} (the swan icon must stay)"
        )
    else:
        print(f"ok  logo.svg matches mjswan ({logo.stat().st_size} bytes)")

    js = "\n".join(path.read_text(errors="ignore") for path in dist.rglob("*.js"))
    if "powered by mjswan" not in js:
        problems.append('viewer bundle has no "powered by mjswan" dialog title')
    else:
        print('ok  viewer bundle contains "powered by mjswan"')

    page = index.read_text(errors="ignore")
    for label in ("最初から", "立て直した", "倒れた"):
        if label not in page:
            problems.append(f"index.html has no lesson control {label}")
        else:
            print(f"ok  lesson control {label}")
    from physical_ai_sim_playground.licenses import problems as license_problems

    found = license_problems(dist)
    problems.extend(found)
    if not found:
        print("ok  license scan")

    base = _base_path(page)
    rels = _asset_rels(dist)
    for rel in _referenced(index.read_text(errors="ignore"), base):
        if rel not in rels:
            if (dist / rel).is_file():
                rels.append(rel)
            else:
                problems.append(f"index.html references missing file {rel}")
    if not any(rel.endswith(".wasm") for rel in rels):
        problems.append("no .wasm file under dist/")
    if not any(rel.endswith(".onnx") for rel in rels):
        problems.append("no .onnx file under dist/")
    if not any(rel.endswith(".mjz") for rel in rels):
        problems.append("no .mjz scene under dist/")

    mount, cleanup = _mount(dist, base)
    handler = _handler(mount)
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_address[1]}"
    print(f"checking {len(rels)} URLs at {origin}{base}")
    try:
        for rel in rels:
            url_path = _public(base, rel)
            status, nbytes, error = _get(origin + url_path)
            if status != 200 or nbytes <= 0:
                problems.append(f"{status} {url_path} ({error or str(nbytes) + ' bytes'})")
            else:
                print(f"200  {nbytes:10d}  {url_path}")
    finally:
        server.shutdown()
        if cleanup is not None:
            shutil.rmtree(cleanup, ignore_errors=True)

    if problems:
        print("\nverify failed:", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"\nverify ok  ({len(rels)} URLs, base {base})")
    return 0


def _check_base(base_path: str) -> str:
    if not (base_path.startswith("/") and base_path.endswith("/")):
        raise SystemExit(
            f"base path must start and end with /, got {base_path!r}. "
            f"Example: /{PAGES_REPOSITORY}/"
        )
    return base_path


def _print_failures(failed: list[tuple[str, str]]) -> None:
    if not failed:
        return
    print("\nfailed tasks:", file=sys.stderr)
    for task, why in failed:
        print(f"  {task}: {why}", file=sys.stderr)


def _rmtree(path: Path) -> None:
    shutil.rmtree(path)


def _engine_logo() -> Path | None:
    try:
        from importlib.metadata import distribution
    except ImportError:
        return None
    files = distribution("mjswan").files
    if not files:
        return None
    for entry in files:
        if entry.match("*/template/public/logo.svg"):
            path = Path(str(entry.locate()))
            return path if path.is_file() else None
    return None


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_path(index_html: str) -> str:
    """The prefix Vite wrote into the first absolute asset URL, or `/`."""
    for token in ('src="', "href='", 'href="', "src='"):
        start = index_html.find(token)
        if start < 0:
            continue
        rest = index_html[start + len(token) :]
        if not rest.startswith("/"):
            continue
        # /assets/... or /<repo>/assets/...
        assets = rest.find("/assets/")
        if assets < 0:
            continue
        return rest[:assets] + "/" if assets else "/"
    return "/"


def _mount(dist: Path, base: str) -> tuple[Path, Path | None]:
    """Directory whose URL root corresponds to the viewer's base path.

    Returns ``(serve_root, tempdir)``. ``tempdir`` is set when ``base`` is not ``/``
    and the caller deletes it.
    """
    prefix = base.strip("/")
    if not prefix:
        return dist, None
    import tempfile

    root = Path(tempfile.mkdtemp(prefix="playground-verify-"))
    link = root / prefix
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(dist, target_is_directory=True)
    return root, root


def _asset_rels(dist: Path) -> list[str]:
    """Paths relative to the site root for the page and the simulator's files."""
    names = ["index.html", "logo.svg", "manifest.json", "THIRD_PARTY_LICENSES.md"]
    suffixes = {".wasm", ".onnx", ".mjz", ".js", ".npz"}
    rels: list[str] = []
    seen: set[str] = set()

    def add(path: Path) -> None:
        rel = path.relative_to(dist).as_posix()
        if rel not in seen:
            seen.add(rel)
            rels.append(rel)

    for name in names:
        path = dist / name
        if path.is_file():
            add(path)
    for path in dist.rglob("*"):
        if path.is_file() and path.suffix.lower() in suffixes and "node_modules" not in path.parts:
            add(path)
    return rels


def _referenced(index_html: str, base: str) -> list[str]:
    rels = []
    for match in re.findall(r'(?:src|href)="([^"]+)"', index_html):
        if match.startswith(("http://", "https://", "data:")):
            continue
        path = match.split("?", 1)[0].split("#", 1)[0]
        if path.startswith(base):
            path = path[len(base) :]
        if path.startswith("./"):
            path = path[2:]
        path = path.lstrip("/")
        if path:
            rels.append(path)
    return rels


def _public(base: str, rel: str) -> str:
    return base.rstrip("/") + "/" + rel.lstrip("/")


def _handler(directory: Path):
    root = str(directory)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=root, **kwargs)

        def log_message(self, format: str, *args) -> None:
            return

    return Handler


def _get(url: str) -> tuple[int, int, str]:
    try:
        with urlopen(url, timeout=60) as response:
            body = response.read()
            return response.status, len(body), ""
    except HTTPError as exc:
        return exc.code, 0, str(exc)
    except URLError as exc:
        return 0, 0, str(exc.reason)

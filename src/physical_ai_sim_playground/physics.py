"""The coefficient page at ``dist/physics/``: four experiments where the attendee
changes friction, damping, mass or the time step and sees what changes.

The page is zalo/mujoco_wasm (MIT) with the experiments added and the panel in
Japanese. Its sources and scenes live in ``physics/`` at the repository root. The
two libraries it runs on are not committed: they are fetched from the npm registry
at the versions and hashes pinned below, and only the files the page loads are
copied out of the packages.
"""

from __future__ import annotations

import base64
import hashlib
import io
import os
import shutil
import tarfile
from pathlib import Path
from urllib.request import urlopen

# (package, version, sha512 integrity from the npm registry, {path in package: path under lib/})
PACKAGES = (
    (
        "three",
        "0.181.2",
        "sha512-k/CjiZ80bYss6Qs7/ex1TBlPD11whT9oKfT8oTGiHa34W4JRd1NiH/Tr1DbHWQ2/vMUypxksLnF2CfmlmM5XFQ==",
        {
            "LICENSE": "three/LICENSE",
            "build/three.module.js": "three/three.module.js",
            "build/three.core.js": "three/three.core.js",
            "examples/jsm/libs/lil-gui.module.min.js": "three/lil-gui.module.min.js",
            "examples/jsm/controls/OrbitControls.js": "three/OrbitControls.js",
        },
    ),
    (
        "@mujoco/mujoco",
        "3.17.0",
        "sha512-0gXUIoedxw1jPAWQC79CC4qU9B3pu0PPa9a4Vt+qGrw4HXFh/KdQhWogybLndOusIGKvzUsU0HG6GgZOvQYj0Q==",
        {
            "mujoco.js": "mujoco/mujoco.js",
            "mujoco.wasm": "mujoco/mujoco.wasm",
        },
    ),
)

# MuJoCo's npm package ships no LICENSE file; its package.json says Apache-2.0.
MUJOCO_NOTICE = """MuJoCo WebAssembly build (@mujoco/mujoco 3.17.0)
Copyright DeepMind Technologies Limited
Licensed under the Apache License, Version 2.0.
https://github.com/google-deepmind/mujoco
"""


def cache_dir() -> Path:
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "physical-ai-sim-playground" / "npm"


def install(root: Path, site: Path) -> None:
    """Copy ``root/physics`` to ``site/physics`` and add the pinned libraries under ``lib/``."""
    source = root / "physics"
    dest = site / "physics"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(source, dest)
    lib = dest / "lib"
    for name, version, integrity, files in PACKAGES:
        tarball = _fetch(name, version, integrity)
        with tarfile.open(fileobj=io.BytesIO(tarball), mode="r:gz") as archive:
            for inner, target in files.items():
                member = archive.getmember(f"package/{inner}")
                data = archive.extractfile(member)
                if data is None:
                    raise RuntimeError(f"{name}@{version} has no file {inner}")
                out = lib / target
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data.read())
    (lib / "mujoco" / "NOTICE").write_text(MUJOCO_NOTICE)


def _fetch(name: str, version: str, integrity: str) -> bytes:
    short = name.rsplit("/", 1)[-1]
    cached = cache_dir() / f"{short}-{version}.tgz"
    if cached.is_file():
        data = cached.read_bytes()
        if _sri(data) == integrity:
            return data
    url = f"https://registry.npmjs.org/{name}/-/{short}-{version}.tgz"
    with urlopen(url, timeout=120) as response:
        data = response.read()
    if _sri(data) != integrity:
        raise RuntimeError(f"{url} does not match the pinned sha512")
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def _sri(data: bytes) -> str:
    return "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()

"""Scene copies that change the floor, the torso mass, or the ground in front.

mjswan can write ``geom_friction`` from a traced event, and the walk already does
that for the feet. It cannot tie that write to a slider: an event is traced
without the command manager, so a ``ui_command`` never reaches it. MuJoCo also
takes the larger of the two geoms' friction, so a slippery floor alone does
nothing while the feet stay near 1. Each lesson is therefore its own scene.
The policy files are copies; the network is unchanged.

A payload is extra mass at the torso's existing center of mass. A point mass
there does not change the inertia about that point, so ``diaginertia`` stays.
"""

from __future__ import annotations

import json
import re
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path

# Sliding friction. 0.2 still walks like the default floor; 0.08 does not.
ICE_FRICTION = 0.08
# Fractions of the robot's mass, added on the torso. 40% still walks on both.
# 55% drops the 20 kg K1 and only slows the 33 kg G1.
LIGHT_FRACTION = 0.40
HEAVY_FRACTION = 0.55
# Full height of the box. 8 cm trips the G1 walk; a lower curb does too.
STEP_HEIGHT_M = 0.08
# Pitch of the ramp, degrees. 8 degrees already shortens the walk.
SLOPE_DEG = 8.0


@dataclass(frozen=True)
class Lesson:
    suffix: str
    name: str
    kind: str


LESSONS = (
    Lesson("ice", "氷の床", "ice"),
    Lesson("light", "軽い荷物", "light"),
    Lesson("heavy", "重い荷物", "heavy"),
    Lesson("step", "段差", "step"),
    Lesson("slope", "坂", "slope"),
)


def add_walk_variants(dest: Path, task: str) -> None:
    """Copy the walking scene into the five lessons and point the manifest at them."""
    manifest_path = dest / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    project = manifest["projects"][0]
    root = dest / project["id"]
    walk = _walk_scene(project, task)
    walk_dir = root / walk["id"]
    xml_name, xml = _read_xml(walk_dir / "scene.mjz")
    total = _total_mass(xml)
    body = _payload_body(xml)
    made: list[str] = []
    insert_at = project["scenes"].index(walk) + 1
    for lesson in LESSONS:
        # One underscore. The viewer sanitizes the query by collapsing every
        # non-alphanumeric run, so a double underscore never matches the id.
        scene_id = f"{walk['id']}_{lesson.suffix}"
        scene_dir = root / scene_id
        if scene_dir.exists():
            shutil.rmtree(scene_dir)
        shutil.copytree(walk_dir, scene_dir)
        patched = _patch(xml, lesson.kind, body, total)
        _write_xml(scene_dir / "scene.mjz", xml_name, patched)
        entry = json.loads(json.dumps(walk))
        entry["id"] = scene_id
        entry["name"] = lesson.name
        if lesson.kind == "ice":
            _pin_foot_friction(entry, ICE_FRICTION)
        project["scenes"].insert(insert_at, entry)
        insert_at += 1
        made.append(f"{lesson.name} ({scene_id})")
    walk["name"] = "歩行"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    kilos = total
    light = LIGHT_FRACTION * kilos
    heavy = HEAVY_FRACTION * kilos
    print(
        f"variants on {walk['id']}: 歩行, {', '.join(made)}\n"
        f"  robot mass {kilos:.2f} kg, light +{light:.2f} kg, heavy +{heavy:.2f} kg "
        f"on {body}, ice μ={ICE_FRICTION}, step {STEP_HEIGHT_M * 100:.0f} cm, "
        f"slope {SLOPE_DEG:.0f} deg",
        flush=True,
    )


def _walk_scene(project: dict, task: str) -> dict:
    scenes = project.get("scenes") or []
    if task == "unitreerl":
        found = [scene for scene in scenes if "flat" in scene["id"]]
    elif task == "booster":
        found = [
            scene
            for scene in scenes
            if re.search(r"walk", scene["id"], re.I)
            or re.search(r"\bWalk\b", scene.get("name", ""))
        ]
    else:
        found = []
    if len(found) != 1:
        names = ", ".join(scene["id"] for scene in scenes) or "(none)"
        raise RuntimeError(
            f"{task} should have one walking scene to copy, found {len(found)} ({names})."
        )
    return found[0]


def _read_xml(mjz: Path) -> tuple[str, str]:
    with zipfile.ZipFile(mjz) as archive:
        names = [name for name in archive.namelist() if name.endswith(".xml")]
        if len(names) != 1:
            raise RuntimeError(f"{mjz} has {len(names)} XML files, expected one.")
        return names[0], archive.read(names[0]).decode()


def _write_xml(mjz: Path, xml_name: str, xml: str) -> None:
    temporary = mjz.with_suffix(".mjz.tmp")
    with zipfile.ZipFile(mjz) as source, zipfile.ZipFile(temporary, "w") as target:
        for info in source.infolist():
            data = xml.encode() if info.filename == xml_name else source.read(info.filename)
            target.writestr(info.filename, data, compress_type=zipfile.ZIP_DEFLATED)
    temporary.replace(mjz)


def _total_mass(xml: str) -> float:
    masses = [float(value) for value in re.findall(r'<inertial\b[^>]*\bmass="([^"]+)"', xml)]
    if not masses:
        raise RuntimeError("The scene XML has no inertial mass.")
    return sum(masses)


def _payload_body(xml: str) -> str:
    names = re.findall(r'<body\b[^>]*\bname="([^"]+)"', xml)
    for name in names:
        bare = name.rsplit("/", 1)[-1]
        if bare in {"torso_link", "trunk"}:
            return name
    raise RuntimeError("No torso_link or trunk body to hang a payload on.")


def _patch(xml: str, kind: str, body: str, total: float) -> str:
    if kind == "ice":
        return _friction_all(xml, ICE_FRICTION)
    if kind == "light":
        return _add_mass(xml, body, LIGHT_FRACTION * total)
    if kind == "heavy":
        return _add_mass(xml, body, HEAVY_FRACTION * total)
    if kind == "step":
        half = STEP_HEIGHT_M / 2
        geom = (
            f'<geom name="lesson_step" type="box" pos="1.05 0 {half:.4f}" '
            f'size="0.35 1.2 {half:.4f}" rgba="0.72 0.48 0.28 1" '
            f'friction="1 0.005 0.0001"/>'
        )
        return _after_plane(xml, geom)
    if kind == "slope":
        return _after_plane(xml, _slope_geom())
    raise RuntimeError(f"unknown lesson {kind}")


def _friction_all(xml: str, mu: float) -> str:
    friction = f'friction="{mu:.4f} 0.001 0.0001"'

    def edit(match: re.Match[str]) -> str:
        tag = match.group(0)
        if "friction=" in tag:
            return re.sub(r'friction="[^"]*"', friction, tag, count=1)
        return tag[:-2] + " " + friction + "/>" if tag.endswith("/>") else tag

    return re.sub(r"<geom\b[^>]*/>", edit, xml)


def _add_mass(xml: str, body: str, extra: float) -> str:
    pattern = rf'(<body\b[^>]*\bname="{re.escape(body)}"[^>]*>\s*<inertial\b[^>]*\bmass=")([^"]+)(")'
    found = re.search(pattern, xml)
    if found is None:
        raise RuntimeError(f"{body} has no inertial mass to add to.")
    updated = f"{float(found.group(2)) + extra:.6g}"
    xml = xml[: found.start(2)] + updated + xml[found.end(2) :]
    # The mass text changed length, so find the inertial tag's end again.
    close = xml.find("/>", found.start())
    if close < 0:
        raise RuntimeError(f"{body} inertial tag does not close with />.")
    # A box with no collision, so the mass is visible and the contacts stay the feet's.
    box = (
        '\n            <geom name="lesson_payload" type="box" pos="-0.08 0 0.2" '
        'size="0.06 0.09 0.07" contype="0" conaffinity="0" rgba="0.9 0.45 0.15 1"/>'
    )
    return xml[: close + 2] + box + xml[close + 2 :]


def _after_plane(xml: str, geom: str) -> str:
    match = re.search(r'<geom\b[^>]*\btype="plane"[^>]*/>', xml)
    if match is None:
        raise RuntimeError("The scene has no plane geom to put a step or a slope after.")
    return xml[: match.end()] + "\n      " + geom + xml[match.end() :]


def _slope_geom() -> str:
    import math

    theta = math.radians(SLOPE_DEG)
    half_len = 1.4
    half_thick = 0.02
    # The near edge sits on the ground, ahead of the feet. Negative pitch
    # raises the far end; that is the sign the G1 walk slows down on.
    height = half_len * math.sin(theta) + half_thick * math.cos(theta)
    near = 0.7
    center = near + half_len * math.cos(theta)
    # The exported scenes set compiler angle="radian".
    return (
        f'<geom name="lesson_slope" type="box" pos="{center:.4f} 0 {height:.4f}" '
        f'euler="0 {-theta:.5f} 0" size="{half_len:g} 1.2 {half_thick:g}" '
        f'rgba="0.45 0.62 0.78 1" friction="1 0.005 0.0001"/>'
    )


def _pin_foot_friction(scene: dict, mu: float) -> None:
    """The startup event overwrites foot friction. A fixed draw keeps the ice."""
    pinned = False
    for event in _events(scene):
        if event.get("name") != "foot_friction":
            continue
        event["rand_ranges"] = [[mu, mu]]
        params = event.get("params")
        if isinstance(params, dict) and "ranges" in params:
            params["ranges"] = [mu, mu]
        pinned = True
    if pinned:
        return
    print("  no foot_friction startup event; the .mjz friction is what the browser uses")


def _events(node: object):
    if isinstance(node, dict):
        events = node.get("events")
        if isinstance(events, list):
            yield from (event for event in events if isinstance(event, dict))
        for value in node.values():
            yield from _events(value)
    elif isinstance(node, list):
        for value in node:
            yield from _events(value)

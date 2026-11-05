"""Japanese names and labels for the merged site, written into ``dist/manifest.json``.

The stock viewer reads project, scene, policy and command labels from the manifest,
so they are renamed here. Labels the viewer itself draws (``Scene``, ``Interact``,
``Reset``...) are renamed in the page by ``overlay.py``.

Scenes that are not part of the lesson are dropped here as well, together with their
directories, so they are neither listed nor shipped.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

# Display order and names. Ids stay as they are: they are the URL (?project=...).
PROJECTS: dict[str, str] = {
    "unitree_rl_mjlab": "人型ロボット G1",
    "booster_k1": "小型の人型ロボット K1",
    "luwu_mjlab": "四足ロボット",
    "pac_man": "ボールをよける G1",
    "leap_hand": "ロボットの手",
}

SCENES: dict[str, str] = {
    # G1 and K1 lesson scenes are already named by variants.py.
    "mini2s_walk_flat": "Mini2S 歩行",
    "mini2s_turn_flat": "Mini2S 起き上がり",
    "mini2sw_walk_flat": "Mini2SW 歩行（足先が車輪）",
    "mini2sw_turn_flat": "Mini2SW 起き上がり",
    "lite3_walk_flat": "Lite3 歩行",
    "unitree_g1_amp_dodge_depth_single_ballonly_flat": "ボールをよける",
    "unitree_g1_amp_flat": "歩行",
    "mjlab_leap_left_custom_handcube_rotate": "キューブを回す",
}

# Upstream K1 motion clips whose source dataset booster_deploy does not name.
DROP_SCENES: dict[str, set[str]] = {
    "booster_k1": {"k1_mj_dance", "k1_fight"},
}

COMMAND_LABELS: dict[str, str] = {
    "enabled": "自分で操作",
    "lin_vel_x": "前後の速さ",
    "lin_vel_y": "左右の速さ",
    "ang_vel_z": "向きを変える",
    "zero": "止める",
}


def localize(site: Path) -> None:
    path = site / "manifest.json"
    manifest = json.loads(path.read_text())

    projects = manifest["projects"]
    unknown = [p["id"] for p in projects if p["id"] not in PROJECTS]
    if unknown:
        raise RuntimeError(f"no Japanese name for project(s): {', '.join(unknown)}")
    order = list(PROJECTS)
    projects.sort(key=lambda p: order.index(p["id"]))

    for project in projects:
        project["name"] = PROJECTS[project["id"]]
        project["default"] = project["id"] == order[0]
        drop = DROP_SCENES.get(project["id"], set())
        for scene_id in drop:
            shutil.rmtree(site / project["id"] / scene_id, ignore_errors=True)
        project["scenes"] = [s for s in project["scenes"] if s["id"] not in drop]
        for scene in project["scenes"]:
            if scene["id"] in SCENES:
                scene["name"] = SCENES[scene["id"]]
            for policy in scene.get("policies", []):
                policy["name"] = "学習済みポリシー"
            for mdp in scene.get("mdps", []):
                for command in (mdp.get("commands") or {}).values():
                    inputs = (command.get("ui") or {}).get("inputs", [])
                    if inputs and not any(i.get("type") == "slider" for i in inputs):
                        # Get-up scenes: only "Enable" and "Zero", which steer nothing.
                        command.pop("ui", None)
                        continue
                    for item in inputs:
                        if item.get("name") in COMMAND_LABELS:
                            item["label"] = COMMAND_LABELS[item["name"]]
                        # The "Max ..." companion sliders only rescale the drag range.
                        item.pop("adjustable_range", None)

    # The environment sliders (env.py): one reset-only plugin event in every MDP.
    from physical_ai_sim_playground.env import EVENT_NAME, PLUGIN_FILE

    manifest["plugins"] = PLUGIN_FILE
    for project in projects:
        for scene in project["scenes"]:
            for mdp in scene.get("mdps", []):
                events = mdp.setdefault("events", [])
                if not any(e.get("name") == EVENT_NAME for e in events):
                    events.append({"name": EVENT_NAME})

    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")

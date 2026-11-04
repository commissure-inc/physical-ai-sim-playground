"""Walk the lesson scenes with the shipped policy and compare them to 歩行.

Loads each scene's ``.mjz`` and the ONNX files beside it. The command is a
steady 0.6 m/s forward for 4 s. Prints base height and forward distance.
Exits 1 when 歩行 falls, or when 氷の床 / 重い荷物 / 段差 / 坂 do not move
the outcome relative to 歩行.

    uv run --with onnxruntime python scripts/check_lessons.py dist

The default scene's browser build also draws a foot friction in the startup
event's range. This script uses the friction stored in the ``.mjz``.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import zipfile
from pathlib import Path

import mujoco
import numpy as np

LESSONS = ("歩行", "氷の床", "軽い荷物", "重い荷物", "段差", "坂")
# Only these projects carry the lesson variants. Others may reuse a name ("歩行").
LESSON_PROJECTS = ("unitree_rl_mjlab", "booster_k1")
SECONDS = 4.0
FORWARD = 0.6


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("site", type=Path, help="directory written by `uv run build`")
    args = parser.parse_args()
    site = args.site.resolve()
    manifest = json.loads((site / "manifest.json").read_text())
    import onnxruntime as ort

    failed = False
    for project in manifest.get("projects") or []:
        if project["id"] not in LESSON_PROJECTS:
            continue
        rows = []
        for scene in project.get("scenes") or []:
            if scene.get("name") not in LESSONS:
                continue
            row = _run(site, project, scene, ort)
            rows.append(row)
            print(
                f"{project['id']:<22} {scene['name']:<8} "
                f"z_end {row['z_end']:.3f}  z_min {row['z_min']:.3f}  x_end {row['x_end']:.3f}"
            )
        if rows:
            failed = failed or _judge(project["id"], rows)
    raise SystemExit(1 if failed else 0)


def _run(site: Path, project: dict, scene: dict, ort) -> dict:
    scene_dir = site / project["id"] / scene["id"]
    model = _model(scene_dir / scene.get("scene", "scene.mjz"))
    data = mujoco.MjData(model)
    if model.nkey > 0:
        mujoco.mj_resetDataKeyframe(model, data, 0)
    else:
        mujoco.mj_resetData(model, data)
    mujoco.mj_forward(model, data)

    policy = _session(ort, _one(scene_dir, "policy/*.onnx"))
    obs_path = _one(scene_dir, "mdp/*/obs/actor.onnx")
    obs = _session(ort, obs_path) if obs_path else None
    names, defaults, scale, stiffness, damping = _action(scene)
    hinges = _hinges(model)
    actuators = {
        int(model.actuator_trnid[index, 0]): index for index in range(model.nu)
    }
    joint_ids = [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name) for name in names]
    if any(index < 0 for index in joint_ids):
        missing = [name for name, index in zip(names, joint_ids) if index < 0]
        raise SystemExit(f"{scene['id']} is missing joints {missing}")
    gyro_adr = _gyro(model)
    control_dt = float(scene["control_dt"])
    decimation = max(1, int(round(control_dt / model.opt.timestep)))
    steps = int(round(SECONDS / control_dt))
    last = np.zeros(_action_width(policy, names), np.float32)
    carry = _carry(policy)
    zs: list[float] = []
    xs: list[float] = []
    for step in range(steps):
        vector = _observe(obs, model, data, hinges, names, gyro_adr, last, step)
        action, carry = _policy(policy, vector, step, carry)
        last = np.resize(action, last.shape).astype(np.float32)
        for _ in range(decimation):
            # K1's exported actuators are torques. The browser recomputes
            # kp*(target-q) - kd*qd on every physics step. G1's actuators are
            # position servos, so the same write just holds the target.
            _apply(
                model, data, names, joint_ids, actuators, defaults, scale, stiffness, damping, action
            )
            mujoco.mj_step(model, data)
        xs.append(float(data.qpos[0]))
        zs.append(float(data.qpos[2]))
    return {"name": scene["name"], "z_end": zs[-1], "z_min": min(zs), "x_end": xs[-1]}


def _judge(project_id: str, rows: list[dict]) -> bool:
    by_name = {row["name"]: row for row in rows}
    missing = [name for name in LESSONS if name not in by_name]
    if missing:
        print(f"FAIL {project_id}: missing {', '.join(missing)}", file=sys.stderr)
        return True
    base = by_name["歩行"]
    failed = False
    if base["z_min"] < 0.48 or base["z_end"] < 0.48 or base["x_end"] < 0.8:
        print(
            f"FAIL {project_id}: 歩行 did not stay up and walk "
            f"(z_end {base['z_end']:.3f}, z_min {base['z_min']:.3f}, x_end {base['x_end']:.3f})",
            file=sys.stderr,
        )
        failed = True
    checks = (
        ("氷の床", 0.25, 0.04),
        ("軽い荷物", 0.15, 0.03),
        ("重い荷物", 0.25, 0.05),
        ("段差", 0.25, 0.12),
        ("坂", 0.15, 0.08),
    )
    for name, dx, dz in checks:
        row = by_name[name]
        moved = (
            abs(row["x_end"] - base["x_end"]) >= dx
            or abs(row["z_min"] - base["z_min"]) >= dz
            or abs(row["z_end"] - base["z_end"]) >= dz
        )
        if not moved:
            print(f"FAIL {project_id}: {name} did not change the walk", file=sys.stderr)
            failed = True
    return failed


def _model(mjz: Path) -> mujoco.MjModel:
    with tempfile.TemporaryDirectory() as directory:
        zipfile.ZipFile(mjz).extractall(directory)
        xmls = list(Path(directory).glob("*.xml"))
        if len(xmls) != 1:
            raise SystemExit(f"{mjz} has {len(xmls)} XML files")
        return mujoco.MjModel.from_xml_path(str(xmls[0]))


def _session(ort, path: Path | None):
    if path is None:
        raise SystemExit("missing an ONNX file")
    return ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])


def _one(scene_dir: Path, pattern: str) -> Path | None:
    found = sorted(scene_dir.glob(pattern))
    if not found:
        return None
    actor = [path for path in found if path.name == "actor.onnx"]
    return actor[0] if actor else found[0]


def _action(scene: dict) -> tuple[list[str], np.ndarray, object, object, object]:
    policy = scene["policies"][0]
    names = list(policy["policy_joint_names"])
    defaults = np.array(policy["default_joint_pos"], np.float64)
    action = scene["mdps"][0]["actions"]["joint_pos"]
    return names, defaults, action.get("scale", 1.0), action.get("stiffness"), action.get("damping")


def _hinges(model: mujoco.MjModel) -> list[tuple[str, int, int]]:
    hinges = []
    for index in range(model.njnt):
        if model.jnt_type[index] == mujoco.mjtJoint.mjJNT_FREE:
            continue
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, index)
        hinges.append((name, int(model.jnt_qposadr[index]), int(model.jnt_dofadr[index])))
    return hinges


def _gyro(model: mujoco.MjModel) -> int:
    for index in range(model.nsensor):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_SENSOR, index) or ""
        if "ang_vel" in name or model.sensor_type[index] == mujoco.mjtSensor.mjSENS_GYRO:
            return int(model.sensor_adr[index])
    raise SystemExit("no gyro sensor")


def _action_width(policy, names: list[str]) -> int:
    for output in policy.get_outputs():
        if output.name in {"action", "actions"}:
            shape = output.shape
            if shape and isinstance(shape[-1], int):
                return int(shape[-1])
    return len(names)


def _carry(policy) -> np.ndarray | None:
    for item in policy.get_inputs():
        if "hx" in item.name or item.name.startswith("adapt"):
            width = 128
            for dim in item.shape:
                if isinstance(dim, int) and dim > 1:
                    width = dim
            return np.zeros((1, width), np.float32)
    return None


def _observe(obs, model, data, hinges, names, gyro_adr, last, step) -> np.ndarray:
    by_name = {name: (qpos, qvel) for name, qpos, qvel in hinges}
    # The observation graph wants either every hinge, the policy's joints, or the
    # policy's joints with the head left out (the K1 walk). The slot width picks.
    q_all = np.array([data.qpos[adr] for _, adr, _ in hinges], np.float32)
    qd_all = np.array([data.qvel[adr] for _, _, adr in hinges], np.float32)
    ordered = [by_name[name] for name in names if name in by_name]
    q_named = np.array([data.qpos[adr] for adr, _ in ordered], np.float32)
    qd_named = np.array([data.qvel[adr] for _, adr in ordered], np.float32)
    no_head = [(adr, vel) for name, adr, vel in hinges if "head" not in name.lower()]
    q_body = np.array([data.qpos[adr] for adr, _ in no_head], np.float32)
    qd_body = np.array([data.qvel[adr] for _, adr in no_head], np.float32)
    q = q_named if q_named.size else q_all
    qd = qd_named if qd_named.size else qd_all
    gyro = np.array(data.sensordata[gyro_adr : gyro_adr + 3], np.float32)
    gravity = _body_gravity(data.qpos[3:7]).astype(np.float32)
    command = np.array([FORWARD, 0.0, 0.0], np.float32)
    if obs is None:
        return np.concatenate([gyro, gravity, command, q, qd])[None, :]
    feeds = {}
    for item in obs.get_inputs():
        feeds[item.name] = _slot(
            item.name, item.shape, q, qd, q_all, qd_all, q_body, qd_body, gyro, gravity, command, last, step
        )
    return np.asarray(obs.run(None, feeds)[0], np.float32)


def _slot(name, shape, q, qd, q_all, qd_all, q_body, qd_body, gyro, gravity, command, last, step) -> np.ndarray:
    width = shape[-1] if shape else None
    if "joint_pos" in name or "joint_vel" in name:
        table = q if "joint_pos" in name else qd
        full = q_all if "joint_pos" in name else qd_all
        body = q_body if "joint_pos" in name else qd_body
        if isinstance(width, int):
            if table.size == width:
                value = table
            elif full.size == width:
                value = full
            elif body.size == width:
                value = body
            else:
                raise SystemExit(
                    f"{name} wants {width} joints; policy list {table.size}, "
                    f"hinges {full.size}, without head {body.size}"
                )
        else:
            value = table
    elif "gravity" in name:
        value = gravity
    elif "ang_vel" in name or "gyro" in name or name.endswith("imu"):
        value = gyro
    elif "step_count" in name or "gait" in name:
        value = np.array([step], np.float32)
    elif "command" in name:
        value = command
    elif "action" in name:
        value = last
    else:
        value = np.zeros(width or 1, np.float32)
    value = np.asarray(value, np.float32).reshape(-1)
    if isinstance(width, int) and value.size != width:
        raise SystemExit(f"{name} wants width {width}, got {value.size}")
    return value.reshape(1, -1)


def _policy(policy, vector, step: int, carry):
    feeds = {}
    for item in policy.get_inputs():
        if item.name in {"obs", "actor"} or "obs" in item.name:
            feeds[item.name] = vector
        elif item.name == "is_init":
            feeds[item.name] = np.array([step == 0], dtype=np.bool_)
        elif carry is not None and ("hx" in item.name or item.name.startswith("adapt")):
            feeds[item.name] = carry
        else:
            feeds[item.name] = np.zeros(
                [1 if not isinstance(dim, int) else dim for dim in item.shape], np.float32
            )
    outputs = policy.run(None, feeds)
    names = [item.name for item in policy.get_outputs()]
    action = None
    for name, value in zip(names, outputs):
        if name in {"action", "actions"}:
            action = np.asarray(value, np.float32).reshape(-1)
        if carry is not None and "hx" in name:
            carry = np.asarray(value, np.float32)
    if action is None:
        action = np.asarray(outputs[0], np.float32).reshape(-1)
    return action, carry


def _apply(model, data, names, joint_ids, actuators, defaults, scale, stiffness, damping, action) -> None:
    for index, (name, joint) in enumerate(zip(names, joint_ids)):
        if index >= action.size:
            break
        gain = scale[name] if isinstance(scale, dict) else float(scale)
        target = float(defaults[index]) + float(gain) * float(action[index])
        actuator = actuators[joint]
        if not stiffness:
            data.ctrl[actuator] = target
            continue
        kp = float(stiffness[name] if isinstance(stiffness, dict) else stiffness)
        kd = float(damping[name] if isinstance(damping, dict) else damping or 0.0)
        q = float(data.qpos[int(model.jnt_qposadr[joint])])
        qd = float(data.qvel[int(model.jnt_dofadr[joint])])
        torque = kp * (target - q) - kd * qd
        low, high = model.actuator_forcerange[actuator]
        data.ctrl[actuator] = float(min(max(torque, low), high))


def _body_gravity(quat: np.ndarray) -> np.ndarray:
    """Gravity in the root frame. ``quat`` is MuJoCo's wxyz."""
    w, x, y, z = quat
    inverse = np.array([w, -x, -y, -z])
    return _rotate(inverse, np.array([0.0, 0.0, -1.0]))


def _rotate(quat: np.ndarray, vector: np.ndarray) -> np.ndarray:
    w, x, y, z = quat
    u = np.array([x, y, z])
    return 2 * np.dot(u, vector) * u + (w * w - np.dot(u, u)) * vector + 2 * w * np.cross(u, vector)


if __name__ == "__main__":
    main()

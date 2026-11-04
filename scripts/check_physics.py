"""Check that the four coefficient experiments show what the page says they show.

The page (physics/src/experiments.js) writes the slider value into the model and
restarts. This script does the same with MuJoCo's Python bindings and checks the
outcome the lesson text promises:

- ramp: the box slides off at friction 0.3 and stays at 0.5 (tan 20° = 0.364);
- bounce: a smaller damping ratio bounces higher;
- mass: a heavier box takes longer to reach the 1 m mark;
- time step: the ball bounces off the wall at 0.001 s and passes through at 0.04 s.

    uv run python scripts/check_physics.py

Exits 1 when an outcome does not hold. The Python bindings and the page's wasm build
are different MuJoCo versions; the margins below are wide enough for both.
"""

from __future__ import annotations

import sys
from pathlib import Path

import mujoco

SCENES = Path(__file__).resolve().parents[1] / "physics" / "scenes"
BALL_SPEED = 4  # experiments.js BALL_SPEED


def load(name: str) -> mujoco.MjModel:
    return mujoco.MjModel.from_xml_path(str(SCENES / name))


def geoms(model: mujoco.MjModel, names: list[str]) -> list[int]:
    return [mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, n) for n in names]


def body(model: mujoco.MjModel, name: str) -> int:
    return mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)


def ramp(friction: float, seconds: float = 3.0) -> float:
    """Height the box loses once it rests on the ramp, in metres.

    The box starts a few centimetres above the surface; the first 0.3 s is that drop.
    """
    model = load("exp_ramp.xml")
    for g in geoms(model, ["ramp", "box"]):
        model.geom_friction[g, 0] = friction
    data = mujoco.MjData(model)
    b = body(model, "box")
    while data.time < 0.3:
        mujoco.mj_step(model, data)
    start = data.xpos[b, 2]
    while data.time < seconds:
        mujoco.mj_step(model, data)
    return start - data.xpos[b, 2]


def bounce(dampratio: float) -> float:
    """Highest point of the ball after its first contact with the floor."""
    model = load("exp_bounce.xml")
    for g in geoms(model, ["floor", "ball"]):
        model.geom_solref[g, 1] = dampratio
    data = mujoco.MjData(model)
    b = body(model, "ball")
    touched = False
    peak = 0.0
    while data.time < 2.0:
        mujoco.mj_step(model, data)
        z = data.xpos[b, 2]
        if not touched and data.ncon > 0:
            touched = True
        if touched:
            peak = max(peak, z)
    return peak


def mass(kg: float) -> float | None:
    """Seconds until the box reaches the 1 m mark, or None."""
    model = load("exp_mass.xml")
    b = body(model, "box")
    scale = kg / model.body_mass[b]
    model.body_mass[b] *= scale
    model.body_inertia[b] *= scale
    data = mujoco.MjData(model)
    mujoco.mj_setConst(model, data)
    data.ctrl[0] = 1
    while data.time < 20.0:
        mujoco.mj_step(model, data)
        if data.xpos[b, 0] >= 1.0:
            return data.time
    return None


def timestep(dt: float) -> bool:
    """True when the ball ends up past the wall."""
    model = load("exp_timestep.xml")
    model.opt.timestep = dt
    data = mujoco.MjData(model)
    data.qvel[0] = BALL_SPEED
    b = body(model, "ball")
    while data.time < 2.0:
        mujoco.mj_step(model, data)
    return data.xpos[b, 0] > 0.06  # experiments.js: "壁の向こう側"


def main() -> None:
    problems: list[str] = []

    slid = ramp(0.3)
    held = ramp(0.5)
    print(f"ramp      friction 0.30 drops {slid:.3f} m, 0.50 drops {held:.3f} m")
    if slid < 0.1:
        problems.append("ramp: the box does not slide at friction 0.3")
    if held > 0.01:
        problems.append("ramp: the box does not stay at friction 0.5")
    edge = next(
        (mu / 100 for mu in range(20, 50) if ramp(mu / 100) < 0.01),
        None,
    )
    print(f"          first friction that holds the box: {edge}")
    if edge is None or not 0.33 <= edge <= 0.40:
        problems.append(f"ramp: threshold {edge} is not near tan 20° = 0.364")

    high = bounce(0.05)
    low = bounce(0.8)
    print(f"bounce    dampratio 0.05 peaks at {high:.3f} m, 0.80 at {low:.3f} m")
    if not high > low + 0.05:
        problems.append("bounce: a smaller damping ratio does not bounce visibly higher")

    light = mass(1.0)
    heavy = mass(4.0)
    print(f"mass      1 kg reaches 1 m at {light}, 4 kg at {heavy}")
    if light is None or heavy is None or not heavy > light * 1.5:
        problems.append("mass: the heavier box does not arrive clearly later")

    fine = timestep(0.001)
    coarse = timestep(0.04)
    print(f"timestep  0.001 s passes the wall: {fine}, 0.04 s: {coarse}")
    if fine:
        problems.append("timestep: the ball passes the wall at 0.001 s")
    if not coarse:
        problems.append("timestep: the ball does not pass the wall at 0.04 s")

    if problems:
        print("\ncheck_physics failed:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        raise SystemExit(1)
    print("\ncheck_physics ok")


if __name__ == "__main__":
    main()

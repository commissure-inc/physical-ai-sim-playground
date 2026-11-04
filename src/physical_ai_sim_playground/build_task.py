"""Build one task into a directory. One process per task.

unitreerl's own builder also adds the LAFAN1 dance. This module builds only
the velocity walk, then copies that scene into the lesson variants. Booster
is the stock task, with the same copies on the K1 walk. Anything else is
mjswan_playground's builder unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

from physical_ai_sim_playground.variants import add_walk_variants

LESSON_TASKS = ("unitreerl", "booster")


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) != 2:
        print(
            "usage: python -m physical_ai_sim_playground.build_task <task> <output-dir>",
            file=sys.stderr,
        )
        return 2
    task, dest = argv[0], Path(argv[1]).resolve()
    if task == "unitreerl":
        _build_unitree_walk(dest)
    else:
        _build_stock(task, dest)
    if task in LESSON_TASKS:
        add_walk_variants(dest, task)
    return 0


def _build_unitree_walk(dest: Path) -> None:
    import mjswan
    from mjswan_playground.unitreerl import upstream
    from mjswan_playground.unitreerl.main import _add_walk

    root = upstream.resolve_root()
    upstream.register_tasks(root)
    builder = mjswan.Builder()
    project = builder.add_project(name="unitree_rl_mjlab", license=root / "LICENCE")
    # The dance scene is the other half of setup_builder. It is LAFAN1.
    _add_walk(project, root)
    builder.build(output_dir=dest)


def _build_stock(task: str, dest: Path) -> None:
    import typer

    from mjswan_playground._cli import _build

    try:
        _build(task, dest)
    except typer.Exit as exc:
        raise SystemExit(exc.exit_code) from exc


if __name__ == "__main__":
    raise SystemExit(main())

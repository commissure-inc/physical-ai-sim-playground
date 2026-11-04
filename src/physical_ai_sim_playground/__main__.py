"""`python -m physical_ai_sim_playground build|serve|verify`."""

import sys

from physical_ai_sim_playground.cli import build, serve, verify

_COMMANDS = {"build": build, "serve": serve, "verify": verify}


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in _COMMANDS:
        names = ", ".join(_COMMANDS)
        print(f"usage: python -m physical_ai_sim_playground {{{names}}}", file=sys.stderr)
        raise SystemExit(2)
    command = sys.argv.pop(1)
    _COMMANDS[command]()


if __name__ == "__main__":
    main()

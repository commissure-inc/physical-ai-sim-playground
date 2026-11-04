# Agent notes

Browser-only static site for an in-person training session. Attendees open one GitHub Pages URL. No install, no account, no GPU, no simulation server. MuJoCo WASM and the ONNX policies run in the browser.

## Build and check

Python is 3.12 via uv (mjswan_playground requires `>=3.11,<3.13`). Do not use the system 3.9.

```sh
uv sync
uv run build          # writes dist/; local base path is /
uv run serve          # http://127.0.0.1:8080/  (mjswan serve, with COOP/COEP)
uv run verify         # plain static server, HTTP 200 for index, logo, wasm, onnx, mjz
uvx --from playwright python scripts/check_browser.py dist
```

`uv run build` runs one process per task (`unitreerl`, `booster`, `luwu`, `pacman`, `leap`) and merges them with mjswan_playground's site merge. `luwu` downloads its ONNX policies from the Hugging Face Hub, so `huggingface_hub` is a dependency. `unitreerl` builds only the G1 velocity walk (the LAFAN1 dance scene is not built). `booster` and `unitreerl` then copy that walk into lesson scenes: 氷の床, 軽い荷物, 重い荷物, 段差, 坂. If one task fails, the reason is printed and the others still build. The process exits 1 when any task failed or the license scan finds a non-commercial, no-derivatives, GPL, CERN-OHL, or missing license on a shipped asset. `dist/` then contains only the tasks that built.

```sh
uv run --with onnxruntime python scripts/check_lessons.py dist
```

That drives each lesson's shipped ONNX for 4 s at 0.6 m/s and compares base height and forward distance with 歩行. `scripts/check_browser.py` opens every scene, clicks the tally, and prints a control-step rate for the pacman scenes.

GitHub Actions sets `MJSWAN_BASE_PATH=/physical-ai-sim-playground/` (see `.github/workflows/deploy.yml`). A local build must keep the default `/`, or `uv run serve` will not find the assets. The workflow uploads `dist/` with `actions/upload-pages-artifact` and publishes it with `actions/deploy-pages`. Do not enable GitHub Pages from the agent; that is a repository setting.

Upstream checkouts land in `~/.cache/mjswan_playground/` because the installed package has no `pyproject.toml` beside it. Do not commit `dist/`, `.venv/`, or that cache.

## Keep

- mjswan's swan icon (`logo.svg`) and the dialog it opens (`powered by mjswan`). Company pages are asked to leave both in place. Do not restyle or remove them.
- Per-scene `LICENSE` / `NOTICE` files the builders write. The repo `NOTICE` lists upstream licenses. Do not ship microduck (CC BY-NC-SA meshes) or the LAFAN1 dance clip (CC BY-NC-ND). `uv run verify` fails if a shipped `LICENSE*` / `NOTICE*` file or a recorded SPDX id is non-commercial, no-derivatives, GPL (unless another `OR` side is usable), CERN-OHL, or missing.

## Lessons

Floor friction, payload, a step, and a slope are separate scenes, not a live slider. An mjswan event can write `geom_friction`, but the event tracer does not serve UI commands, and MuJoCo uses the greater of the two geoms' friction, so the feet and the floor both have to change. Payload mass is added at the torso center of mass and the inertia about that point is left as it was. The contact-force arrows MuJoCo can draw are not in this mjswan viewer: the render loop is three.js and has no `mjvOption` contact flag. A tally (`立て直した` / `倒れた`) and `最初から` are injected into `index.html`; the count stays in the page.

## UI (Japanese)

After the merge, `localize.py` rewrites `dist/manifest.json`: Japanese project/scene/command labels, project order, the `Max ...` companion sliders removed, command panels with no slider removed (get-up scenes), and the K1 dance/fight scenes dropped (their clips name no source dataset). `overlay.py` then injects into `index.html`: `?debug=0` by default, a text-node renamer for labels the stock viewer draws itself (`Scene`, `Interact`, `Push`, `Reset`...), hidden rows (FOV, policy picker, All envs), the pointer starting in Push with the Interact folder open, the lesson bar, and a help card (`?help=0` skips it). The swan logo and its About dialog are untouched. If a new mjswan version renames its labels, `scripts/check_browser.py` fails on English labels still shown. The step-rate probe lives in `scripts/check_browser.py` (injected with `add_init_script`), not in the shipped page.

Curriculum text is still later. Do not add it here.

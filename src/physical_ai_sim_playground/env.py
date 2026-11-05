"""Live sliders for the floor friction, the payload, and gravity on the robot page.

mjswan loads an author plugin module named by the manifest's top-level ``plugins``
(document-root relative) and hands each plugin event the running ``mjModel`` on every
episode reset. The event below does nothing to the simulation itself: it publishes the
model on ``window.__paspModel`` and calls ``window.__paspApply`` (defined by the overlay,
``overlay.py``), which writes the slider values into the model. Writes to
``geom_friction``, ``body_mass`` and ``opt.gravity`` take effect on the next step.

``localize.py`` adds the event to every MDP, so it runs in every scene.
"""

from __future__ import annotations

from pathlib import Path

PLUGIN_FILE = "pasp-plugins.js"
EVENT_NAME = "pasp_expose"

_PLUGIN = """// physical-ai-sim-playground: hands the running model to the page (see env.py).
class PaspExpose {
  constructor(config) {
    this.config = config;
  }
  onReset(context) {
    window.__paspModel = {
      mujoco: context.mujoco || null,
      mjModel: context.mjModel || null,
      mjData: context.mjData || null,
    };
    if (typeof window.__paspApply === "function") {
      try {
        window.__paspApply();
      } catch (error) {
        console.warn("[pasp] could not apply the environment sliders:", error);
      }
    }
  }
}

export const events = { %s: PaspExpose };
""" % EVENT_NAME


def install(site: Path) -> None:
    """Write the plugin module at the document root of ``site``."""
    (site / PLUGIN_FILE).write_text(_PLUGIN)

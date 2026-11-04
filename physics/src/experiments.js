// 係数を変える4つの実験と、触って確かめる4つのシーン。
// scripts/check_physics.py が同じ場に同じ値を書いて結果を確かめる。値を変えたらそちらも直す。

const BALL_SPEED = 4;

// id は URL の ?scene= に使う。並びはパネルのシーン一覧の並び。
const SCENES = [
  { id: "ramp", file: "exp_ramp.xml", label: "斜面の箱" },
  { id: "bounce", file: "exp_bounce.xml", label: "落下と跳ね返り" },
  { id: "mass", file: "exp_mass.xml", label: "押した箱" },
  { id: "timestep", file: "exp_timestep.xml", label: "薄い壁と時間の刻み" },
  { id: "mug", file: "mug.xml", label: "マグカップ",
    text: "マグカップをドラッグして持ち上げ、離す。机の上で引きずって滑らせる。" },
  { id: "hand", file: "shadow_hand/scene_right.xml", label: "ロボットの手",
    text: "手をドラッグして動かす。「関節を動かす」を開くと、指の関節を1つずつ曲げられる。" },
  { id: "cloth", file: "hammock.xml", label: "布",
    text: "人形がハンモックに落ちる。赤い点が布の格子。人形や布をドラッグして、布のたわみ方を見る。" },
  { id: "humanoid", file: "humanoid.xml", label: "人型",
    text: "力を入れていない人型。ドラッグで引っ張ると、関節が曲がって崩れる。" },
];

// Files the scenes above read, fetched once into MuJoCo's virtual file system.
const HAND_MESHES = [
  "f_distal_pst", "f_knuckle", "f_middle", "f_proximal", "forearm_0", "forearm_1",
  "forearm_collision", "lf_metacarpal", "mounting_plate", "palm", "th_distal_pst",
  "th_middle", "th_proximal", "wrist",
];
export const SCENE_FILES = [
  "exp_ramp.xml", "exp_bounce.xml", "exp_mass.xml", "exp_timestep.xml",
  "mug.xml", "mug.obj", "mug.png", "hammock.xml", "humanoid.xml",
  "shadow_hand/right_hand.xml", "shadow_hand/scene_right.xml",
  ...HAND_MESHES.map((name) => `shadow_hand/assets/${name}.obj`),
];

export function sceneOptions() {
  const options = {};
  for (const scene of SCENES) options[scene.label] = scene.file;
  return options;
}

export function initialSceneFromURL() {
  const id = new URLSearchParams(window.location.search).get("scene");
  const found = SCENES.find((scene) => scene.id === id);
  return (found || SCENES[0]).file;
}

export function rememberScene(file) {
  const found = SCENES.find((scene) => scene.file === file);
  if (!found) return;
  try {
    const url = new URL(window.location.href);
    url.searchParams.set("scene", found.id);
    window.history.replaceState(null, "", url);
  } catch (e) {}
}

const EXPERIMENTS = {
  "exp_ramp.xml": {
    text: "20度の斜面に箱を置く。摩擦係数が約 0.36 より小さいと滑り落ち、大きいと止まる（境目は tan 20°）。",
    camera: { pos: [1.35, -1.75, 1.05], target: [0, 0, 0.32] },
    sliders: [{ key: "friction", label: "摩擦係数", min: 0.05, max: 1, step: 0.01, value: 0.5 }],
  },
  "exp_bounce.xml": {
    text: "同じ高さから球を落とす。跳ね返りを決める値（減衰比）が小さいほど高く跳ねる。",
    camera: { pos: [1.15, -1.45, 0.7], target: [0, 0, 0.35] },
    sliders: [{ key: "dampratio", label: "減衰比", min: 0.02, max: 1, step: 0.01, value: 0.2 }],
  },
  "exp_mass.xml": {
    text: "同じ力で箱を押し続ける。質量を変えて、1m の目印に着くまでの時間を比べる。",
    camera: { pos: [0.8, -2.6, 0.9], target: [0.8, 0, 0] },
    sliders: [{ key: "mass", label: "質量（kg）", min: 0.2, max: 5, step: 0.1, value: 1 }],
  },
  "exp_timestep.xml": {
    text: "球が薄い壁に向かって進む。刻みが 0.001 秒なら壁で跳ね返る。刻みを粗くすると、値によって壁をすり抜ける（0.04 秒ではすり抜ける）。",
    camera: { pos: [0, -2.6, 1.0], target: [0, 0, 0] },
    sliders: [{ key: "timestep", label: "時間の刻み（秒）", min: 0.001, max: 0.05, step: 0.001, value: 0.001 }],
  },
};

function nameAt(model, adr, index) {
  const names = model.names;
  let start = adr[index];
  let end = start;
  while (end < names.length && names[end] !== 0) end++;
  return new TextDecoder("utf-8").decode(names.subarray(start, end));
}

function bodyId(model, name) {
  for (let b = 0; b < model.nbody; b++) {
    if (nameAt(model, model.name_bodyadr, b) === name) return b;
  }
  return -1;
}

function geomsNamed(model, wanted) {
  const ids = [];
  for (let g = 0; g < model.ngeom; g++) {
    const name = nameAt(model, model.name_geomadr, g);
    if (wanted.includes(name)) ids.push(g);
  }
  return ids;
}

function setLesson(text) {
  const el = document.getElementById("lesson-text");
  if (el) el.textContent = text;
}

function setReadout(text) {
  const el = document.getElementById("readout");
  if (!el) return;
  if (el.textContent !== text) el.textContent = text;
  el.hidden = !text;
}

// camera の値は MuJoCo の座標（z が上）。描画側（three.js）は y が上なので (x, z, -y) に直す。
function look(demo, camera) {
  const [px, py, pz] = camera.pos;
  const [tx, ty, tz] = camera.target;
  demo.camera.position.set(px, pz, -py);
  demo.controls.target.set(tx, tz, -ty);
  demo.controls.update();
}

function clearFolder(folder) {
  while (folder.controllers.length) folder.controllers[0].destroy();
}

function applyRamp(demo) {
  const mu = demo.params.friction;
  for (const g of geomsNamed(demo.model, ["ramp", "box"])) {
    demo.model.geom_friction[g * 3] = mu;
  }
}

function applyBounce(demo) {
  const ratio = demo.params.dampratio;
  for (const g of geomsNamed(demo.model, ["floor", "ball"])) {
    demo.model.geom_solref[g * 2 + 1] = ratio;
  }
}

function applyMass(demo) {
  const box = bodyId(demo.model, "box");
  const base = demo.expBase;
  const scale = demo.params.mass / base.mass[box];
  demo.model.body_mass[box] = base.mass[box] * scale;
  for (let k = 0; k < 3; k++) {
    demo.model.body_inertia[box * 3 + k] = base.inertia[box * 3 + k] * scale;
  }
  demo.mujoco.mj_setConst(demo.model, demo.data);
}

function applyTimestep(demo) {
  demo.model.opt.timestep = demo.params.timestep;
}

function resetState(demo, scene) {
  demo.mujoco.mj_resetData(demo.model, demo.data);
  demo.reachedAt = null;
  if (scene === "exp_mass.xml") demo.data.ctrl[0] = 1;
  if (scene === "exp_timestep.xml") demo.data.qvel[0] = BALL_SPEED;
  demo.mujoco.mj_forward(demo.model, demo.data);
}

function measure(demo, scene) {
  if (scene === "exp_ramp.xml") {
    const box = bodyId(demo.model, "box");
    const z = demo.data.xpos[box * 3 + 2];
    return `摩擦係数 ${demo.params.friction.toFixed(2)}　箱の高さ ${z.toFixed(2)}`;
  }
  if (scene === "exp_bounce.xml") {
    const ball = bodyId(demo.model, "ball");
    const z = demo.data.xpos[ball * 3 + 2];
    return `減衰比 ${demo.params.dampratio.toFixed(2)}　球の高さ ${z.toFixed(2)}`;
  }
  if (scene === "exp_mass.xml") {
    const box = bodyId(demo.model, "box");
    const x = demo.data.xpos[box * 3];
    if (x >= 1.0 && demo.reachedAt === null) demo.reachedAt = demo.data.time;
    const arrival = demo.reachedAt === null ? "まだ着いていない" : `${demo.reachedAt.toFixed(2)} 秒で着いた`;
    return `質量 ${demo.params.mass.toFixed(1)} kg　1m の目印に${arrival}`;
  }
  if (scene === "exp_timestep.xml") {
    const ball = bodyId(demo.model, "ball");
    const x = demo.data.xpos[ball * 3];
    const side = x > 0.06 ? "壁の向こう側（すり抜けた）" : "壁の手前";
    return `時間の刻み ${demo.params.timestep.toFixed(3)} 秒　球は${side}`;
  }
  return "";
}

export function setupExperiments(demo) {
  if (!demo.expFolder) {
    demo.expFolder = demo.gui.addFolder("実験");
  }
  const folder = demo.expFolder;

  const rebuild = () => {
    const scene = demo.params.scene;
    const exp = EXPERIMENTS[scene];
    clearFolder(folder);
    demo.expBase = {
      mass: Array.from(demo.model.body_mass),
      inertia: Array.from(demo.model.body_inertia),
    };
    if (!exp) {
      demo.reapplyExperiment = null;
      demo.updateReadout = null;
      const info = SCENES.find((s) => s.file === scene);
      setLesson(info && info.text ? info.text : "ドラッグで物体を引っ張る。");
      setReadout("");
      folder.hide();
      return;
    }
    folder.show();
    setLesson(exp.text);
    look(demo, exp.camera);
    for (const slider of exp.sliders) {
      demo.params[slider.key] = slider.value;
      folder.add(demo.params, slider.key, slider.min, slider.max, slider.step)
        .name(slider.label)
        .onChange(() => demo.reapplyExperiment && demo.reapplyExperiment());
    }
    const applyModel = () => {
      if (scene === "exp_ramp.xml") applyRamp(demo);
      if (scene === "exp_bounce.xml") applyBounce(demo);
      if (scene === "exp_mass.xml") applyMass(demo);
      if (scene === "exp_timestep.xml") applyTimestep(demo);
      resetState(demo, scene);
    };
    demo.reapplyExperiment = applyModel;
    demo.updateReadout = () => setReadout(measure(demo, scene));
    applyModel();
    demo.updateReadout();
  };

  demo.updateGUICallbacks.push(() => rebuild());
  rebuild();
}

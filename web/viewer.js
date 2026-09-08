// The 3D diff viewer.
//
// Loads out/manifest.json, then loads the .glb for the selected iteration and
// the one before it. The current design draws solid; the previous draws as a
// translucent ghost. Any mesh whose `rocinante_part` matches a name in
// `changed_parts` draws in the accent colour.
//
// STATUS: scene, loading, ghosting and selection work. The trajectory
// animation is the stub at the bottom.

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const ACCENT = 0xff5a3c;
const GHOST = 0x5b6472;
const SOLID = 0xc8ced9;

const el = (id) => document.getElementById(id);
const loader = new GLTFLoader();

let manifest = { iterations: [] };
let selected = 0;
const cache = new Map();

// --- scene ---------------------------------------------------------------

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(38, 1, 0.01, 100);
camera.position.set(0.55, 0.25, 0.55);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
el("canvas").appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotate = true;
controls.autoRotateSpeed = 0.7;

scene.add(new THREE.HemisphereLight(0xffffff, 0x202430, 2.2));
const key = new THREE.DirectionalLight(0xffffff, 2);
key.position.set(2, 3, 2);
scene.add(key);

const grid = new THREE.GridHelper(2, 20, 0x262b33, 0x1a1e24);
scene.add(grid);

const currentGroup = new THREE.Group();
const ghostGroup = new THREE.Group();
scene.add(currentGroup, ghostGroup);

// glTF from Blender arrives Y-up, so the rocket's long axis is Y here.
let framed = false;
function frame(object) {
  const box = new THREE.Box3().setFromObject(object);
  if (box.isEmpty()) return;
  const sphere = box.getBoundingSphere(new THREE.Sphere());

  grid.position.y = box.min.y - sphere.radius * 0.08;
  grid.scale.setScalar(Math.max(sphere.radius * 1.5, 0.1));

  // Fit the bounding sphere to the tighter field of view. A rocket is long
  // and thin, so on a wide frame that is always the vertical one.
  const fovY = THREE.MathUtils.degToRad(camera.fov);
  const fovX = 2 * Math.atan(Math.tan(fovY / 2) * camera.aspect);
  const distance = (sphere.radius / Math.sin(Math.min(fovX, fovY) / 2)) * 1.15;

  const direction = new THREE.Vector3(0.62, 0.28, 0.73).normalize();
  camera.position.copy(sphere.center).addScaledVector(direction, distance);
  camera.near = distance / 100;
  camera.far = distance * 10;
  camera.updateProjectionMatrix();
  controls.target.copy(sphere.center);
  controls.update();
}

function resize() {
  const { clientWidth: w, clientHeight: h } = el("canvas");
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
  if (framed && currentGroup.children.length) frame(currentGroup);
}
addEventListener("resize", resize);

function tick() {
  requestAnimationFrame(tick);
  controls.update();
  renderer.render(scene, camera);
}

// --- loading -------------------------------------------------------------

async function loadGlb(name) {
  if (!name) return null;
  if (!cache.has(name)) {
    cache.set(name, new Promise((res, rej) => loader.load(name, (g) => res(g.scene), undefined, rej)));
  }
  return (await cache.get(name)).clone(true);
}

function partOf(obj) {
  // Blender custom properties arrive under userData when export_extras is on.
  return obj.userData?.rocinante_part ?? obj.name?.replace(/\.\d+$/, "");
}

function matches(part, patterns) {
  return patterns.some((p) =>
    p.endsWith("*") ? (part ?? "").startsWith(p.slice(0, -1)) : part === p,
  );
}

function paint(root, { ghost, changed }) {
  root.traverse((obj) => {
    if (!obj.isMesh) return;
    const isChanged = el("highlight").checked && matches(partOf(obj), changed);
    obj.material = new THREE.MeshStandardMaterial({
      color: ghost ? GHOST : isChanged ? ACCENT : SOLID,
      roughness: ghost ? 0.9 : 0.45,
      metalness: ghost ? 0 : 0.15,
      transparent: ghost,
      opacity: ghost ? 0.22 : 1,
      depthWrite: !ghost,
      emissive: isChanged ? ACCENT : 0x000000,
      emissiveIntensity: isChanged ? 0.25 : 0,
    });
  });
}

// Loads are async, so a fast click sequence can land out of order. Only the
// most recent request is allowed to touch the scene.
let request = 0;

async function show(index) {
  const it = manifest.iterations[index];
  if (!it) return;
  const token = ++request;
  selected = index;
  const prev = manifest.iterations[index - 1];

  renderDetail(it, prev);
  renderTimeline();

  const [model, old] = await Promise.all([
    loadGlb(it.glb),
    prev && el("ghost").checked ? loadGlb(prev.glb) : null,
  ]);
  if (token !== request) return; // a newer selection won

  currentGroup.clear();
  ghostGroup.clear();
  if (model) {
    paint(model, { ghost: false, changed: it.changed_parts ?? [] });
    currentGroup.add(model);
  }
  if (old) {
    paint(old, { ghost: true, changed: [] });
    ghostGroup.add(old);
  }

  if (!framed && model) {
    frame(currentGroup);
    framed = true;
  }
}

// --- panels --------------------------------------------------------------

function delta(before, after, digits = 0, higherIsBetter = true) {
  if (before == null || after == null) return `${(after ?? 0).toFixed(digits)}`;
  const d = after - before;
  if (Math.abs(d) < 10 ** -digits / 2) return after.toFixed(digits);
  const cls = (d > 0) === higherIsBetter ? "up" : "down";
  return `${after.toFixed(digits)} <span class="${cls}">${d > 0 ? "+" : ""}${d.toFixed(digits)}</span>`;
}

function renderDetail(it, prev) {
  el("version").textContent = `${it.name} · v${it.index}`;
  el("rationale").textContent = it.rationale || "";

  const r = it.result;
  const p = prev?.result;
  el("metrics").innerHTML = !r
    ? `<dt>Simulation</dt><dd>${it.error ?? "failed"}</dd>`
    : `
      <dt>Apogee</dt><dd>${delta(p?.apogee_m, r.apogee_m, 0)} m</dd>
      <dt>Stability</dt><dd>${delta(p?.stability_margin_cal, r.stability_margin_cal, 2)} cal</dd>
      <dt>Rail exit</dt><dd>${delta(p?.rail_exit_velocity_ms, r.rail_exit_velocity_ms, 1)} m/s</dd>
      <dt>Max velocity</dt><dd>${delta(p?.max_velocity_ms, r.max_velocity_ms, 0)} m/s</dd>
      <dt>Liftoff mass</dt><dd>${delta(p?.liftoff_mass_kg, r.liftoff_mass_kg, 3, false)} kg</dd>`;

  el("changes").innerHTML = (it.changes ?? []).map((c) => `<li>${c}</li>`).join("") || "<li>—</li>";

  const link = el("review");
  link.hidden = !it.review_session_id;
  if (it.review_session_id) link.href = `/rs/${it.review_session_id}`;
}

function renderTimeline() {
  el("timeline").innerHTML = "";
  manifest.iterations.forEach((it, i) => {
    const b = document.createElement("button");
    b.className = "tick" + (it.result ? "" : " fail");
    b.setAttribute("aria-current", String(i === selected));
    b.innerHTML = `v${it.index}<b>${
      it.result ? `${it.result.apogee_m.toFixed(0)} m · ${it.result.stability_margin_cal.toFixed(2)} cal` : "failed"
    }</b>`;
    b.onclick = () => show(i);
    el("timeline").appendChild(b);
  });
}

// --- trajectory ----------------------------------------------------------
// TODO: draw result.trajectory as a THREE.Line and fly the rocket along it on
// a scrub bar. This is the "wow" shot -- but it is also the first thing to cut
// if the clock runs out.

// --- boot ----------------------------------------------------------------

for (const id of ["ghost", "highlight"]) el(id).onchange = () => show(selected);
el("wipe").oninput = (e) => {
  ghostGroup.visible = Number(e.target.value) < 100;
};

// Handy from the browser console while building: rocinante.frame(rocinante.currentGroup)
window.rocinante = { scene, camera, controls, currentGroup, ghostGroup, frame, show };

fetch("manifest.json")
  .then((r) => r.json())
  .then((m) => {
    manifest = m;
    el("goal").textContent = m.goal ?? "";
    resize();
    tick();
    show(Math.max(0, m.iterations.length - 1));
  })
  .catch(() => {
    el("goal").textContent = "No manifest.json. Run `rocinante design` first.";
    resize();
    tick();
  });

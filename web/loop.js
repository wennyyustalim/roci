const el=id=>document.getElementById(id);
let state, scene, busy=false, pollTimer=null;
const fmt=(n,d=1)=>n.toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
async function api(path,payload) {
  const response=await fetch(`/api/${path}`,payload ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)} : {});
  const data=await response.json(); if(!response.ok) throw new Error(data.error || "Request failed"); return data;
}
function list(id,values) { el(id).replaceChildren(...values.map(value=> {const li=document.createElement("li");li.textContent=value;return li;})); }
function metric(id,label,value,unit,old,digits=1) {
  const dt=document.createElement("dt"), dd=document.createElement("dd"); dt.textContent=label; dd.textContent=`${fmt(value,digits)} ${unit}`.trim();
  if(old != null && Math.abs(value-old)>10**(-digits)/2) {const change=document.createElement("small");change.textContent=`${value>old ? "+" : ""}${fmt(value-old,digits)}`;dd.append(change);}
  el(id).append(dt,dd);
}
function text(id,label,value) { const dt=document.createElement("dt"), dd=document.createElement("dd"); dt.textContent=label; dd.textContent=value; el(id).append(dt,dd); }
function step(name,stateName,message) { const li=document.querySelector(`#progress li[data-step=${name}]`); li.dataset.state=stateName; li.querySelector("em").textContent=message; }

const current=()=>state.iterations[state.accepted];
const inFlight=it=>["exporting","sharing"].includes(it.handoff?.status) || (state.auto_share && it.handoff?.status==="exported");

async function renderScene() {
  if(!scene || !state) return;
  const it=current(), prev=state.iterations[it.parent];
  const source=await scene.update(it,prev,{ghost:el("ghost").checked,highlight:el("highlight").checked});
  if(source==="demo") el("geometry-source").textContent="Detailed ship model"; else if(source==="export") el("geometry-source").textContent="Blender export"; else if(source==="schematic") el("geometry-source").textContent="Schematic · no export yet";
}

function renderProgress(it,prev) {
  if(busy) { step("astra","busy",state.mode==="live" ? `${state.model} is designing` : "fixture"); for(const s of ["physics","blender","openrocket","kord"]) step(s,"","waiting"); el("kord-link").hidden=true; return; }
  if(!prev) { step("astra","","baseline, no ask yet"); step("physics","done","computed from the baseline spec"); step("blender","done",state.blender ? "showing the baseline ship" : "off"); step("openrocket","done",state.openrocket ? "showing the baseline torpedo" : "off"); step("kord","","first ask shares a comparison"); el("kord-link").hidden=true; return; }
  step("astra","done",it.model ? `${it.model} returned a full spec` : "fixture preset");
  const moved=Object.keys(it.derived).filter(k=>Math.abs(it.derived[k]-prev.derived[k])>1e-6).length;
  step("physics","done",moved ? `${moved} derived figure${moved===1 ? "" : "s"} moved` : "no performance change");
  const parts=it.geometry_changed_parts ?? [];
  step("blender","done",!state.blender ? "off" : parts.length ? `hull rebuilt · ${parts.join(", ")}` : "ship unchanged");
  step("openrocket",it.torpedo?.changed ? "done" : "",!state.openrocket ? "off" : it.torpedo?.changed ? `reopened with torpedo v${it.index}` : "torpedo unchanged");
  const h=it.handoff ?? {}, kord={exporting:["busy","exporting geometry"],exported:[state.auto_share ? "busy" : "done",state.auto_share ? "uploading" : "exported, not shared"],sharing:["busy",`uploading the ${h.compared ?? "ship"} pair`],shared:["done",`${h.compared ?? "ship"} comparison ready`],share_failed:["error","upload failed"],export_failed:["error","export failed"]}[h.status] ?? ["","no export"];
  step("kord",...kord); el("kord-link").hidden=!h.share_url; if(h.share_url) el("kord-link").href=h.share_url;
}

function render() {
  const it=current(), prev=state.iterations[it.parent];
  el("mode").textContent=state.mode==="fixture" ? "Fixture mode · no model call" : `Live · ${state.model}`;
  el("preset").hidden=state.mode!=="fixture"; el("ask").hidden=state.mode!=="live"; el("samples").hidden=state.mode!=="live";
  el("propose").textContent=state.mode==="live" ? "Ask Astra →" : "Run fixture →";
  el("propose").disabled=busy;
  el("title").textContent=`${it.name} · v${it.index}`;
  el("comparison").textContent=prev ? `${it.ask}` : "Salvaged Martian gunship · home to the crew";
  el("rationale").textContent=prev ? it.rationale : "";
  renderProgress(it,prev);
  el("metrics").replaceChildren();
  const w=it.spec.weapons, pw=prev?.spec.weapons;
  metric("metrics","Launch tubes",w.torpedo_tubes,"",pw?.torpedo_tubes,0);
  metric("metrics","Tube station",(w.tube_station ?? .7)*100,"% from stern",pw ? (pw.tube_station ?? .7)*100 : null,0);
  metric("metrics","Magazine",w.magazine_m3,"m³",pw?.magazine_m3);
  for(const [key,label,unit,digits] of [["torpedo_capacity","Torpedoes carried","",0],["dry_mass_t","Dry mass","t",1],["delta_v_km_s","Delta-v","km/s",1],["max_accel_g","Drive limit","g",2],["sustained_burn_hours","Cruise endurance","h",2]])
    metric("metrics",label,it.derived[key],unit,prev?.derived[key],digits);
  el("torpedo").replaceChildren();
  const t=it.torpedo, pt=prev?.torpedo;
  if(t) {
    metric("torpedo","Length",t.length_m*100,"cm",pt ? pt.length_m*100 : null);
    metric("torpedo","Diameter",t.diameter_m*1000,"mm",pt ? pt.diameter_m*1000 : null,0);
    metric("torpedo","Fins",t.fins,"",pt?.fins,0);
    metric("torpedo","Fin span",t.fin_span_m*1000,"mm",pt ? pt.fin_span_m*1000 : null,0);
    text("torpedo","Motor",t.motor);
  }
  list("changes",it.changes?.length ? it.changes : [prev ? "No spec changes" : "Baseline as salvaged"]);
  renderScene();
  clearTimeout(pollTimer);
  if(!busy && inFlight(it)) pollTimer=setTimeout(async()=>{ try { state=await api("state"); render(); } catch(error) { el("status").textContent=error.message; } },1500);
}

async function propose() {
  if(busy) return;
  busy=true; render();
  el("status").textContent=state.mode==="live" ? "Astra is designing the refit. Every number you see next is computed from the spec it returns." : "Applying the fixture preset…";
  try {
    state=await api("propose",{preset:el("preset").value,ask:el("ask").value});
    const it=current();
    el("status").textContent=`v${it.index} is the ship now. Blender ${it.geometry_changed_parts?.length ? "rebuilt the hull" : "kept the hull"}; ${it.torpedo?.changed ? "OpenRocket has the new torpedo" : "the torpedo is unchanged"}.`;
  } catch(error) { el("status").textContent=error.message; }
  finally { busy=false; render(); }
}

el("proposal").onsubmit=e=>{e.preventDefault();propose();};
for(const id of ["ghost","highlight"]) el(id).onchange=renderScene;
const deckDescriptions={
  Cockpit:"Alex’s flight station. A restrained crash couch, wraparound consoles and a direct connection to the ship below.",
  Ops:"Holden’s command deck. A central tactical table, status screens and access down the ship’s vertical spine.",
  Crew:"Off-watch. Stacked bunks, personal storage and the quietest corner of a very loud ship.",
  Galley:"The heart of the Roci. A shared table, coffee station and a little green life in the bulkhead.",
  "Machine shop":"Amos’s territory. A working bench, tool racks and service crates, ready for the next repair.",
  Engineering:"Naomi’s station. The reactor vessel, coolant manifolds and diagnostic consoles above the Epstein drive.",
};
let expanded=false;
el("canvas").addEventListener("assemblychange",event=>{
  const detail=event.detail; expanded=detail.expanded;
  if(!detail.suspended) for(const button of document.querySelectorAll("[data-view]")) button.setAttribute("aria-pressed",String(button.dataset.view==="ship"));
  el("disassemble").disabled=!detail.decks.length;
  el("disassemble").setAttribute("aria-pressed",String(expanded));
  el("disassemble").innerHTML=`<span class="explode-icon" aria-hidden="true">${expanded ? "▰" : "▱"}</span> ${expanded ? "Assemble Roci" : "Disassemble Roci"}`;
  el("assembly-status").textContent=detail.moving ? (expanded ? "Separating hull, decks and drive…" : "Bringing the Roci back together…") : detail.focus!==null ? "Inside the Roci · drag to orbit" : expanded ? "Exploded view · choose a deck to step inside" : "Six decks. Four crew. One home.";
  el("deck-nav").hidden=!detail.decks.length;
  el("deck-nav").replaceChildren(...detail.decks.map(d=>{
    const button=document.createElement("button");button.type="button";button.setAttribute("aria-pressed",String(detail.focus===d.index));
    const number=document.createElement("span");number.textContent=String(d.index+1).padStart(2,"0");
    button.append(number,document.createTextNode(d.name));button.onclick=()=>scene?.focusDeck(d.index);return button;
  }));
  const selected=detail.decks.find(d=>d.index===detail.focus);
  el("deck-detail").hidden=!selected;
  if(selected) {
    el("deck-number").textContent=`DECK ${String(selected.index+1).padStart(2,"0")}`;
    el("deck-title").textContent=selected.name;
    el("deck-description").textContent=deckDescriptions[selected.name] || "A furnished compartment along the ship’s thrust axis.";
    el("deck-crew").textContent=selected.crew.length ? `ON STATION / ${selected.crew.join(" · ")}` : "HABITABLE DECK";
  }
});
el("disassemble").onclick=()=>scene?.setExpanded(!expanded);
el("all-decks").onclick=()=>scene?.fit();
el("presentation").onclick=()=>{
  const on=document.body.classList.toggle("presentation");
  el("presentation").setAttribute("aria-pressed",String(on));
  el("presentation").textContent=on ? "Show workshop" : "Presentation mode";
  requestAnimationFrame(()=>scene?.fit());
};
el("rotate").onchange=()=>scene?.setRotate(el("rotate").checked);
function selectView(name) {
  scene?.focus(name);
  for(const button of document.querySelectorAll("[data-view]")) button.setAttribute("aria-pressed",String(button.dataset.view===name));
}
for(const button of document.querySelectorAll("[data-view]")) button.onclick=()=>selectView(button.dataset.view);
el("fit").onclick=()=>selectView("ship");
try {
  state=await api("state");
  for(const [value,label] of Object.entries(state.presets)) {const option=document.createElement("option");option.value=value;option.textContent=label;el("preset").append(option);}
  el("samples").replaceChildren(...(state.sample_asks ?? []).map(ask=> {const b=document.createElement("button");b.type="button";b.textContent=ask;b.onclick=()=>{el("ask").value=ask;el("ask").focus();};return b;}));
  if(!el("ask").value && state.sample_asks?.length) el("ask").value=state.sample_asks[0];
  el("status").textContent="Explore the ship, then design a torpedo. Blender, OpenRocket and Kord follow your changes.";
  render();
} catch(error) {el("status").textContent=`Unable to load the ship: ${error.message}`;el("propose").disabled=true;}
try {const {createScene}=await import("./primitives.js");scene=createScene(el("canvas"));renderScene();}
catch(error) {el("scene-error").hidden=false;el("scene-error").textContent="3D view unavailable. Check WebGL and access to cdn.jsdelivr.net. The panel still works.";console.error(error);}

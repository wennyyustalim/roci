const el=id=>document.getElementById(id);
const setOptionalText=(id,value)=>{const node=el(id);if(node) node.textContent=value;};
let launching=false, launchRequest=0, desktopClock=null, launchPresentation=null;
let state, scene, busy=false, pollTimer=null, selectedTorpedo=null, selectionVersion=0, selectionSync=Promise.resolve(), syncTimer=null;
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
  if(!scene || !state || launching) return;
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
  step("openrocket",it.torpedo?.changed ? "done" : "",!state.openrocket ? "off" : it.torpedo?.changed ? `updated torpedo v${it.index} in place` : "torpedo unchanged");
  const h=it.handoff ?? {}, kord={exporting:["busy","exporting geometry"],exported:[state.auto_share ? "busy" : "done",state.auto_share ? "uploading" : "exported, not shared"],sharing:["busy",`uploading the ${h.compared ?? "ship"} pair`],shared:["done",`${h.compared ?? "ship"} comparison ready`],share_failed:["error","upload failed"],export_failed:["error","export failed"]}[h.status] ?? ["","no export"];
  step("kord",...kord); el("kord-link").hidden=!h.share_url; if(h.share_url) el("kord-link").href=h.share_url;
}

function render() {
  const it=current(), prev=state.iterations[it.parent];
  renderScope();
  syncStatus(state);
  el("preset").hidden=state.mode!=="fixture"; el("ask").hidden=state.mode!=="live"; el("samples").hidden=state.mode!=="live";
  el("propose").textContent=state.mode==="live" ? "Ask gpt-6-astra" : "Run fixture →";
  el("propose").disabled=busy || launching;
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
  const t=state.workshop_torpedo || it.torpedo, pt=selectedTorpedo ? null : prev?.torpedo;
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
  if(busy || launching) return;
  const request={preset:el("preset").value,ask:el("ask").value,torpedo_id:selectedTorpedo};
  const pendingSelection=selectionSync;
  busy=true; render();
  el("status").textContent=state.mode==="live" ? "Astra is designing the refit. Every number you see next is computed from the spec it returns." : "Applying the fixture preset…";
  try {
    await pendingSelection;
    state=await api("propose",request);
    const it=current();
    el("status").textContent=`v${it.index} is the ship now. Blender ${it.geometry_changed_parts?.length ? "rebuilt the hull" : "kept the hull"}; ${it.torpedo?.changed ? "OpenRocket has the new torpedo" : "the torpedo is unchanged"}.`;
  } catch(error) { el("status").textContent=error.message; }
  finally { busy=false; render(); }
}

function renderScope() {
  for(const launch of document.querySelectorAll(".torpedo-launch")) {
    launch.disabled=busy || launching || !scene;
    launch.textContent=launching ? "Launch in progress…" : "Launch";
  }
  const workshop=selectedTorpedo ? `${selectedTorpedo.replace("torpedo_","Torpedo ")} workshop` : "General workshop";
  el("workshop-title").textContent=state.mode==="fixture" ? `${workshop} · Fixture` : workshop;
  setOptionalText("workshop-scope",selectedTorpedo ? "Refits apply only to this loaded torpedo." : "No torpedo selected · general refit");
  if(el("clear-selection")) el("clear-selection").hidden=!selectedTorpedo;
  el("ask").placeholder=selectedTorpedo ? "How should Astra refit this torpedo?" : "What should Astra change on the Roci?";
  const oldPreset=el("preset").value;
  el("preset").replaceChildren(...Object.entries(state.presets).map(([value,label])=>{const option=document.createElement("option");option.value=value;option.textContent=label;return option;}));
  if([...el("preset").options].some(o=>o.value===oldPreset)) el("preset").value=oldPreset;
  el("samples").replaceChildren(...(state.sample_asks ?? []).map(ask=>{const b=document.createElement("button");b.type="button";b.textContent=ask;b.onclick=()=>{el("ask").value=ask;el("ask").focus();};return b;}));
}
function syncStatus(snapshot) {
  const container=el("selection-sync"); if(!container) return;
  const entries=Object.entries(snapshot.integrations || {}).map(([app,result])=>({
    name:({blender:"Blender",openrocket:"OpenRocket"})[app] || app,
    status:result.status,
    label:result.status==="synced" ? "in sync" : result.status==="error" ? "sync failed" : result.status==="pending" ? "focusing…" : "off",
    detail:result.message || "Selection sync",
  }));
  const it=snapshot.iterations[snapshot.accepted], h=it.handoff || {};
  const kord={
    exporting:["pending","exporting…"],
    exported:[snapshot.auto_share ? "pending" : "idle",snapshot.auto_share ? "uploading…" : "not shared"],
    sharing:["pending","uploading…"],
    shared:[h.share_url ? "synced" : "idle",h.share_url ? "in sync" : "not shared"],
    share_failed:["error","upload failed"],
    export_failed:["error","export failed"],
  }[h.status] || ["idle",it.parent == null ? "awaiting refit" : "not shared"];
  entries.push({name:"Kord",status:kord[0],label:kord[1],
    detail:h.error || (kord[0]==="synced" ? `Comparison for v${it.index} shared with Kord. Selection focus is not linked.` : "Kord receives a before/after comparison when a refit is shared.")});
  const nodes=entries.map(({name,status,label,detail})=>{
    const item=document.createElement("span");
    item.className="sync-indicator"; item.dataset.status=status; item.title=detail;
    item.setAttribute("aria-label",`${name}: ${label}`);
    const dot=document.createElement("span"); dot.className="sync-dot"; dot.setAttribute("aria-hidden","true");
    item.append(dot,document.createTextNode(status==="synced" ? name : `${name}: ${label}`));
    return item;
  });
  // Avoid repeating live-region announcements when polling returns the same state.
  if(container.innerHTML!==nodes.map(node=>node.outerHTML).join("")) container.replaceChildren(...nodes);
}
function selectModel(selection) {
  const id=selection.kind==="torpedo" ? selection.id : null;
  if(launching) return;
  setPresentation(Boolean(id));
  selectedTorpedo=id; const version=++selectionVersion;
  renderScope(); el("propose").disabled=true; setOptionalText("selection-sync","Syncing selection…");
  selectionSync=selectionSync.catch(()=>{}).then(async()=>{
    const next=await api("select",{selection});
    if(version!==selectionVersion) return;
    state=next; render(); syncStatus(next);
    clearTimeout(syncTimer);
    let attempts=0;
    const poll=async()=>{
      if(version!==selectionVersion) return;
      const status=await api("state"); if(version!==selectionVersion) return;
      syncStatus(status);
      if(Object.values(status.integrations || {}).some(s=>s.status==="pending") && ++attempts<30) syncTimer=setTimeout(()=>poll().catch(error=>{setOptionalText("selection-sync",error.message);}),500);
    };
    syncTimer=setTimeout(()=>poll().catch(error=>{setOptionalText("selection-sync",error.message);}),500);
  }).catch(error=>{if(version===selectionVersion) {setOptionalText("selection-sync",`Selection could not sync: ${error.message}`);el("propose").disabled=true;} throw error;});
  // Keep a rejected selection pending for submission, without an unhandled rejection.
  selectionSync.catch(()=>{});
}
function launchBusy(on) {
  launching=on;
  for(const id of ["ghost","highlight","rotate","presentation","clear-selection"]) el(id).disabled=on;
  el("propose").disabled=on || busy;
  renderScope();
}
function setPresentation(on) {
  document.body.classList.toggle("presentation",on);
  el("presentation").setAttribute("aria-pressed",String(on));
  const label=on ? "Expand sidebar" : "Collapse sidebar";
  el("presentation").setAttribute("aria-label",label);
  el("presentation").title=label;
  el("sidebar-toggle-icon").textContent=on ? "›" : "‹";
  requestAnimationFrame(()=>scene?.fit());
}
function desktopSample(phase,time,force=false) {
  const clock=desktopClock;if(!clock) return;
  clock.time=time;
  const now=performance.now();
  if(!force && (clock.busy || now-clock.sent<120)) return;
  clock.sent=now;clock.busy=true;
  api("launch/playback",{launch_id:clock.id,sequence:++clock.sequence,time,phase})
    .then(status=>{if(desktopClock===clock && status.status==="error") el("launch-desktop").textContent=`OpenRocket plot: ${status.message}`;})
    .catch(()=>{if(desktopClock===clock) el("launch-desktop").textContent="OpenRocket plot clock disconnected";})
    .finally(()=>{clock.busy=false;});
}
function cancelLaunch() {
  desktopSample("cancelled",desktopClock?.time || 0,true);desktopClock=null;
  ++launchRequest; scene?.cancelLaunch(); launchBusy(false);el("launch-hud").hidden=true;
  if(launchPresentation!==null) setPresentation(launchPresentation);
  launchPresentation=null;
}
async function launchTorpedo(target=selectedTorpedo) {
  if(launching || busy || !selectedTorpedo || !scene) return;
  if(target!==selectedTorpedo) return;
  scene.cancelLaunch();desktopClock=null;
  const request=++launchRequest, index=current().index;
  launchPresentation=document.body.classList.contains("presentation");
  setPresentation(true);
  launchBusy(true);el("launch-hud").hidden=false;
  el("launch-desktop").textContent="";
  el("launch-phase").textContent="Running OpenRocket…";
  el("launch-caption").textContent="Computing this torpedo’s atmospheric flight";
  el("launch-telemetry").hidden=true;el("flight-details").hidden=true;
  el("cancel-launch").textContent="Cancel launch";
  try {
    await selectionSync;
    const data=await api("launch",{torpedo_id:target,index});
    if(request!==launchRequest) return;
    el("flight-details").hidden=false;
    const sim=data.simulation;
    el("flight-results").textContent=`OpenRocket 23.09 · ${data.spec.motor.designation} · Apogee ${fmt(sim.apogee_m)} m · Max speed ${fmt(sim.max_velocity_ms)} m/s · Initial stability ${fmt(sim.stability_margin_cal,2)} cal`;
    el("flight-warnings").textContent=sim.warnings.length ? `OpenRocket warnings: ${sim.warnings.join(" · ")}` : "No OpenRocket warnings.";
    if(data.openrocket_plot?.status==="pending") {
      const clock={id:data.launch_id,sequence:0,time:0,sent:0,busy:false};desktopClock=clock;
      el("launch-desktop").textContent="Opening flight plot in OpenRocket…";
      for(let attempt=0;attempt<40;attempt++) {
        if(request!==launchRequest) return;
        const status=await api("launch/playback",{launch_id:clock.id,sequence:++clock.sequence,time:0,phase:"ready"});
        if(request!==launchRequest) return;
        if(status.status!=="pending") {
          el("launch-desktop").textContent=status.status==="synced" ? "OpenRocket plot connected · live time cursor" : `OpenRocket plot: ${status.message}`;
          break;
        }
        if(attempt===39) el("launch-desktop").textContent="OpenRocket plot is still opening";
        await new Promise(resolve=>setTimeout(resolve,200));
      }
    } else if(data.openrocket_plot?.status==="error") el("launch-desktop").textContent=`OpenRocket plot: ${data.openrocket_plot.message}`;
    if(request!==launchRequest) return;
    scene.launch(data);
  } catch(error) {
    if(request!==launchRequest) return;
    launchBusy(false);el("launch-phase").textContent="Launch unavailable";
    el("launch-caption").textContent=error.message;el("cancel-launch").textContent="Close";
  }
}
el("canvas").addEventListener("launchrequest",event=>launchTorpedo(event.detail.id));
el("cancel-launch").onclick=()=>{cancelLaunch();if(selectedTorpedo) scene?.selectTorpedo(selectedTorpedo,false);};
addEventListener("keydown",event=>{if(event.key==="Escape" && launching) {cancelLaunch();scene?.reset();}});
el("canvas").addEventListener("launchchange",({detail:d})=>{
  if(d.phase==="idle") {launchBusy(false);el("launch-hud").hidden=true;return;}
  const phases={pullback:"Pulling back to the Roci",assembling:"Assembling the ship",tracking:"Acquiring moving target",flight:"Torpedo away",impact:"Target destroyed",complete:"Training run complete"};
  if(phases[d.phase]) el("launch-phase").textContent=phases[d.phase];
  if(d.phase==="pullback") el("launch-caption").textContent="OpenRocket atmospheric ascent · fictional target in space";
  if(d.phase==="flight") {
    el("launch-telemetry").hidden=false;
    el("launch-caption").textContent=`OpenRocket ascent · ${fmt(d.rate,2)}× playback · fictional target`;
  }
  if(d.phase==="telemetry") {
    desktopSample("flight",d.time);
    el("launch-time").textContent=`T+ ${fmt(d.time,2)} s`;
    el("launch-speed").textContent=`${fmt(d.speed)} m/s · ${d.thrust>.05 ? "BURN" : "COAST"}`;
    el("launch-range").textContent=`${fmt(d.range)} m to target`;
  }
  if(d.phase==="impact") {el("launch-range").textContent="CONTACT";desktopSample("impact",desktopClock?.time || 0,true);}
  if(d.phase==="complete") {desktopSample("complete",desktopClock?.time || 0,true);launchBusy(false);el("cancel-launch").textContent="Back to workshop";}
});

el("canvas").addEventListener("modelselect",event=>selectModel(event.detail));
el("clear-selection")?.addEventListener("click",()=>scene?.reset());

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
el("canvas").addEventListener("assemblychange",event=>{
  const detail=event.detail;
  const selected=detail.decks.find(d=>d.index===detail.focus);
  el("deck-detail").hidden=!selected;
  if(selected) {
    el("deck-number").textContent=`DECK ${String(selected.index+1).padStart(2,"0")}`;
    el("deck-title").textContent=selected.name;
    el("deck-description").textContent=deckDescriptions[selected.name] || "A furnished compartment along the ship’s thrust axis.";
    el("deck-crew").textContent=selected.crew.length ? `ON STATION / ${selected.crew.join(" · ")}` : "HABITABLE DECK";
  }
});
el("all-decks").onclick=()=>scene?.fit();
el("presentation").onclick=()=>{
  setPresentation(!document.body.classList.contains("presentation"));
};
el("rotate").onchange=()=>scene?.setRotate(el("rotate").checked);
el("fit").onclick=()=>{cancelLaunch();scene?.reset();};
try {
  state=await api("state"); selectedTorpedo=state.selected_torpedo || null;
  for(const [value,label] of Object.entries(state.presets)) {const option=document.createElement("option");option.value=value;option.textContent=label;el("preset").append(option);}
  el("samples").replaceChildren(...(state.sample_asks ?? []).map(ask=> {const b=document.createElement("button");b.type="button";b.textContent=ask;b.onclick=()=>{el("ask").value=ask;el("ask").focus();};return b;}));
  if(!el("ask").value && state.sample_asks?.length) el("ask").value=state.sample_asks[0];
  el("status").textContent="Explore the ship";
  render();
} catch(error) {el("status").textContent=`Unable to load the ship: ${error.message}`;el("propose").disabled=true;}
try {const {createScene}=await import("./primitives.js");scene=createScene(el("canvas"));await renderScene();scene.restoreSelection(state.selected_model || (selectedTorpedo ? {kind:"torpedo",id:selectedTorpedo} : null));renderScope();}
catch(error) {el("scene-error").hidden=false;el("scene-error").textContent="3D view unavailable. Check WebGL and access to cdn.jsdelivr.net. The panel still works.";console.error(error);}

const el=id=>document.getElementById(id);
let state, selected=0, scene, busy=false, download;
const fmt=(n,d=1)=>n.toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});
async function api(path,payload) {
  const response=await fetch(`/api/${path}`,payload ? {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)} : {});
  const data=await response.json(); if(!response.ok) throw new Error(data.error || "Request failed"); return data;
}
function list(id,values) { el(id).replaceChildren(...values.map(value=> {const li=document.createElement("li");li.textContent=value;return li;})); }
function metric(id,label,value,unit,old,digits=1) {
  const dt=document.createElement("dt"), dd=document.createElement("dd"); dt.textContent=label; dd.textContent=`${fmt(value,digits)} ${unit}`;
  if(old != null && Math.abs(value-old)>10**(-digits)/2) {const change=document.createElement("small");change.textContent=`${value>old ? "+" : ""}${fmt(value-old,digits)}`;dd.append(change);}
  el(id).append(dt,dd);
}
function renderScene() {
  if(!scene || !state) return;
  const current=state.iterations[selected];
  scene.update(current,state.iterations[current.parent],{ghost:el("ghost").checked,highlight:el("highlight").checked,rotate:el("rotate").checked});
}
function render() {
  const it=state.iterations[selected], prev=state.iterations[it.parent], pending=state.iterations.at(-1).status==="pending";
  el("mode").textContent=state.mode==="fixture" ? "Fixture mode · no model call" : `Live model proposals${state.model ? ` · ${state.model}` : ""}`;
  el("preset").hidden=state.mode!=="fixture"; el("ask").hidden=state.mode!=="live";
  el("propose").disabled=busy || pending;
  el("title").textContent=`${it.name} / v${it.index}`;
  el("comparison").textContent=prev ? `Compared with accepted v${prev.index} · ${it.status} · ${it.model || it.source} proposal` : "Accepted baseline · drag to orbit, scroll to zoom";
  const tubeDelta=prev ? it.spec.weapons.torpedo_tubes-prev.spec.weapons.torpedo_tubes : 0;
  el("geometry-note").textContent=!prev ? "" : tubeDelta
    ? `${Math.abs(tubeDelta)} launch tube${Math.abs(tubeDelta)===1 ? "" : "s"} ${tubeDelta>0 ? "added" : "removed"} · blue highlights mark input-only edits`
    : !it.geometry_changed_parts ? "Highlights identify affected assemblies"
    : it.geometry_changed_parts.length ? "Orange highlights mark assemblies with geometry edits"
    : "Exterior unchanged · highlights mark affected engineering inputs";
  el("rationale").textContent=it.rationale;
  el("timeline").replaceChildren(...state.iterations.map((item,i)=> {
    const button=document.createElement("button");button.className="revision";button.setAttribute("aria-current",String(i===selected));
    button.textContent=`v${item.index} ${i===state.accepted ? "· active" : ""}`;
    const small=document.createElement("small");small.textContent=`${item.status} · ${item.derived.torpedo_capacity} torpedoes`;button.append(small);
    button.onclick=()=>{selected=i;render();};return button;
  }));
  el("metrics").replaceChildren();
  for(const [key,label,unit,digits] of [
    ["delta_v_km_s","Delta-v","km/s",1],["dry_mass_t","Dry mass","t",1],
    ["torpedo_capacity","Torpedoes","",0],["max_accel_g","Drive limit","g",2],
    ["crew_g_limit","Crew limit","g",1],["sustained_burn_hours","Cruise endurance","h",2],
  ]) metric("metrics",label,it.derived[key],unit,prev?.derived[key],digits);
  el("torpedo").replaceChildren();
  const torpedo=it.torpedo, prevTorpedo=prev?.torpedo;
  if(torpedo) {
    metric("torpedo","Length",torpedo.length_m*100,"cm",prevTorpedo ? prevTorpedo.length_m*100 : null);
    metric("torpedo","Diameter",torpedo.diameter_m*1000,"mm",prevTorpedo ? prevTorpedo.diameter_m*1000 : null,0);
    metric("torpedo","Fins",torpedo.fins,"",prevTorpedo?.fins,0);
    metric("torpedo","Fin span",torpedo.fin_span_m*1000,"mm",prevTorpedo ? prevTorpedo.fin_span_m*1000 : null,0);
    const dt=document.createElement("dt"), dd=document.createElement("dd"); dt.textContent="Motor"; dd.textContent=torpedo.motor; el("torpedo").append(dt,dd);
    el("torpedo-note").textContent=!prev ? (state.openrocket ? "Open in OpenRocket." : "")
      : torpedo.changed ? `Torpedo changed in this revision${state.openrocket ? " · OpenRocket reopened with it" : ""}.`
      : `Torpedo unchanged from v${prev.index}.`;
  }
  el("mission").replaceChildren();
  metric("mission","Flip",it.mission.flip_time_s/3600,"h");
  metric("mission","Arrival",it.mission.total_time_s/3600,"h");
  metric("mission","Delta-v margin",it.delta_v_margin,"km/s",prev?.delta_v_margin);
  list("warnings",it.mission.warnings.length ? it.mission.warnings : ["Mission checks passed"]);
  list("changes",it.changes.length ? it.changes : ["No spec changes"]);
  el("verdict").textContent=it.status==="pending" ? "Pending your review. Approval advances the active design." : `${it.status[0].toUpperCase()+it.status.slice(1)} · active design is v${state.accepted}`;
  for(const id of ["approve","reject"]) el(id).disabled=busy || it.status!=="pending";
  const handoff=it.handoff ?? {};
  el("export").disabled=busy || !prev || Boolean(handoff.share_url);
  el("share").disabled=busy || !prev || !["exported","share_failed"].includes(handoff.status) || Boolean(handoff.share_url);
  el("share").textContent=handoff.status==="share_failed" ? "Retry Kord share" : "Share with Kord";
  el("handoff-status").textContent=handoff.error || ({exported:"GLB pair exported and ready to share.",shared:"Comparison shared. Link saved with this revision."}[handoff.status]) || (prev ? "Export this revision and its accepted parent through Blender." : "Select a proposal to export.");
  el("share-destination").textContent=`Destination: ${state.kord_base}`;
  el("kord-link").hidden=!handoff.share_url;
  if(handoff.share_url) el("kord-link").href=handoff.share_url;
  el("artifacts").hidden=!handoff.artifacts || handoff.status==="export_failed";
  el("artifacts").replaceChildren();
  if(handoff.artifacts) {
    const directory=`/exports/v${String(it.index).padStart(4,"0")}/`;
    for(const [file,label] of [["before.glb","Before GLB ↓"],["after.glb","After GLB ↓"],["comparison.json","Comparison report ↓"]]) {
      if(!handoff.artifacts[file.split(".")[0]] && file!=="comparison.json") continue;
      if(file==="comparison.json" && !prev) continue;
      const link=document.createElement("a");link.href=directory+file;link.download=file;link.textContent=label;el("artifacts").append(link);
    }
  }
  if(download) URL.revokeObjectURL(download);
  download=URL.createObjectURL(new Blob([JSON.stringify(it.spec,null,2)],{type:"application/json"}));el("download").href=download;
  renderScene();
}
async function act(path,payload) {
  if(busy) return;
  busy=true;render();el("status").textContent=({propose:"Proposing → validating spec → computing consequences…",export:"Exporting both ships through Blender…",share:"Uploading the exported pair to Kord…",decide:"Saving your decision…"})[path];
  try {
    state=await api(path,payload);selected=payload.index ?? state.iterations.length-1;
    el("status").textContent=({propose:"Proposal ready. Inspect the changes, then approve or reject.",decide:"Decision saved. The next proposal starts from the accepted revision.",export:"Export finished. See the Kord comparison panel for results.",share:"Sharing finished. See the Kord comparison panel for results."})[path];
  }
  catch(error) {el("status").textContent=error.message;}
  finally {busy=false;render();}
}
el("proposal").onsubmit=e=>{e.preventDefault();if(!busy) act("propose",{preset:el("preset").value,ask:el("ask").value});};
for(const [id,verdict] of [["approve","approved"],["reject","rejected"]]) el(id).onclick=()=>act("decide",{index:selected,verdict});
for(const path of ["export","share"]) el(path).onclick=()=>act(path,{index:selected});
for(const id of ["ghost","highlight","rotate"]) el(id).onchange=renderScene;
el("fit").onclick=()=>scene?.fit();
try {
  state=await api("state"); selected=state.iterations.length-1;
  for(const [value,label] of Object.entries(state.presets)) {const option=document.createElement("option");option.value=value;option.textContent=label;el("preset").append(option);}
  el("status").textContent=state.iterations.at(-1).status==="pending"
    ? "Saved proposal awaiting review. Approve or reject it before requesting the next refit."
    : "Choose a refit to run the loop. Every performance number is computed from its spec.";render();
} catch(error) {el("status").textContent=`Unable to load workbench: ${error.message}`;el("propose").disabled=true;}
// Keep review and metrics usable even if WebGL or the external module CDN fails.
try {const {createScene}=await import("./primitives.js");scene=createScene(el("canvas"));renderScene();}
catch(error) {el("scene-error").hidden=false;el("scene-error").textContent="3D view unavailable. Check WebGL and access to cdn.jsdelivr.net. Spec review still works.";console.error(error);}

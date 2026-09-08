import * as THREE from "three";

// Presentation transforms only: the immutable mesh/spec never changes.
export function createAssembly(models, camera, controls, container) {
  let pieces=[], labels=[], decks=[], amount=0, target=0, startAmount=0, started=0;
  let focusIndex=null, focusObject=null, cameraMove=null, suspended=false;
  const layer=document.createElement("div"); layer.className="part-labels"; container.append(layer);
  const reduced=matchMedia("(prefers-reduced-motion: reduce)");
  const smooth=t=>t*t*t*(t*(t*6-15)+10);
  const emit=()=>container.dispatchEvent(new CustomEvent("assemblychange",{detail:{
    expanded:target>0, moving:amount!==target, focus:focusIndex, suspended,
    subject:focusObject?.userData.crew_name || (focusObject ? "Torpedo" : null),
    decks:decks.map(d=>({index:d.index,name:d.name,crew:d.crew})),
  }}));
  function moveCamera(center,distance,direction=new THREE.Vector3(.8,.52,-1)) {
    // Flush OrbitControls' residual damping so it cannot tug at the new target.
    const position=camera.position.clone(), look=controls.target.clone();
    const damping=controls.enableDamping, rotating=controls.autoRotate;
    controls.enableDamping=false; controls.autoRotate=false; controls.update();
    controls.enableDamping=damping; controls.autoRotate=rotating;
    camera.position.copy(position); controls.target.copy(look); camera.lookAt(look);
    controls.maxDistance=Math.max(2500,distance*1.5);
    cameraMove={time:performance.now(),from:camera.position.clone(),to:center.clone().addScaledVector(direction.normalize(),distance),
      lookFrom:controls.target.clone(),lookTo:center.clone()};
  }
  controls.addEventListener("start",()=>{cameraMove=null;});
  function boundsAtEnd() {
    const box=new THREE.Box3();
    for(const p of pieces) {
      if(p.ghost || p.kind==="torpedo") continue;
      p.object.position.copy(p.base).addScaledVector(p.offset,target);
      box.union(new THREE.Box3().setFromObject(p.object));
      p.object.position.copy(p.base).addScaledVector(p.offset,amount);
    }
    return box;
  }
  function frame() {
    suspended=false;
    focusIndex=null; focusObject=null; applyVisibility();
    const box=boundsAtEnd(); if(box.isEmpty()) return;
    const sphere=box.getBoundingSphere(new THREE.Sphere());
    const fov=Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
    moveCamera(sphere.center,sphere.radius/Math.sin(fov/2)*1.10);
    emit();
  }
  function applyVisibility() {
    for(const root of models.children) if(root.userData.assemblyGhost) root.visible=focusIndex===null && !focusObject && amount<.02;
    for(const p of pieces) p.object.visible=focusObject && focusIndex===null ? !p.ghost && p.object===focusObject :
      focusIndex===null ? (!p.ghost || amount<.02) : !p.ghost && p.index===focusIndex;
  }
  function bind() {
    const selectedName=focusObject?.name;
    layer.replaceChildren(); pieces=[]; labels=[]; decks=[]; focusObject=null;
    models.updateMatrixWorld(true);
    for(const root of models.children) {
      const ghost=!!root.userData.assemblyGhost;
      root.traverse(object=> {
        const data=object.userData, name=data.rocinante_part || object.name;
        const semantic=data.assembly_kind || (/^(drive_|tube_|pdc_)/.test(name) && data.rocinante_part);
        if(!semantic) return;
        // A glTF semantic node may own multiple material meshes; move it once.
        if(object.parent?.userData.assembly_kind || object.parent?.userData.rocinante_part===name) return;
        const box=new THREE.Box3().setFromObject(object), center=box.getCenter(new THREE.Vector3());
        const offset=data.assembly_offset ? new THREE.Vector3(...data.assembly_offset) :
          name.startsWith("drive_") ? new THREE.Vector3(0,name==="drive_bell" ? -13 : -8,0) :
          new THREE.Vector3(Math.sign(center.x || 1)*5,0,Math.sign(center.z || 1)*11);
        pieces.push({object,base:object.position.clone(),offset,ghost,index:data.deck_index,kind:data.assembly_kind});
        if(ghost) return;
        if(data.assembly_kind==="deck") {
          decks.push({object,index:data.deck_index,name:data.deck_label,crew:[]});
          const element=document.createElement("span"); element.className="part-label";
          element.textContent=`${String(data.deck_index+1).padStart(2,"0")}  ${data.deck_label}`;
          layer.append(element);
          const local=object.worldToLocal(center.clone()); local.x=box.getSize(new THREE.Vector3()).x*.52;
          labels.push({object,element,local,index:data.deck_index,crew:false});
        } else if(data.assembly_kind==="torpedo") {
          const element=document.createElement("span"); element.className="part-label torpedo-label";
          element.textContent="TORPEDO · ENLARGED"; layer.append(element);
          labels.push({object,element,local:object.worldToLocal(new THREE.Vector3(center.x,box.max.y+1,center.z)),torpedo:true});
        } else if(data.assembly_kind==="crew") {
          const element=document.createElement("span"); element.className="crew-label"; element.textContent=data.crew_name;
          layer.append(element);
          const local=object.worldToLocal(new THREE.Vector3(center.x,box.max.y+.32,center.z));
          labels.push({object,element,local,index:data.deck_index,crew:true});
        }
      });
    }
    for(const d of decks) d.crew=labels.filter(l=>l.crew && l.index===d.index).map(l=>l.element.textContent);
    decks.sort((a,b)=>a.index-b.index);
    for(const p of pieces) p.object.position.copy(p.base).addScaledVector(p.offset,amount);
    focusObject=pieces.find(p=>!p.ghost && p.object.name===selectedName)?.object || null;
    if(focusIndex!==null && !decks.some(d=>d.index===focusIndex)) focusIndex=null;
    applyVisibility();
    if(focusObject) focus(focusIndex,focusObject); else emit();
  }
  function expand(on) {
    focusIndex=null; focusObject=null; startAmount=amount; target=on ? 1 : 0; started=performance.now();
    if(reduced.matches) {
      amount=target;
      for(const p of pieces) p.object.position.copy(p.base).addScaledVector(p.offset,amount);
    }
    applyVisibility(); frame(); emit();
  }
  function focus(index, object=null) {
    suspended=false;
    const deck=decks.find(d=>d.index===index); if(!deck && !object) return;
    focusIndex=deck ? index : null; focusObject=object;
    // Stay at the current assembly positions; a click never snaps the geometry.
    const box=new THREE.Box3().setFromObject(object || deck.object);
    if(!object) for(const p of pieces) if(p.index===index) box.union(new THREE.Box3().setFromObject(p.object));
    const sphere=box.getBoundingSphere(new THREE.Sphere());
    const fov=Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
    target=amount; // Freeze a reveal in progress at the clicked object's position.
    applyVisibility();
    moveCamera(sphere.center,Math.max(2,sphere.radius/Math.sin(fov/2)*1.18),new THREE.Vector3(.48,.8,-1)); emit();
  }
  function pick(object) {
    const piece=pieces.find(p=>!p.ghost && (p.object===object || p.object.getObjectById(object.id)));
    if(!piece) return false;
    if(piece.kind==="crew") focus(piece.index,piece.object);
    else if(piece.kind==="deck") focus(piece.index);
    else if(piece.kind==="hull") expand(true);
    else return false;
    return true;
  }
  function selectable(object) {
    return pieces.some(p=>!p.ghost && ["deck","crew","hull"].includes(p.kind) &&
      (p.object===object || p.object.getObjectById(object.id)));
  }
  function tick(now) {
    const moving=amount!==target;
    if(moving) {
      const t=reduced.matches ? 1 : THREE.MathUtils.clamp((now-started)/1800,0,1);
      amount=startAmount+(target-startAmount)*smooth(t);
      if(t===1) amount=target;
      for(const p of pieces) p.object.position.copy(p.base).addScaledVector(p.offset,amount);
      applyVisibility(); if(amount===target) emit();
    }
    if(cameraMove) {
      const t=reduced.matches ? 1 : THREE.MathUtils.clamp((now-cameraMove.time)/1350,0,1), eased=smooth(t);
      camera.position.lerpVectors(cameraMove.from,cameraMove.to,eased);
      controls.target.lerpVectors(cameraMove.lookFrom,cameraMove.lookTo,eased);
      camera.lookAt(controls.target);
      if(t===1) { cameraMove=null; controls.update(); }
    }
    models.updateMatrixWorld(true); camera.updateMatrixWorld();
    const width=container.clientWidth,height=container.clientHeight;
    for(const l of labels) {
      const point=l.object.localToWorld(l.local.clone()).project(camera);
      const visible=!suspended && (l.torpedo ? l.object.visible : amount>.94) && point.z<1 && point.z>-1 && Math.abs(point.x)<.94 && Math.abs(point.y)<.94 &&
        (l.torpedo ? focusIndex===null : l.crew ? focusIndex===l.index : focusIndex===null);
      l.element.hidden=!visible;
      if(visible) {l.element.style.left=`${(point.x*.5+.5)*width}px`;l.element.style.top=`${(-point.y*.5+.5)*height}px`;}
    }
  }
  return {bind,expand,focus,frame,tick,pick,selectable,moveCamera,get movingCamera(){return !!cameraMove;},
    suspend(){cameraMove=null;suspended=true;focusIndex=null;focusObject=null;applyVisibility();emit();},get expanded(){return target>0;},get ready(){return decks.length>0;}};
}

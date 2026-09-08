import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

// The stage: deep space, the Roci in the middle, the neighbourhood far away.
// Blender's export is the ship; the schematic below is only the fallback
// while no export exists. Part IDs match build_ship.py and the structured diff.

function schematicShip(spec, changed, ghost, geometryChanged=[]) {
  const group = new THREE.Group();
  const matches = (name) => changed.some(p => p.endsWith("*") ? name.startsWith(p.slice(0,-1)) : p === name);
  const moved = (name) => geometryChanged.some(p => p.endsWith("*") ? name.startsWith(p.slice(0,-1)) : p === name);
  function part(name, geometry, x, y, z) {
    const material = new THREE.MeshStandardMaterial({
      color:ghost ? 0x84a1c0 : moved(name) ? 0xff7855 : matches(name) ? 0x99c4e5 : 0xb5c8da,
      roughness:.65, metalness:.2, transparent:ghost, opacity:ghost ? .22 : 1, wireframe:ghost, depthWrite:!ghost,
    });
    const mesh = new THREE.Mesh(geometry,material);
    mesh.name=name; mesh.userData.rocinante_part=name; mesh.position.set(x,y,z); group.add(mesh);
    return mesh;
  }
  const h=spec.hull, d=spec.drive, w=spec.weapons, r=h.beam_m/2;
  part("hull_body",new THREE.CylinderGeometry(r*h.taper,r,h.length_m,6),0,h.length_m/2,0);
  part("drive_cone",new THREE.CylinderGeometry(d.cone_radius_m*.3,d.cone_radius_m,d.cone_length_m,12,1,true),0,-d.cone_length_m/2,0);
  for(let i=0;i<w.torpedo_tubes;i++) {
    const row=Math.floor(i/2), x=(i%2 ? 1 : -1)*(r*.85+1.2), y=h.length_m*(w.tube_station ?? .7)-row*6;
    part(`tube_${String(i+1).padStart(2,"0")}`,new THREE.CylinderGeometry(.8,.8,4,8),x,y,0);
  }
  for(let i=0;i<w.pdc_mounts;i++) {
    const a=2*Math.PI*i/Math.max(1,w.pdc_mounts);
    part(`pdc_${String(i+1).padStart(2,"0")}`,new THREE.BoxGeometry(1.7,1.7,2.5),Math.cos(a)*r*.85,h.length_m*.3,Math.sin(a)*r*.85);
  }
  group.position.y=-h.length_m/2;
  return group;
}

// --- the sky ---------------------------------------------------------------

function seeded(seed) { let s=seed>>>0; return ()=> { s=(s*1664525+1013904223)>>>0; return s/4294967296; }; }

function galaxyTexture() {
  const w=2048, h=1024, canvas=document.createElement("canvas"); canvas.width=w; canvas.height=h;
  const ctx=canvas.getContext("2d"), rand=seeded(7);
  ctx.fillStyle="#03050c"; ctx.fillRect(0,0,w,h);
  // The band: a tilted sine of soft blobs, brighter and warmer toward the core.
  const blob=(x,y,r,rgb,a)=> { const g=ctx.createRadialGradient(x,y,0,x,y,r); g.addColorStop(0,`rgba(${rgb},${a})`); g.addColorStop(1,`rgba(${rgb},0)`); ctx.fillStyle=g; ctx.fillRect(x-r,y-r,2*r,2*r); };
  for(let i=0;i<900;i++) {
    const t=rand(), x=t*w, core=Math.exp(-((t-.42)**2)/.03);
    const y=h*.5+Math.sin(t*Math.PI*2)*h*.16+(rand()-.5)*h*(.06+.10*core);
    const warm=rand()<.4+core*.4;
    blob(x,y,18+rand()*70*(0.5+core),warm ? "232,205,170" : "140,170,230",.09+.16*core);
  }
  for(let i=0;i<40;i++) { // dust lanes
    const t=rand(), x=t*w, y=h*.5+Math.sin(t*Math.PI*2)*h*.16+(rand()-.5)*h*.05;
    blob(x,y,25+rand()*60,"5,6,14",.45);
  }
  for(let i=0;i<8;i++) blob(rand()*w,rand()*h,120+rand()*220,rand()<.5 ? "120,90,200" : "80,140,200",.12); // nebulae
  const texture=new THREE.CanvasTexture(canvas); texture.mapping=THREE.EquirectangularReflectionMapping; texture.colorSpace=THREE.SRGBColorSpace;
  return texture;
}

function starDot() {
  const c=document.createElement("canvas"); c.width=c.height=32; const ctx=c.getContext("2d");
  const g=ctx.createRadialGradient(16,16,0,16,16,16); g.addColorStop(0,"rgba(255,255,255,1)"); g.addColorStop(.35,"rgba(255,255,255,.6)"); g.addColorStop(1,"rgba(255,255,255,0)");
  ctx.fillStyle=g; ctx.fillRect(0,0,32,32); return new THREE.CanvasTexture(c);
}

function stars(count, radius, size, seed) {
  const rand=seeded(seed), positions=new Float32Array(count*3), colors=new Float32Array(count*3);
  for(let i=0;i<count;i++) {
    const u=rand()*2-1, phi=rand()*Math.PI*2, s=Math.sqrt(1-u*u);
    positions.set([radius*s*Math.cos(phi),radius*u,radius*s*Math.sin(phi)],i*3);
    const tint=rand(); colors.set(tint<.15 ? [1,.82,.7] : tint<.3 ? [.75,.85,1] : [1,1,1],i*3);
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute("position",new THREE.BufferAttribute(positions,3));
  geometry.setAttribute("color",new THREE.BufferAttribute(colors,3));
  return new THREE.Points(geometry,new THREE.PointsMaterial({size,map:starDot(),vertexColors:true,transparent:true,depthWrite:false,sizeAttenuation:false,opacity:.9}));
}

function label(text, size) {
  const c=document.createElement("canvas"); c.width=512; c.height=128; const ctx=c.getContext("2d");
  ctx.font="500 44px ui-monospace, Menlo, monospace"; ctx.textAlign="center"; ctx.textBaseline="middle";
  ctx.fillStyle="rgba(190,205,225,.95)"; ctx.fillText(text,256,64);
  const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:new THREE.CanvasTexture(c),transparent:true,depthWrite:false}));
  sprite.scale.set(size*4,size,1); return sprite;
}

function neighbourhood() {
  const group=new THREE.Group(), rand=seeded(3);
  // Ceres: a lumpy rock.
  const rock=new THREE.IcosahedronGeometry(90,4), pos=rock.getAttribute("position");
  for(let i=0;i<pos.count;i++) { const v=new THREE.Vector3().fromBufferAttribute(pos,i); v.multiplyScalar(1+(rand()-.5)*.12); pos.setXYZ(i,v.x,v.y,v.z); }
  rock.computeVertexNormals();
  const ceres=new THREE.Mesh(rock,new THREE.MeshStandardMaterial({color:0x8a8078,roughness:.95,metalness:.05,flatShading:true}));
  ceres.position.set(-1100,-160,1500); group.add(ceres);
  const ceresLabel=label("CERES",60); ceresLabel.position.copy(ceres.position).add(new THREE.Vector3(0,150,0)); group.add(ceresLabel);
  // Tycho: a spinning ring station.
  const tycho=new THREE.Group();
  tycho.add(new THREE.Mesh(new THREE.TorusGeometry(70,9,12,48),new THREE.MeshStandardMaterial({color:0x9aa7b8,roughness:.6,metalness:.4})));
  tycho.add(new THREE.Mesh(new THREE.CylinderGeometry(16,16,110,16),new THREE.MeshStandardMaterial({color:0xb5c0cf,roughness:.5,metalness:.5})).rotateX(Math.PI/2));
  for(let i=0;i<4;i++) { const spoke=new THREE.Mesh(new THREE.BoxGeometry(4,140,4),new THREE.MeshStandardMaterial({color:0x7d8896})); spoke.rotation.z=i*Math.PI/4; tycho.add(spoke); }
  tycho.position.set(1300,240,1100); tycho.rotation.x=.5; tycho.userData.spin=.0018; group.add(tycho);
  const tychoLabel=label("TYCHO",60); tychoLabel.position.copy(tycho.position).add(new THREE.Vector3(0,130,0)); group.add(tychoLabel);
  // The Ring: far, huge, faintly lit from inside.
  const ring=new THREE.Mesh(new THREE.TorusGeometry(520,14,20,200),new THREE.MeshStandardMaterial({color:0x5c6b85,emissive:0x2a4d7a,emissiveIntensity:.7,roughness:.4,metalness:.6}));
  ring.position.set(500,1000,4200); ring.rotation.set(1.05,.4,0); ring.userData.spin=.0004; group.add(ring);
  const ringLabel=label("THE RING",200); ringLabel.position.copy(ring.position).add(new THREE.Vector3(0,620,0)); group.add(ringLabel);
  return group;
}

export function createScene(container) {
  const scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(40,1,.1,30000);
  const renderer=new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=1.05;
  container.append(renderer.domElement);
  scene.background=galaxyTexture();
  scene.add(stars(5000,9000,2.2,11), stars(1200,8000,3.4,13));
  const far=neighbourhood(); scene.add(far);
  const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.autoRotateSpeed=.5; controls.minDistance=8; controls.maxDistance=2500;
  scene.add(new THREE.HemisphereLight(0xb9d4ff,0x1a2233,1.4));
  const sun=new THREE.DirectionalLight(0xfff1de,4.5); sun.position.set(600,900,-700); scene.add(sun);
  const fill=new THREE.DirectionalLight(0x9bc0ff,1.6); fill.position.set(-500,100,400); scene.add(fill);
  const models=new THREE.Group(); scene.add(models);
  const gltf=new GLTFLoader(), glbCache=new Map();
  let loadRequest=0;

  // Blender writes the semantic part tag as a glTF extra; fall back to names.
  function partOf(object) {
    for(let node=object;node;node=node.parent) if(node.userData?.rocinante_part) return node.userData.rocinante_part;
    for(let node=object;node;node=node.parent) if(/^(hull_|drive_|pdc_|tube_|deck_)/.test(node.name)) return node.name.replace(/\.\d+$/,"");
    return "";
  }
  const matches=(name,patterns)=>patterns.some(pattern=>pattern.endsWith("*") ? name.startsWith(pattern.slice(0,-1)) : name===pattern);

  function geometrySignatures(root) {
    const parts=new Map(); root.updateMatrixWorld(true);
    root.traverse(object=> {
      if(!object.isMesh) return;
      const name=partOf(object), positions=object.geometry.getAttribute("position"), vertices=[];
      if(!name || !positions) return;
      for(let i=0;i<positions.count;i++) vertices.push(positions.getX(i),positions.getY(i),positions.getZ(i));
      const signature=JSON.stringify([object.matrixWorld.elements,vertices,Array.from(object.geometry.index?.array ?? [])]);
      if(!parts.has(name)) parts.set(name,[]);
      parts.get(name).push(signature);
    });
    return new Map([...parts].map(([name,meshes])=>[name,meshes.sort().join("|")]));
  }

  function paintExport(root,{ghost,changed,geometryChanged=[]}) {
    root.traverse(object=> {
      if(!object.isMesh) return;
      const geometryEdit=!ghost && matches(partOf(object),geometryChanged);
      const changedPart=!ghost && (geometryEdit || matches(partOf(object),changed));
      if(!ghost && !changedPart) return;
      const tint=geometryEdit ? 0xff7855 : 0x99c4e5;
      const highlightMaterial=original=> {
        if(ghost) return new THREE.MeshStandardMaterial({color:0x71889e,roughness:.9,metalness:0,transparent:true,opacity:.16,depthWrite:false});
        const material=original.clone(); material.color.lerp(new THREE.Color(tint),.65);
        if(material.emissive) { material.emissive.set(tint); material.emissiveIntensity=.2; }
        return material;
      };
      object.material=Array.isArray(object.material) ? object.material.map(highlightMaterial) : highlightMaterial(object.material);
      object.userData.rocinantePreviewMaterial=true;
    });
  }

  function dispose(root) {
    const primitive=root.userData.rocinantePrimitive;
    root.traverse(object=> {
      if(!object.isMesh) return;
      if(primitive) object.geometry.dispose();
      if(primitive || object.userData.rocinantePreviewMaterial) for(const material of Array.isArray(object.material) ? object.material : [object.material]) material?.dispose();
    });
  }
  function clearModels() { for(const child of [...models.children]) { dispose(child); models.remove(child); } }
  function artifactSource(artifact) {
    const file=artifact?.file;
    if(typeof file!=="string" || !/^exports\/v\d+\/(before|after)\.glb$/.test(file)) return null;
    return {url:`/${file}`,key:`${file}:${artifact.sha256 || "unverified"}`};
  }
  async function loadGlb(source) {
    if(!glbCache.has(source.key)) glbCache.set(source.key,gltf.loadAsync(source.url).then(result=>result.scene));
    try { return (await glbCache.get(source.key)).clone(true); }
    catch(error) { glbCache.delete(source.key); throw error; }
  }
  function centre(root) { // Keep the Roci at the origin whatever Blender's origin was.
    const box=new THREE.Box3().setFromObject(root); if(box.isEmpty()) return root;
    const c=box.getCenter(new THREE.Vector3()); root.position.sub(c); return root;
  }
  let framed=false;
  function fit() {
    const box=new THREE.Box3().setFromObject(models); if(box.isEmpty()) return;
    const sphere=box.getBoundingSphere(new THREE.Sphere());
    const fov=Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
    const distance=sphere.radius/Math.sin(fov/2)*1.25;
    const direction=models.userData.rocinanteGlb ? new THREE.Vector3(.7,.25,-1) : new THREE.Vector3(.7,.25,1);
    camera.position.copy(sphere.center).addScaledVector(direction.normalize(),distance);
    controls.target.copy(sphere.center); controls.update(); framed=true;
  }
  new ResizeObserver(() => {
    const {clientWidth:w,clientHeight:h}=container; renderer.setSize(w,h); camera.aspect=w/Math.max(h,1); camera.updateProjectionMatrix(); if(!framed) fit();
  }).observe(container);
  renderer.setAnimationLoop(() => {
    for(const child of far.children) if(child.userData.spin) child.rotation.z+=child.userData.spin;
    controls.update(); renderer.render(scene,camera);
  });
  return {
    fit,
    setRotate(on) { controls.autoRotate=on; },
    async update(current,previous,{ghost,highlight}) {
      const request=++loadRequest;
      const artifacts=current.handoff?.artifacts;
      const afterSource=artifactSource(artifacts?.after), beforeSource=previous ? artifactSource(artifacts?.before) : null;
      const keepCamera=framed;
      if(afterSource) {
        try {
          const [after,before]=await Promise.all([loadGlb(afterSource),beforeSource ? loadGlb(beforeSource) : null]);
          if(request!==loadRequest) return "stale";
          const geometryGroups=current.geometry_changed_parts ?? [];
          const beforeGeometry=before ? geometrySignatures(before) : new Map();
          const actualEdits=[...geometrySignatures(after)].filter(([name,signature])=>matches(name,geometryGroups) && beforeGeometry.get(name)!==signature).map(([name])=>name);
          const inputOnly=(current.changed_parts ?? []).filter(part=>!geometryGroups.includes(part));
          clearModels(); models.userData.rocinanteGlb=true;
          if(before && ghost) { paintExport(before,{ghost:true,changed:[]}); models.add(centre(before)); }
          paintExport(after,{ghost:false,changed:highlight ? inputOnly : [],geometryChanged:highlight ? actualEdits : []}); models.add(centre(after));
          if(!keepCamera) fit();
          return "export";
        } catch(error) { if(request!==loadRequest) return "stale"; console.warn("Exported GLB failed to load; schematic instead.",error); }
      }
      if(request!==loadRequest) return "stale";
      clearModels(); models.userData.rocinanteGlb=false;
      const after=schematicShip(current.spec,highlight ? current.changed_parts ?? [] : [],false,highlight ? current.geometry_changed_parts ?? [] : []);
      after.userData.rocinantePrimitive=true; models.add(after);
      if(previous && ghost) { const before=schematicShip(previous.spec,[],true); before.userData.rocinantePrimitive=true; models.add(before); }
      if(!keepCamera) fit();
      return "schematic";
    },
  };
}

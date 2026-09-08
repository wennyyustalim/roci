import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

// Deliberately schematic. Part IDs match the Blender exporter and structured diff.
function ship(spec, changed, ghost) {
  const group = new THREE.Group();
  const matches = (name) => changed.some(p => p.endsWith("*") ? name.startsWith(p.slice(0,-1)) : p === name);
  function part(name, geometry, x, y, z) {
    const material = new THREE.MeshStandardMaterial({
      color:ghost ? 0x84a1c0 : matches(name) ? 0xff7855 : 0xb5c8da,
      roughness:.65, metalness:.2, transparent:ghost, opacity:ghost ? .22 : 1,
      wireframe:ghost, depthWrite:!ghost,
    });
    const mesh = new THREE.Mesh(geometry,material);
    mesh.name=name; mesh.userData.rocinante_part=name; mesh.position.set(x,y,z); group.add(mesh);
    return mesh;
  }
  const h=spec.hull, d=spec.drive, w=spec.weapons, r=h.beam_m/2;
  part("hull_body",new THREE.CylinderGeometry(r*h.taper,r,h.length_m,6),0,h.length_m/2,0);
  part("drive_cone",new THREE.CylinderGeometry(d.cone_radius_m*.3,d.cone_radius_m,d.cone_length_m,12,1,true),0,-d.cone_length_m/2,0);
  for(let i=0;i<w.torpedo_tubes;i++) {
    const row=Math.floor(i/2), x=(i%2 ? 1 : -1)*(r*.85+1.2), y=h.length_m*.75-row*6;
    part(`tube_${String(i+1).padStart(2,"0")}`,new THREE.CylinderGeometry(.8,.8,4,8),x,y,0);
    // One simple loaded torpedo per tube, sharing its assembly's part ID.
    part(`tube_${String(i+1).padStart(2,"0")}`,new THREE.ConeGeometry(.6,1.5,8),x,y+2.75,0);
  }
  for(let i=0;i<w.pdc_mounts;i++) {
    const a=2*Math.PI*i/Math.max(1,w.pdc_mounts);
    part(`pdc_${String(i+1).padStart(2,"0")}`,new THREE.BoxGeometry(1.7,1.7,2.5),Math.cos(a)*r*.85,h.length_m*.3,Math.sin(a)*r*.85);
  }
  return group;
}

export function createScene(container) {
  const scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(38,1,.01,2000);
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure=1.1;
  container.append(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.autoRotateSpeed=.6;
  scene.add(new THREE.HemisphereLight(0xc8e5ff,0x202d43,2.6));
  const light=new THREE.DirectionalLight(0xffffff,3); light.position.set(50,90,70); scene.add(light);
  const models=new THREE.Group(); scene.add(models);
  const gltf=new GLTFLoader(), glbCache=new Map();
  let loadRequest=0;

  // Blender writes the semantic part tag as a glTF extra. Keep the name
  // fallback for an export made without extras, or for an older artifact.
  function partOf(object) {
    for(let node=object;node;node=node.parent) {
      if(node.userData?.rocinante_part) return node.userData.rocinante_part;
      if(node.name) return node.name.replace(/\.\d+$/,"");
    }
    return "";
  }
  const matches=(name,patterns)=>patterns.some(pattern=>
    pattern.endsWith("*") ? name.startsWith(pattern.slice(0,-1)) : name===pattern);

  function paintExport(root,{ghost,changed}) {
    root.traverse(object=> {
      if(!object.isMesh) return;
      const changedPart=!ghost && matches(partOf(object),changed);
      if(!ghost && !changedPart) return; // Preserve Blender's authored materials.
      object.material=new THREE.MeshStandardMaterial({
        color:ghost ? 0x5b6472 : 0xff7855,
        roughness:ghost ? .9 : .45, metalness:ghost ? 0 : .18,
        transparent:ghost, opacity:ghost ? .22 : 1, depthWrite:!ghost,
        emissive:changedPart ? 0xff7855 : 0x000000,
        emissiveIntensity:changedPart ? .22 : 0,
      });
      object.userData.rocinantePreviewMaterial=true;
    });
  }

  function dispose(root) {
    const primitive=root.userData.rocinantePrimitive;
    root.traverse(object=> {
      if(!object.isMesh) return;
      if(primitive) object.geometry.dispose();
      if(primitive || object.userData.rocinantePreviewMaterial) {
        for(const material of Array.isArray(object.material) ? object.material : [object.material]) material?.dispose();
      }
    });
  }
  function clearModels() {
    for(const child of [...models.children]) { dispose(child); models.remove(child); }
  }
  function artifactSource(artifact) {
    const file=artifact?.file;
    if(typeof file!=="string" || !/^exports\/v\d+\/(before|after)\.glb$/.test(file)) return null;
    // A retry can overwrite the same artifact path. Keep the parsed scene
    // keyed to its immutable digest rather than reusing stale geometry.
    return {url:`/${file}`,key:`${file}:${artifact.sha256 || "unverified"}`};
  }
  async function loadGlb(source) {
    if(!glbCache.has(source.key)) glbCache.set(source.key,gltf.loadAsync(source.url).then(result=>result.scene));
    try { return (await glbCache.get(source.key)).clone(true); }
    catch(error) { glbCache.delete(source.key); throw error; }
  }
  function showFallback(message) {
    const notice=document.getElementById("scene-error");
    notice.hidden=!message;
    notice.textContent=message || "";
  }
  function fit() {
    const box=new THREE.Box3().setFromObject(models); if(box.isEmpty()) return;
    const sphere=box.getBoundingSphere(new THREE.Sphere());
    const fov=Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
    const distance=sphere.radius/Math.sin(fov/2)*1.3;
    const direction=models.userData.rocinanteGlb
      ? new THREE.Vector3(.7,.25,-1) // Blender export: Z-up, tubes face -Z.
      : new THREE.Vector3(.7,.25,1); // Schematic preview: long axis is Y.
    camera.position.copy(sphere.center).addScaledVector(direction.normalize(),distance);
    camera.near=Math.max(distance/1000,.01); camera.far=Math.max(distance*10,100); camera.updateProjectionMatrix();
    controls.target.copy(sphere.center); controls.update();
  }
  new ResizeObserver(() => {
    const {clientWidth:w,clientHeight:h}=container; renderer.setSize(w,h); camera.aspect=w/Math.max(h,1); camera.updateProjectionMatrix(); fit();
  }).observe(container);
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene,camera); });
  return {
    fit,
    async update(current,previous,{ghost,highlight,rotate}) {
      const request=++loadRequest;
      controls.autoRotate=rotate;
      const artifacts=current.handoff?.artifacts;
      const afterSource=artifactSource(artifacts?.after), beforeSource=ghost && previous ? artifactSource(artifacts?.before) : null;

      // An exported pair always belongs to this revision and its recorded
      // accepted parent, so it is the authoritative comparison when present.
      if(afterSource) {
        try {
          const [after,before]=await Promise.all([loadGlb(afterSource),beforeSource ? loadGlb(beforeSource) : null]);
          if(request!==loadRequest) return;
          clearModels();
          models.userData.rocinanteGlb=true;
          if(before) { paintExport(before,{ghost:true,changed:[]}); models.add(before); }
          paintExport(after,{ghost:false,changed:highlight ? current.changed_parts ?? [] : []}); models.add(after);
          showFallback(""); fit(); return;
        } catch(error) {
          if(request!==loadRequest) return;
          console.warn("Unable to load exported GLB; using schematic preview.",error);
          showFallback("Exported geometry could not be loaded. Showing the schematic preview.");
        }
      } else if(request===loadRequest) showFallback("");

      if(request!==loadRequest) return;
      clearModels();
      models.userData.rocinanteGlb=false;
      const after=ship(current.spec,highlight ? current.changed_parts ?? [] : [],false);
      after.userData.rocinantePrimitive=true; models.add(after);
      if(previous && ghost) {
        const before=ship(previous.spec,[],true);
        before.userData.rocinantePrimitive=true; models.add(before);
      }
      fit();
    },
  };
}

import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";

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
  const scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(38,1,.1,2000);
  const renderer=new THREE.WebGLRenderer({antialias:true,alpha:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2)); container.append(renderer.domElement);
  const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.autoRotateSpeed=.6;
  scene.add(new THREE.HemisphereLight(0xc8e5ff,0x202d43,2.6));
  const light=new THREE.DirectionalLight(0xffffff,3); light.position.set(50,90,70); scene.add(light);
  const models=new THREE.Group(); scene.add(models);
  function fit() {
    const box=new THREE.Box3().setFromObject(models); if(box.isEmpty()) return;
    const sphere=box.getBoundingSphere(new THREE.Sphere());
    const fov=Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
    const distance=sphere.radius/Math.sin(fov/2)*1.3;
    camera.position.copy(sphere.center).addScaledVector(new THREE.Vector3(.7,.25,1).normalize(),distance);
    camera.far=distance*10; camera.updateProjectionMatrix(); controls.target.copy(sphere.center); controls.update();
  }
  new ResizeObserver(() => {
    const {clientWidth:w,clientHeight:h}=container; renderer.setSize(w,h); camera.aspect=w/Math.max(h,1); camera.updateProjectionMatrix(); fit();
  }).observe(container);
  renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene,camera); });
  return {
    fit,
    update(current,previous,{ghost,highlight,rotate}) {
      models.traverse(obj=> { if(obj.isMesh) {obj.geometry.dispose(); obj.material.dispose();} }); models.clear();
      models.add(ship(current.spec,highlight ? current.changed_parts : [],false));
      if(previous && ghost) models.add(ship(previous.spec,[],true));
      controls.autoRotate=rotate; fit();
    },
  };
}

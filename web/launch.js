import * as THREE from "three";
import { buildTorpedo } from "./torpedo.js";

// Overlapping, soft turbulent volumes cool from fire to soot. Expansion is
// radial in this space scene; there is no gravity-driven mushroom cloud.
function buildExplosion() {
  const root=new THREE.Group(), time={value:0}, clouds=[];
  const plane=new THREE.PlaneGeometry(1,1);
  const vertexShader=`varying vec2 vUv;
    void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);}`;
  const fragmentShader=`
    varying vec2 vUv;
    uniform float time, seed;
    float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
    float noise(vec2 p){
      vec2 i=floor(p),f=fract(p);f=f*f*(3.0-2.0*f);
      return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
    }
    float fbm(vec2 p){
      float n=0.0,a=0.5;
      for(int i=0;i<4;i++){n+=a*noise(p);p=p*2.03+vec2(5.2,1.7);a*=0.5;}
      return n;
    }
    void main(){
      vec2 p=vUv*2.0-1.0;
      float n=fbm(p*3.8+vec2(seed,time*0.6));
      float detail=fbm(p*9.0+vec2(n*2.0+seed,-time*0.8));
      float edge=length(p)+(n-0.5)*0.48;
      float density=(1.0-smoothstep(0.48,0.98,edge))*(0.55+detail*0.45);
      float heat=clamp(1.35-time*0.82+n*0.65-length(p)*0.45,0.0,1.0);
      vec3 soot=mix(vec3(0.045,0.038,0.035),vec3(0.19,0.17,0.15),n);
      vec3 fire=mix(vec3(0.5,0.055,0.008),vec3(1.0,0.38,0.035),smoothstep(0.15,0.7,heat));
      fire=mix(fire,vec3(1.0,0.91,0.65),smoothstep(0.76,1.0,heat));
      vec3 color=mix(soot,fire,smoothstep(0.08,0.6,heat));
      float alpha=density*(1.0-smoothstep(2.0,4.8,time))*smoothstep(0.0,0.07,time);
      gl_FragColor=vec4(color,alpha*0.88);
    }`;
  for(let i=0;i<14;i++) {
    const cloud=new THREE.Mesh(plane,new THREE.ShaderMaterial({
      uniforms:{time,seed:{value:i*7.13}},vertexShader,fragmentShader,
      transparent:true,depthWrite:false,toneMapped:false,
    }));
    const angle=i*2.399963, y=1-2*(i+.5)/14, radius=Math.sqrt(1-y*y);
    cloud.userData.direction=new THREE.Vector3(Math.cos(angle)*radius,y,Math.sin(angle)*radius);
    cloud.userData.size=3.8+(i%4)*.65;
    root.add(cloud);clouds.push(cloud);
  }
  const flash=new THREE.Mesh(plane,new THREE.ShaderMaterial({
    uniforms:{time},vertexShader,fragmentShader:`varying vec2 vUv;uniform float time;
      void main(){vec2 p=vUv*2.0-1.0;float halo=pow(max(0.0,1.0-length(p)),3.0);
      float core=exp(-dot(p,p)*36.0);
      gl_FragColor=vec4(1.0,0.84,0.57,(halo+core)*exp(-time*15.0));}`,
    transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,toneMapped:false,
  }));
  root.add(flash);
  const light=new THREE.PointLight(0xffa34c,0,65);root.add(light);
  return {root,tick(t,camera){
    time.value=t;
    const expansion=1-Math.exp(-t*1.8);
    for(const cloud of clouds) {
      cloud.position.copy(cloud.userData.direction).multiplyScalar(expansion*(1.3+t*.7));
      cloud.scale.setScalar(cloud.userData.size*(.3+expansion*.8+t*.25));
      cloud.quaternion.copy(camera.quaternion);
    }
    flash.quaternion.copy(camera.quaternion);flash.scale.setScalar(10+t*18);flash.visible=t<.5;
    light.intensity=240*Math.exp(-t*5);
  }};
}

// Real OR coordinates/timing, translated to the tube mouth. The drone's crossing
// path and impact effects are staged; no guidance or space-flight model is claimed.
export function createLaunch({scene,camera,controls,assembly,container,torpedo}) {
  let run=null;
  const up=new THREE.Vector3(0,1,0);
  const emit=(phase,extra={})=>container.dispatchEvent(new CustomEvent("launchchange",{detail:{phase,...extra}}));
  const material=(color,opacity=1)=>new THREE.MeshBasicMaterial({color,transparent:true,opacity,depthWrite:false,toneMapped:false});
  function dispose(root) {
    const geometries=new Set(), materials=new Set(), textures=new Set();
    root.traverse(o=>{if(o.geometry) geometries.add(o.geometry);for(const m of o.material ? [o.material].flat() : []) {materials.add(m);if(m.map) textures.add(m.map);}});
    geometries.forEach(g=>g.dispose()); materials.forEach(m=>m.dispose());textures.forEach(t=>t.dispose());
    root.removeFromParent();
  }
  function cancel() {
    if(!run) return;
    const previous=run;run=null;
    previous.loaded.visible=true;
    dispose(previous.root);previous.tag.remove();
    controls.enabled=previous.enabled;controls.autoRotate=previous.rotate;
    emit("idle");
  }
  function start(data) {
    if(run?.phase==="complete") cancel();
    if(run) throw new Error("A launch is already in progress.");
    const loaded=torpedo(data.torpedo_id), samples=data.simulation?.ascent;
    if(!loaded || !samples?.length || samples.length<2 || samples.some(s=>s.length!==6 || s.some(n=>!Number.isFinite(n)))) throw new Error("No usable OpenRocket ascent for this torpedo.");
    const end=samples.at(-1)[0];
    if(end<=0 || samples.some((s,i)=>i>0 && s[0]<=samples[i-1][0])) throw new Error("Invalid OpenRocket sample timing.");
    const root=new THREE.Group();scene.add(root);
    const round=buildTorpedo(data.spec,"training-round");root.add(round);round.visible=false;
    round.scale.copy(loaded.scale);
    const plumeLength=round.userData.length_m*.7;
    const flame=new THREE.Group();round.add(flame);
    for(const [width,length,color,opacity] of [[1,1,0x46adff,.35],[.45,.75,0xdaf6ff,.9]]) {
      const plume=new THREE.Mesh(new THREE.ConeGeometry(data.spec.body.at(-1).outer_radius_m*1.5*width,plumeLength*length,24),material(color,opacity));
      plume.material.blending=THREE.AdditiveBlending;
      plume.rotation.z=Math.PI;plume.position.y=-plumeLength*length/2;flame.add(plume);
    }
    const glow=new THREE.PointLight(0xffb66a,15,12);round.add(glow);
    const drone=new THREE.Group();root.add(drone);drone.visible=false;
    const body=new THREE.Mesh(new THREE.OctahedronGeometry(1.1),new THREE.MeshStandardMaterial({color:0x567983,metalness:.6,roughness:.3}));drone.add(body);
    for(const x of [-1.5,1.5]) {
      const wing=new THREE.Mesh(new THREE.BoxGeometry(1.5,.12,1.5),new THREE.MeshStandardMaterial({color:0x253c4e,metalness:.6,roughness:.4}));wing.position.x=x;drone.add(wing);
    }
    const beacon=new THREE.Mesh(new THREE.SphereGeometry(.22,12,8),material(0xff8862));beacon.position.z=-1;drone.add(beacon);
    const targetRing=new THREE.Mesh(new THREE.TorusGeometry(2.4,.035,8,64),material(0xff9975,.7));drone.add(targetRing);
    const explosion=buildExplosion(), burst=explosion.root;root.add(burst);burst.visible=false;
    const trailGeometry=new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(new Float32Array((samples.length+2)*3),3));
    trailGeometry.setDrawRange(0,0);
    const trail=new THREE.Line(trailGeometry,new THREE.LineBasicMaterial({color:0xffbd7d,transparent:true,opacity:.65}));trail.frustumCulled=false;root.add(trail);
    const tag=document.createElement("div");tag.className="training-target";tag.textContent="DRONE 01 / MOVING TARGET";tag.hidden=true;container.append(tag);
    run={data,root,round,loaded,drone,body,targetRing,burst,explosion,flame,glow,trail,tag,samples,end,
      phase:"pullback",elapsed:0,clock:0,cursor:0,enabled:controls.enabled,rotate:controls.autoRotate,playbackRate:Math.min(1,end/9)};
    controls.enabled=false;controls.autoRotate=false;
    assembly.frame();emit("pullback",{torpedo:data.torpedo_id,simulation:data.simulation});
  }
  function stage() {
    const r=run;
    r.origin=new THREE.Vector3(...r.loaded.userData.launch_position);
    const first=new THREE.Vector3(...r.samples[0].slice(1,4));
    r.points=r.samples.map(s=>new THREE.Vector3(...s.slice(1,4)).sub(first).add(r.origin));
    // Nose contact determines impact, not a wall-clock timeout.
    r.impact=r.points.at(-1).clone();
    const direction=r.points.at(-1).clone().sub(r.points.at(-2)).normalize();
    r.impact.addScaledVector(direction,r.round.userData.length_m*r.round.scale.y);
    r.crossing=new THREE.Vector3(16,0,5);
    r.drone.position.copy(r.impact).sub(r.crossing);r.drone.visible=true;r.tag.hidden=false;
    r.round.position.copy(r.origin);
    const initialDirection=r.points[1].clone().sub(r.points[0]).normalize();
    if(initialDirection.lengthSq()) r.round.quaternion.setFromUnitVectors(up,initialDirection);
    // Stay outside the selected launch rail as the camera closes in.
    r.cameraDirection=new THREE.Vector3(.8,.35,Math.sign(r.origin.z) || -1).normalize();
    const framing=flightFrame(r);
    assembly.moveCamera(framing.center,framing.distance,r.cameraDirection.clone());
    r.phase="tracking";emit("tracking");
  }
  function flightFrame(r) {
    // Leave room behind the body for the exhaust while filling more of the view.
    const center=r.round.localToWorld(new THREE.Vector3(0,r.round.userData.length_m*.3,0));
    const radius=Math.max(2.5,r.round.userData.length_m*r.round.scale.y*.9);
    const fov=Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
    return {center,distance:radius/Math.sin(fov/2)*1.18};
  }
  function tick(dt) {
    const r=run;if(!r) return;
    r.elapsed+=dt;
    if(r.phase==="pullback" && !assembly.movingCamera) {
      r.phase="assembling";assembly.expand(false);emit("assembling");
    } else if(r.phase==="assembling" && !assembly.moving && !assembly.movingCamera) stage();
    else if(r.phase==="tracking" && !assembly.movingCamera) {
      r.phase="flight";r.round.visible=true;r.loaded.visible=false;r.clock=0;
      emit("flight",{rate:r.playbackRate,duration:r.end});
    }
    if(r.phase==="flight") {
      r.clock=Math.min(r.end,r.clock+dt*r.playbackRate);
      while(r.cursor<r.samples.length-2 && r.samples[r.cursor+1][0]<r.clock) r.cursor++;
      const a=r.samples[r.cursor], b=r.samples[r.cursor+1];
      const f=THREE.MathUtils.clamp((r.clock-a[0])/(b[0]-a[0]),0,1);
      r.round.position.lerpVectors(r.points[r.cursor],r.points[r.cursor+1],f);
      const direction=r.points[r.cursor+1].clone().sub(r.points[r.cursor]).normalize();
      if(direction.lengthSq()) r.round.quaternion.setFromUnitVectors(up,direction);
      // Translate with the round at a steady distance. Smoothing its world
      // position would let fast flights outrun the camera.
      const framing=flightFrame(r);
      controls.target.copy(framing.center);
      camera.position.copy(framing.center).addScaledVector(r.cameraDirection,framing.distance);
      camera.lookAt(controls.target);
      const thrust=THREE.MathUtils.lerp(a[5],b[5],f);
      r.flame.visible=thrust>.05;r.glow.intensity=thrust>.05 ? 15 : 0;
      r.flame.scale.set(1,1+.15*Math.sin(r.elapsed*45),1);
      const positions=r.trail.geometry.attributes.position;
      for(let i=0;i<=r.cursor;i++) positions.setXYZ(i,...r.points[i].toArray());
      positions.setXYZ(r.cursor+1,...r.round.position.toArray());positions.needsUpdate=true;
      r.trail.geometry.setDrawRange(0,r.cursor+2);
      r.drone.position.copy(r.impact).addScaledVector(r.crossing,r.clock/r.end-1);
      r.body.rotation.y+=dt*.7;
      const nose=r.round.localToWorld(new THREE.Vector3(0,r.round.userData.length_m,0));
      const range=nose.distanceTo(r.drone.position);
      emit("telemetry",{time:r.clock,speed:THREE.MathUtils.lerp(a[4],b[4],f),range,thrust});
      if(range<1.15 || r.clock===r.end && range<2) {
        r.phase="impact";r.clock=0;r.round.visible=false;r.drone.visible=false;
        r.burst.position.copy(r.drone.position);r.burst.visible=true;r.tag.textContent="DRONE 01 / DESTROYED";
        r.impactCamera=camera.position.clone();r.impactLook=controls.target.clone();
        emit("impact");
      }
    }
    if(r.phase==="impact") {
      r.clock+=dt;const t=r.clock;
      const fov=Math.min(THREE.MathUtils.degToRad(camera.fov),2*Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*camera.aspect));
      const distance=Math.max(r.impactCamera.distanceTo(r.impactLook),12/Math.sin(fov/2));
      const destination=r.burst.position.clone().addScaledVector(r.cameraDirection,distance);
      const ease=1-Math.exp(-t*2.5);
      camera.position.lerpVectors(r.impactCamera,destination,ease);
      controls.target.lerpVectors(r.impactLook,r.burst.position,ease);camera.lookAt(controls.target);
      r.explosion.tick(t,camera);
      r.trail.material.opacity=Math.max(0,.65-t*.65);
      if(t>4.8) {r.phase="complete";r.burst.visible=false;controls.enabled=r.enabled;controls.autoRotate=r.rotate;emit("complete");}
    }
    if(r.drone.visible) r.targetRing.quaternion.copy(camera.quaternion);
    if(!r.tag.hidden) {
      const p=(r.phase==="impact" || r.phase==="complete" ? r.burst : r.drone).position.clone().project(camera);
      r.tag.style.left=`${THREE.MathUtils.clamp(p.x*.5+.5,.15,.85)*container.clientWidth}px`;r.tag.style.top=`${THREE.MathUtils.clamp(-p.y*.5+.5,.14,.9)*container.clientHeight-28}px`;
    }
  }
  return {start,cancel,tick,get active(){return !!run && run.phase!=="complete";}};
}

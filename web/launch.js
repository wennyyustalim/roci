import * as THREE from "three";
import { buildTorpedo } from "./torpedo.js";

// A miniature Death Star-style training target, built entirely from geometry.
// The open polar cap gives the dish a real recess instead of a painted circle.
function buildBattleStation() {
  const body=new THREE.Group(), radius=1.8, dishAngle=.34;
  let seed=1977;
  const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed/4294967296;};
  const canvas=document.createElement("canvas");canvas.width=2048;canvas.height=1024;
  const ctx=canvas.getContext("2d");
  ctx.fillStyle="#4d5155";ctx.fillRect(0,0,2048,1024);
  for(let row=0;row<96;row++) {
    const y=row*1024/96, height=1024/96;
    for(let x=-random()*40;x<2048;) {
      const width=12+Math.floor(random()*58), shade=83+Math.floor(random()*57);
      ctx.fillStyle=`rgb(${shade},${shade+3},${shade+5})`;
      ctx.fillRect(x+1,y+1,width-2,height-2);
      ctx.fillStyle="rgba(215,225,230,.18)";ctx.fillRect(x+2,y+1,width-4,.7);
      for(let i=0;i<width/6;i++) {
        ctx.fillStyle=random()>.5 ? "#42484c" : "#92999d";
        ctx.fillRect(x+3+random()*(width-6),y+3,1+random()*3,1+random()*4);
      }
      if(random()>.78) {
        ctx.fillStyle="#c3cccf";
        for(let i=0;i<3;i++) ctx.fillRect(x+4+i*3,y+height-3,1,.8);
      }
      x+=width;
    }
  }
  // Broad service bands and a dark continuous equatorial trench.
  for(const y of [218,350,674,806]) {
    ctx.fillStyle="#444a4e";ctx.fillRect(0,y,2048,3);
    ctx.fillStyle="#939a9d";ctx.fillRect(0,y+3,2048,1);
  }
  ctx.fillStyle="#151c22";ctx.fillRect(0,503,2048,18);
  for(let x=0;x<2048;x+=9) {
    ctx.fillStyle="#56616a";ctx.fillRect(x,506,3,12);
    if(random()>.65) {ctx.fillStyle="#bbcbd2";ctx.fillRect(x,510,2,1);}
  }
  const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
  texture.wrapS=THREE.RepeatWrapping;texture.anisotropy=4;
  const hullMaterial=new THREE.MeshStandardMaterial({map:texture,bumpMap:texture,bumpScale:.009,metalness:.42,roughness:.78});
  const dishMaterial=new THREE.MeshStandardMaterial({color:0x646d73,metalness:.5,roughness:.72,side:THREE.DoubleSide});
  const rimMaterial=new THREE.MeshStandardMaterial({color:0x949ca0,metalness:.5,roughness:.65});
  const darkMaterial=new THREE.MeshStandardMaterial({color:0x202a30,metalness:.4,roughness:.82});
  const dishDirection=new THREE.Vector3(.32,.5,.8).normalize();
  const orientation=new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),dishDirection);
  const hullGeometry=new THREE.SphereGeometry(radius,192,128,0,Math.PI*2,dishAngle,Math.PI-dishAngle);
  hullGeometry.applyQuaternion(orientation);
  const positions=hullGeometry.attributes.position, uv=hullGeometry.attributes.uv, point=new THREE.Vector3();
  for(let i=0;i<positions.count;i++) {
    point.fromBufferAttribute(positions,i);
    // Keep panel courses horizontal even though the mesh pole follows the dish.
    uv.setXY(i,.5+Math.atan2(point.z,point.x)/(Math.PI*2),.5+Math.asin(point.y/radius)/Math.PI);
    if(Math.abs(point.y)<.05) point.multiplyScalar(.973);
    positions.setXYZ(i,point.x,point.y,point.z);
  }
  hullGeometry.computeVertexNormals();
  // Unwrap triangles crossing the texture seam to avoid stretched panel stripes.
  const hullSurface=hullGeometry.toNonIndexed();hullGeometry.dispose();
  const surfaceUv=hullSurface.attributes.uv;
  for(let i=0;i<surfaceUv.count;i+=3) {
    const values=[surfaceUv.getX(i),surfaceUv.getX(i+1),surfaceUv.getX(i+2)];
    if(Math.max(...values)-Math.min(...values)>.5)
      values.forEach((u,j)=>{if(u<.5) surfaceUv.setX(i+j,u+1);});
  }
  body.add(new THREE.Mesh(hullSurface,hullMaterial));
  const dish=new THREE.Group();dish.quaternion.copy(orientation);body.add(dish);
  const rimRadius=radius*Math.sin(dishAngle), rimHeight=radius*Math.cos(dishAngle);
  const profile=[];
  for(let i=0;i<=24;i++) {
    const t=i/24;profile.push(new THREE.Vector2(rimRadius*t,rimHeight-.27*(1-t*t)));
  }
  dish.add(new THREE.Mesh(new THREE.LatheGeometry(profile,96),dishMaterial));
  function ring(r,y,width,mat) {
    const mesh=new THREE.Mesh(new THREE.TorusGeometry(r,width,8,96),mat);
    mesh.rotation.x=-Math.PI/2;mesh.position.y=y;dish.add(mesh);
  }
  ring(rimRadius,rimHeight,.018,rimMaterial);
  for(const t of [.28,.57,.82]) ring(rimRadius*t,rimHeight-.27*(1-t*t)+.003,.005,darkMaterial);
  const ribPoints=[];
  for(let i=0;i<24;i++) {
    const angle=i*Math.PI/12;
    for(let j=3;j<24;j++) {
      for(const t of [j/24,(j+1)/24]) ribPoints.push(rimRadius*t*Math.cos(angle),rimHeight-.27*(1-t*t)+.004,rimRadius*t*Math.sin(angle));
    }
  }
  dish.add(new THREE.LineSegments(new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(ribPoints,3)),new THREE.LineBasicMaterial({color:0x343e45})));
  const aperture=new THREE.Mesh(new THREE.CylinderGeometry(.068,.068,.012,32),darkMaterial);
  aperture.position.y=rimHeight-.263;dish.add(aperture);
  body.userData.radius=radius;
  return body;
}

// Overlapping, soft turbulent volumes cool from fire to soot. Expansion is
// radial in this space scene; there is no gravity-driven mushroom cloud.
function buildExplosion() {
  const root=new THREE.Group(), time={value:0}, clouds=[];
  const plane=new THREE.PlaneGeometry(1,1);
  const vertexShader=`varying vec2 vUv;
    #include <common>
    #include <logdepthbuf_pars_vertex>
    void main(){
      vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);
      #include <logdepthbuf_vertex>
    }`;
  const fragmentShader=`
    #include <logdepthbuf_pars_fragment>
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
      #include <logdepthbuf_fragment>
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
      #include <logdepthbuf_pars_fragment>
      void main(){
      #include <logdepthbuf_fragment>
      vec2 p=vUv*2.0-1.0;float halo=pow(max(0.0,1.0-length(p)),3.0);
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
    const body=buildBattleStation();drone.add(body);
    const targetRing=new THREE.Mesh(new THREE.TorusGeometry(2.3,.018,8,96),material(0xff9975,.4));drone.add(targetRing);
    const explosion=buildExplosion(), burst=explosion.root;root.add(burst);burst.visible=false;
    const trailGeometry=new THREE.BufferGeometry().setAttribute("position",new THREE.Float32BufferAttribute(new Float32Array((samples.length+2)*3),3));
    trailGeometry.setDrawRange(0,0);
    const trail=new THREE.Line(trailGeometry,new THREE.LineBasicMaterial({color:0xffbd7d,transparent:true,opacity:.65}));trail.frustumCulled=false;root.add(trail);
    const tag=document.createElement("div");tag.className="training-target";tag.textContent="DEATH STAR / TRAINING TARGET";tag.hidden=true;container.append(tag);
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
    r.body.rotation.y=Math.atan2(r.cameraDirection.x,r.cameraDirection.z)-.25;
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
      r.body.rotation.y+=dt*.035;
      const nose=r.round.localToWorld(new THREE.Vector3(0,r.round.userData.length_m,0));
      const range=nose.distanceTo(r.drone.position);
      emit("telemetry",{time:r.clock,speed:THREE.MathUtils.lerp(a[4],b[4],f),range,thrust});
      if(range<r.body.userData.radius || r.clock===r.end && range<2) {
        r.phase="impact";r.clock=0;r.round.visible=false;r.drone.visible=false;
        r.burst.position.copy(r.drone.position);r.burst.visible=true;r.tag.textContent="DEATH STAR / DESTROYED";
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

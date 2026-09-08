import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { createAssembly } from "./assembly.js";
import { buildTorpedo } from "./torpedo.js";
import { createLaunch } from "./launch.js";

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

// Enlarge the displayed round to fill its launch rail; simulation specs stay in metres.
function loadedTorpedo(spec, id, bay) {
  const group=buildTorpedo(spec,id);
  const length=spec.nose.length_m+spec.body.reduce((sum,t)=>sum+t.length_m,0);
  const r=spec.body.at(-1).outer_radius_m, fins=spec.fins;
  const box=new THREE.Box3().setFromObject(bay), center=box.getCenter(new THREE.Vector3());
  const scale=Math.max(1,(box.max.y-box.min.y)*.9/length);
  group.scale.setScalar(scale);
  const side=Math.sign(center.z || -1), clearance=(r+fins.height_m)*scale+.04;
  group.position.set(center.x,center.y-length*scale/2,side<0 ? box.min.z-clearance : box.max.z+clearance);
  group.userData.launch_position=group.position.toArray();
  group.userData.assembly_offset=[Math.sign(center.x || 1)*5,0,side*11];
  return group;
}

// --- the sky ---------------------------------------------------------------

function seeded(seed) { let s=seed>>>0; return ()=> { s=(s*1664525+1013904223)>>>0; return s/4294967296; }; }

function galaxyTexture() {
  const w=2048, h=1024, canvas=document.createElement("canvas"); canvas.width=w; canvas.height=h;
  const ctx=canvas.getContext("2d"), rand=seeded(7), pixels=ctx.createImageData(w,h);
  // Fix the galactic plane in world space, crossing the default Roci bearing.
  // It stays distant while the ship and nearby landmarks move as we orbit.
  const forward=new THREE.Vector3(-.8,-.52,1).normalize();
  const right=new THREE.Vector3().crossVectors(forward,new THREE.Vector3(0,1,0)).normalize();
  const up=new THREE.Vector3().crossVectors(right,forward).normalize();
  const normal=right.clone().multiplyScalar(.55).addScaledVector(up,.835).normalize();
  const along=new THREE.Vector3().crossVectors(normal,forward).normalize();
  const hash=(x,y)=>{let n=Math.imul(x,374761393)+Math.imul(y,668265263);n=Math.imul(n^(n>>>13),1274126177);return ((n^(n>>>16))>>>0)/4294967295;};
  function noise(x,y) {
    const ix=Math.floor(x),iy=Math.floor(y); let u=x-ix,v=y-iy;
    u=u*u*(3-2*u);v=v*v*(3-2*v);
    return THREE.MathUtils.lerp(THREE.MathUtils.lerp(hash(ix,iy),hash(ix+1,iy),u),
      THREE.MathUtils.lerp(hash(ix,iy+1),hash(ix+1,iy+1),u),v);
  }
  function cloud(x,y) {return .52*noise(x,y)+.27*noise(x*2.03+13,y*2.03+7)+.14*noise(x*4.1+37,y*4.1)+.07*noise(x*8.3,y*8.3+51);}
  const direction=new THREE.Vector3();
  for(let y=0;y<h;y++) {
    const latitude=(.5-y/h)*Math.PI, cosLat=Math.cos(latitude), sinLat=Math.sin(latitude);
    for(let x=0;x<w;x++) {
      const longitude=(x/w-.5)*Math.PI*2;
      direction.set(cosLat*Math.cos(longitude),sinLat,cosLat*Math.sin(longitude));
      const lat=Math.asin(THREE.MathUtils.clamp(direction.dot(normal),-1,1));
      const lon=Math.atan2(direction.dot(along),direction.dot(forward));
      const offset=(noise(lon*5+20,3)-.5)*.038;
      const d=lat-offset, detail=cloud(lon*18+100,lat*32+100);
      const core=.55+.45*Math.exp(-(((lon-.18)/.65)**2));
      const haze=Math.exp(-((d/.21)**2))*(.3+detail)*core;
      const band=Math.exp(-((d/.075)**2))*(.18+detail*detail*2)*core;
      // A branching, uneven dust lane cuts through the luminous star clouds.
      const rift=lat-.021*Math.sin(lon*17)-.022*(noise(lon*29+8,6)-.5);
      const dust=Math.exp(-((rift/.017)**2))*(.55+.4*noise(lon*43,lat*47));
      const light=(haze*12+band*40)*(1-dust*.72);
      const warm=Math.exp(-(((lon-.18)/.45)**2)), i=(y*w+x)*4;
      pixels.data[i]=3+light*(.72+warm*.28);
      pixels.data[i+1]=5+light*(.83+warm*.08);
      pixels.data[i+2]=11+light*(1-warm*.14);
      pixels.data[i+3]=255;
    }
  }
  ctx.putImageData(pixels,0,0);
  // A faint unresolved star field keeps the galactic band behind the ship.
  for(let i=0;i<12000;i++) {
    const lon=(rand()-.5)*Math.PI*2, lat=(rand()+rand()+rand()-1.5)*.14;
    direction.copy(forward).multiplyScalar(Math.cos(lon)*Math.cos(lat))
      .addScaledVector(along,Math.sin(lon)*Math.cos(lat)).addScaledVector(normal,Math.sin(lat));
    const x=(Math.atan2(direction.z,direction.x)/(Math.PI*2)+.5)*w;
    const y=(.5-Math.asin(direction.y)/Math.PI)*h;
    ctx.fillStyle=`rgba(175,190,210,${.05+rand()*.15})`;
    const size=.25+rand()*.4;ctx.fillRect(x,y,size,size);
  }
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

function label(text, size, subtitle="") {
  const c=document.createElement("canvas"); c.width=512; c.height=128; const ctx=c.getContext("2d");
  ctx.font="500 30px ui-monospace, Menlo, monospace"; ctx.textAlign="center"; ctx.textBaseline="middle";
  ctx.fillStyle="rgba(196,213,231,.9)"; ctx.fillText(text,256,44);
  ctx.fillStyle="rgba(126,158,184,.7)"; ctx.font="18px ui-monospace, Menlo, monospace"; ctx.fillText(subtitle,256,80);
  ctx.fillRect(232,108,48,1);
  const texture=new THREE.CanvasTexture(c); texture.colorSpace=THREE.SRGBColorSpace;
  const sprite=new THREE.Sprite(new THREE.SpriteMaterial({map:texture,transparent:true,depthWrite:false,toneMapped:false}));
  sprite.scale.set(size*4,size,1); return sprite;
}

const metal=(color,roughness=.65)=>new THREE.MeshStandardMaterial({color,roughness,metalness:.55});
const luminous=color=>new THREE.MeshBasicMaterial({color,toneMapped:false});
function mesh(parent,geometry,material,x=0,y=0,z=0) {
  const object=new THREE.Mesh(geometry,material); object.position.set(x,y,z); parent.add(object); return object;
}
function hoop(parent,radius,tube,material,z=0) {
  return mesh(parent,new THREE.TorusGeometry(radius,tube,8,128),material,0,0,z);
}
// Repeated hull plates and windows share geometry and a single draw call.
function radialInstances(parent,geometry,material,count,radius,z=0,phase=0) {
  const instances=new THREE.InstancedMesh(geometry,material,count), transform=new THREE.Object3D();
  for(let i=0;i<count;i++) {
    const angle=i/count*Math.PI*2+phase;
    transform.position.set(Math.cos(angle)*radius,Math.sin(angle)*radius,z);
    transform.rotation.z=angle; transform.updateMatrix(); instances.setMatrixAt(i,transform.matrix);
  }
  parent.add(instances); return instances;
}

function ceresBody() {
  const group=new THREE.Group(), rand=seeded(31), craters=[];
  for(let i=0;i<46;i++) {
    const y=rand()*2-1, a=rand()*Math.PI*2, r=Math.sqrt(1-y*y);
    craters.push({center:new THREE.Vector3(r*Math.cos(a),y,r*Math.sin(a)),radius:.035+rand()*.17});
  }
  // Continuous surface displacement keeps the UV seam and poles joined.
  const terrain=v=> {
    let height=.0008*Math.sin(v.x*37+v.y*19)*Math.sin(v.z*41-v.y*23)
      +.003*Math.sin(v.x*12+v.z*9)*Math.cos(v.y*17-v.z*6);
    for(const crater of craters) {
      const d=v.distanceTo(crater.center)/crater.radius;
      if(d<1.4) height+=crater.radius*(-.19*Math.exp(-d*d*3.4)+.065*Math.exp(-(((d-.95)/.16)**2)));
    }
    return height;
  };
  const rock=new THREE.SphereGeometry(150,160,96), pos=rock.getAttribute("position"), colors=[];
  const direction=new THREE.Vector3(), color=new THREE.Color();
  for(let i=0;i<pos.count;i++) {
    direction.fromBufferAttribute(pos,i).normalize(); const height=terrain(direction);
    const grain=Math.sin(direction.x*73)*Math.sin(direction.y*91)*Math.sin(direction.z*83);
    const shade=THREE.MathUtils.clamp(.2+height*1.5+.012*grain,.1,.28);
    color.setRGB(shade*1.06,shade,shade*.91); colors.push(color.r,color.g,color.b);
    direction.multiplyScalar(150*(1+height)); pos.setXYZ(i,direction.x,direction.y*.94,direction.z);
  }
  rock.setAttribute("color",new THREE.Float32BufferAttribute(colors,3)); rock.computeVertexNormals();
  // Independent solar shading keeps a readable terminator without changing the
  // brighter workbench lights used to inspect the ship and station hardware.
  mesh(group,rock,new THREE.ShaderMaterial({
    vertexColors:true,
    vertexShader:`varying vec3 surfaceNormal; varying vec3 surfaceColor;
      void main() {
        surfaceNormal=mat3(modelMatrix)*normal; surfaceColor=color;
        gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0);
      }`,
    fragmentShader:`varying vec3 surfaceNormal; varying vec3 surfaceColor;
      void main() {
        vec3 n=normalize(surfaceNormal);
        float sunlight=max(dot(n,normalize(vec3(-.45,.8,-.2))),0.0);
        gl_FragColor=vec4(surfaceColor*(.07+sunlight*2.4),1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
  }));
  // Clusters of warm ports embedded in an equatorial belt, not an atmosphere.
  const lights=[], lightColors=[];
  for(let i=0;i<320;i++) {
    const cluster=i%7, angle=cluster*.9+(rand()-.5)*.16, latitude=(rand()-.5)*.1;
    direction.set(Math.cos(angle)*Math.cos(latitude),Math.sin(latitude),Math.sin(angle)*Math.cos(latitude));
    direction.multiplyScalar(150*(1+terrain(direction))+.45); direction.y*=.94;
    lights.push(direction.x,direction.y,direction.z); lightColors.push(1,.5+rand()*.3,.25);
  }
  const ports=new THREE.BufferGeometry(); ports.setAttribute("position",new THREE.Float32BufferAttribute(lights,3));
  ports.setAttribute("color",new THREE.Float32BufferAttribute(lightColors,3));
  group.add(new THREE.Points(ports,new THREE.PointsMaterial({map:starDot(),vertexColors:true,size:1.7,sizeAttenuation:false,transparent:true,depthWrite:false,toneMapped:false})));
  group.userData.spin=.008; return group;
}

function tychoStation() {
  const group=new THREE.Group(), habitat=new THREE.Group(); group.add(habitat);
  const hull=metal(0x87939c), dark=metal(0x273642), edge=metal(0xb2b9b8), rust=metal(0x9d5036);
  const warm=luminous(0xffbf73), cool=luminous(0x8dd8ef);
  hoop(habitat,128,10,dark);
  for(const z of [-9,9]) hoop(habitat,128,2,edge,z);
  radialInstances(habitat,new THREE.BoxGeometry(20,15,19),hull,48,128);
  radialInstances(habitat,new THREE.BoxGeometry(1,9,2),warm,96,139,5);
  radialInstances(habitat,new THREE.BoxGeometry(23,4,21),rust,12,128);
  // A rotating habitat around a stationary construction spindle.
  for(let i=0;i<6;i++) {
    const arm=new THREE.Group(); arm.rotation.z=i*Math.PI/3; habitat.add(arm);
    for(const z of [-6,6]) mesh(arm,new THREE.BoxGeometry(110,2.2,2.2),edge,70,0,z);
    for(let j=0;j<7;j++) {
      const brace=mesh(arm,new THREE.BoxGeometry(17,1.4,1.4),dark,24+j*15,0,0);
      brace.rotation.y=(j%2 ? 1 : -1)*.65;
    }
  }
  mesh(group,new THREE.CylinderGeometry(21,26,155,24),hull).rotation.x=Math.PI/2;
  for(const z of [-72,-42,42,72]) hoop(group,25,3,dark,z);
  mesh(group,new THREE.CylinderGeometry(31,31,12,24),dark,0,0,-80).rotation.x=Math.PI/2;
  hoop(group,22,1.5,cool,-87);
  for(let i=0;i<3;i++) {
    const dock=new THREE.Group(); dock.rotation.z=i*Math.PI*2/3+.3; group.add(dock);
    mesh(dock,new THREE.BoxGeometry(130,6,8),edge,80,0,52);
    mesh(dock,new THREE.BoxGeometry(7,7,75),rust,142,0,20);
    mesh(dock,new THREE.BoxGeometry(26,18,40),hull,90,0,52);
    mesh(dock,new THREE.BoxGeometry(38,28,2),dark,58,22,53);
    for(let j=0;j<5;j++) mesh(dock,new THREE.BoxGeometry(1,26,1),edge,42+j*8,22,55);
    mesh(dock,new THREE.SphereGeometry(2,8,6),warm,142,0,-18);
  }
  habitat.userData.spin=.045; return group;
}

function ringGate() {
  const group=new THREE.Group(), shell=metal(0x273b47,.42), rib=metal(0x50616a,.5), glow=luminous(0x80eaff);
  hoop(group,520,16,shell);
  for(const z of [-11,11]) {
    hoop(group,520,3,rib,z); hoop(group,503,1.9,glow,z);
  }
  radialInstances(group,new THREE.BoxGeometry(30,7,31),rib,96,520);
  radialInstances(group,new THREE.BoxGeometry(3,19,5),glow,192,500);
  radialInstances(group,new THREE.BoxGeometry(44,21,39),shell,12,520);
  // A transparent edge field leaves distant stars visible through the aperture.
  const field=new THREE.ShaderMaterial({
    uniforms:{time:{value:0}}, transparent:true, depthWrite:false, side:THREE.DoubleSide,
    blending:THREE.AdditiveBlending,
    vertexShader:`varying vec2 local; void main() { local=position.xy/560.0; gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.0); }`,
    fragmentShader:`varying vec2 local; uniform float time;
      void main() {
        float r=length(local), angle=atan(local.y,local.x);
        float rim=exp(-abs(r-.896)*95.0);
        float halo=exp(-abs(r-.896)*20.0)*.14;
        float ripple=sin(r*95.0-time*.7+sin(angle*7.0)*.8)*.5+.5;
        float inner=smoothstep(.5,.89,r)*(1.0-smoothstep(.89,.92,r));
        gl_FragColor=vec4(.21,.68,.85,(rim*.36+halo+inner*ripple*.035));
      }`,
  });
  mesh(group,new THREE.PlaneGeometry(1120,1120),field);
  group.userData.field=field; return group;
}

function neighbourhood() {
  const group=new THREE.Group();
  const landmarks={ceres:ceresBody(),tycho:tychoStation(),ring:ringGate()};
  // The Roci sits at the origin, surrounded by three separate bearings.
  // Leave the Ring farther out to retain its much larger sense of scale.
  const destinations=[
    {name:"ring",distance:5200,height:600},
    {name:"tycho",distance:2800,height:300},
    {name:"ceres",distance:2800,height:-400},
  ];
  destinations.forEach(({name,distance,height},index)=> {
    const bearing=-Math.PI/4+index*Math.PI*2/3;
    landmarks[name].position.set(Math.sin(bearing)*distance,height,Math.cos(bearing)*distance);
  });
  for(const [name,body] of Object.entries(landmarks)) {
    body.name=name;
    if(name!=="ceres") body.lookAt(0,0,0);
    if(name==="tycho") body.rotateY(.35);
    group.add(body);
    const size=name==="ring" ? 150 : 65, offset=name==="ring" ? 660 : 220;
    const tag=label(name==="ring" ? "THE RING" : name.toUpperCase(),size,
      {ceres:"BELT / CERES STATION",tycho:"TYCHO / CONSTRUCTION YARDS",ring:"SOL / RING GATE"}[name]);
    tag.position.copy(body.position).add(new THREE.Vector3(0,offset,0)); group.add(tag);
  }
  group.userData.landmarks=landmarks; return group;
}

export function createScene(container) {
  const scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(40,1,.005,30000);
  const renderer=new THREE.WebGLRenderer({antialias:true});
  renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  renderer.outputColorSpace=THREE.SRGBColorSpace;
  renderer.toneMapping=THREE.ACESFilmicToneMapping; renderer.toneMappingExposure=1.05;
  container.append(renderer.domElement);
  scene.background=galaxyTexture();
  scene.add(stars(3600,14000,1.15,11), stars(180,13000,2.5,13));
  const far=neighbourhood(); scene.add(far);
  const controls=new OrbitControls(camera,renderer.domElement); controls.enableDamping=true; controls.autoRotateSpeed=.5; controls.minDistance=.12; controls.maxDistance=2500;
  scene.add(new THREE.HemisphereLight(0xb9d4ff,0x1a2233,1.4));
  const sun=new THREE.DirectionalLight(0xfff1de,4.5); sun.position.set(600,900,-700); scene.add(sun);
  const fill=new THREE.DirectionalLight(0x9bc0ff,1.6); fill.position.set(-500,100,400); scene.add(fill);
  const models=new THREE.Group(); scene.add(models);
  const gltf=new GLTFLoader(), glbCache=new Map();
  let loadRequest=0, lastUpdate="", torpedoes=new Map();
  const assembly=createAssembly(models,camera,controls,container);
  const launch=createLaunch({scene,camera,controls,assembly,container,torpedo:id=>torpedoes.get(id)});
  container.addEventListener("assemblychange",event=>{far.visible=event.detail.focus===null && !event.detail.subject;});

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

  function highlightTubes(root) {
    root.traverse(object=> {
      if(!object.isMesh || !partOf(object).startsWith("tube_")) return;
      const paint=original=> {
        const material=original.clone();
        const shade=material.color.getHSL({}).l;
        material.color.setHSL(.57,.08,shade);
        if(material.emissive) { material.emissive.set(0x000000); material.emissiveIntensity=0; }
        return material;
      };
      const originals=Array.isArray(object.material) ? object.material : [object.material];
      object.material=Array.isArray(object.material) ? originals.map(paint) : paint(object.material);
      if(object.userData.rocinantePreviewMaterial || root.userData.rocinantePrimitive) originals.forEach(m=>m.dispose());
      object.userData.rocinantePreviewMaterial=true;
    });
  }
  function addTorpedoes(current, root) {
    torpedoes=new Map();
    const bays=[]; root.traverse(o=>{if(o.userData.rocinante_part?.match(/^tube_\d+$/) && !o.parent?.userData.rocinante_part?.match(/^tube_\d+$/)) bays.push(o);});
    // Earlier detailed exports may already carry rounds; use the current instance specs.
    for(const object of [...root.children]) if(object.userData.assembly_kind==="torpedo") root.remove(object);
    for(const bay of bays) {
      const id=bay.userData.rocinante_part.replace("tube_","torpedo_");
      const round=loadedTorpedo(current.torpedoes?.[id] || current.spec.torpedo,id,bay);
      torpedoes.set(id,round); models.add(round);
    }
  }
  function selectTorpedo(id, notify=true) {
    if(launch.active) return;
    launch.cancel();
    const round=torpedoes.get(id); if(!round) return;
    assembly.focus(null,round);
    if(notify) container.dispatchEvent(new CustomEvent("modelselect",{detail:{kind:"torpedo",id}}));
  }
  function notifySelection(selection) { container.dispatchEvent(new CustomEvent("modelselect",{detail:selection})); }
  function clearSelection() { notifySelection({kind:"ship",expanded:assembly.expanded}); }
  function dispose(root) {
    const primitive=root.userData.rocinantePrimitive;
    root.traverse(object=> {
      if(!object.isMesh && !object.isSprite) return;
      if(primitive) object.geometry?.dispose();
      if(primitive || object.userData.rocinantePreviewMaterial) for(const material of Array.isArray(object.material) ? object.material : [object.material]) { if(primitive) material?.map?.dispose(); material?.dispose(); }
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
  async function refreshInterior(root) {
    const rooms=[];
    root.traverse(o=>{if(o.userData.assembly_kind==="deck") rooms.push(o);});
    if(!rooms.some(o=>(o.userData.interior_revision || 0)<2)) return;
    const detailed=await loadGlb({url:"/rocinante.glb",key:"demo-interior-v2"});
    const replacements=new Map();
    detailed.traverse(o=>{if(o.userData.rocinante_part) replacements.set(o.userData.rocinante_part,o);});
    const upgraded=new Set();
    for(const room of rooms) {
      const next=replacements.get(room.userData.rocinante_part);
      if(!next || (room.userData.interior_revision || 0)>=2) continue;
      // Only refresh rooms with the same floor station and footprint. A refit
      // that changes hull dimensions or deck layout keeps its own geometry.
      const a=new THREE.Box3().setFromObject(room).getSize(new THREE.Vector3());
      const b=new THREE.Box3().setFromObject(next).getSize(new THREE.Vector3());
      if(Math.abs(room.userData.deck_station-next.userData.deck_station)>.01 ||
         Math.abs(a.x-b.x)>.05 || Math.abs(a.z-b.z)>.05) continue;
      const parent=room.parent;
      parent.remove(room); parent.add(next);
      upgraded.add(room.userData.deck_index);
    }
    const crew=[];
    root.traverse(o=>{if(o.userData.assembly_kind==="crew" && upgraded.has(o.userData.deck_index)) crew.push(o);});
    for(const member of crew) {
      const next=replacements.get(member.userData.rocinante_part);
      if(next) {const parent=member.parent; parent.remove(member); parent.add(next);}
    }
  }
  function centre(root) { // Keep the Roci at the origin whatever Blender's origin was.
    const box=new THREE.Box3().setFromObject(root); if(box.isEmpty()) return root;
    const c=box.getCenter(new THREE.Vector3()); root.position.sub(c); return root;
  }
  let framed=false;
  function viewport() {
    const {clientWidth:w,clientHeight:h}=container;
    return {w,h,left:0,top:0,width:w,height:h};
  }
  function frameDistance(radius,padding) {
    const view=viewport();
    const halfFov=Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov)/2)*Math.min(view.width,view.height)/Math.max(view.h,1));
    const distance=radius/Math.sin(halfFov)*padding;
    controls.maxDistance=Math.max(2500,distance*1.5);
    return distance;
  }
  function fit() {
    if(assembly.ready) { assembly.frame(); framed=true; return; }
    const box=new THREE.Box3().setFromObject(models); if(box.isEmpty()) return;
    const sphere=box.getBoundingSphere(new THREE.Sphere());
    const distance=frameDistance(sphere.radius,1.1);
    const direction=new THREE.Vector3(.7,.25,-1);
    assembly.moveCamera(sphere.center,distance,direction); framed=true;
  }
  new ResizeObserver(() => {
    const view=viewport(), {w,h}=view; renderer.setSize(w,h); camera.aspect=w/Math.max(h,1);
    camera.clearViewOffset();
    camera.updateProjectionMatrix(); if(!framed) fit();
  }).observe(container);
  let lastTime;
  const reducedMotion=matchMedia("(prefers-reduced-motion: reduce)");
  renderer.setAnimationLoop(time => {
    assembly.tick(time);
    const dt=lastTime===undefined ? 0 : Math.min((time-lastTime)/1000,.05); lastTime=time;
    if(!reducedMotion.matches) far.traverse(child=> {
      if(child.userData.spin) child.rotation.z+=child.userData.spin*dt;
      if(child.userData.field) child.userData.field.uniforms.time.value+=dt;
    });
    launch.tick(dt);
    if(!assembly.movingCamera && !launch.active) controls.update();
    renderer.render(scene,camera);
  });
  function focus(name) {
    if(launch.active) return;
    if(name==="ship") { reset(); return; }
    const body=far.userData.landmarks[name]; if(!body) return;
    assembly.suspend(); notifySelection({kind:"landmark",id:name});
    const radius=name==="ring" ? 570 : name==="tycho" ? 185 : 155;
    const direction=camera.position.clone().sub(body.position).normalize();
    assembly.moveCamera(body.position,frameDistance(radius,1.15),direction);
  }
  function reset() {
    launch.cancel();
    if(assembly.ready) assembly.expand(false); else { assembly.suspend(); fit(); }
    clearSelection();
  }
  const raycaster=new THREE.Raycaster(), pointer=new THREE.Vector2();
  function paddedTorpedoHit(rect, visible) {
    // Screen-space picking must not require a second precise mesh hit.
    const cursor=new THREE.Vector2((pointer.x+1)*rect.width/2,(1-pointer.y)*rect.height/2);
    let best=null, bestDistance=Infinity;
    for(const [id,round] of torpedoes) {
      if(!visible(round)) continue;
      const length=round.userData.length_m;
      const start=round.localToWorld(new THREE.Vector3(0,length*.1,0)).project(camera);
      const end=round.localToWorld(new THREE.Vector3(0,length*.9,0)).project(camera);
      if(start.z < -1 || start.z > 1 || end.z < -1 || end.z > 1) continue;
      const a=new THREE.Vector2((start.x+1)*rect.width/2,(1-start.y)*rect.height/2);
      const b=new THREE.Vector2((end.x+1)*rect.width/2,(1-end.y)*rect.height/2);
      const axis=b.clone().sub(a);
      const t=THREE.MathUtils.clamp(cursor.clone().sub(a).dot(axis)/Math.max(axis.lengthSq(),.001),0,1);
      const nearest=a.clone().addScaledVector(axis,t), distance=nearest.distanceTo(cursor);
      if(distance>32 || distance>=bestDistance) continue;
      best={kind:"torpedo",id}; bestDistance=distance;
    }
    return best;
  }
  container.addEventListener("torpedoselect",event=>selectTorpedo(event.detail.id));
  function hitAt(event) {
    if(launch.active) return null;
    const rect=renderer.domElement.getBoundingClientRect();
    pointer.set((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1);
    scene.updateMatrixWorld(true); camera.updateMatrixWorld(); raycaster.setFromCamera(pointer,camera);
    const visible=object=> { for(let p=object;p;p=p.parent) if(!p.visible || p.userData.assemblyGhost) return false; return true; };
    const hits=raycaster.intersectObjects([models,far],true);
    // Direct mesh hits win when neighboring padded targets overlap.
    const first=hits.find(hit=>hit.object.isMesh && visible(hit.object));
    for(let node=first?.object;node;node=node.parent) {
      if(node.userData.torpedo_id) return {kind:"torpedo",id:node.userData.torpedo_id};
    }
    const padded=paddedTorpedoHit(rect,visible);
    if(padded) return padded;
    for(const hit of hits) {
      if(!hit.object.isMesh || !visible(hit.object)) continue;
      for(let node=hit.object;node;node=node.parent) {
        if(node.userData.torpedo_id) return {kind:"torpedo",id:node.userData.torpedo_id};
        const part=partOf(node);
        // The visible round is the only torpedo target; its mounting hardware is inert.
        if(part.startsWith("tube_")) return null;
        if(Object.values(far.userData.landmarks).includes(node)) return {kind:"landmark",name:node.name};
      }
      if(assembly.selectable(hit.object)) return {kind:"part",object:hit.object};
      // Opaque ship geometry blocks selection of anything behind it.
      return null;
    }
    return null;
  }
  let press=null;
  const activePointers=new Set();
  renderer.domElement.addEventListener("pointerdown",event=> {
    activePointers.add(event.pointerId);
    press=activePointers.size===1 && event.button===0 ? {id:event.pointerId,x:event.clientX,y:event.clientY,dragged:false} : null;
  });
  renderer.domElement.addEventListener("pointermove",event=> {
    if(press && Math.hypot(event.clientX-press.x,event.clientY-press.y)>6) press.dragged=true;
    renderer.domElement.style.cursor=activePointers.size ? "grabbing" : hitAt(event) ? "pointer" : "grab";
  });
  renderer.domElement.addEventListener("pointerup",event=> {
    activePointers.delete(event.pointerId);
    const click=press && press.id===event.pointerId && !press.dragged && Math.hypot(event.clientX-press.x,event.clientY-press.y)<=6;
    press=null; if(!click || launch.active) return;
    const hit=hitAt(event); if(!hit) { clearSelection(); assembly.frame(); return; }
    if(hit.kind==="landmark") focus(hit.name);
    else if(hit.kind==="torpedo") selectTorpedo(hit.id);
    else { const selection=assembly.pick(hit.object); if(selection) notifySelection(selection); }
  },{capture:true});
  renderer.domElement.addEventListener("pointercancel",event=>{activePointers.delete(event.pointerId);press=null;});
  renderer.domElement.addEventListener("lostpointercapture",event=>{activePointers.delete(event.pointerId);press=null;});
  renderer.domElement.setAttribute("tabindex","0");
  renderer.domElement.setAttribute("aria-label","Explore the Rocinante. Click the hull to disassemble or reassemble the ship. Click a deck, crew member, torpedo or distant landmark to zoom. Press Escape to reset view.");
  renderer.domElement.addEventListener("keydown",event=>{if(event.key==="Escape") reset();});
  return {
    fit() { clearSelection(); fit(); }, reset, focus, selectTorpedo,
    restoreSelection(selection) {
      if(!selection || selection.kind==="ship") { if(selection?.expanded) assembly.expand(true); return; }
      if(selection.kind==="torpedo") { selectTorpedo(selection.id,false); return; }
      if(selection.kind==="landmark") {
        const body=far.userData.landmarks[selection.id]; if(!body) return;
        assembly.suspend();
        assembly.moveCamera(body.position,frameDistance(selection.id==="ring" ? 570 : 185,1.15)); return;
      }
      if(selection.kind==="deck") { assembly.focus(selection.id); return; }
      let object; models.traverse(o=>{if(!object && o.userData.rocinante_part===selection.id && !o.parent?.userData.assemblyGhost) object=o;});
      if(object) assembly.focus(object.userData.deck_index ?? null,object);
    },
    launch: data=>launch.start(data), cancelLaunch: ()=>launch.cancel(),
    setExpanded(on) { if(launch.active) return; assembly.expand(on); clearSelection(); },
    focusDeck(index) { if(launch.active) return; assembly.focus(index); notifySelection({kind:"deck",id:index}); },
    setRotate(on) { if(!launch.active) controls.autoRotate=on; },
    async update(current,previous,{ghost,highlight}) {
      const signature=JSON.stringify([current.index,current.handoff?.artifacts,current.torpedoes,ghost,highlight]);
      if(signature===lastUpdate) return "unchanged";
      launch.cancel();
      const request=++loadRequest;
      const artifacts=current.handoff?.artifacts;
      const exportedSource=artifactSource(artifacts?.after);
      const afterSource=exportedSource || {url:"/rocinante.glb",key:"demo-interior-v2"}, beforeSource=previous ? artifactSource(artifacts?.before) : null;
      const keepCamera=framed;
      if(afterSource) {
        try {
          let [after,before]=await Promise.all([loadGlb(afterSource),beforeSource ? loadGlb(beforeSource) : null]);
          let hasInterior=false; after.traverse(o=>{if(o.userData.assembly_kind==="deck") hasInterior=true;});
          if(!hasInterior) {
            // Older exports remain immutable. Upgrade the demo presentation,
            // retaining the actual revision's launch cassettes.
            const detailed=await loadGlb({url:"/rocinante.glb",key:"demo-interior-v2"});
            for(const o of [...detailed.children]) if(o.userData.rocinante_part?.startsWith("tube_")) detailed.remove(o);
            for(const o of [...after.children]) if(o.userData.rocinante_part?.startsWith("tube_")) detailed.add(o);
            after=detailed;
          }
          await Promise.all([refreshInterior(after),before ? refreshInterior(before) : null]);
          if(request!==loadRequest) return "stale";
          const geometryGroups=current.geometry_changed_parts ?? [];
          const beforeGeometry=before ? geometrySignatures(before) : new Map();
          const actualEdits=[...geometrySignatures(after)].filter(([name,signature])=>matches(name,geometryGroups) && beforeGeometry.get(name)!==signature).map(([name])=>name);
          const inputOnly=(current.changed_parts ?? []).filter(part=>!geometryGroups.includes(part));
          clearModels(); models.userData.rocinanteGlb=true;
          if(before && ghost) { paintExport(before,{ghost:true,changed:[]}); before.userData.assemblyGhost=true; models.add(centre(before)); }
          paintExport(after,{ghost:false,changed:highlight ? inputOnly : [],geometryChanged:highlight ? actualEdits : []}); models.add(centre(after));
          highlightTubes(after); addTorpedoes(current,after);
          assembly.bind(); lastUpdate=signature;
          if(!keepCamera) fit();
          return exportedSource ? "export" : "demo";
        } catch(error) { if(request!==loadRequest) return "stale"; console.warn("Exported GLB failed to load; schematic instead.",error); }
      }
      if(request!==loadRequest) return "stale";
      clearModels(); models.userData.rocinanteGlb=false;
      const after=schematicShip(current.spec,highlight ? current.changed_parts ?? [] : [],false,highlight ? current.geometry_changed_parts ?? [] : []);
      after.userData.rocinantePrimitive=true; models.add(after);
      if(previous && ghost) { const before=schematicShip(previous.spec,[],true); before.userData.rocinantePrimitive=true; before.userData.assemblyGhost=true; models.add(before); }
      highlightTubes(after); addTorpedoes(current,after);
      assembly.bind();
      if(!keepCamera) fit();
      return "schematic";
    },
  };
}

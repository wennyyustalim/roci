import * as THREE from "three";

// Cosmetic hardware follows the editable envelope. Units are metres, +Y is forward.
// Keep the same detailing recipe in blend/torpedo_details.py for the desktop view.
export function buildTorpedo(spec, id="torpedo") {
  const group=new THREE.Group(); group.name=id;
  group.userData={assembly_kind:"torpedo",torpedo_id:id,rocinantePrimitive:true};
  const paint=(color,metalness,roughness)=>new THREE.MeshStandardMaterial({color,metalness,roughness});
  const materials={shell:paint(0xb9c4c5,.5,.38),panel:paint(0x617078,.65,.36),
    dark:paint(0x151e27,.4,.42),steel:paint(0x89979e,.8,.27),amber:paint(0xe5a23b,.35,.4)};
  function add(name,geometry,material,x=0,y=0,z=0) {
    const obj=new THREE.Mesh(geometry,materials[material]);
    obj.name=name; obj.position.set(x,y,z); obj.userData.rocinante_part=id;
    group.add(obj); return obj;
  }
  function ring(name,radius,width,y,material="steel") {
    return add(name,new THREE.CylinderGeometry(radius,radius,width,64),material,0,y,0);
  }
  function radialBox(name,width,length,depth,radius,y,angle,material) {
    const obj=add(name,new THREE.BoxGeometry(width,length,depth),material,
      radius*Math.sin(angle),y,radius*Math.cos(angle));
    obj.rotation.y=angle; return obj;
  }
  function lathe(name,points,material) {
    return add(name,new THREE.LatheGeometry(points.map(([r,y])=>new THREE.Vector2(r,y)),64),material);
  }
  let y=spec.body.reduce((sum,t)=>sum+t.length_m,0);
  const bodyLength=y, length=y+spec.nose.length_m;
  spec.body.forEach((tube,i)=> {
    const r=tube.outer_radius_m, h=tube.length_m, bottom=y-h, band=Math.min(r*.065,h*.04);
    ring(`section_${i}`,r,h,bottom+h/2,i%3===2 ? "panel" : "shell");
    ring(`seam_${i}`,r*1.008,band*2,y-band,"dark");
    ring(`collar_${i}`,r*1.025,band,y-band*2.6);
    for(let j=0;j<8;j++) {
      const a=j*Math.PI/4;
      radialBox(`fastener_${i}_${j}`,r*.065,band*.8,r*.025,r*1.018,y-band*2.6,a,"dark");
    }
    // Long service panels with recessed borders and captive corner screws.
    if(h>r*1.5) for(let j=0;j<4;j++) {
      const a=(j+.5)*Math.PI/2, panelLength=h*.56, mid=bottom+h*.49;
      radialBox(`panel_gasket_${i}_${j}`,r*.62,panelLength,r*.04,r*.985,mid,a,"dark");
      radialBox(`service_panel_${i}_${j}`,r*.55,panelLength*.94,r*.045,r*1.006,mid,a,"panel");
      for(const end of [-1,1]) radialBox(`panel_lock_${i}_${j}_${end}`,r*.12,r*.045,r*.018,
        r*1.035,mid+end*panelLength*.39,a,"steel");
    }
    y=bottom;
  });
  const nose=spec.nose, profile=[];
  for(let i=0;i<=48;i++) {
    const t=i/48, f=1-t, p=nose.shape_parameter;
    const theta=Math.acos(1-2*f);
    let radius;
    if(nose.shape==="conical") radius=f;
    else if(nose.shape==="ellipsoid") radius=Math.sqrt(1-t*t);
    else if(nose.shape==="parabolic") radius=(2*f-p*f*f)/(2-p);
    else if(nose.shape==="haack") radius=Math.sqrt(Math.max(0,(theta-Math.sin(2*theta)/2+p*Math.sin(theta)**3)/Math.PI));
    else { const rho=(nose.base_radius_m**2+nose.length_m**2)/(2*nose.base_radius_m);
      radius=(Math.sqrt(Math.max(0,rho*rho-(t*nose.length_m)**2))+nose.base_radius_m-rho)/nose.base_radius_m; }
    profile.push([Math.max(0,radius)*nose.base_radius_m,bodyLength+t*nose.length_m]);
  }
  lathe("ceramic_radome",profile,"dark");
  const nr=nose.base_radius_m;
  ring("nose_lock",nr*1.025,nr*.12,bodyLength+nr*.04);
  ring("identification_band",nr*1.028,nr*.17,bodyLength-nr*.23,"amber");
  ring("band_separator",nr*1.03,nr*.035,bodyLength-nr*.39,"dark");
  const fins=spec.fins, r=spec.body.at(-1).outer_radius_m, aft=fins.offset_from_aft_m;
  const shape=new THREE.Shape(); shape.moveTo(r,aft); shape.lineTo(r,aft+fins.root_chord_m);
  shape.lineTo(r+fins.height_m,aft+fins.root_chord_m-fins.sweep_m);
  shape.lineTo(r+fins.height_m,aft+fins.root_chord_m-fins.sweep_m-fins.tip_chord_m); shape.closePath();
  const geometry=new THREE.ExtrudeGeometry(shape,{depth:fins.thickness_m,bevelEnabled:false});
  geometry.translate(0,0,-fins.thickness_m/2);
  for(let i=0;i<fins.count;i++) {
    const a=i/fins.count*Math.PI*2;
    add(`fin_${i}`,geometry,"panel").rotation.y=a;
    radialBox(`fin_hinge_${i}`,r*.16,fins.root_chord_m*.82,r*.13,r,
      aft+fins.root_chord_m*.48,Math.PI/2+a,"steel");
  }
  // Exhaust recess is inside the tail envelope; no extra length or fake motor thrust.
  lathe("nozzle_rim",[[r,0],[r,r*.13],[r*.69,r*.13],[r*.69,0],[r,0]],"steel");
  lathe("nozzle_throat",[[r*.69,0],[r*.40,r*.46]],"dark");
  ring("exhaust_shadow",r*.4,r*.015,r*.46,"dark");
  // The tail disk would cover the recess: replace its aft face with the nozzle opening.
  const tail=group.getObjectByName(`section_${spec.body.length-1}`);
  const tailTube=spec.body.at(-1);
  tail.geometry.dispose();
  tail.geometry=new THREE.CylinderGeometry(r,r,tailTube.length_m,64,1,true);
  for(let j=0;j<12;j++) {
    const a=j*Math.PI/6;
    radialBox(`tail_flute_${j}`,r*.10,r*.6,r*.06,r*1.015,r*.46,a,"steel");
  }
  // Cooling slots follow the booster length and stay ahead of the fin roots.
  const ventBottom=Math.max(aft+fins.root_chord_m+r*.2,tailTube.length_m*.65);
  if(ventBottom+r*.5<tailTube.length_m) for(let j=0;j<4;j++) for(let k=0;k<5;k++) {
    radialBox(`vent_${j}_${k}`,r*.38,r*.04,r*.035,r*1.014,ventBottom+k*r*.1,j*Math.PI/2,"dark");
  }
  // Small applied stencil plates, repeated around the circumference for inspection.
  if(typeof document!=="undefined") {
    const canvas=document.createElement("canvas"); canvas.width=512; canvas.height=128;
    const ctx=canvas.getContext("2d"); ctx.fillStyle="#b9c4c5";ctx.fillRect(0,0,512,128);
    ctx.fillStyle="#24313a";ctx.font="bold 46px monospace";ctx.fillText("ROCINANTE",16,50);
    ctx.font="25px monospace";ctx.fillText(`MK VI / ${id.replace("torpedo_","").toUpperCase()}`,18,84);
    for(let i=0;i<60;i++) if(i%3!==1) ctx.fillRect(18+i*6,100,2+(i%2),16);
    const map=new THREE.CanvasTexture(canvas); map.colorSpace=THREE.SRGBColorSpace;
    const stencil=new THREE.MeshStandardMaterial({map,roughness:.55,metalness:.2});
    const tube=spec.body[Math.min(1,spec.body.length-1)];
    const top=bodyLength-spec.body.slice(0,1).reduce((s,t)=>s+t.length_m,0);
    const mid=spec.body.length>1 ? top-tube.length_m*.5 : bodyLength*.5;
    for(let j=0;j<4;j++) {
      const a=j*Math.PI/2;
      const obj=add(`stencil_${j}`,new THREE.PlaneGeometry(tube.outer_radius_m*.85,
        Math.min(tube.outer_radius_m*.22,tube.length_m*.18)),"shell",
        Math.sin(a)*tube.outer_radius_m*1.018,mid,Math.cos(a)*tube.outer_radius_m*1.018);
      obj.rotation.y=a; obj.material=stencil;
    }
  }
  group.userData.length_m=length;
  return group;
}

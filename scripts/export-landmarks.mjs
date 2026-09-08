// Bake the browser's actual landmark meshes for Blender, without a second modeling recipe.
// Usage: node scripts/export-landmarks.mjs [path/to/three/build/three.module.js]
// The optional path allows using an existing Three.js install; otherwise install three@0.169.
import {readFileSync, writeFileSync} from 'node:fs';
import {gzipSync} from 'node:zlib';
import {pathToFileURL} from 'node:url';
const THREE=await import(process.argv[2] ? pathToFileURL(process.argv[2]).href : 'three');
const source=readFileSync(new URL('../web/primitives.js',import.meta.url),'utf8');
const seeded=source.slice(source.indexOf('function seeded('),source.indexOf('function galaxyTexture('));
const geometry=source.slice(source.indexOf('const metal='),source.indexOf('export function createScene('));
const scene=new Function('THREE','starDot','label',`${seeded}\n${geometry}\nreturn neighbourhood();`)(THREE,()=>null,()=>new THREE.Object3D());
scene.updateMatrixWorld(true);
const geometries=[], cache=new Map(), objects=[];
for(const [id,root] of Object.entries(scene.userData.landmarks)) root.traverse(object=>{
  if(!object.isMesh) return;
  if(!cache.has(object.geometry)) {
    const g=object.geometry, p=g.getAttribute('position'), c=g.getAttribute('color');
    cache.set(g,geometries.length);
    geometries.push({positions:Array.from(p.array),indices:g.index ? Array.from(g.index.array) : Array.from({length:p.count},(_,i)=>i),colors:c ? Array.from(c.array) : null});
  }
  const m=object.material;
  const material={color:m.color?.toArray() || (m.vertexColors ? [.22,.21,.19] : [.21,.68,.85]),
    metallic:m.metalness ?? 0,roughness:m.roughness ?? .7,emission:!!m.isMeshBasicMaterial,
    opacity:m.isShaderMaterial && !m.vertexColors ? .04 : m.opacity};
  for(let i=0;i<(object.isInstancedMesh ? object.count : 1);i++) {
    const matrix=object.matrixWorld.clone();
    if(object.isInstancedMesh) { const instance=new THREE.Matrix4(); object.getMatrixAt(i,instance); matrix.multiply(instance); }
    objects.push({id,geometry:cache.get(object.geometry),matrix:matrix.toArray(),material});
  }
});
const output=new URL('../src/rocinante/blend/landmarks.json.gz',import.meta.url);
writeFileSync(output,gzipSync(JSON.stringify({geometries,objects})));
console.log(`Exported ${objects.length} landmark meshes from the browser geometry to ${output.pathname}`);

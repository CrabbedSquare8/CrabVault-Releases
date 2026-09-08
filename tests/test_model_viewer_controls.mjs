import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

// Exercise the real viewer loop and bundled OrbitControls. Only WebGL and the
// DOM are replaced; no models, conversion cache or running application needed.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const viewerPath = path.join(root, 'frontend', 'model-viewer.js');
const threePath = path.join(root, 'frontend', 'vendor', 'three', 'three.module.min.js');
const frames = new Map();
let frameId = 0;
function eventTarget() {
  const listeners = new Map();
  return {
    style: {},
    addEventListener(type, listener) {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type).add(listener);
    },
    removeEventListener(type, listener) { listeners.get(type)?.delete(listener); },
    dispatch(type, event) { listeners.get(type)?.forEach(listener => listener(event)); },
  };
}
const document = eventTarget();
const context = vm.createContext({console, window:{devicePixelRatio:1}, document,
  AbortController, AbortSignal, setTimeout, clearTimeout,
  ResizeObserver:class { observe() {} disconnect() {} },
  requestAnimationFrame(callback) { frames.set(++frameId, callback); return frameId; },
  cancelAnimationFrame(id) { frames.delete(id); },
});
const modules = new Map();
const replacements = new Map();
async function moduleFor(filename) {
  if (modules.has(filename)) return modules.get(filename);
  let source = fs.readFileSync(filename, 'utf8');
  if (filename === viewerPath) source += '\nexport { setupRenderer };';
  const module = new vm.SourceTextModule(source, {context, identifier:filename});
  modules.set(filename, module);
  await module.link((specifier, reference) => {
    if (reference.identifier === viewerPath && replacements.has(specifier)) return replacements.get(specifier);
    return moduleFor(path.resolve(path.dirname(reference.identifier), specifier));
  });
  return module;
}
function synthetic(exports) {
  return new vm.SyntheticModule(Object.keys(exports), function () {
    for (const [name, value] of Object.entries(exports)) this.setExport(name, value);
  }, {context});
}
const three = await moduleFor(threePath);
await three.evaluate();
class Renderer {
  renderCount = 0;
  setPixelRatio() {}
  setSize() {}
  render(_scene, camera) { this.renderCount++; this.position = camera.position.clone(); }
}
replacements.set('./vendor/three/three.module.min.js', synthetic({...three.namespace,
  WebGLRenderer:Renderer,
  PMREMGenerator:class { fromScene() { return {texture:{}}; } dispose() {} },
}));
replacements.set('./vendor/three/addons/loaders/GLTFLoader.js', synthetic({GLTFLoader:class {}}));
replacements.set('./vendor/three/addons/environments/RoomEnvironment.js', synthetic({RoomEnvironment:class {}}));
replacements.set('./native-textures.js', synthetic({supportedTextureFormats:()=>[],
  completeTextureMipmaps:()=>null, loadPreviewTexture:()=>null}));
const module = await moduleFor(viewerPath);
await module.evaluate();

const canvas = Object.assign(eventTarget(), {getRootNode:()=>document,
  getBoundingClientRect:()=>({left:0,top:0,width:800,height:600})});
const stage = {clientWidth:800,clientHeight:600,querySelector:()=>canvas};
const viewer = {overlay:{querySelector:()=>stage},closed:false};
module.namespace.setupRenderer(viewer);
function frame() {
  const queued = [...frames.values()];
  frames.clear();
  queued.forEach(callback => callback());
}
function wheel(deltaY, ctrlKey = false) {
  canvas.dispatch('wheel', {deltaY,deltaMode:0,ctrlKey,clientX:400,clientY:300,preventDefault(){}});
}
viewer.camera.position.set(0, 0, 10);
viewer.controls.update();
viewer.needsRender = true;
frame();
const initialCount = viewer.renderer.renderCount;
for (let i = 0; i < 10; i++) frame();
assert.equal(viewer.renderer.renderCount, initialCount, 'A cena parada não deve renderizar continuamente.');

for (const [delta, pinch] of [[-120,false], [120,false], [-12,true], [12,true]]) {
  const oldPosition = viewer.camera.position.clone();
  const before = viewer.renderer.renderCount;
  wheel(delta, pinch);
  assert.ok(viewer.camera.position.distanceTo(oldPosition) > 0, 'O evento deve alterar a câmera.');
  frame();
  assert.equal(viewer.renderer.renderCount, before + 1, 'O zoom precisa aparecer no próximo frame sem arrastar.');
  assert.ok(viewer.renderer.position.equals(viewer.camera.position));
  frame();
  assert.equal(viewer.renderer.renderCount, before + 1, 'A cena deve voltar a ficar ociosa após o zoom.');
}
const beforeBurst = viewer.renderer.renderCount;
wheel(-50); wheel(-50); wheel(-50);
frame();
assert.equal(viewer.renderer.renderCount, beforeBurst + 1, 'Vários eventos no mesmo frame devem renderizar só uma vez.');
viewer.closed = true;
viewer.controls.dispose();
frame();
assert.equal(frames.size, 0, 'Fechar não deve deixar novos frames agendados.');
console.log('Zoom in/out, pinch, eventos agrupados e renderização ociosa — OK');

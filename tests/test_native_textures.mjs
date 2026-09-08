import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import {fileURLToPath} from 'node:url';

// No browser globals or downloads: validate the binary parser against the same
// local Three.js modules shipped with the desktop application.
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const context = vm.createContext({console, ArrayBuffer, DataView, Uint8Array, Math, Error,
  AbortController, AbortSignal, setTimeout, clearTimeout});
const modules = new Map();
async function moduleFor(filename) {
  if (modules.has(filename)) return modules.get(filename);
  const module = new vm.SourceTextModule(fs.readFileSync(filename, 'utf8'), {context, identifier:filename});
  modules.set(filename, module);
  await module.link((specifier, reference) => moduleFor(path.resolve(path.dirname(reference.identifier), specifier)));
  return module;
}
const module = await moduleFor(path.join(root, 'frontend', 'native-textures.js'));
await module.evaluate();
const {parseNativeTexture, supportedTextureFormats} = module.namespace;

function texture(format = 1, width = 4, height = 4) {
  const size = Math.ceil(width/4) * Math.ceil(height/4) * (format === 1 ? 8 : 16);
  const bytes = new ArrayBuffer(28 + size);
  const view = new DataView(bytes);
  [0x58544d4d,1,format,1,width,height,size].forEach((value,index) => view.setUint32(index*4,value,true));
  return bytes;
}

for (const format of [1,2,3,4]) {
  const parsed = parseNativeTexture(texture(format));
  assert.equal(parsed.isCompressedTexture, true);
  assert.equal(parsed.mipmaps.length, 1);
  assert.equal(parsed.image.width, 4);
  assert.equal(parsed.image.height, 4);
  assert.equal(parsed.generateMipmaps, false);
}
assert.throws(() => parseNativeTexture(new ArrayBuffer(8)), /inválida/);
const invalidFormat = texture();
new DataView(invalidFormat).setUint32(8, 77, true);
assert.throws(() => parseNativeTexture(invalidFormat), /Formato/);
const truncated = texture(4).slice(0,-1);
assert.throws(() => parseNativeTexture(truncated), /inválidos/);
const badSize = texture();
new DataView(badSize).setUint32(16, 65536, true);
assert.throws(() => parseNativeTexture(badSize), /inválidos/);
const extraBytes = new ArrayBuffer(texture().byteLength + 4);
new Uint8Array(extraBytes).set(new Uint8Array(texture()));
assert.throws(() => parseNativeTexture(extraBytes), /Tamanho/);
assert.equal(supportedTextureFormats({extensions:{has:()=>false}}).length, 0);
assert.equal(supportedTextureFormats({extensions:{has:name=>name.includes('bptc')}}).join(','), 'bc7');
assert.equal(supportedTextureFormats({extensions:{has:()=>true}}).join(','), 'dxt1,dxt3,dxt5,bc7');
console.log('12 verificações: parser de textura, formatos da GPU e dados inválidos — OK');

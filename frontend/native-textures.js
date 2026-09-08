import * as THREE from "./vendor/three/three.module.min.js";

export function supportedTextureFormats(renderer) {
  const formats = [];
  if (renderer.extensions.has("WEBGL_compressed_texture_s3tc")) formats.push("dxt1", "dxt3", "dxt5");
  if (renderer.extensions.has("EXT_texture_compression_bptc")) formats.push("bc7");
  return formats;
}

// The original BC blocks go directly to WebGL. No CPU image expansion or PNG
// recompression; unsupported formats still arrive through the standard loader.
export function parseNativeTexture(buffer) {
  const data = new DataView(buffer);
  if (buffer.byteLength < 28 || data.getUint32(0, true) !== 0x58544d4d || data.getUint32(4, true) !== 1)
    throw new Error("Textura de prévia inválida.");
  const formats = {1: THREE.RGBA_S3TC_DXT1_Format, 2: THREE.RGBA_S3TC_DXT3_Format,
    3: THREE.RGBA_S3TC_DXT5_Format, 4: THREE.RGBA_BPTC_Format};
  const formatId = data.getUint32(8, true);
  const format = formats[formatId];
  const count = data.getUint32(12, true);
  if (!format || count < 1 || count > 16) throw new Error("Formato de textura inválido.");
  const mips = [];
  let offset = 16;
  for (let level = 0; level < count; level++) {
    if (offset + 12 > buffer.byteLength) throw new Error("Textura incompleta.");
    const width = data.getUint32(offset, true);
    const height = data.getUint32(offset + 4, true);
    const length = data.getUint32(offset + 8, true);
    offset += 12;
    const expected = Math.ceil(width / 4) * Math.ceil(height / 4) * (formatId === 1 ? 8 : 16);
    if (!width || !height || width > 32768 || height > 32768 || expected !== length || offset + length > buffer.byteLength)
      throw new Error("Dimensões ou dados de textura inválidos.");
    if (level && (width !== Math.max(1, mips[level - 1].width >> 1) || height !== Math.max(1, mips[level - 1].height >> 1)))
      throw new Error("Níveis de textura inválidos.");
    mips.push({width, height, data: new Uint8Array(buffer, offset, length)});
    offset += length;
  }
  if (offset !== buffer.byteLength) throw new Error("Tamanho de textura inválido.");
  const texture = new THREE.CompressedTexture(mips, mips[0].width, mips[0].height, format);
  const last = mips[mips.length - 1];
  texture.minFilter = last.width === 1 && last.height === 1 && mips.length > 1
    ? THREE.LinearMipmapLinearFilter : THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  return texture;
}

export async function loadPreviewTexture(url) {
  if (!/\.mmtx(?:[?#]|$)/i.test(url)) return new THREE.TextureLoader().loadAsync(url);
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Não foi possível ler a textura (${response.status}).`);
  return parseNativeTexture(await response.arrayBuffer());
}

export function completeTextureMipmaps(renderer, texture, copy = false) {
  if (!copy && (!texture.isCompressedTexture || texture.minFilter !== THREE.LinearFilter
      || (texture.image.width === 1 && texture.image.height === 1))) return null;
  // Many mod textures contain only the top mip. Render the original blocks
  // once on the GPU and build filtered mip levels there, instead of showing
  // noisy/aliased details or decompressing/re-encoding the image on the CPU.
  const target = new THREE.WebGLRenderTarget(texture.image.width, texture.image.height, {
    depthBuffer: false, stencilBuffer: false, generateMipmaps: true,
    minFilter: THREE.LinearMipmapLinearFilter, magFilter: THREE.LinearFilter,
    colorSpace: texture.colorSpace, wrapS: THREE.RepeatWrapping, wrapT: THREE.RepeatWrapping,
  });
  const geometry = new THREE.PlaneGeometry(2, 2);
  const material = new THREE.MeshBasicMaterial({map: texture, toneMapped: false,
    transparent: true, blending: THREE.NoBlending, depthTest: false, depthWrite: false});
  const scene = new THREE.Scene();
  scene.add(new THREE.Mesh(geometry, material));
  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 2);
  camera.position.z = 1;
  const previousTarget = renderer.getRenderTarget();
  try {
    renderer.setRenderTarget(target);
    renderer.render(scene, camera);
  } catch (error) {
    target.dispose();
    throw error;
  } finally {
    renderer.setRenderTarget(previousTarget);
    geometry.dispose();
    material.dispose();
  }
  if (!copy) texture.dispose();
  return target;
}

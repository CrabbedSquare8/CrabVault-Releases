import * as THREE from "./vendor/three/three.module.min.js";
import { GLTFLoader } from "./vendor/three/addons/loaders/GLTFLoader.js";
import { OrbitControls } from "./vendor/three/addons/controls/OrbitControls.js";
import { RoomEnvironment } from "./vendor/three/addons/environments/RoomEnvironment.js";
import { completeTextureMipmaps, loadPreviewTexture, supportedTextureFormats } from "./native-textures.js";

let activeViewer = null;

function cancelPreparation(viewer) {
  const requestId = viewer.requestId;
  viewer.requestId = null;
  if (requestId) {
    Promise.resolve(window.pywebview?.api?.cancel_component_3d_preview?.(requestId)).catch(() => {});
  }
}

async function prepareModel(viewer, modelKey = null) {
  cancelPreparation(viewer);
  const requestId = crypto.randomUUID();
  viewer.requestId = requestId;
  try {
    return await window.pywebview.api.prepare_component_3d_preview(
      viewer.modId, viewer.componentId, modelKey, requestId, viewer.gpuFormats,
    );
  } finally {
    if (viewer.requestId === requestId) viewer.requestId = null;
  }
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, (character) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[character]);
}

function materialList(material) {
  return Array.isArray(material) ? material : [material];
}

function disposeObject(root) {
  if (!root) return;
  root.traverse((child) => {
    child.geometry?.dispose?.();
    materialList(child.material).filter(Boolean).forEach((material) => material.dispose?.());
  });
}

function closeViewer() {
  const viewer = activeViewer;
  if (!viewer) return;
  activeViewer = null;
  viewer.closed = true;
  cancelPreparation(viewer);
  cancelAnimationFrame(viewer.frame || 0);
  viewer.resizeObserver?.disconnect();
  document.removeEventListener("keydown", viewer.onKeyDown, true);
  viewer.controls?.removeEventListener("change", viewer.onControlsChange);
  viewer.controls?.dispose();
  disposeObject(viewer.model);
  viewer.textures?.forEach((texture) => texture.dispose?.());
  viewer.textureTargets?.forEach((target) => target.dispose());
  viewer.environment?.dispose?.();
  viewer.renderer?.dispose();
  viewer.overlay.remove();
}

function createOverlay(componentName) {
  closeViewer();
  const overlay = document.createElement("div");
  overlay.id = "component-3d-overlay";
  overlay.className = "model-viewer-overlay";
  overlay.innerHTML = `
    <section class="model-viewer-dialog" role="dialog" aria-modal="true" aria-label="Visualizador 3D">
      <header>
        <div class="model-viewer-title">
          <b>Visualizador 3D</b>
          <small>${escapeHtml(componentName || "Componente Mesh")}</small>
        </div>
        <div class="model-viewer-toolbar">
          <label class="model-viewer-model-picker" hidden>Modelo
            <select aria-label="Escolher modelo 3D"></select>
          </label>
          <button class="model-viewer-tool textures-on" type="button" data-action="textures" disabled>Texturas</button>
          <button class="model-viewer-tool" type="button" data-action="wireframe" disabled>Wireframe</button>
          <button class="model-viewer-tool" type="button" data-action="reset" disabled>Centralizar</button>
          <button class="model-viewer-close" type="button" aria-label="Fechar visualizador">✕</button>
        </div>
      </header>
      <div class="model-viewer-stage">
        <canvas aria-label="Modelo 3D do componente"></canvas>
        <div class="model-viewer-status">
          <span class="model-viewer-spinner"></span>
          <b>Preparando modelo e texturas…</b>
          <small>Na primeira abertura, o suporte de leitura é baixado automaticamente. Depois, apenas a variante escolhida é preparada. Esc cancela.</small>
        </div>
        <div class="model-viewer-help" hidden>Arraste para girar · roda para aproximar · botão direito para mover · Esc para sair</div>
      </div>
    </section>`;
  document.body.appendChild(overlay);
  return overlay;
}

function showStatus(viewer, title, detail = "", error = false) {
  const status = viewer.overlay.querySelector(".model-viewer-status");
  status.hidden = false;
  status.classList.toggle("is-error", error);
  status.querySelector(".model-viewer-spinner").hidden = error;
  status.querySelector("b").textContent = title;
  status.querySelector("small").textContent = detail;
}

function hideStatus(viewer) {
  viewer.overlay.querySelector(".model-viewer-status").hidden = true;
  viewer.overlay.querySelector(".model-viewer-help").hidden = false;
}

function setupRenderer(viewer) {
  const stage = viewer.overlay.querySelector(".model-viewer-stage");
  const canvas = stage.querySelector("canvas");
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.22;
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));

  const scene = new THREE.Scene();
  const environmentGenerator = new THREE.PMREMGenerator(renderer);
  const environment = environmentGenerator.fromScene(new RoomEnvironment(), 0.04).texture;
  environmentGenerator.dispose();
  scene.environment = environment;
  scene.add(new THREE.AmbientLight(0xffffff, 0.75));
  scene.add(new THREE.HemisphereLight(0xdce7ff, 0x30202e, 2.8));
  const keyLight = new THREE.DirectionalLight(0xffffff, 4.2);
  keyLight.position.set(4, 7, 6);
  scene.add(keyLight);
  const rimLight = new THREE.DirectionalLight(0xff7f91, 1.5);
  rimLight.position.set(-5, 3, -4);
  scene.add(rimLight);

  const camera = new THREE.PerspectiveCamera(35, 1, 0.001, 1000);
  const controls = new OrbitControls(camera, canvas);
  controls.enableDamping = true;
  controls.dampingFactor = 0.075;
  controls.screenSpacePanning = true;
  controls.minDistance = 0.01;
  controls.maxDistance = 100;
  // Wheel/pinch handlers update the camera before the animation frame. Keep
  // that change pending even when the next controls.update() returns false.
  viewer.onControlsChange = () => { viewer.needsRender = true; };
  controls.addEventListener("change", viewer.onControlsChange);

  const resize = () => {
    const width = Math.max(1, stage.clientWidth);
    const height = Math.max(1, stage.clientHeight);
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    viewer.needsRender = true;
  };
  const resizeObserver = new ResizeObserver(resize);
  resizeObserver.observe(stage);
  resize();

  Object.assign(viewer, { stage, canvas, renderer, scene, camera, controls, resizeObserver, environment });
  viewer.gpuFormats = supportedTextureFormats(renderer);
  const render = () => {
    if (viewer.closed) return;
    const changed = controls.update();
    if (changed || viewer.needsRender) {
      renderer.render(scene, camera);
      viewer.needsRender = false;
    }
    viewer.frame = requestAnimationFrame(render);
  };
  render();
}

function normalizedMaterialName(value) {
  return String(value || "").replace(/\.\d+$/, "").toLocaleLowerCase();
}

function fallbackMaterialColor(name) {
  const value = normalizedMaterialName(name);
  if (/hair|brow|lash/.test(value)) return 0x242128;
  if (/eye/.test(value)) return 0xa9c7d8;
  if (/tooth|teeth/.test(value)) return 0xe9e3d8;
  if (/head|body|skin|face/.test(value)) return 0xc98f79;
  if (/metal|equip|weapon/.test(value)) return 0x777b84;
  return 0x77727e;
}

async function loadTexture(viewer, url, color = false) {
  if (!url) return null;
  const key = `${url}|${color ? 'srgb' : 'linear'}`;
  if (!viewer.texturePromises.has(key)) {
    viewer.texturePromises.set(key, loadPreviewTexture(url).then((texture) => {
      if (viewer.closed) { texture.dispose(); return null; }
      texture.flipY = false;
      texture.wrapS = THREE.RepeatWrapping;
      texture.wrapT = THREE.RepeatWrapping;
      texture.colorSpace = color ? THREE.SRGBColorSpace : THREE.NoColorSpace;
      texture.needsUpdate = true;
      const target = completeTextureMipmaps(viewer.renderer, texture);
      if (target) {
        viewer.textureTargets.add(target);
        texture = target.texture;
      }
      viewer.textures.add(texture);
      return texture;
    }).catch((error) => { viewer.texturePromises.delete(key); throw error; }));
  }
  return viewer.texturePromises.get(key);
}

function textureForMaterial(viewer, texture, materialName) {
  if (!texture) return null;
  const uv = normalizedMaterialName(materialName).match(/uv(\d+)/);
  const channel = uv ? Math.max(0, Number(uv[1]) - 1) : 0;
  if (channel === 0) return texture;
  const key = `${texture.uuid}:${channel}`;
  if (viewer.uvTextures.has(key)) return viewer.uvTextures.get(key);
  let clone;
  if (texture.isRenderTargetTexture) {
    // A render-target texture cannot be cloned like an Image: its pixels live
    // only on the GPU. Copy them there when a material needs a different UV set.
    const target = completeTextureMipmaps(viewer.renderer, texture, true);
    viewer.textureTargets.add(target);
    clone = target.texture;
  } else {
    clone = texture.clone();
    clone.needsUpdate = true;
  }
  clone.channel = channel;
  viewer.textures.add(clone);
  viewer.uvTextures.set(key, clone);
  return clone;
}

async function applyMaterialTextures(viewer, root, manifest, generation) {
  const byName = new Map(Object.entries(manifest || {}).map(([name, value]) => [normalizedMaterialName(name), value]));
  const tasks = [];
  root.traverse((child) => {
    if (!child.isMesh) return;
    materialList(child.material).filter(Boolean).forEach((material) => {
      if (viewer.materials.has(material)) return;
      viewer.materials.add(material);
      const specification = byName.get(normalizedMaterialName(material.name));
      material.side = THREE.DoubleSide;
      material.vertexColors = false;
      material.userData.viewerMaps = {};
      material.color?.setHex(fallbackMaterialColor(material.name));
      material.metalness = 0.04;
      material.roughness = 0.72;
      if (!specification) {
        material.needsUpdate = true;
        return;
      }
      tasks.push((async () => {
        const [baseColor, normal, orm, emissive] = await Promise.all([
          loadTexture(viewer, specification.base_color, true),
          loadTexture(viewer, specification.normal),
          loadTexture(viewer, specification.orm),
          loadTexture(viewer, specification.emissive, true),
        ]);
        if (viewer.closed || generation !== viewer.loadGeneration) return;
        const maps = material.userData.viewerMaps;
        const materialBaseColor = textureForMaterial(viewer, baseColor, material.name);
        const materialNormal = textureForMaterial(viewer, normal, material.name);
        const materialOrm = textureForMaterial(viewer, orm, material.name);
        const materialEmissive = textureForMaterial(viewer, emissive, material.name);
        if (materialBaseColor) {
          maps.map = materialBaseColor;
          material.color?.setHex(0xffffff);
        }
        if (materialNormal) {
          maps.normalMap = materialNormal;
          material.normalScale?.set(1, -1);
        }
        if (materialOrm) {
          maps.roughnessMap = materialOrm;
          material.roughness = 1;
          material.metalness = 0.04;
        }
        if (materialEmissive && materialEmissive !== materialBaseColor) {
          maps.emissiveMap = materialEmissive;
          material.emissive?.set(0xffffff);
          material.emissiveIntensity = 0.65;
        } else if (materialBaseColor) {
          maps.emissiveMap = materialBaseColor;
          material.emissive?.set(0xffffff);
          material.emissiveIntensity = 0.32;
        }
        if (specification.translucent) {
          material.transparent = true;
          material.depthWrite = false;
        }
        Object.assign(material, maps);
        material.needsUpdate = true;
      })());
    });
  });
  await Promise.allSettled(tasks);
}

function frameModel(viewer) {
  if (!viewer.model) return;
  viewer.model.position.set(0, 0, 0);
  const box = new THREE.Box3().setFromObject(viewer.model);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  viewer.model.position.sub(center);
  const maximum = Math.max(size.x, size.y, size.z, 0.1);
  viewer.camera.near = Math.max(maximum / 1000, 0.001);
  viewer.camera.far = maximum * 100;
  viewer.camera.position.set(maximum * 1.15, maximum * 0.42, maximum * 2.15);
  viewer.camera.updateProjectionMatrix();
  viewer.controls.target.set(0, 0, 0);
  viewer.controls.minDistance = maximum * 0.08;
  viewer.controls.maxDistance = maximum * 12;
  viewer.controls.update();
  viewer.needsRender = true;
}

function applyViewerOptions(viewer) {
  viewer.needsRender = true;
  viewer.materials.forEach((material) => {
    material.wireframe = viewer.wireframe;
    const maps = material.userData.viewerMaps || {};
    Object.keys(maps).forEach((name) => { material[name] = viewer.texturesEnabled ? maps[name] : null; });
    material.needsUpdate = true;
  });
  const textureButton = viewer.overlay.querySelector('[data-action="textures"]');
  textureButton.classList.toggle("textures-on", viewer.texturesEnabled);
  textureButton.textContent = viewer.texturesEnabled ? "Texturas" : "Sem texturas";
  viewer.overlay.querySelector('[data-action="wireframe"]').classList.toggle("is-active", viewer.wireframe);
}

async function loadModel(viewer, modelInfo) {
  const generation = ++viewer.loadGeneration;
  cancelPreparation(viewer);
  showStatus(viewer, modelInfo.ready ? "Carregando modelo…" : "Preparando esta variante…", modelInfo.name);
  try {
    if (!modelInfo.ready || !modelInfo.url) {
      const result = await prepareModel(viewer, modelInfo.key);
      if (viewer.closed || generation !== viewer.loadGeneration) return;
      if (!result?.ok) throw new Error(result?.error || "Não foi possível preparar esta variante.");
      result.models.forEach((model) => {
        const existing = viewer.models.find((item) => item.key === model.key);
        if (existing) Object.assign(existing, model);
      });
      modelInfo = viewer.models.find((item) => item.key === modelInfo.key);
    }
    const gltf = await new GLTFLoader().loadAsync(modelInfo.url);
    if (viewer.closed || generation !== viewer.loadGeneration) {
      disposeObject(gltf.scene);
      return;
    }
    if (viewer.model) {
      viewer.scene.remove(viewer.model);
      disposeObject(viewer.model);
    }
    // Shared texture promises survive variant switches; only the old geometry
    // and materials are released. Closing the viewer releases everything.
    viewer.materials.clear();
    viewer.model = gltf.scene;
    viewer.scene.add(gltf.scene);
    frameModel(viewer);
    showStatus(viewer, "Aplicando texturas…", `${modelInfo.material_count || 0} material(is)`);
    await applyMaterialTextures(viewer, gltf.scene, modelInfo.materials, generation);
    if (viewer.closed || generation !== viewer.loadGeneration) return;
    applyViewerOptions(viewer);
    hideStatus(viewer);
  } catch (error) {
    if (!viewer.closed && generation === viewer.loadGeneration)
      showStatus(viewer, "Não foi possível abrir este modelo.", error?.message || String(error), true);
  }
}

async function openViewer({ modId, componentId, componentName }) {
  const overlay = createOverlay(componentName);
  const viewer = {
    overlay,
    modId,
    componentId,
    models: [],
    closed: false,
    model: null,
    textures: new Set(),
    textureTargets: new Set(),
    uvTextures: new Map(),
    texturePromises: new Map(),
    materials: new Set(),
    texturesEnabled: true,
    wireframe: false,
    loadGeneration: 0,
  };
  activeViewer = viewer;
  viewer.onKeyDown = (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopImmediatePropagation();
    closeViewer();
  };
  document.addEventListener("keydown", viewer.onKeyDown, true);
  overlay.querySelector(".model-viewer-close").onclick = closeViewer;
  overlay.onclick = (event) => { if (event.target === overlay) closeViewer(); };

  try {
    const bridge = window.pywebview?.api;
    if (!bridge?.prepare_component_3d_preview) throw new Error("A API do visualizador ainda não está disponível.");
    setupRenderer(viewer);
    const result = await prepareModel(viewer);
    if (viewer.closed || activeViewer !== viewer) return;
    if (!result?.ok || !result.models?.length) {
      showStatus(viewer, "Não foi possível preparar o modelo.", result?.error || "Nenhum Mesh renderizável foi encontrado.", true);
      return;
    }

    viewer.models = result.models;
    const picker = overlay.querySelector(".model-viewer-model-picker");
    const select = picker.querySelector("select");
    result.models.forEach((model, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = model.name;
      select.appendChild(option);
    });
    picker.hidden = result.models.length < 2;
    select.onchange = () => loadModel(viewer, viewer.models[Number(select.value) || 0]);
    overlay.querySelectorAll(".model-viewer-tool").forEach((button) => { button.disabled = false; });
    overlay.querySelector('[data-action="textures"]').onclick = () => {
      viewer.texturesEnabled = !viewer.texturesEnabled;
      applyViewerOptions(viewer);
    };
    overlay.querySelector('[data-action="wireframe"]').onclick = () => {
      viewer.wireframe = !viewer.wireframe;
      applyViewerOptions(viewer);
    };
    overlay.querySelector('[data-action="reset"]').onclick = () => frameModel(viewer);
    const selected = Math.max(0, viewer.models.findIndex((model) => model.key === result.selected));
    select.value = String(selected);
    await loadModel(viewer, viewer.models[selected]);
  } catch (error) {
    if (!viewer.closed) showStatus(viewer, "Falha ao iniciar o visualizador.", error?.message || String(error), true);
  }
}

window.Marvel3DViewer = { open: openViewer, close: closeViewer };

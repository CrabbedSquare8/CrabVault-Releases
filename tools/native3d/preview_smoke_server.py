"""Opt-in local QA page for the real viewer/API, without catalog/game mutations."""
import argparse
import json
import pathlib
import sys
import tempfile
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from backend import mod_ops

PAGE = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="/style.css"><title>Teste do visualizador 3D</title>
<style>body {padding:32px; color:#eee; background:#18181d} button {margin:12px;padding:12px}</style>
<h1>Teste local do visualizador 3D</h1>
<p>Cache isolado. Nenhuma alteração nos mods ativos ou no catálogo.</p>
<button data-mod="161ae7ec4946" data-component="6995679c057f">SuperBuu</button>
<button data-mod="532fb31ea935" data-component="a82a6db8b2f8">Lopunny</button>
<button data-mod="13f27c511d5c" data-component="838b0a98653b">Peni</button>
<p id="test-result"></p>
<script type="module">
import '/model-viewer.js';
window.pywebview = {api: new Proxy({}, {get: (_, method) => async (...args) => {
  const response = await fetch('/__api/' + method, {method:'POST',
    headers:{'Content-Type':'application/json'}, body:JSON.stringify(args)});
  const data = await response.json();
  if (method === 'prepare_component_3d_preview') {
    document.getElementById('test-result').textContent = JSON.stringify({ok:data.ok,
      error:data.error,seconds:data.elapsed_seconds,cache:data.cached,
      models:data.models?.length,ready:data.models?.filter(m=>m.ready).length,
      warnings:data.warnings,textures:data.texture_statistics});
  }
  return data;
}})};
document.querySelectorAll('button[data-mod]').forEach(button => {
  button.onclick = async () => {
    const start = performance.now();
    await window.Marvel3DViewer.open({modId:button.dataset.mod,
      componentId:button.dataset.component,componentName:button.textContent});
    await new Promise(requestAnimationFrame);
    document.getElementById('test-result').textContent +=
      ` | Até aparecer: ${((performance.now()-start)/1000).toFixed(2)} s`;
  };
});
</script></html>"""


class Handler(SimpleHTTPRequestHandler):
    baseline_root = None
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(pathlib.Path(mod_ops.storage.BASE_DIR) / "frontend"), **kwargs)

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/__preview_test":
            page = PAGE
            if self.baseline_root:
                page = page.replace('<p id="test-result">', '<button data-mod="baseline" data-component="baseline">Antes da otimização</button><p id="test-result">')
            body = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().do_GET()

    def do_POST(self):
        methods = {"prepare_component_3d_preview": mod_ops.prepare_component_3d_preview,
                   "cancel_component_3d_preview": mod_ops.cancel_component_3d_preview}
        method = methods.get(self.path.removeprefix("/__api/"))
        length = int(self.headers.get("Content-Length", "0"))
        if not method or not 0 < length < 32768:
            self.send_error(400)
            return
        args = json.loads(self.rfile.read(length))
        start = time.perf_counter()
        if args and args[0] == "baseline" and self.baseline_root and "prepare_component" in self.path:
            glb = next(iter(sorted(self.baseline_root.rglob("*.glb"))), None)
            result = mod_ops._native3d_build_result(str(self.baseline_root), "Antes da otimização",
                {"selected":"baseline", "models":[{"key":"baseline", "name":glb.stem}], "meshes":[str(glb)]})
        else:
            result = method(*args)
        if "models" in result:
            print(json.dumps({"seconds":round(time.perf_counter()-start, 3),
                              "cached":result.get("cached"), "timings":result.get("timings")}), flush=True)
        body = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--baseline-root", type=pathlib.Path)
    arguments = parser.parse_args()
    Handler.baseline_root = arguments.baseline_root
    cache = tempfile.mkdtemp(prefix="qa-", dir=mod_ops._NATIVE3D_CACHE_ROOT)
    print(f"Cache isolado: {cache}", flush=True)
    with patch.object(mod_ops, "_NATIVE3D_CACHE_ROOT", cache), \
            patch.object(mod_ops, "_record_activity"), \
            patch.object(mod_ops.storage, "save_mods"):
        ThreadingHTTPServer(("127.0.0.1", arguments.port), Handler).serve_forever()

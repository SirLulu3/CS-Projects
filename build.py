"""Embed the readable compiler source into the standalone HTML interface."""
from pathlib import Path
import base64
import json
import html
root = Path(__file__).parent
compiler = (root / 'compiler.py').read_text()
assert '</script' not in compiler.lower()
template = (root / 'index.template.html').read_text()
template = template.replace('<!-- RUNTIME_LICENSE -->', html.escape((root / 'vendor' / 'pyodide' / 'LICENSE').read_text()))
template = template.replace('/* EDITOR_HELPERS */', (root / 'editor.js').read_text())
template = template.replace('/* RUNTIME_LOADER */', (root / 'runtime-loader.js').read_text())
loader = (root / 'vendor' / 'pyodide' / 'pyodide.js').read_text()
module = (root / 'vendor' / 'pyodide' / 'pyodide.asm.mjs').read_text()
assert '</script' not in loader.lower() and '</script' not in module.lower()
inline = '<script>' + loader + '\n globalThis.oneRuntimeModule = new Promise(resolve => { globalThis.oneRuntimeModuleResolve = resolve; });</script>'
inline += '<script type="module">' + module + '\n globalThis.oneRuntimeModuleResolve(_createPyodideModule);</script>'
template = template.replace('<!-- INLINE_RUNTIME -->', inline)
assets = {name: base64.b64encode((root / 'vendor' / 'pyodide' / name).read_bytes()).decode('ascii') for name in ('pyodide.js', 'pyodide.asm.mjs', 'pyodide.asm.wasm', 'python_stdlib.zip', 'pyodide-lock.json')}
template = template.replace('<!-- RUNTIME_ASSETS -->', '<script id="runtime-assets" type="application/json">' + json.dumps(assets) + '</script>')
(root / 'index.html').write_text(template.replace('<!-- COMPILER_SOURCE -->', '<script id="compiler-source" type="text/plain">\n' + compiler + '</script>'))

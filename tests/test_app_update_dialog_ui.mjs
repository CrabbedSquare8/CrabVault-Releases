import assert from 'node:assert/strict';
import fs from 'node:fs';

const source = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const css = fs.readFileSync(new URL('../frontend/style.css', import.meta.url), 'utf8');
const start = source.indexOf('function openAppUpdateDialog(');
const end = source.indexOf('document.getElementById("setting-check-app-update")', start);

assert.ok(start >= 0 && end > start, 'the integrated update dialog must exist');
const dialog = source.slice(start, end);
assert.match(dialog, /role="alertdialog"/);
assert.match(dialog, /CrabVault.*latest_version/);
assert.match(dialog, /SHA-256/);
assert.match(dialog, /Configurações, mods e mídias permanecerão no lugar/);
assert.match(dialog, /Settings, mods, and media will remain in place/);
assert.match(dialog, /Baixar e atualizar/);
assert.match(dialog, /Download and update/);
assert.match(dialog, /event\.key === "Escape"/);
assert.doesNotMatch(source.slice(end, source.indexOf('async function refreshNative3dSupportStatus', end)), /confirm\(question\)/);
assert.match(css, /\.app-update-dialog/);
assert.match(css, /var\(--bg-panel\)/);

console.log('App update dialog UI: themed bilingual confirmation and native-confirm removal passed.');

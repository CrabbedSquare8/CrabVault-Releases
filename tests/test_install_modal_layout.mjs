import assert from "node:assert/strict";
import fs from "node:fs";

const html = fs.readFileSync(new URL("../frontend/index.html", import.meta.url), "utf8");
const css = fs.readFileSync(new URL("../frontend/style.css", import.meta.url), "utf8");

assert.match(
  html,
  /<label class="modal-check" id="install-cover-toggle">/,
  "the obsolete cover checkbox label must be targetable as a whole",
);
assert.match(html, /class="install-control-row install-tags-row"/, "tags must have a dedicated labeled row");
assert.match(html, /class="install-control-row install-image-row"/, "media must have a dedicated labeled row");
assert.match(html, /for="install-image-plus">Adicionar imagem<\/label>/, "the media row must have a clear label");
assert.match(css, /grid-template-columns:112px minmax\(0,1fr\)/, "wide dialogs must align labels beside controls");
assert.match(css, /#install-tag-plus \{ order:-1; flex:0 0 32px; \}/, "the tag add button must align at the start like the media button");
assert.match(css, /@media \(max-width:620px\)[\s\S]*?grid-template-columns:1fr/, "narrow dialogs must stack labels safely");
assert.match(
  css,
  /#add-mod-overlay #install-cover-toggle[^\{]*\{ display:none !important; \}/,
  "the whole obsolete cover control must be hidden, not only its checkbox",
);
assert.match(
  css,
  /#add-mod-overlay \.modal-body \{[\s\S]*?height:auto;[\s\S]*?max-height:none;[\s\S]*?overflow:visible;/,
  "the regular install modal must size itself to its content",
);
assert.match(
  css,
  /@media \(max-height:560px\)[\s\S]*?#add-mod-overlay \.modal-body \{[\s\S]*?overflow-y:auto;/,
  "very short windows must retain a safe scrolling fallback",
);

console.log("install modal layout tests passed");

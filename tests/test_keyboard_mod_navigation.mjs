import assert from "node:assert/strict";
import fs from "node:fs";

const source = fs.readFileSync(new URL("../frontend/app.js", import.meta.url), "utf8");
const start = source.indexOf("let modNavigationFrame = 0;");
const end = source.indexOf('if (event.key === "Enter")', start);
assert.ok(start >= 0 && end > start, "keyboard navigation block must exist");

const navigation = source.slice(start, end);
const focusStart = navigation.indexOf("const focusMod = (index) => {");
assert.ok(focusStart >= 0, "focusMod must exist");
const focusBlock = navigation.slice(focusStart);

assert.doesNotMatch(focusBlock, /renderMods\s*\(/, "a key press must not rebuild every card");
assert.match(navigation, /requestAnimationFrame\s*\(/, "visual focus updates must be coalesced per frame");
assert.match(navigation, /behavior:\s*"auto"/, "keyboard scrolling must not queue smooth animations");
for (const key of ["w", "a", "s", "d"]) {
  assert.match(navigation, new RegExp(`"${key}"`), `WASD mapping must include ${key.toUpperCase()}`);
}
assert.match(navigation, /!event\.ctrlKey && !event\.altKey && !event\.metaKey/,
  "WASD must not override modified shortcuts");

console.log("Keyboard mod navigation: coalesced focus, immediate scrolling and WASD passed.");

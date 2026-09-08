import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source = fs.readFileSync(new URL('../frontend/app.js', import.meta.url), 'utf8');
const thumbnailCode = source.slice(source.indexOf('async function refreshModInState('), source.indexOf('// Titlebar'));
const renderCode = source.slice(source.indexOf('function renderMods()'), source.indexOf('function renderHeaderCount()'));
const reloadStart = source.indexOf('async function reloadAll()');
const reloadCode = source.slice(reloadStart, source.indexOf('// Init', reloadStart));
const settle = async () => { for (let step = 0; step < 12; step++) await Promise.resolve(); };

function mod(id, key = `revision-${id}`, imageUrl = null) {
  return {id, thumbnail_key: key, image_url: imageUrl, image: 'cover.png', images: ['cover.png'],
    tags: [], name: id, character: 'Hela', size_mb: 1, enabled: true};
}

function classList() {
  const classes = new Set();
  return {contains: value => classes.has(value), add: value => classes.add(value),
    remove: value => classes.delete(value), toggle: (value, enabled) => enabled ? classes.add(value) : classes.delete(value)};
}

function setup(mods, {observer = true} = {}) {
  const requests = [], frames = [], observers = [], detailCalls = [], listeners = new Map();
  const overlay = {classList: classList()};
  const scroll = {children: [], classList: classList(), listeners: new Map(),
    getBoundingClientRect: () => ({top: 0, bottom: 600}),
    addEventListener(name, callback) { this.listeners.set(name, callback); },
    removeEventListener(name, callback) { if (this.listeners.get(name) === callback) this.listeners.delete(name); },
    appendChild(card) { card.isConnected = true; this.children.push(card); },
    set innerHTML(value) { this.children.forEach(card => { card.isConnected = false; }); this.children = []; },
  };
  const makeCard = () => {
    const cover = {classList: classList(), style: {}, textContent: 'placeholder'};
    const children = new Map([['.mod-cover', cover]]);
    return {dataset: {}, isConnected: false, cover, top: scroll.children.length * 350,
      addEventListener() {},
      getBoundingClientRect() { return {top: this.top, bottom: this.top + 300}; },
      querySelector(selector) {
        if (!children.has(selector)) children.set(selector, {addEventListener() {}});
        return children.get(selector);
      },
      querySelectorAll(selector) { return selector === '.count-btn' ? [{}, {}] : []; },
    };
  };
  class Observer {
    constructor(callback, options) { this.callback = callback; this.options = options; this.targets = new Set(); observers.push(this); }
    observe(card) { this.targets.add(card); }
    unobserve(card) { this.targets.delete(card); }
    disconnect() { this.disconnected = true; this.targets.clear(); }
    emit(cards, visible = true) { this.callback(cards.map(target => ({target, isIntersecting: visible}))); }
  }
  const state = {mods, settings: {}, view: 'grid', conflictsByMod: new Map(), selectedModIds: new Set(),
    thumbnailPending: new Set(), thumbnailQueue: [], thumbnailWorkers: 0};
  const backend = {
    get_mod_thumbnail: modId => new Promise((resolve, reject) => requests.push({modId, resolve, reject})),
    get_mod_details: async (...args) => { detailCalls.push(args); return mod(args[0]); },
    get_library_snapshot: async () => ({mods: state.mods.map(item => mod(item.id, item.thumbnail_key)), characters: [], types: [], tags: [], folders: []}),
  };
  const context = vm.createContext({state, THUMBNAIL_WORKER_LIMIT: 3, api: () => backend, setTimeout,
    requestAnimationFrame: callback => frames.push(callback),
    window: {addEventListener: (event, callback) => listeners.set(event, callback),
      removeEventListener: (event, callback) => { if (listeners.get(event) === callback) listeners.delete(event); }},
    document: {getElementById: id => id === 'mods-scroll' ? scroll : id === 'mod-detail-overlay' ? overlay : null,
      createElement: makeCard},
    ...(observer ? {IntersectionObserver: Observer} : {}),
    filteredMods: () => state.mods, escapeHtml: value => String(value), displayModName: value => value,
    modTypes: () => ['Mesh'], modTypeClass: () => 'mesh', formatModSize: () => '1 MB', renderBulkActions() {},
    renderCharacters() {}, renderTypes() {}, renderTags() {}, renderFolders() {}, renderHeaderCount() {},
    scheduleConflictRefresh() {}, loadCharacterSkins: async () => {}, safeRender: fn => fn(),
  });
  vm.runInContext(thumbnailCode + '\n' + renderCode + '\n' + reloadCode, context);
  return {context, state, backend, requests, observers, scroll, overlay, frames, detailCalls,
    async resolve(index, key = state.mods.find(item => item.id === requests[index].modId)?.thumbnail_key, image = `data:cover-${index}`) {
      requests[index].resolve({ok: true, thumbnail_key: key, image_url: image}); await settle();
    },
    flushFrames() { while (frames.length) frames.shift()(); },
  };
}

let scenarios = 0;
{
  const t = setup([]);
  const previous = mod('a', 'same', 'data:saved');
  const fresh = mod('a', 'same');
  assert.equal(t.context.preserveModThumbnail(fresh, previous), fresh);
  assert.equal(fresh.image_url, 'data:saved');
  for (const incoming of [mod('a', 'changed'), mod('other', 'same'), mod('a', ''), mod('a', null)]) {
    assert.equal(t.context.preserveModThumbnail(incoming, previous).image_url, null, 'different/absent revisions must invalidate cached covers');
  }
  const explicit = mod('a', 'same', 'data:fresh-from-backend');
  assert.equal(t.context.preserveModThumbnail(explicit, previous).image_url, 'data:fresh-from-backend');
  scenarios++;
}
{
  const t = setup([mod('a', 'revision-a', 'data:saved')]);
  const refreshed = await t.context.refreshModInState('a');
  assert.deepEqual(t.detailCalls, [['a', false]], 'refresh must not request a gallery or thumbnail conversion');
  assert.equal(refreshed.image_url, 'data:saved');
  t.backend.get_mod_details = async () => mod('a', 'new-revision');
  assert.equal((await t.context.refreshModInState('a')).image_url, null);
  scenarios++;
}
{
  const t = setup([mod('a', 'same', 'data:saved'), mod('b', 'before', 'data:outdated')]);
  t.backend.get_library_snapshot = async () => ({mods: [mod('a', 'same'), mod('b', 'after')], characters: [], types: [], tags: [], folders: []});
  await t.context.reloadAll();
  assert.equal(t.state.mods[0].image_url, 'data:saved');
  assert.equal(t.state.mods[1].image_url, null);
  assert.equal(t.requests.length, 0, 'reload does not enqueue the full library before viewport observation');
  assert.equal(t.observers.at(-1).targets.size, 1, 'cached covers are not observed again');
  scenarios++;
}
{
  const t = setup(Array.from({length: 294}, (_, index) => mod(`m${index}`)));
  t.context.renderMods();
  assert.equal(t.scroll.children.length, 18, 'large libraries render only the first visible rows synchronously');
  assert.ok(t.frames.length, 'remaining cards are deferred so filters and search stay responsive');
  t.flushFrames();
  assert.equal(t.scroll.children.length, 294);
  const warmedCards = [...t.scroll.children];
  t.context.renderMods();
  t.flushFrames();
  assert.equal(t.scroll.children[0], warmedCards[0], 'warmed cards are reused instead of reconstructed');
  assert.equal(t.requests.length, 0, 'creating cards does not start 294 backend requests');
  const observer = t.observers.at(-1);
  assert.equal(observer.options.root, t.scroll);
  assert.equal(observer.options.rootMargin, '400px 0px');
  observer.emit(t.scroll.children.slice(0, 4));
  assert.equal(t.requests.length, 3);
  assert.equal(t.state.thumbnailQueue.length, 1);
  await t.resolve(0);
  assert.equal(t.requests.length, 4, 'only the fourth nearby card fills the next available worker');
  assert.deepEqual(t.requests.map(item => item.modId), ['m0', 'm1', 'm2', 'm3']);
  await Promise.all([t.resolve(1), t.resolve(2), t.resolve(3)]);
  assert.equal(t.state.thumbnailWorkers, 0);
  assert.equal(t.state.thumbnailPending.size, 0);
  scenarios++;
}
{
  const t = setup([mod('a'), mod('b'), mod('c'), mod('d')]);
  t.context.renderMods();
  const observer = t.observers.at(-1);
  observer.emit(t.scroll.children);
  observer.emit([t.scroll.children[3]], false);
  await Promise.all([t.resolve(0), t.resolve(1), t.resolve(2)]);
  assert.equal(t.requests.length, 3, 'a queued card scrolled away is skipped before dispatch');
  assert.equal(t.state.thumbnailQueue.length, 0);
  assert.equal(t.state.thumbnailPending.size, 0);
  scenarios++;
}
{
  const t = setup([mod('a')]);
  t.context.renderMods();
  const oldObserver = t.observers.at(-1);
  const oldCard = t.scroll.children[0];
  oldObserver.emit([oldCard]);
  t.context.renderMods();
  const newCard = t.scroll.children[0];
  t.observers.at(-1).emit([newCard]);
  oldObserver.emit([oldCard]);
  assert.equal(t.requests.length, 1, 'rerender keeps matching in-flight work without reopening a request');
  assert.equal(oldObserver.disconnected, true);
  await t.resolve(0, 'revision-a', 'data:ready');
  assert.equal(t.state.mods[0].image_url, 'data:ready');
  assert.equal(newCard, oldCard, 'unchanged rerender reuses the warmed card');
  assert.equal(newCard.cover.style.backgroundImage, "url('data:ready')");
  scenarios++;
}
{
  const t = setup([mod('a', 'old')]);
  t.context.renderMods();
  t.observers.at(-1).emit(t.scroll.children);
  t.state.mods = [mod('a', 'new')];
  t.context.renderMods();
  t.observers.at(-1).emit(t.scroll.children);
  assert.equal(t.requests.length, 2, 'a new revision is not blocked by the obsolete worker for the same mod');
  await t.resolve(0, 'old', 'data:outdated');
  assert.equal(t.state.mods[0].image_url, null);
  assert.equal(t.state.thumbnailPending.size, 1, 'finishing the old revision must not release the new request');
  await t.resolve(1, 'new', 'data:current');
  assert.equal(t.state.mods[0].image_url, 'data:current');
  assert.equal(t.state.thumbnailPending.size, 0);
  scenarios++;
}
{
  const t = setup([mod('a', 'expected')]);
  t.context.renderMods();
  t.observers.at(-1).emit(t.scroll.children);
  await t.resolve(0, 'changed-during-backend-read');
  assert.equal(t.state.mods[0].image_url, null, 'the response revision must match both request and current state');
  assert.equal(t.state.thumbnailWorkers, 0);
  scenarios++;
}
{
  const t = setup([mod('a'), mod('b'), mod('c'), mod('d'), mod('e')]);
  t.context.renderMods();
  t.observers.at(-1).emit(t.scroll.children);
  t.overlay.classList.add('open');
  t.context.renderMods();
  const observer = t.observers.at(-1);
  observer.emit([t.scroll.children[4]]);
  assert.equal(t.state.thumbnailQueue.length, 1, 'rerender discards old queued cards but preserves active workers');
  await Promise.all([t.resolve(0), t.resolve(1), t.resolve(2)]);
  assert.equal(t.requests.length, 3, 'finishing workers does not dispatch cover conversions behind the detail overlay');
  t.overlay.classList.remove('open');
  t.context.drainThumbnailQueue();
  assert.equal(t.requests.length, 4);
  assert.equal(t.requests[3].modId, 'e', 'the discarded card d never dispatches');
  await t.resolve(3);
  scenarios++;
}
{
  const t = setup([mod('a'), mod('b')], {observer: false});
  t.context.renderMods();
  const [first, second] = t.scroll.children;
  second.top = 5000;
  t.flushFrames();
  assert.deepEqual(t.requests.map(item => item.modId), ['a']);
  await t.resolve(0);
  first.top = -2000;
  second.top = 100;
  t.scroll.listeners.get('scroll')();
  t.flushFrames();
  assert.deepEqual(t.requests.map(item => item.modId), ['a', 'b'], 'fallback observes scroll bounds instead of loading all cards');
  await t.resolve(1);
  scenarios++;
}
{
  const t = setup([mod('a')]);
  t.context.renderMods();
  t.observers.at(-1).emit(t.scroll.children);
  t.requests[0].reject(new Error('thumbnail unavailable'));
  await settle();
  assert.equal(t.state.thumbnailWorkers, 0);
  assert.equal(t.state.thumbnailPending.size, 0);
  assert.equal(t.state.mods[0].image_url, null);
  scenarios++;
}
console.log(`Thumbnail queue UI: ${scenarios} scenarios passed.`);

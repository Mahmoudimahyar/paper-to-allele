// Run the review page's script against a minimal DOM and report what happened.
//
// This exists because the page shipped completely blank: `let labels = load()`
// ran before `let storageWorks` was initialised, so a temporal-dead-zone
// ReferenceError killed the script before a single row was rendered. Nothing in
// the Python test suite could see that — the tests read the HTML as text — and
// the failure was invisible until someone opened it.
//
// Usage: node review_page_smoke.mjs <index.html> <pack.js>
// Prints one JSON object; exit code 1 if the page failed to come up.

import { readFileSync } from 'node:fs';

const [htmlPath, packPath, annotator] = process.argv.slice(2);
const html = readFileSync(htmlPath, 'utf8');
const packJs = readFileSync(packPath, 'utf8');

// --- the smallest DOM this page's startup path actually touches ------------
let idSeq = 0;
class El {
  constructor(tag = 'div') {
    this.tagName = tag.toUpperCase();
    this.children = [];
    this.parent = null;
    this.attrs = {};
    this.style = {};
    this.dataset = {};
    this._text = '';
    this._html = '';
    this.classList = new Set();
    this.listeners = {};
    this.value = '';
    this.checked = false;
    this.disabled = false;
    this.options = [];
    this.files = [];
    this._id = ++idSeq;
  }
  get className() { return [...this.classList].join(' '); }
  set className(v) { this.classList = new Set(String(v).split(/\s+/).filter(Boolean)); }
  get textContent() { return this._text; }
  set textContent(v) { this._text = String(v); }
  get innerHTML() { return this._html; }
  set innerHTML(v) {
    this._html = String(v);
    // A <select> gets real option objects in a browser; the page writes its
    // option list as HTML and then addresses `options[i]`.
    const n = (this._html.match(/<option/g) || []).length;
    this.options = Array.from({ length: n }, () => new El('option'));
  }
  setAttribute(k, v) { this.attrs[k] = v; }
  getAttribute(k) { return this.attrs[k] ?? null; }
  hasAttribute(k) { return k in this.attrs; }
  removeAttribute(k) { delete this.attrs[k]; }
  appendChild(c) { c.parent = this; this.children.push(c); return c; }
  insertBefore(c) { return this.appendChild(c); }
  addEventListener(t, fn) { (this.listeners[t] = this.listeners[t] || []).push(fn); }
  removeEventListener() {}
  dispatchEvent() { return true; }
  querySelector() { return null; }
  querySelectorAll() { return []; }
  closest() { return null; }
  getBoundingClientRect() { return { width: 800, height: 600, top: 0, left: 0, right: 800, bottom: 600 }; }
  scrollTo() {}
  focus() {}
  select() {}
  click() {}
  get clientWidth() { return 800; }
  get clientHeight() { return 600; }
  get scrollHeight() { return 600; }
}

// Any id the page asks for gets an element. Naming them individually meant a
// renamed control returned null and the page crashed inside the harness rather
// than in the browser, which tells you nothing useful.
const byId = new Proxy({}, {
  get(target, id) {
    if (typeof id !== 'string') return undefined;
    if (!(id in target)) target[id] = new El(id === 'page' ? 'img' : 'div');
    return target[id];
  },
});

const store = new Map();
const documentStub = {
  getElementById: (id) => byId[id],
  querySelector: (sel) => new El('div'),
  querySelectorAll: () => [],
  createElement: (t) => new El(t),
  addEventListener: () => {},
  body: new El('body'),
  activeElement: null,
};
documentStub.body.insertBefore = () => {};

globalThis.window = {
  addEventListener: () => {},
  innerWidth: 1280,
  innerHeight: 820,
};
globalThis.document = documentStub;
globalThis.localStorage = {
  getItem: (k) => (store.has(k) ? store.get(k) : null),
  setItem: (k, v) => store.set(k, String(v)),
  removeItem: (k) => store.delete(k),
  clear: () => store.clear(),
};
globalThis.URL = { createObjectURL: () => 'blob:x', revokeObjectURL: () => {} };
globalThis.Blob = class { constructor(p) { this.parts = p; } };
globalThis.KeyboardEvent = class {};
globalThis.Event = class {};
globalThis.getComputedStyle = () => ({ display: 'block' });
globalThis.Image = class { set src(v) { this._src = v; } get src() { return this._src; } };
globalThis.requestAnimationFrame = (fn) => setTimeout(fn, 0);

// pack.js assigns window.PACK
eval(packJs.replace(/^window\./, 'globalThis.window.'));
globalThis.window.PACK = globalThis.window.PACK || globalThis.PACK;

// The page refuses to show any cell until an annotator is named, because
// labels are stored per annotator and two people must stay independent. Give it
// one unless the caller is deliberately testing the unnamed state.
byId.annotator.value = annotator === undefined ? 'smoke-tester' : annotator;

const script = html.split('<script>').pop().split('</script>')[0];

const result = { started: false, error: null, renderedHtmlLength: 0, wroteProgress: '' };
try {
  eval(script);
  result.started = true;
  result.renderedHtmlLength = byId.panel.innerHTML.length;
  result.wroteProgress = byId.progress.innerHTML || byId.progress.textContent;
} catch (e) {
  result.error = `${e.name}: ${e.message}`;
}

// The page came up if it rendered a document into the panel and said where it is.
result.panelText = String(byId.panel.innerHTML).replace(/<[^>]*>/g, ' ');
result.askedForName = /Type your name/.test(result.panelText);
result.ok = result.started
  && (result.askedForName || result.renderedHtmlLength > 500)
  && /\d+ \/ \d+ cells/.test(result.wroteProgress);
console.log(JSON.stringify(result));
process.exit(result.ok ? 0 : 1);

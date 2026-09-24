import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { createContext, runInContext } from 'node:vm';
import * as core from '../core.mjs';
import { EngineBindings } from '../bindings.mjs';

// Evaluate the actual runtime with DOM boundaries stubbed. No browser, server,
// engine package or GPU is started. Real promises still exercise unhandled
// rejection detection in node:test when legacy callers discard their result.
const source = (await readFile(new URL('../runtime.mjs', import.meta.url), 'utf8'))
  .replace(/^import .*;\n/gm, '');
const settle = () => new Promise(resolve => setImmediate(resolve));
const denial = () => Object.assign(new Error('The root document of this element is not valid for pointer lock.'), { name:'WrongDocumentError' });

function surface() {
  const listeners = new Map();
  return {
    addEventListener(type, fn) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(fn);
    },
    dispatch(type, event = {}) { for (const fn of listeners.get(type) ?? []) fn(event); }
  };
}
function runtime(request, method = 'requestPointerLock') {
  const messages = [], calls = [];
  const canvas = Object.assign(surface(), { focus() { calls.push('focus'); }, blur() {}, dispatchEvent() {} });
  if (request) canvas[method] = request;
  const document = Object.assign(surface(), {
    getElementById: () => canvas, pointerLockElement:null, exitPointerLock() {}, hasFocus:() => true
  });
  const window = Object.assign(surface(), { Module:{ pauseMainLoop() { calls.push('pause'); } } });
  const context = createContext({ ...core, EngineBindings, window, document, console, URL,
    parent:{ postMessage: message => messages.push(message), document },
    location:{ origin:'http://localhost' }, clearInterval() {},
    Promise, performance, KeyboardEvent:class {} });
  runInContext(source, context, { filename:'runtime.mjs' });
  return { canvas, document, window, messages, calls,
    evaluate: code => runInContext(code, context),
    reports: type => messages.filter(message => message.type === type)
  };
}

// The legacy JSEvents key handler runs deferred calls before/after the native
// callback. Its requestPointerLock helper discards the browser's return value.
function engineKeyRequest(r) {
  const deferred = [() => { r.canvas.requestPointerLock(); }];
  r.canvas.addEventListener('keydown', () => {
    while (deferred.length) deferred.shift()();
  });
  r.canvas.dispatch('keydown', { key:'`', code:'Backquote' });
}

test('engine deferred keyboard capture rejection is recoverable before and after runtime initialization', async () => {
  for (const initialized of [false, true]) {
    const r = runtime(() => Promise.reject(denial()));
    r.evaluate(`initialized = ${initialized}; runtimeInitialized = ${initialized}; inMenu = false;`);
    // Browser.init normalizes this property; it must retain the installed guard.
    r.canvas.requestPointerLock = r.canvas.requestPointerLock || r.canvas.mozRequestPointerLock;
    engineKeyRequest(r);
    await settle();
    assert.equal(r.reports('pointer-error').length, 1);
    assert.match(r.reports('pointer-error')[0].detail, /WrongDocumentError.*root document.*retry/);
    assert.equal(r.reports('error').length, 0);
    assert.equal(r.evaluate('failed || disposed'), false);
    assert.equal(r.calls.includes('pause'), false);
  }
});

test('guard preserves synchronous invocation, receiver, options, promise and successful retry', async () => {
  let count = 0, result;
  const options = { unadjustedMovement:true };
  const r = runtime(function(value) {
    assert.equal(this, r.canvas);
    assert.equal(value, options);
    result = ++count === 1 ? Promise.reject(denial()) : Promise.resolve();
    return result;
  });
  const first = r.canvas.requestPointerLock(options);
  assert.equal(count, 1);
  assert.equal(first, result);
  await settle(); // Deliberately no catch on first: the engine ignores it too.
  assert.equal(r.canvas.requestPointerLock(options), result);
  await settle();
  assert.equal(count, 2);
  assert.equal(r.reports('pointer-error').length, 1);
  assert.equal(r.reports('error').length, 0);
});

test('legacy prefixed, void-returning and synchronously throwing requests remain nonfatal', async () => {
  for (const method of ['requestPointerLock','mozRequestPointerLock','webkitRequestPointerLock','msRequestPointerLock']) {
    let count = 0;
    const r = runtime(() => { if (++count === 1) throw denial(); }, method);
    assert.doesNotThrow(() => engineKeyRequest(r));
    assert.equal(r.canvas.requestPointerLock(), undefined);
    await settle();
    assert.equal(count, 2);
    assert.equal(r.reports('pointer-error').length, 1);
    assert.equal(r.reports('error').length, 0);
  }
});

test('launcher capture still activates audio before requesting pointer lock, with one denial report', async () => {
  const order = [];
  const r = runtime(() => { order.push('pointer'); return Promise.reject(denial()); });
  r.window.Module.resumeBrowserAudio = () => { order.push('audio'); return Promise.resolve('running'); };
  r.evaluate('initialized = true;');
  r.window.captureUT4Pointer();
  assert.deepEqual(order, ['audio','pointer']);
  await settle();
  assert.equal(r.reports('pointer-error').length, 1);
  assert.equal(r.reports('error').length, 0);
});

test('unavailable pointer lock and pointerlockerror event remain recoverable', () => {
  const r = runtime();
  r.evaluate('initialized = true;');
  r.window.captureUT4Pointer();
  assert.match(r.reports('pointer-error')[0].detail, /unavailable/);
  r.document.dispatch('pointerlockerror');
  assert.equal(r.reports('pointer-error').length, 2);
  assert.equal(r.reports('error').length, 0);
});

test('launcher still handles a later support-script replacement of the request method', async () => {
  const r = runtime(() => Promise.resolve());
  r.evaluate('initialized = true;');
  r.canvas.requestPointerLock = () => Promise.reject(denial());
  r.window.captureUT4Pointer();
  await settle();
  assert.equal(r.reports('pointer-error').length, 1);
  assert.equal(r.reports('error').length, 0);
});

test('unrelated unhandled rejections still fail even with identical pointer-lock error text', () => {
  const r = runtime(() => Promise.resolve());
  r.window.dispatch('unhandledrejection', { reason:denial(), preventDefault() { assert.fail('must not suppress globally'); } });
  assert.equal(r.evaluate('failed'), true);
  assert.equal(r.reports('error').length, 1);
  assert.equal(r.calls.includes('pause'), true);
});

test('pending pointer rejection after disposal is handled without notifying the retired runtime', async () => {
  let reject;
  const r = runtime(() => new Promise((resolve, no) => { reject = no; }));
  engineKeyRequest(r);
  r.window.disposeUT4Runtime();
  const count = r.messages.length;
  reject(denial());
  await settle();
  assert.equal(r.messages.length, count);
  assert.equal(r.evaluate('disposed'), true);
});

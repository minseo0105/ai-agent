// Deterministic transport/privacy tests without a server or production services.
const fs = require('fs');
const vm = require('vm');
const assert = require('node:assert/strict');
const path = require('path');
const crypto = require('crypto');
const root = path.resolve(__dirname, '..');
const ts = require(root + '/web/node_modules/typescript');
const code = ts.transpileModule(fs.readFileSync(root + '/web/src/lib/analytics.ts', 'utf8'), {
  compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
}).outputText;

function environment(storage = new Map(), {storageFails = false, fetchFails = false} = {}) {
  const calls = [], timers = new Map(); let sequence = 0;
  const context = {exports: {}, process: {env: {}}, crypto, AbortController,
    window: {location: {pathname: '/realestate'}},
    sessionStorage: {getItem: k => {if (storageFails) throw Error(); return storage.get(k);},
      setItem: (k,v) => {if (storageFails) throw Error(); storage.set(k,v);}},
    setTimeout: (fn, ms) => {const id = ++sequence; timers.set(id, {fn, ms}); return id;},
    clearTimeout: id => timers.delete(id),
    fetch: async (url, options) => {calls.push({url, ...options, body: JSON.parse(options.body)}); if(fetchFails) throw Error(); return {status: 204};},
  };
  vm.runInNewContext(code, context);
  async function flush() {
    const pending = [...timers];
    timers.clear();
    for (const [, {fn}] of pending) fn();
    await new Promise(resolve => setImmediate(resolve));
  }
  return {...context.exports, calls, timers, flush, storage};
}

(async () => {
  const a = environment();
  a.recordPageView('/realestate'); a.recordPageView('/realestate'); a.recordPageView('/realestate');
  assert.equal(a.calls.length, 0, 'no fetch during render/effect');
  await a.flush();
  assert.equal(a.calls.length, 1); assert.equal(a.calls[0].body.events.length, 1);
  a.recordPageView('/golf'); a.recordPageView('/realestate'); await a.flush();
  assert.equal(a.calls[1].body.events.length, 2);
  const sid = a.calls[0].body.events[0].session_id;
  assert(a.calls.flatMap(c => c.body.events).every(e => e.session_id === sid));
  const reload = environment(a.storage); reload.recordPageView('/realestate'); await reload.flush();
  assert.equal(reload.calls[0].body.events[0].session_id, sid);
  const newTab = environment(); newTab.recordPageView('/'); await newTab.flush();
  assert.notEqual(newTab.calls[0].body.events[0].session_id, sid);
  for (const opts of [{storageFails: true}, {fetchFails: true}]) {
    const b = environment(new Map(), opts); b.recordPageView('/'); await b.flush();
    b.trackUsage('search', 'golf_search', '/golf'); await b.flush();
    assert.equal(b.calls.length, 2);
    assert.equal(b.calls[0].body.events[0].session_id, b.calls[1].body.events[0].session_id);
    assert.equal(b.timers.size, 0, 'failed telemetry is not retried');
  }
  a.trackUsage('page_view', undefined, '/golf/club?id=private@example.com');
  a.trackUsage('page_view', undefined, '/private@example.com');
  a.trackUsage('page_view', undefined, '/admin'); await a.flush();
  const latest = a.calls.at(-1);
  assert.equal(latest.body.events.length, 2);
  assert.equal(latest.body.events[0].route, '/golf/club');
  assert.equal(latest.body.events[1].route, '/other');
  assert(!JSON.stringify(latest.body).includes('private'));
  assert.equal(latest.credentials, 'omit'); assert.equal(latest.referrerPolicy, 'no-referrer');
  assert(!Object.keys(latest.headers).some(k => /authorization|cookie|apikey/i.test(k)));
  const flood = environment();
  for (let i=0;i<10000;i++) flood.trackUsage('map_click');
  for (let i=0;i<5;i++) await flood.flush();
  assert.equal(flood.calls.flatMap(c=>c.body.events).length,64);
  assert(flood.calls.every(c=>c.body.events.length<=20));
  console.log('PASS analytics: dedup/remount replay, route returns, sessions/reload/storage denial, privacy, delayed bounded batches, failed transport');
})().catch(e => {console.error(e); process.exitCode=1;});

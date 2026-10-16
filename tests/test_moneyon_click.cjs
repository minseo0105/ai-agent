// MONEY:ON home-card click telemetry: one click -> one external_link_click event; failures never throw.
const fs = require('fs'), vm = require('vm'), assert = require('node:assert/strict'), crypto = require('crypto'), path = require('path');
const root = path.resolve(__dirname, '..');
const ts = require(root + '/web/node_modules/typescript');
const code = ts.transpileModule(fs.readFileSync(root + '/web/src/lib/analytics.ts', 'utf8'),
  {compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022}}).outputText;

async function click({storageFails = false, fetchFails = false, clicks = 1} = {}) {
  const calls = [], timers = new Map(); let n = 0;
  const context = {exports: {}, process: {env: {}}, crypto, AbortController, window: {location: {pathname: '/'}},
    sessionStorage: {getItem() { if (storageFails) throw Error(); }, setItem() { if (storageFails) throw Error(); }},
    setTimeout: (f) => { timers.set(++n, f); return n; }, clearTimeout: (i) => timers.delete(i),
    fetch: async (u, o) => { calls.push(JSON.parse(o.body)); if (fetchFails) throw Error(); return {status: 204}; }};
  vm.runInNewContext(code, context);
  for (let i = 0; i < clicks; i++) context.exports.trackMoneyCardClick();
  for (const [, f] of [...timers]) f();
  await new Promise((r) => setImmediate(r));
  return calls;
}

(async () => {
  const calls = await click();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].events.length, 1);
  const e = calls[0].events[0];
  assert.deepEqual([e.service, e.route, e.event_type, e.metadata], ['moneyon', '/moneyon', 'external_link_click', {action: 'moneyon_card_click'}]);
  assert.deepEqual(Object.keys(e).sort(), ['event_type', 'metadata', 'route', 'service', 'session_id']);
  assert.equal((await click({clicks: 3}))[0].events.length, 3);
  await click({fetchFails: true}); await click({storageFails: true});
  console.log('PASS moneyon click: one event per click, no extra fields, transport/storage failures are silent');
})();

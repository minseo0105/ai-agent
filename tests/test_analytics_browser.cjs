// Run after STATIC_EXPORT=1 builds. No external requests; mock service responses only.
// npm install --prefix reports/analytics-browser playwright (test tooling only)
const {chromium} = require('../reports/analytics-browser/node_modules/playwright');
const fs = require('fs');
const path = require('path');
const http = require('http');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const ts = require('../web/node_modules/typescript');
const access = {site_mode:'public',site_allowed:true,notice:null,me:null,services:{}};
const estate = {regions:{서울:['송파구','강동구'],경기:[]},property_types:['아파트'],supply_types:[],kinds:[],statuses:[],event_types:[],api_key:true,storage:'supabase'};
const golf = {areas:[],subregions:{},budgets:[],avg_scores:[],counts:{all:1,searchable:1,pool:1,by_area:{}},data_coverage:{night:0,three_person:0,caddie:0,green_fee:0},runtime_ok:true,naver_enabled:false};
const project = {project_id:'fixture-project',name:'Analytics Test Project',type_label:'재개발',
  stage:{label:'정비계획'},stage_timeline:{steps:['정비계획'],current_index:0},
  location_accuracy:{code:'NO_LOCATION',label:'위치 확인 중'},trust:{label:'공식자료 확인',tone:'info'},
  official_source:{name:'fixture',url:'https://example.invalid/official'},
  naver_real_estate:{url:'https://example.invalid/naver',label:'네이버 부동산',note:'fixture',search_query:'fixture'}};
const development = {status:'ok',projects:[project],points:[],hidden_completed:0,truncated:false};
const fixtures = {'/api/access/status':access,'/api/realestate/options':estate,
  '/api/realestate/notifications':{items:[],unread:0}, '/api/realestate/map/config':{sdk:null},
  '/api/realestate/development/map':development, '/api/golf/options':golf};

function server(folder) {
  return http.createServer((req,res)=>{
    const name=decodeURIComponent(new URL(req.url,'http://local').pathname);
    let file=path.resolve(folder, '.' + name);
    if(!file.startsWith(folder+path.sep) && file!==folder) {res.writeHead(403);return res.end();}
    if(name==='/') file=path.join(folder,'index.html');
    else if(!path.extname(file)) file+='.html';
    if(!fs.existsSync(file)){res.writeHead(404);return res.end();}
    const types={'.js':'application/javascript','.html':'text/html','.css':'text/css','.json':'application/json'};
    res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');
    res.end(fs.readFileSync(file));
  });
}
async function listen(s) {await new Promise(r=>s.listen(0,'127.0.0.1',r));return `http://127.0.0.1:${s.address().port}`;}
async function sample(browser, folder, analyticsExpected) {
  const s=server(folder), base=await listen(s), context=await browser.newContext();
  const calls=[], events=[], errors=[];
  let analyticsFailure=false;
  await context.route('**/*', async route=>{
    const req=route.request(), url=new URL(req.url());
    if(url.pathname.startsWith('/api/')) {
      calls.push(url.pathname);
      if(url.pathname==='/api/analytics/events') {
        events.push(...req.postDataJSON().events);
        assert(!req.headers()['authorization']); assert(!req.headers()['cookie']); assert(!req.headers()['referer']);
        return route.fulfill({status:analyticsFailure?503:204,body:''});
      }
      if(fixtures[url.pathname]) return route.fulfill({json:fixtures[url.pathname]});
      if(url.pathname.startsWith('/api/golf/search')) return route.fulfill({json:{applied:[],trace:{},sort:'추천순',notice:null,top_ids:[],items:[],has_departure:false}});
      return route.fulfill({status:404,json:{detail:'Mock unavailable'}});
    }
    if(url.origin!==base) return route.abort();
    return route.continue();
  });
  const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
  await page.goto(base+'/realestate');
  await page.getByRole('heading',{name:'부동산 개발정보 지도',exact:true}).waitFor();
  await page.waitForTimeout(3800);
  const initial=calls.slice();
  assert.equal(events.filter(e=>e.event_type==='page_view').length,analyticsExpected?1:0);
  const input=page.getByRole('textbox',{name:'사업명 · 동 · 유형 검색'});
  await input.fill('private@example.com secret-address'); await input.blur();
  await page.waitForTimeout(2000);
  assert.equal(events.filter(e=>e.event_type==='page_view').length,analyticsExpected?1:0,'rerender does not count a visit');
  assert(!JSON.stringify(events).includes('private'));
  await input.fill(''); await input.blur();
  await page.getByText('Analytics Test Project',{exact:true}).first().click();
  await page.getByRole('link',{name:/네이버 부동산/}).click();
  await page.waitForTimeout(2000);
  if(analyticsExpected) {
    assert.equal(events.filter(e=>e.event_type==='project_click').length,1,'nested external link is not a second card click');
    assert.equal(events.filter(e=>e.metadata.action==='naver_land_click').length,1);
    assert(!JSON.stringify(events).includes('fixture-project'));
    assert(!JSON.stringify(events).includes('example.invalid'));
  }
  await page.getByRole('radio',{name:'실거래',exact:true}).click();
  await page.getByRole('radio',{name:'개발지도',exact:true}).click();
  await page.waitForTimeout(1000);
  const remount=calls.filter(p=>p==='/api/realestate/development/map').length;
  assert.equal(remount,2,'existing tab remount makes a second development call');
  assert.equal(events.filter(e=>e.event_type==='page_view').length,analyticsExpected?1:0);
  analyticsFailure=true;
  await page.goto(base+'/golf');
  await page.getByText('어디서 치시나요',{exact:true}).waitFor();
  await page.locator('form').first().evaluate(form=>form.requestSubmit());
  await page.waitForTimeout(3800);
  assert(calls.some(p=>p.startsWith('/api/golf/search')),'golf search still runs when analytics fails');
  assert.equal(errors.length,0,errors.join('\n'));
  if(analyticsExpected) {
    assert(events.some(e=>e.metadata.action==='address_search'));
    assert(events.some(e=>e.metadata.action==='golf_search'));
  }
  await context.close(); await new Promise(r=>s.close(r));
  return {core:initial.filter(p=>p!=='/api/analytics/events'), analytics:initial.filter(p=>p==='/api/analytics/events').length,developmentCallsAfterTabReturn:remount};
}

async function strictMode(browser) {
  // Actual React development effects/hydration/remounts, not just calling a mock hook.
  const context=await browser.newContext(), page=await context.newPage();
  const out=path.join(root,'web/out'), s=server(out),base=await listen(s);
  await page.route('**/*', route => route.fulfill({contentType:'text/html',body:'<!doctype html><html><body></body></html>'}));
  await page.goto(base+'/');
  const bundle=ts.transpileModule(fs.readFileSync(path.join(root,'web/src/lib/analytics.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  // React's browser-compatible CJS development builds are evaluated with explicit dependencies.
  const react=fs.readFileSync(require.resolve('../web/node_modules/react/cjs/react.development.js'),'utf8');
  const dom=fs.readFileSync(path.join(root,'web/node_modules/react-dom/cjs/react-dom.development.js'),'utf8');
  const scheduler=fs.readFileSync(path.join(root,'web/node_modules/scheduler/cjs/scheduler.development.js'),'utf8');
  const client=fs.readFileSync(path.join(root,'web/node_modules/react-dom/cjs/react-dom-client.development.js'),'utf8');
  const result=await page.evaluate(async ({bundle,react,dom,scheduler,client})=>{
    const modules={};
    function load(code){const module={exports:{}};new Function('module','exports','require','process',code)(module,module.exports,n=>modules[n],{env:{NODE_ENV:'development'}});return module.exports;}
    modules.react=load(react);modules['react-dom']=load(dom);modules.scheduler=load(scheduler);
    const React=modules.react, renderer=load(client), analytics=load(bundle);
    const sent=[];window.fetch=async (url,options)=>{sent.push(...JSON.parse(options.body).events);return new Response(null,{status:204});};
    const node=document.createElement('div');document.body.replaceChildren(node);node.innerHTML='<span>route</span>';
    let runs=0;
    function Tracker({route}) {React.useEffect(()=>{runs++;analytics.recordPageView(route);},[route]);return React.createElement('span',null,'route');}
    const view=(route,key)=>React.createElement(React.StrictMode,null,React.createElement(Tracker,{route,key}));
    const app=renderer.hydrateRoot(node,view('/realestate','a'));
    const wait=()=>new Promise(r=>setTimeout(r,100));
    await wait();app.render(view('/realestate','a'));await wait();app.render(view('/realestate','b'));await wait();
    app.render(view('/golf','b'));await wait();app.render(view('/realestate','b'));await wait();
    await new Promise(r=>setTimeout(r,3800));app.unmount();
    return {runs,routes:sent.map(e=>e.route)};
  },{bundle,react,dom,scheduler,client});
  assert(result.runs>3,'StrictMode/remount effects replayed');
  assert.deepEqual(result.routes,['/realestate','/golf','/realestate']);
  await context.close();await new Promise(r=>s.close(r));return result;
}

(async()=>{
  const browser=await chromium.launch({channel:'chrome',headless:true});
  try {
    const before=await sample(browser,path.join(root,'reports/analytics-baseline/web/out'),false);
    const after=await sample(browser,path.join(root,'web/out'),true);
    assert.deepEqual(after.core.sort(),before.core.sort());assert.equal(after.analytics,1);
    const strict=await strictMode(browser);
    console.log(JSON.stringify({before,after,strict},null,2));
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});

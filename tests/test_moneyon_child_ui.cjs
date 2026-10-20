// UI projection and branding checks. No DB, API, network, or browser required.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),web=path.join(root,'web');
const ts=require(path.join(web,'node_modules','typescript'));
const React=require(path.join(web,'node_modules','react'));
const {renderToStaticMarkup}=require(path.join(web,'node_modules','react-dom','server'));
function loader(brand){
  const cache=new Map();
  function load(file){
    if(file.endsWith('.css'))return {};
    if(!path.extname(file))file+=fs.existsSync(file+'.tsx')?'.tsx':'.ts';
    if(cache.has(file))return cache.get(file).exports;
    const module={exports:{}};cache.set(file,module);
    const code=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX}}).outputText;
    const requireFor=id=>id.startsWith('@/')?load(path.join(web,'src',id.slice(2))):id.startsWith('.')?load(path.join(path.dirname(file),id)):require(require.resolve(id,{paths:[web]}));
    vm.runInNewContext(code,{module,exports:module.exports,require:requireFor,process:{env:{NEXT_PUBLIC_MONEYON_COACH_NAME:brand}}},{filename:file});
    return module.exports;
  }
  return load;
}
const fixture={wallet:6000,vault:1000,next_payday:'2026-10-19',cycles:[{id:'cycle',eligible:6000,interest:600,ended:false,settled:0}],xp:30,stage:0,badges:[],quests:[],goals:[],report:{},transactions:[],banking:{accounts:[{id:'wallet',kind:'wallet',balance:6000},{id:'vault',kind:'vault',balance:1000}],transactions:[1,2,3,4].map((n)=>({account_id:'wallet',transaction_id:'tx-'+n,transfer_id:'transfer-'+n,transaction_type:'MANUAL_EXPENSE',merchant:'문구점',note:'공책',amount:-1000,balance_after:6000,occurred_at:'2026-10-15T10:00:00+09:00',category:'문구',legacy:0}))}};
let checks=0;
for(const brand of [undefined,'우리모니']){
  const load=loader(brand);const config=load(path.join(web,'src/lib/moneyonCoach.ts'));
  const name=brand||'이자니';assert.equal(config.COACH_BRAND.displayName,name);checks++;
  const Woorumi=load(path.join(web,'src/app/moneyon/Izani.tsx')).default;
  for(const mood of ['greeting','allowance','spending','goal','interest','help','celebration']){
    const html=renderToStaticMarkup(React.createElement(Woorumi,{mood}));assert(html.includes(`data-coach-state="${mood}"`));assert(html.includes(`alt="${name}`));assert(html.includes('<img'));assert(html.includes('/moneyon/characters/izani-bee.png'));assert(html.includes('single-bee'));checks++;
  }
  const facts=Object.freeze({eligible:6000,interest:1});
  const message=config.ruleBasedCoach.explain('interest',facts);
  assert(message.text.includes('6,000원'));assert(message.text.includes('1원'));assert(!message.text.includes('600원'));checks++;
  assert(!config.ruleBasedCoach.explain('interest').text.includes('원'));checks++;
  const Child=load(path.join(web,'src/app/moneyon/ChildExperience.tsx')).default;
  const child={id:'child',profile:{name:'재현',avatar:'🐰',theme:'animals',grade:3}};
  const html=renderToStaticMarkup(React.createElement(Child,{child,state:fixture,api:()=>{throw Error('Unexpected API call in display');},run:async()=>{},busy:false,error:'',demo:false,onLock:()=>{},onState:()=>{},onTransact:async()=>true,onDismissError:()=>{}}));
  assert(html.includes(name));if(brand)assert(!html.includes('우루미'));checks++;
  assert(html.includes('data-theme="animals"'));assert(html.includes('data-testid="child-balance">6,000원'));assert(html.includes('data-testid="child-reward">600원'));assert(html.includes('아직 안 들어왔어요'));checks++;
  const nav=html.match(/<nav[^>]*aria-label="어린이 주요 메뉴"[^>]*>([\s\S]*?)<\/nav>/)[1];
  assert.equal((nav.match(/<button/g)||[]).length,3);assert(nav.includes('>홈<'));assert(nav.includes('>통장<'));assert(nav.includes('>저축<'));checks++;
  const recent=html.match(/data-testid="recent-transactions">([\s\S]*?)<\/ul>/)[1];assert.equal((recent.match(/<li/g)||[]).length,3);checks++;
  assert(html.includes('우리금융 공식 캐릭터가 아니에요.'));checks++;
}
console.log(`PASS ${checks} child UI/coach checks: two brand configurations, single bee asset in seven contexts, ledger facts, capped rewards, three-tab nav, three recent transactions`);

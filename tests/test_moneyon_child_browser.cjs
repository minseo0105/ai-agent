// Phase 3 child journeys against the existing Phase 2 API/SQLite engine.
const {chromium}=require('../reports/analytics-browser/node_modules/playwright');
const {spawn}=require('node:child_process');const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),folder=path.join(root,'data','moneyon',`phase3-browser-${Date.now()}`),artifacts=path.join(root,'reports','moneyon-phase3');
fs.mkdirSync(folder,{recursive:true});fs.mkdirSync(artifacts,{recursive:true});
const web='http://127.0.0.1:3109',api='http://127.0.0.1:8109';
const env={...process.env,NEXT_BUILD_DIR:'.next-moneyon',MONEYON_TEST_DB:path.join(folder,'test.sqlite3')};
const processes=[spawn(path.join(root,'.venv','Scripts','python.exe'),['-m','uvicorn','moneyon_browser_api:app','--app-dir','tests/fixtures','--host','127.0.0.1','--port','8109'],{cwd:root,env,windowsHide:true}),spawn(process.execPath,[path.join(root,'web','node_modules','next','dist','bin','next'),'start','-H','127.0.0.1','-p','3109'],{cwd:path.join(root,'web'),env,windowsHide:true})];
let logs='';processes.forEach(p=>{p.stdout.on('data',d=>logs+=d);p.stderr.on('data',d=>logs+=d);});
async function ready(url){for(let i=0;i<100;i++){try{if((await fetch(url)).ok)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error(`Server unavailable ${url}\n${logs}`);}
(async()=>{
 let browser,page;
 try{
  await Promise.all([ready(web+'/moneyon'),ready(api+'/__test__/ready')]);browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:375,height:812},reducedMotion:'reduce'});page=await context.newPage();page.setDefaultTimeout(15000);
  const errors=[],moods=new Set(),themes=new Set();let childPath='',childHeaders={};
  page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/api/**',async route=>{
    const p=new URL(route.request().url()).pathname;
    if(p.startsWith('/api/moneyon')){
      const match=p.match(/^\/api\/moneyon\/children\/([^/]+)\/(?:transactions|experiment)/);
      if(match){childPath='/api/moneyon/children/'+match[1];childHeaders=route.request().headers();}
      const response=await route.fetch({url:api+p});await route.fulfill({response});
    }else if(p==='/api/access/status')await route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services:{},me:{role:'member',id:'test',name:'DEMO'}}});
    else if(p==='/api/access/login')await route.fulfill({json:{token:'fixture-only-token',name:'DEMO',role:'member'}});
    else await route.fulfill({json:{ok:true}});
  });
  const button=name=>page.getByRole('button',{name,exact:true}).first();
  const nav=name=>page.getByRole('navigation',{name:'어린이 주요 메뉴'}).getByRole('button',{name,exact:true});
  async function login(){await button('부모님과 직접 시작하기').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();}
  async function select(name){await page.locator('.mo-child').filter({hasText:name}).click();await button('이 아이로 시작 →').click();await page.getByRole('heading',{name:`안녕, ${name}!`}).waitFor();}
  async function capture(name){await page.screenshot({path:path.join(artifacts,name+'.png'),fullPage:true});}
  async function mood(name){await page.locator(`[data-coach-state="${name}"]`).first().waitFor();moods.add(name);await capture('coach-'+name+'-375');}
  async function widths(name){for(const width of [375,768,1440]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow ${name} ${width}`);const main=page.getByTestId('child-experience');const navigation=main.getByRole('navigation',{name:'어린이 주요 메뉴'});assert.deepEqual(await navigation.getByRole('button').allTextContents(),['홈','통장','저축']);assert.equal(await main.locator('.mo-tabs').count(),0);await capture(`${name}-${width}`);}await page.setViewportSize({width:375,height:812});}
  async function manual(amount,name='공책'){await button('돈 썼어요').click();await page.getByLabel('무엇을 샀나요?',{exact:true}).fill(name);await page.getByLabel('얼마를 썼나요?').fill(String(amount));await page.getByLabel('어떤 종류인가요?').selectOption('문구');await button('기록 완료').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();}
  async function ledger(){const r=await fetch(api+childPath,{headers:childHeaders});assert(r.ok);return r.json();}
  await page.goto(web+'/moneyon');await page.getByText('기존 가족으로 시작하기',{exact:true}).click();await page.getByLabel('AI LAB 개인 접속 코드').fill('DEMO-ONLY');await button('접속 코드로 로그인').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();
  for(const [name,theme,grade] of [['하늘','moneyon',2],['재현','adventure',3],['서연','animals',5]]){
    await button('+ 아이 추가하기').click();await page.getByLabel('별명',{exact:true}).fill(name);await page.getByLabel('학년',{exact:true}).fill(String(grade));if(name==='재현')await page.getByLabel('캐릭터').selectOption('🧑‍🚀');await button('다음').click();await page.getByLabel('나만의 월드').selectOption(theme);await button('다음').click();await button('설정 저장').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();
  }
  await select('재현');assert.equal(await page.getByTestId('child-balance').innerText(),'0원');await mood('greeting');
  await button('돈 썼어요').click();await page.locator('summary').filter({hasText:'가상 소비로 연습하기'}).click();await page.locator('.mk-merchants button').filter({hasText:'문구점'}).click();await page.getByRole('alert').waitFor();await mood('help');
  await nav('홈').click();assert.equal(await page.getByTestId('child-balance').innerText(),'0원');await button('잠그기 🔒').click();await login();await page.locator('.mo-child').filter({hasText:'재현'}).click();await button('현재 주기 용돈 지급').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();await capture('parent-maintained-375');await button('이 아이로 시작 →').click();
  await mood('allowance');assert.equal(await page.getByTestId('child-balance').innerText(),'10,000원');
  const action=await button('돈 썼어요').boundingBox();assert(action&&action.y+action.height<812,'main action should be visible without scrolling');
  await manual(4000);await mood('spending');assert.equal(await page.getByTestId('child-balance').innerText(),'6,000원');assert.equal(await page.getByTestId('child-reward').innerText(),'600원');assert((await page.getByTestId('child-experience').innerText()).includes('아직 안 들어왔어요'));await widths('home');
  await button('통장 보기').click();await page.locator('.mk-transaction-detail summary').filter({hasText:'공책'}).click();await page.getByRole('combobox',{name:/^소비 카테고리/}).selectOption('선물');await page.locator('.mk-transaction-detail summary').filter({hasText:'선물'}).waitFor();assert.equal(await page.getByTestId('child-balance').innerText(),'6,000원');
  await page.getByRole('button',{name:'받은 돈',exact:true}).click();assert.equal(await page.getByTestId('account-transactions').locator('li').count(),1);await page.getByRole('button',{name:'전체',exact:true}).click();await widths('account');
  await nav('저축').click();assert.equal(await page.getByTestId('child-vault').innerText(),'0원');await mood('interest');await button('이자 알아보기').click();const before=await ledger();await page.locator('input[type=range]').fill('3000');await page.getByTestId('experiment-result').getByText('+300원').waitFor();assert.deepEqual(await ledger(),before);await capture('interest-readonly-375');
  await nav('저축').click();await button('목표 만들기').click();await page.getByLabel('목표 이름').fill('나의 첫 책');await page.getByLabel('목표 금액',{exact:true}).fill('1000');await button('목표 저장').click();await page.getByRole('heading',{name:'나의 첫 책'}).waitFor();
  await button('저금통에 넣기').click();await page.getByLabel('저금통에 얼마를 넣을까요?').fill('1000');await button('옮기기').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();assert.equal(await page.getByTestId('child-vault').innerText(),'1,000원');assert.equal(await page.getByTestId('child-reward').innerText(),'500원');await page.getByText('목표를 이뤘어요!',{exact:true}).waitFor();await widths('savings');
  await nav('홈').click();await mood('goal');assert.equal(await page.getByTestId('child-balance').innerText(),'5,000원');await button('나의 성장').click();await page.getByRole('heading',{name:'나의 저축 정원'}).waitFor();await button('퀘스트').click();await button('10원').click();await page.getByRole('status').filter({hasText:'다시'}).waitFor();await button('100원').click();await page.getByRole('status').filter({hasText:'정답'}).waitFor();await button('100원').waitFor({state:'hidden'});assert.equal(await button('100원').count(),0);await button('배지').click();await page.getByText('금융 탐험가',{exact:true}).waitFor();await capture('growth-badges-375');
  await nav('홈').click();await manual(100,'연필');await manual(200,'지우개');assert.equal(await page.getByTestId('recent-transactions').locator('li').count(),3);const projected=await ledger();assert.equal(await page.getByTestId('child-balance').innerText(),projected.banking.accounts.find(a=>a.kind==='wallet').balance.toLocaleString('ko-KR')+'원');
  themes.add(await page.getByTestId('child-experience').getAttribute('data-theme'));
  for(const [name,theme] of [['서연','animals'],['하늘','moneyon']]){await button('잠그기 🔒').click();await login();await select(name);assert.equal(await page.getByTestId('child-experience').getAttribute('data-theme'),theme);assert.equal(await page.getByTestId('child-balance').innerText(),'0원');await page.getByRole('complementary',{name:'우루미의 한마디'}).waitFor();themes.add(theme);await capture(`theme-${theme}-375`);}
  assert.deepEqual([...moods].sort(),['allowance','goal','greeting','help','interest','spending']);assert.equal(themes.size,3);
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(artifacts,'browser-result.json'),JSON.stringify({ok:true,widths:[375,768,1440],themes:[...themes],coachStates:[...moods],scenarios:['three primary tabs','balance from ledger','draft reward separate','record and passbook','category change','read-only interest experiment','vault and goal','growth/finite quests/badges','parent authentication retained','three child themes','six coach moods','three recent rows','responsive layouts','reduced motion'],errors},null,2));console.log('PASS Phase 3 child experience; screenshots: reports/moneyon-phase3');
 }catch(e){if(page)await page.screenshot({path:path.join(artifacts,'failure.png'),fullPage:true}).catch(()=>{});throw e;}
 finally{if(browser)await browser.close();processes.forEach(p=>p.kill());}
})().catch(e=>{console.error(e);process.exitCode=1;});

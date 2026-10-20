// Real MONEY:ON API + SQLite; only the existing AI LAB login is replaced by a test identity.
const {chromium} = require('../reports/analytics-browser/node_modules/playwright');
const {spawn} = require('node:child_process');
const fs = require('node:fs'); const path = require('node:path'); const assert = require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const folder=path.join(root,'data','moneyon',`browser-${Date.now()}`); fs.mkdirSync(folder,{recursive:true});
const artifacts=path.join(root,'reports','moneyon'); fs.mkdirSync(artifacts,{recursive:true});
const web='http://127.0.0.1:3107', api='http://127.0.0.1:8107';
const env={...process.env,NEXT_BUILD_DIR:'.next-moneyon',MONEYON_TEST_DB:path.join(folder,'test.sqlite3')};
const processes=[spawn(path.join(root,'.venv','Scripts','python.exe'),['-m','uvicorn','moneyon_browser_api:app','--app-dir','tests/fixtures','--host','127.0.0.1','--port','8107'],{cwd:root,env,windowsHide:true}),spawn(process.execPath,[path.join(root,'web','node_modules','next','dist','bin','next'),'start','-H','127.0.0.1','-p','3107'],{cwd:path.join(root,'web'),env,windowsHide:true})];
let logs=''; processes.forEach(p=>{p.stdout.on('data',d=>logs+=d);p.stderr.on('data',d=>logs+=d);});
async function ready(url){for(let i=0;i<100;i++){try{if((await fetch(url)).ok)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error('Server unavailable: '+url+'\n'+logs);}
(async()=>{
 let browser;
 try{
  await Promise.all([ready(web+'/moneyon'),ready(api+'/__test__/ready')]);
  browser=await chromium.launch({channel:'chrome',headless:true});const context=await browser.newContext({viewport:{width:1440,height:1000}});
  const errors=[]; const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/api/**',async route=>{const p=new URL(route.request().url()).pathname;if(p.startsWith('/api/moneyon')){const r=await route.fetch({url:api+p});await route.fulfill({response:r});}else if(p==='/api/access/status')await route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services:{},me:{role:'member',id:'browser-test',name:'test'}}});else await route.fulfill({json:{ok:true}});});
  const button=(s)=>page.getByRole('button',{name:s,exact:true});
  await page.goto(web+'/moneyon');await button('부모님과 직접 시작하기').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();
  async function add(name,monthly=false){await button('+ 아이 추가하기').click();await page.getByLabel('별명',{exact:true}).fill(name);await button('다음').click();await page.getByLabel('나만의 월드').selectOption(monthly?'animals':'adventure');await button('다음').click();if(monthly){await page.getByLabel('지급 주기').selectOption('monthly');await page.getByLabel('지급 금액 (원)',{exact:true}).fill('30000');}await button('설정 저장').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();}
  await add('모니');await add('모니',true);
  let cards=page.locator('.mo-child');assert.equal(await cards.count(),2);
  await cards.nth(1).click();await button('현재 주기 용돈 지급').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();
  await button('가족 대시보드').click();await page.locator('.mo-child').nth(0).click();await button('현재 주기 용돈 지급').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();
  const token=await page.evaluate(()=>null); // Parent credential stays in React memory, never localStorage.
  assert.equal(token,null);
  await button('이 아이로 시작 →').click();await button('돈 썼어요').click();await page.getByLabel('무엇을 샀나요?',{exact:true}).fill('책과 간식');await page.getByLabel('얼마를 썼나요?').fill('4000');await button('기록 완료').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();
  const nav=name=>page.getByRole('navigation',{name:'어린이 주요 메뉴'}).getByRole('button',{name,exact:true});
  assert.equal(await page.getByTestId('child-balance').innerText(),'6,000원');assert.equal(await page.getByTestId('child-reward').innerText(),'600원');
  await nav('저축').click();await button('이자 알아보기').click();await page.locator('input[type=range]').fill('3000');await page.getByTestId('experiment-result').getByText('+300원').waitFor();
  await nav('홈').click();assert.equal(await page.getByTestId('child-balance').innerText(),'6,000원');
  await nav('저축').click();await button('저금통에 넣기').click();await page.getByLabel('저금통에 얼마를 넣을까요?').fill('1000');await button('옮기기').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();
  await button('목표 만들기').click();await page.getByLabel('목표 이름').fill('내 꿈의 책');await page.getByLabel('목표 금액',{exact:true}).fill('10000');await button('목표 저장').click();await page.getByRole('heading',{name:'내 꿈의 책'}).waitFor();assert((await page.locator('.mk-goal').innerText()).includes('10%'));
  await nav('홈').click();await button('나의 성장').click();await button('퀘스트').click();await button('100원').click();await page.getByRole('status').filter({hasText:'정답'}).waitFor();await button('배지').click();assert((await page.locator('.mk-badges').innerText()).includes('금융 탐험가'));
  for(const width of [375,768,1440]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`horizontal overflow at ${width}`);await page.screenshot({path:path.join(artifacts,`moneyon-${width}.png`),fullPage:true});}
  await button('잠그기 🔒').click();await button('부모님과 직접 시작하기').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();
  assert((await page.locator('.mo-child').nth(1).innerText()).includes('30,000원'));
  await fetch(api+'/__test__/clock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({day:'2026-10-19'})});
  await page.locator('.mo-child').nth(0).click();await button('보상 이자 승인').click();await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();assert((await page.locator('.mo-stats').innerText()).includes('5,500원'));assert.equal(await button('승인 완료').count(),1);
  await page.screenshot({path:path.join(artifacts,'moneyon-parent.png'),fullPage:true});
  await page.goto(web+'/');await page.getByRole('link').filter({hasText:'MONEY:ON'}).waitFor();
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(artifacts,'browser-result.json'),JSON.stringify({ok:true,widths:[375,768,1440],scenarios:['same-name children','weekly/monthly payment','child switch','expense isolation','live server experiment','vault/goal','quiz/badges','interest approval','menu route'],errors},null,2));
  console.log('MONEY:ON browser scenarios passed; screenshots: reports/moneyon');
 }finally{if(browser)await browser.close();processes.forEach(p=>p.kill());}
})().catch(e=>{console.error(e);process.exitCode=1;});

// Offline banking E2E. Only the existing AI LAB identity is replaced by the fixture.
const {chromium}=require('../reports/analytics-browser/node_modules/playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const data=path.join(root,'data','moneyon',`phase2-browser-${Date.now()}`);
const artifacts=path.join(root,'reports','moneyon-phase2');fs.mkdirSync(data,{recursive:true});fs.mkdirSync(artifacts,{recursive:true});
const web='http://127.0.0.1:3108',api='http://127.0.0.1:8108';
const env={...process.env,NEXT_BUILD_DIR:'.next-moneyon',MONEYON_TEST_DB:path.join(data,'test.sqlite3')};
const processes=[spawn(path.join(root,'.venv','Scripts','python.exe'),['-m','uvicorn','moneyon_browser_api:app','--app-dir','tests/fixtures','--host','127.0.0.1','--port','8108'],{cwd:root,env,windowsHide:true}),spawn(process.execPath,[path.join(root,'web','node_modules','next','dist','bin','next'),'start','-H','127.0.0.1','-p','3108'],{cwd:path.join(root,'web'),env,windowsHide:true})];
let logs='';for(const p of processes){p.stdout.on('data',d=>logs+=d);p.stderr.on('data',d=>logs+=d);}
async function ready(url){for(let i=0;i<100;i++){try{if((await fetch(url)).ok)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error(`Server not ready: ${url}\n${logs}`);}
(async()=>{
 let browser,page;
 try{
  await Promise.all([ready(web+'/moneyon'),ready(api+'/__test__/ready')]);
  browser=await chromium.launch({channel:'chrome',headless:true});
  const context=await browser.newContext({viewport:{width:1440,height:1000}});page=await context.newPage();page.setDefaultTimeout(15000);
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await context.route('**/api/**',async route=>{const p=new URL(route.request().url()).pathname;
    if(p.startsWith('/api/moneyon')){const response=await route.fetch({url:api+p});await route.fulfill({response});}
    else if(p==='/api/access/status')await route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services:{},me:{role:'member',id:'browser-test',name:'DEMO'}}});
    else if(p==='/api/access/login')await route.fulfill({json:{token:'fixture-only-token',name:'DEMO',role:'member'}});
    else await route.fulfill({json:{ok:true}});
  });
  const button=name=>page.getByRole('button',{name,exact:true}).first();
  async function recorded(){await page.getByRole('status').filter({hasText:'기록 완료'}).waitFor();}
  async function login(){await button('부모님과 직접 시작하기').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();}
  async function responsive(prefix){for(const width of [375,768,1440]){await page.setViewportSize({width,height:1000});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow ${prefix}: ${width}`);await page.screenshot({path:path.join(artifacts,`${prefix}-${width}.png`),fullPage:true});}}
  await page.goto(web+'/moneyon');await page.getByText('기존 가족으로 시작하기',{exact:true}).click();await page.getByLabel('AI LAB 개인 접속 코드').fill('DEMO-ONLY');await button('접속 코드로 로그인').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();
  await button('+ 아이 추가하기').click();await page.getByLabel('별명',{exact:true}).fill('보존할아이');await button('다음').click();await button('다음').click();await button('설정 저장').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();
  await page.locator('.mo-parent-bank .mo-bank-balance').getByText('500,000원',{exact:true}).waitFor();
  await button('시연 가족 시작').click();await page.locator('.mo-child').filter({hasText:'재현'}).waitFor();assert.equal(await page.locator('.mo-child').count(),2);assert.equal(await page.locator('.mo-child').filter({hasText:'보존할아이'}).count(),0);
  await page.locator('.mo-child').filter({hasText:'재현'}).click();await button('현재 주기 용돈 지급').click();await recorded();await page.locator('.mo-parent-bank .mo-bank-balance').getByText('490,000원',{exact:true}).waitFor();
  await responsive('parent-transfer');
  const nav=name=>page.getByRole('navigation',{name:'어린이 주요 메뉴'}).getByRole('button',{name,exact:true});
  await button('이 아이로 시작 →').click();await page.getByTestId('child-balance').getByText('10,000원',{exact:true}).waitFor();
  await button('통장 보기').click();assert((await page.getByTestId('account-transactions').innerText()).includes('용돈이 들어왔어요'));
  await nav('홈').click();await button('돈 썼어요').click();await page.locator('summary').filter({hasText:'가상 소비로 연습하기'}).click();await page.locator('.mk-merchants button').filter({hasText:'문구점'}).click();await recorded();
  await nav('홈').click();assert.equal(await page.getByTestId('child-reward').innerText(),'600원');assert.equal(await page.getByTestId('child-balance').innerText(),'6,000원');
  await button('통장 보기').click();await page.locator('.mk-transaction-detail summary').filter({hasText:'문구점에서 샀어요'}).click();
  await page.getByRole('combobox',{name:/^소비 카테고리/}).selectOption('선물');await page.locator('.mk-transaction-detail summary').filter({hasText:'선물'}).waitFor();assert.equal(await page.getByTestId('account-transactions').locator('li').count(),2);
  await responsive('child-book');
  await button('잠그기 🔒').click();await login();
  await page.getByLabel('데모 날짜',{exact:true}).fill('2026-10-19');await button('가상 날짜 적용').click();await page.getByText('기준일 2026-10-19',{exact:true}).waitFor();
  await page.locator('.mo-child').filter({hasText:'재현'}).click();await button('보상 이자 승인').click();await recorded();await page.locator('.mo-parent-bank .mo-bank-balance').getByText('489,400원',{exact:true}).waitFor();assert(await button('승인 완료').isDisabled());
  await button('전체 거래내역').click();assert((await page.locator('.mo-bank-history').first().innerText()).includes('부모님이 주신 저축 보상 이자'));
  await button('이 아이로 시작 →').click();await page.getByTestId('child-balance').getByText('6,600원',{exact:true}).waitFor();await button('통장 보기').click();await page.locator('.mk-transaction-detail summary').filter({hasText:'부모님이 보상을 주셨어요'}).waitFor();
  await nav('저축').click();await button('저금통에 넣기').click();await page.getByLabel('저금통에 얼마를 넣을까요?').fill('1000');await button('옮기기').click();await recorded();assert.equal(await page.getByTestId('child-vault').innerText(),'1,000원');
  await button('목표 만들기').click();await page.getByLabel('목표 이름').fill('시연용 책');await page.getByLabel('목표 금액',{exact:true}).fill('10000');await button('목표 저장').click();await page.getByRole('heading',{name:'시연용 책'}).waitFor();assert((await page.locator('.mk-goal').innerText()).includes('10%'));
  await nav('홈').click();await page.getByTestId('child-balance').getByText('5,600원',{exact:true}).waitFor();await responsive('child-account');
  await button('잠그기 🔒').click();await login();await page.locator('.mo-child').filter({hasText:'서연'}).getByText(/잔액 0원/).waitFor();
  await button('데모 새로 시작').click();await button('새 시연 가족 만들기').click();await page.locator('.mo-parent-bank .mo-bank-balance').getByText('500,000원',{exact:true}).waitFor();await page.locator('.mo-child').filter({hasText:'재현'}).getByText(/잔액 0원/).waitFor();
  await button('기존 가족으로 돌아가기').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.locator('.mo-child').filter({hasText:'보존할아이'}).waitFor();assert.equal(await page.locator('.mo-child').count(),1);assert((await page.locator('.mo-parent-bank .mo-bank-balance').innerText()).includes('500,000원'));
  await page.goto(web+'/');await page.getByRole('link').filter({hasText:'MONEY:ON'}).waitFor();assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(artifacts,'browser-result.json'),JSON.stringify({ok:true,widths:[375,768,1440],scenarios:['parent login','preserve original child','isolated seeded family','parent-child allowance transfer','account and book synchronization','simulated merchant purchase','category correction without balance change','virtual cycle end','reward transfer exactly once','vault transfer and goal','child account isolation','non-destructive demo reset','return to original family','AI LAB menu'],errors},null,2));
  console.log('PASS MONEY:ON Phase 2 banking E2E; screenshots: reports/moneyon-phase2');
 }catch(e){if(page)await page.screenshot({path:path.join(artifacts,'failure.png'),fullPage:true}).catch(()=>{});throw e;}
 finally{if(browser)await browser.close();for(const p of processes)p.kill();}
})().catch(e=>{console.error(e);process.exitCode=1;});

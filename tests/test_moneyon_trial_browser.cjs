// Real Chromium + Next production build + disposable FastAPI/SQLite trial DB.
const {chromium}=require('../reports/analytics-browser/node_modules/playwright');
const {spawn}=require('node:child_process');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),artifacts=path.join(root,'reports','moneyon-phase4');
const folder=path.join(root,'data','moneyon',`phase4-browser-${Date.now()}`);
fs.mkdirSync(folder,{recursive:true});fs.mkdirSync(artifacts,{recursive:true});
const web='http://127.0.0.1:3110',api='http://127.0.0.1:8110';
const env={...process.env,NEXT_BUILD_DIR:'.next-moneyon',MONEYON_TEST_DB:path.join(folder,'family.sqlite3')};
const processes=[spawn(path.join(root,'.venv','Scripts','python.exe'),['-m','uvicorn','moneyon_browser_api:app','--app-dir','tests/fixtures','--host','127.0.0.1','--port','8110'],{cwd:root,env,windowsHide:true}),spawn(process.execPath,[path.join(root,'web','node_modules','next','dist','bin','next'),'start','-H','127.0.0.1','-p','3110'],{cwd:path.join(root,'web'),env,windowsHide:true})];
let logs='';processes.forEach(p=>{p.stdout.on('data',d=>logs+=d);p.stderr.on('data',d=>logs+=d);});
async function ready(url){for(let i=0;i<100;i++){try{if((await fetch(url)).ok)return;}catch{}await new Promise(r=>setTimeout(r,300));}throw Error(`Server unavailable ${url}\n${logs}`);}
(async()=>{
 let browser,page;
 const checks=[],errors=[];
 try{
  await Promise.all([ready(web+'/moneyon'),ready(api+'/__test__/ready')]);
  browser=await chromium.launch({channel:'chrome',headless:true});
  async function context(){const c=await browser.newContext({viewport:{width:375,height:900}});await c.route('**/api/**',async route=>{const p=new URL(route.request().url()).pathname;if(p.startsWith('/api/moneyon')){const response=await route.fetch({url:api+p});await route.fulfill({response});}else if(p==='/api/access/status')await route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services:{moneyon:{level:'public',allowed:true,visible:true}},me:null}});else await route.fulfill({json:{ok:true}});});return c;}
  const firstContext=await context();page=await firstContext.newPage();page.setDefaultTimeout(15000);page.on('pageerror',e=>errors.push(e.message));
  const button=name=>page.getByRole('button',{name,exact:true}).first();
  const nav=name=>page.getByRole('navigation',{name:'어린이 주요 메뉴'}).getByRole('button',{name,exact:true});
  async function balance(value){await page.getByTestId('child-balance').filter({hasText:value.toLocaleString('ko-KR')+'원'}).waitFor();}
  async function capture(name){await page.screenshot({path:path.join(artifacts,name+'.png'),fullPage:true});}
  async function widths(name){for(const width of [375,768,1440]){await page.setViewportSize({width,height:900});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`Overflow ${name}/${width}`);assert.deepEqual(await page.getByRole('navigation',{name:'어린이 주요 메뉴'}).getByRole('button').allTextContents(),['홈','통장','저축']);await capture(name+'-'+width);}await page.setViewportSize({width:375,height:900});}
  async function credentials(p=page){return p.evaluate(()=>sessionStorage.getItem('moneyon-trial-v1'));}
  async function snapshot(p=page){const response=await fetch(api+'/api/moneyon/trial/state',{headers:{'X-Moneyon-Trial':await credentials(p)}});assert(response.ok);return response.json();}
  await page.goto(web+'/moneyon');
  await button('바로 체험하기').waitFor();await button('부모님과 직접 시작하기').waitFor();
  await capture('entry-375');await button('바로 체험하기').click();await balance(28500);
  assert.equal(await page.getByLabel('가족 PIN (숫자 6~12자리)').count(),0);
  assert.equal(await page.getByTestId('child-vault').innerText(),'15,000원');assert.equal(await page.getByTestId('child-reward').innerText(),'800원');assert.equal(await page.getByTestId('trial-total').innerText(),'43,500원');
  checks.push('anonymous entry without PIN or parent registration','seed balances and derived reward');await widths('sample-home');
  await button('용돈 받기').click();await page.getByLabel('얼마를 받을까요?').fill('2500');await button('가상 용돈 받기').click();await balance(31000);
  assert.equal(await page.getByTestId('trial-total').innerText(),'46,000원');assert((await page.locator('.mk-coach').first().innerText()).includes('2,500원'));
  checks.push('custom allowance transfer and one sentence coach');await capture('allowance-375');
  await button('돈 썼어요').click();await page.getByLabel('무엇을 샀나요?',{exact:true}).fill('직접 고른 책');await page.getByLabel('얼마를 썼나요?').fill('22000');await page.getByLabel('어떤 종류인가요?').selectOption('책');await button('기록 완료').click();await balance(9000);assert.equal(await page.getByTestId('child-reward').innerText(),'750원');
  const afterExpense=await snapshot();assert.equal(afterExpense.state.report.categories['책'],22000);checks.push('expense ledger, category and automatic reward change');
  // The keyed balance element animates after a successful transaction.
  assert.equal(await page.getByTestId('child-balance').evaluate(e=>getComputedStyle(e).animationName),'mk-money-pop');checks.push('short amount animation');
  await button('통장 보기').click();await page.locator('.mk-transaction-detail summary').filter({hasText:'직접 고른 책'}).click();await page.getByRole('combobox',{name:/소비 카테고리/}).first().selectOption('선물');await page.locator('.mk-transaction-detail summary').filter({hasText:'선물'}).waitFor();await widths('passbook');
  assert.equal((await snapshot()).state.report.categories['선물'],22000);checks.push('passbook updates and category annotation');
  await nav('저축').click();await button('저금통에 넣기').click();await page.getByLabel('저금통에 얼마를 넣을까요?').fill('1000');await button('옮기기').click();await page.getByTestId('child-vault').filter({hasText:'16,000원'}).waitFor();assert.equal(await page.getByTestId('child-reward').innerText(),'650원');assert.equal(await page.getByRole('progressbar',{name:'나의 첫 자전거 달성률'}).getAttribute('value'),'16000');await widths('savings');checks.push('savings preserves total and updates goal/reward');
  const beforeFailure=await snapshot();
  const failed=await fetch(api+`/api/moneyon/trial/children/${beforeFailure.child.id}/transactions`,{method:'POST',headers:{'Content-Type':'application/json','X-Moneyon-Trial':await credentials(),'X-Moneyon-Trial-Version':String(beforeFailure.generation)},body:JSON.stringify({kind:'expense',amount:999999,key:'browser-overdraw'})});assert.equal(failed.status,409);assert.deepEqual(await snapshot(),beforeFailure);checks.push('failed transaction leaves all ledger data unchanged');
  await nav('홈').click();await balance(8000);assert.equal(await page.getByTestId('trial-total').innerText(),'24,000원');
  const beforeRefresh=await credentials();await page.reload();await balance(8000);assert.equal(await credentials(),beforeRefresh);checks.push('refresh resumes exact trial');
  const second=await firstContext.newPage();await second.goto(web+'/moneyon');await second.getByRole('button',{name:'바로 체험하기',exact:true}).click();await second.getByTestId('child-balance').filter({hasText:'28,500원'}).waitFor();assert.notEqual(await credentials(second),await credentials());
  const secondToken=await credentials(second);const firstSnapshot=await snapshot();const blocked=await fetch(api+`/api/moneyon/trial/children/${firstSnapshot.child.id}`,{headers:{'X-Moneyon-Trial':secondToken}});assert.equal(blocked.status,403);checks.push('new tab starts separate trial','cross-visitor read rejected');
  const secondSnapshot=await snapshot(second);await second.getByRole('button',{name:'처음 상태로 돌아가기',exact:true}).click();await second.getByRole('button',{name:'확인하고 초기화',exact:true}).click();await second.getByTestId('child-balance').filter({hasText:'28,500원'}).waitFor();assert.equal((await snapshot()).state.wallet,8000);checks.push('other visitor reset has no effect');
  await second.close();const reopened=await firstContext.newPage();await reopened.goto(web+'/moneyon');await reopened.getByRole('button',{name:'바로 체험하기',exact:true}).waitFor();assert.equal(await credentials(reopened),null);await reopened.close();checks.push('fresh reopened tab has no retained credential');
  const thirdContext=await context(),third=await thirdContext.newPage();await third.goto(web+'/moneyon');await third.getByRole('button',{name:'바로 체험하기',exact:true}).click();await third.getByTestId('child-balance').filter({hasText:'28,500원'}).waitFor();assert.notEqual(await credentials(third),await credentials());await thirdContext.close();checks.push('new browser context isolated');
  await button('보상 체험').click();await page.getByText(/지급된 부모 보상 1,500원/).waitFor();await page.getByLabel('가상 날짜',{exact:true}).fill('2026-10-19');await button('날짜 이동하기').click();await page.getByText('2026-10-19로 이동했어! 끝난 회차의 보상을 확인해 봐.').waitFor();
  await page.reload();await balance(8000);assert.equal((await snapshot()).day,'2026-10-19');
  await button('보상 체험').click();await page.getByLabel('체험 전용 부모 승인에 동의해요').check();const checkbox=await page.getByLabel('체험 전용 부모 승인에 동의해요').boundingBox();assert(checkbox.width===20&&checkbox.height===20);await button('부모 승인 시뮬레이션').click();await balance(8650);checks.push('virtual date plus explicit parent approval simulation');await capture('reward-paid-375');
  await button('보상 체험').click();await page.getByText(/지급된 부모 보상 650원/).waitFor();assert(await button('부모 승인 시뮬레이션').isDisabled());checks.push('paid reward history and duplicate settlement disabled');await capture('reward-history-375');
  await button('처음 상태로 돌아가기').click();await page.getByRole('alertdialog',{name:'체험 초기화 확인'}).waitFor();await page.getByText('체험한 내용만 처음 상태로 돌아가요.',{exact:true}).waitFor();await capture('reset-confirm-375');await button('계속 체험하기').click();await balance(8650);
  await button('처음 상태로 돌아가기').click();await button('확인하고 초기화').click();await balance(28500);assert.equal(await page.getByTestId('child-vault').innerText(),'15,000원');assert.equal(await page.getByTestId('child-reward').innerText(),'800원');const reset=await snapshot();assert.equal(reset.day,'2026-10-12');assert.equal(reset.state.transactions.length,secondSnapshot.state.transactions.length);await capture('reset-restored-375');checks.push('reset cancel preserves data','confirmed reset restores accounts, ledger, dates, reward, goal');
  // Preserve the existing family entry and PIN flow.
  await button('체험 나가기').click();await button('부모님과 직접 시작하기').click();await page.getByLabel('가족 PIN (숫자 6~12자리)').fill('123456');await button('열기').click();await page.getByRole('heading',{name:/우리 가족, 함께 자라요/}).waitFor();checks.push('existing parent entry preserved');
  assert.deepEqual(errors,[]);fs.writeFileSync(path.join(artifacts,'browser-result.json'),JSON.stringify({ok:true,widths:[375,768,1440],checks,errors},null,2));console.log(`PASS Phase 4: ${checks.length} browser scenarios; screenshots: reports/moneyon-phase4`);
 }catch(e){if(page)await page.screenshot({path:path.join(artifacts,'failure.png'),fullPage:true}).catch(()=>{});throw e;}
 finally{if(browser)await browser.close();processes.forEach(p=>p.kill());}
})().catch(e=>{console.error(e);process.exitCode=1;});

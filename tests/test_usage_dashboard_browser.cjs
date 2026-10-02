// Static production build, aggregate fixtures, and loopback only. No production access.
const {chromium}=require('../reports/analytics-browser/node_modules/playwright');
const fs=require('fs'), path=require('path'), http=require('http'), assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'), folder=path.join(root,'web/out');
const fixtures=JSON.parse(fs.readFileSync(path.join(root,'reports/usage-dashboard-ui.json'),'utf8'));
const server=http.createServer((req,res)=>{
  let file=path.resolve(folder,'.'+new URL(req.url,'http://local').pathname);
  if(!file.startsWith(folder+path.sep)){res.writeHead(403);return res.end();}
  if(!path.extname(file)) file+='.html';
  if(!fs.existsSync(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');
  res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  try {
    for(const role of [null,'member','admin']) {
      const context=await browser.newContext({viewport:{width:390,height:844},timezoneId:'America/Los_Angeles'});
      if(role) await context.addInitScript(()=>localStorage.setItem('ailab-access-token','test-only-token'));
      const calls=[], errors=[]; let failure=false;
      await context.route('**/*',async route=>{
        const url=new URL(route.request().url());
        if(url.pathname==='/api/access/status') return route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services:{},me:role?{role,name:'Test'}:null}});
        if(url.pathname==='/api/admin/info') return route.fulfill({json:{configured:true}});
        if(url.pathname==='/api/admin/usage') {
          assert.equal(route.request().method(),'GET');
          assert.equal(route.request().headers().authorization,'Bearer test-only-token');
          const period=url.searchParams.get('period'); calls.push(period);
          return route.fulfill(failure?{status:503,json:{detail:'unavailable'}}:{json:fixtures[period]});
        }
        if(url.pathname.startsWith('/api/')) return route.fulfill({status:404,json:{detail:'Mock unavailable'}});
        if(url.origin!==base) return route.abort();
        return route.continue();
      });
      const page=await context.newPage(); page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base+'/admin/usage');
      if(role!=='admin') {
        await page.getByRole('button',{name:/로그인/}).waitFor();
        assert.equal(calls.length,0); assert.equal(await page.getByRole('region',{name:'기간 요약',exact:true}).count(),0);
      } else {
        const kpis=page.getByRole('region',{name:'기간 요약',exact:true}); await kpis.waitFor();
        assert.match(await kpis.innerText(),/방문 세션\s*5/); assert.match(await kpis.innerText(),/페이지 조회\s*10/);
        assert.match(await page.getByRole('region',{name:'ZIP:ON 이용 흐름',exact:true}).innerText(),/66.7%/);
        assert.match(await page.getByRole('region',{name:'어떤 서비스를 이용했나요?',exact:true}).innerText(),/준비 중/);
        assert.equal(await page.getByRole('region',{name:'최근 활동',exact:true}).locator('li').count(),20);
        await page.screenshot({path:path.join(root,'reports/usage-dashboard-mobile.png'),fullPage:true});
        for(const width of [360,390,1280]) {
          await page.setViewportSize({width,height:900});
          assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);
        }
        await page.getByRole('button',{name:'7일',exact:true}).click();
        await page.getByRole('region',{name:'일별 이용 추이',exact:true}).waitFor();
        const before=calls.length;
        await page.getByRole('button',{name:'Golf',exact:true}).click();
        await page.getByText('일별 수치 보기',{exact:true}).click();
        assert.equal(await page.locator('tbody tr').count(),7); assert.equal(calls.length,before);
        await page.getByRole('button',{name:'30일',exact:true}).click();
        await page.waitForFunction(()=>document.querySelectorAll('tbody tr').length===30);
        await page.getByText('세션별 진행 단계 보기',{exact:true}).first().click();
        await page.screenshot({path:path.join(root,'reports/usage-dashboard-desktop.png'),fullPage:true});
        failure=true; await page.getByRole('button',{name:'새로고침',exact:true}).click();
        await page.getByRole('alert').waitFor(); assert.equal(await kpis.count(),0);
        assert.deepEqual(calls,['today','7d','30d','30d']);
      }
      assert.deepEqual(errors,[]); await context.close();
    }
    console.log('PASS: public/member gated; admin KPIs, distinct rates, 7/30d trends, local filters, recent cap, 360/390/1280 layout, failure without false zeros.');
  } finally {await browser.close(); server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});

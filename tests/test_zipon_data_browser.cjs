// Actual built admin page, local fixtures only. No production requests.
const { chromium }=require('../reports/analytics-browser/node_modules/playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const folder=path.resolve(__dirname,'../web/out');
const server=http.createServer((req,res)=>{
  let file=path.resolve(folder,'.'+new URL(req.url,'http://local').pathname);
  if(!file.startsWith(folder+path.sep)){res.writeHead(403);return res.end();}
  if(!path.extname(file))file+='.html';
  if(!fs.existsSync(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');
  res.end(fs.readFileSync(file));
});
(async()=>{
  await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  try{
    for(const role of [null,'member','admin']){
      const context=await browser.newContext({viewport:{width:390,height:844}});
      if(role)await context.addInitScript(()=>localStorage.setItem('ailab-access-token','fixture-token'));
      let reads=0,failure=false;const errors=[];
      await context.route('**/*',async route=>{
        const u=new URL(route.request().url());
        if(u.pathname==='/api/access/status')return route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services:{},me:role?{role,name:'Test'}:null}});
        if(u.pathname==='/api/admin/info')return route.fulfill({json:{configured:true}});
        if(u.pathname==='/api/admin/zipon-data'){
          reads++;assert.equal(route.request().method(),'GET');assert.equal(route.request().headers().authorization,'Bearer fixture-token');
          return route.fulfill(failure?{status:503,json:{detail:'private-secret-never-render'}}:{json:{total:1203,locations:122,boundaries:4,pending:5,new_30d:3,changed_30d:2,auto_applied_30d:2,last_success:null,last_attempt:new Date().toISOString(),source_date:null,
            runs:[{run_id:'fixture',started_at:new Date().toISOString(),status:'PARTIAL',new_count:3,changed_count:2,unchanged_count:100,validation_failed_count:1,sources:[{source:'seoul_moa',status:'FAILED',source_complete:false}]}],recent_projects:[],recent_changes:[]}});
        }
        if(u.pathname.startsWith('/api/'))return route.fulfill({status:404,json:{detail:'fixture'}});
        if(u.origin!==base)return route.abort();
        return route.continue();
      });
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base+'/admin/zipon-data');
      if(role!=='admin'){
        await page.getByRole('button',{name:/로그인/}).waitFor();assert.equal(reads,0);
      }else{
        await page.getByRole('heading',{name:'개발정보 최신화 현황'}).waitFor();
        await page.getByText('1203',{exact:true}).waitFor();
        assert.match(await page.locator('body').innerText(),/부분 성공/);
        assert.match(await page.locator('body').innerText(),/8일 이상/);
        assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),true);
        await page.screenshot({path:path.resolve(__dirname,'../reports/zipon-admin-mobile.png'),fullPage:true});
        failure=true;await page.getByRole('button',{name:'새로고침',exact:true}).click();
        await page.getByText(/조회할 수 없습니다\. ZIP 연결 설정/).waitFor();
        assert(!((await page.locator('body').innerText()).includes('private-secret')));
        assert.equal(await page.getByText('1203',{exact:true}).count(),0);
      }
      assert.deepEqual(errors,[]);await context.close();
    }
    console.log('PASS: ZIP admin page roles, no writes, partial/failure states, stale warning, mobile layout');
  }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});

// Built homepage with local access fixtures; production APIs are never contacted.
const {chromium}=require('../reports/analytics-browser/node_modules/playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const folder=path.resolve(process.env.HOME_OUT||path.resolve(__dirname,'../web/out')),output=path.resolve(__dirname,'../reports/home-showcase');
const server=http.createServer((req,res)=>{
  const pathname=new URL(req.url,'http://local').pathname;
  let file=path.resolve(folder,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(folder+path.sep)){res.writeHead(403);return res.end();}
  if(!path.extname(file))file+='.html';
  if(!fs.existsSync(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css'})[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
});
(async()=>{
  fs.mkdirSync(output,{recursive:true});await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe',headless:true});
  try{
    for(const width of [360,375,390,430,768,1440]){
      const context=await browser.newContext({viewport:{width,height:960},reducedMotion:'reduce'});
      let services={};const errors=[];
      await context.route('**/*',route=>{
        const u=new URL(route.request().url());
        if(u.pathname==='/api/access/status')return route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services,me:null}});
        if(u.pathname.startsWith('/api/'))return route.fulfill({json:{ok:true}});
        return u.origin===base?route.continue():route.abort();
      });
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base);await page.locator('[data-service]').first().waitFor();
      await page.getByRole('button',{name:'전체',exact:true}).click();
      assert.equal(await page.getByRole('button',{name:'전체',exact:true}).evaluate(n=>getComputedStyle(n).color),'rgb(255, 255, 255)');
      assert.equal(await page.locator('[data-service]').count(),9);
      const links=await page.locator('[data-service]').evaluateAll(nodes=>nodes.map(n=>[n.dataset.service,n.getAttribute('href')]));
      assert.deepEqual(links,[['golf','/golf'],['dreamcar','/dreamcar'],['realestate','/realestate'],['report','/report'],['saju','/saju'],['moneyon','https://minseo2-moneyon-demo.hf.space/'],['car-selector','/car-selector'],['gif','/gif'],['agent','#agent']]);
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`overflow at ${width}`);
      const columns=await page.locator('[aria-label="전체 서비스 목록"]').evaluate(n=>getComputedStyle(n).gridTemplateColumns.split(' ').length);
      assert.equal(columns,width<768?1:width<1024?2:3);
      const featured=await page.locator('[data-service="golf"]').boundingBox();
      const grid=await page.locator('[aria-label="전체 서비스 목록"]').boundingBox();
      if(width<768){assert(Math.abs(featured.width-grid.width)<1);const cta=await page.getByRole('link',{name:/서비스 둘러보기/}).boundingBox();assert(cta.height>=44&&cta.y+cta.height<=960,'핵심 버튼이 첫 화면 안에');}
      else if(width>=1024)assert(featured.width<grid.width*0.75,'PC(3열)에서 추천 카드는 2칸');
      else assert(Math.abs(featured.width-grid.width)<1,'태블릿(2열)에서 추천 카드는 한 줄 전체');
      const clipped=await page.locator('main h1, main h2, main h3, main p, main button').evaluateAll(nodes=>nodes.filter(n=>n.clientWidth&&n.scrollWidth>n.clientWidth+1).map(n=>n.textContent));
      assert.deepEqual(clipped,[]);
      await page.screenshot({path:path.join(output,`${width}.png`),fullPage:true});
      for(const [name,count] of [['AI Agent',1],['Prototype',5],['API / Search',3],['전체',9]]){
        await page.getByRole('button',{name,exact:true}).click();assert.equal(await page.locator('[data-service]').count(),count);
      }
      await page.locator('[data-service="agent"]').click();await page.locator('#agent[open]').waitFor();
      const input=page.locator('#agent textarea');await input.fill('상태 보존 확인');
      await page.getByRole('button',{name:'Prototype',exact:true}).click();
      await page.getByRole('navigation',{name:'메인 탐색'}).getByRole('link',{name:/AI 에이전트/}).click();
      assert(await input.isVisible());assert.equal(await input.inputValue(),'상태 보존 확인');
      await page.locator('#agent summary').focus();await page.keyboard.press('Enter');
      await page.waitForFunction(()=>!document.querySelector('#agent').open);
      await page.keyboard.press('Enter');await page.locator('#agent[open]').waitFor();assert.equal(await input.inputValue(),'상태 보존 확인');
      services={gif:{visible:false,allowed:false},golf:{visible:true,allowed:false},agent:{visible:true,allowed:false}};
      await page.goto(base);await page.getByRole('button',{name:'전체',exact:true}).click();
      await page.waitForFunction(()=>document.querySelectorAll('[data-service]').length===8);
      assert.match(await page.locator('[data-service="golf"]').getAttribute('aria-label'),/등록자 전용/);
      await page.locator('[data-service="agent"]').click();assert.equal(await page.locator('#agent textarea').count(),0);
      assert.match(await page.locator('#agent').innerText(),/접속 코드/);
      assert.deepEqual(errors,[]);await context.close();console.log(`PASS ${width}px: layout, routes, filters, chat state, keyboard, access control`);
    }
  }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});

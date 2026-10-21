// AI LAB 홈(정적 빌드) 브라우저 검사. 접속 상태 API는 가짜 응답이라 실서버는 부르지 않는다.
// 사용: (web 폴더에서 STATIC_EXPORT=1 빌드 후) node tests/test_home_showcase_browser.cjs
//       다른 빌드 폴더는 HOME_OUT=<out 폴더> 로 지정.
// 디자인(남색 히어로·태그 칩·서비스별 파스텔 카드·3D 그림·분류·MONEY:ON 카드)과 모바일 기준(가로 넘침 없음, 터치 44px, 글자 13px, 입력 16px)을 함께 본다.
const {chromium}=require('../reports/analytics-browser/node_modules/playwright');
const fs=require('fs'),path=require('path'),http=require('http'),assert=require('node:assert/strict');
const folder=path.resolve(process.env.HOME_OUT||path.resolve(__dirname,'../web/out')),output=path.resolve(__dirname,'../reports/home-showcase');
const types={'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml','.webp':'image/webp','.png':'image/png'};
const server=http.createServer((req,res)=>{
  const pathname=new URL(req.url,'http://local').pathname;
  let file=path.resolve(folder,'.'+(pathname==='/'?'/index.html':pathname));
  if(!file.startsWith(folder+path.sep)){res.writeHead(403);return res.end();}
  if(!path.extname(file))file+='.html';
  if(!fs.existsSync(file)){res.writeHead(404);return res.end();}
  res.setHeader('Content-Type',types[path.extname(file)]||'application/octet-stream');res.end(fs.readFileSync(file));
});
const ORDER=[['/golf','tee.webp'],['/dreamcar','dream.webp'],['/realestate','zip.webp'],['/report','report.svg'],['/saju','saju.svg'],['/car-selector','car-selector.svg'],['/gif','gif.svg'],['https://minseo2-moneyon-demo.hf.space/','money.webp']];
(async()=>{
  fs.mkdirSync(output,{recursive:true});await new Promise(r=>server.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${server.address().port}`;
  const browser=await chromium.launch({channel:'msedge',headless:true});
  try{
    for(const width of [360,375,390,430,768,1440]){
      const context=await browser.newContext({viewport:{width,height:900},reducedMotion:'reduce'});
      let services={};const errors=[];
      await context.route('**/*',route=>{
        const u=new URL(route.request().url());
        if(u.pathname==='/api/access/status')return route.fulfill({json:{site_mode:'public',site_allowed:true,notice:null,services,me:null}});
        if(u.pathname.startsWith('/api/'))return route.fulfill({json:{ok:true}});
        return u.origin===base?route.continue():route.abort();
      });
      const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
      await page.goto(base);await page.locator('#services a img').first().waitFor();
      for(let y=0;y<4000;y+=400){await page.evaluate(v=>scrollTo(0,v),y);await page.waitForTimeout(40);}
      await page.evaluate(()=>scrollTo(0,0));
      // 디자인: 히어로·태그 칩·카드 8개(순서·그림·파스텔 배경)
      const hero=await page.locator('h1').evaluate(h=>getComputedStyle(h.closest('section')).backgroundImage);
      assert.match(hero,/linear-gradient/,'남색 그라데이션 히어로');
      for(const tag of ['AI Agent','API','Vibe Coding','Prototype'])assert(await page.locator('section').first().getByText(tag,{exact:true}).count(),`태그 칩 ${tag}`);
      const cards=page.locator('#services a').filter({has:page.locator('img')});
      assert.equal(await cards.count(),8);
      const got=await cards.evaluateAll(ns=>ns.map(n=>[n.getAttribute('href'),n.querySelector('img').getAttribute('src').split('/').pop(),n.querySelector('img').naturalWidth>0,getComputedStyle(n).backgroundColor!=='rgba(0, 0, 0, 0)'||getComputedStyle(n).backgroundImage!=='none']));
      assert.deepEqual(got.map(([h,s])=>[h,s]),ORDER,'카드 순서·그림');
      assert(got.every(([,,loaded,colored])=>loaded&&colored),'그림이 뜨고 카드에 배경색이 있음');
      // 열 수: 폰 2 · 태블릿 3 · PC 4
      const cols=await cards.evaluateAll(ns=>new Set(ns.map(n=>Math.round(n.getBoundingClientRect().left))).size);
      assert.equal(cols,width<640?2:width<1024?3:4,`열 수 ${width}px`);
      // 모바일 기준
      assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),`가로 넘침 ${width}px`);
      const chips=page.locator('#services [aria-pressed]');
      assert.equal(await chips.first().evaluate(b=>b.parentElement.scrollWidth<=b.parentElement.clientWidth+1),true,'분류 칩 줄이 가로로 스크롤되지 않음');
      const small=await page.locator('main a[href], main button, footer a, footer button').evaluateAll(ns=>ns.filter(n=>{const r=n.getBoundingClientRect();return r.width&&r.height&&(r.height<44||r.width<44);}).map(n=>n.innerText.trim()||n.getAttribute('aria-label')));
      assert.deepEqual(small,[],'44px 미만 터치 대상');
      const tiny=await page.evaluate(()=>{const out=[],w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);while(w.nextNode()){const n=w.currentNode,t=n.textContent.trim();if(!t||/^\p{Extended_Pictographic}+$/u.test(t)||!n.parentElement)continue;const r=n.parentElement.getBoundingClientRect();if(!r.width)continue;if(parseFloat(getComputedStyle(n.parentElement).fontSize)<13)out.push(t);}return out;});
      assert.deepEqual(tiny,[],'13px 미만 글자');
      if(width<640)assert(parseFloat(await page.locator('#agent textarea').evaluate(t=>getComputedStyle(t).fontSize))>=16,'입력창 16px 이상(아이폰 확대 방지)');
      await page.screenshot({path:path.join(output,`${width}.png`),fullPage:true});
      // 분류 필터
      for(const [name,count] of [['AI Agent',2],['Prototype',4],['API·Search',2],['전체',8]]){
        await chips.filter({hasText:name}).first().click();assert.equal(await cards.count(),count,`${name} 필터`);
      }
      // 권한: 숨김 서비스는 빠지고, 권한 없는 서비스는 자물쇠, 에이전트는 접속 코드 안내
      services={gif:{visible:false,allowed:false},golf:{visible:true,allowed:false},agent:{visible:true,allowed:false}};
      await page.goto(base);await page.waitForFunction(()=>[...document.querySelectorAll('#services a')].filter(a=>a.querySelector('img')).length===7);
      assert.match(await cards.first().innerText(),/🔒/);
      assert.equal(await page.locator('#agent textarea').count(),0);
      assert.match(await page.locator('#agent').innerText(),/접속 코드/);
      assert.deepEqual(errors,[]);await context.close();console.log(`PASS ${width}px: design, card order, columns, overflow, 44px, 13px, filters, access control`);
    }
  }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});

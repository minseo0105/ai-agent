// Verify the exact production homepage renderer; never exercise other agents' APIs.
const {chromium}=require('../reports/analytics-browser/node_modules/playwright');
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),dir=path.join(root,'reports/moneyon-portal');
const portal='https://minseo2-digital-ai-lab.hf.space',money='https://minseo2-moneyon-demo.hf.space/';
const cards='#services a[href]';
const live=process.env.MONEYON_PORTAL_LIVE==='1';
async function cardData(page){return page.locator(cards).evaluateAll(es=>es.map(e=>({href:e.getAttribute('href'),text:e.innerText,classes:e.className})));}
(async()=>{
 fs.mkdirSync(dir,{recursive:true});
 const browser=await chromium.launch({channel:'chrome',headless:true});let server;
 try{
  if(process.argv.includes('--capture-baseline')){
   const p=await browser.newPage();await p.goto(portal);await p.locator(cards).first().waitFor();
   const response=await p.request.get(portal+'/api/access/status');assert(response.ok());const access=await response.json();
   await p.waitForFunction(()=>document.querySelector('#services a[href="/realestate"]'));
   // Wait for settings to hide non-public cards before recording their order.
   await p.waitForFunction(n=>document.querySelectorAll('#services a[href]').length===n,Object.values(access.services).filter(s=>s.visible&&s.id!=='agent').length).catch(()=>{});
   const baseline={cards:await cardData(p),access:{...access,me:null},assets:await p.locator('#services img').evaluateAll(es=>es.map(e=>e.getAttribute('src')))};
   assert(!baseline.cards.some(c=>c.href===money));fs.writeFileSync(path.join(dir,'baseline.json'),JSON.stringify(baseline,null,2));console.log('Captured production portal baseline:',baseline.cards.map(c=>c.href));return;
  }
  const baseline=JSON.parse(fs.readFileSync(path.join(dir,'baseline.json')));
  let origin=portal;
  if(!live){
   const folder=path.join(dir,'local-web/out');
   server=http.createServer(async(req,res)=>{
    try{const name=new URL(req.url,'http://local').pathname;
     if(name==='/api/access/status'){res.setHeader('Content-Type','application/json');return res.end(JSON.stringify(baseline.access));}
     if(name.startsWith('/api/')){res.setHeader('Content-Type','application/json');return res.end('{}');}
     const file=path.resolve(folder,'.'+(name==='/'?'/index.html':name));
     if(!file.startsWith(folder+path.sep)){res.writeHead(403);return res.end();}
     if(fs.existsSync(file)&&fs.statSync(file).isFile()){res.setHeader('Content-Type',({'.html':'text/html','.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'})[path.extname(file)]||'application/octet-stream');return res.end(fs.readFileSync(file));}
     if(baseline.assets.includes(name)){const r=await fetch(portal+name);res.writeHead(r.status,{'Content-Type':r.headers.get('content-type')});return res.end(Buffer.from(await r.arrayBuffer()));}
     res.writeHead(404);res.end();
    }catch(e){res.writeHead(500);res.end(String(e));}
   });await new Promise(r=>server.listen(0,'127.0.0.1',r));origin=`http://127.0.0.1:${server.address().port}`;
  }
  const result=[];
  for(const width of [375,768,1440]){
   const context=await browser.newContext({viewport:{width,height:1000},reducedMotion:'reduce'}),p=await context.newPage();const errors=[];p.on('pageerror',e=>errors.push(e.message));
   await p.goto(origin);const card=p.locator(`#services a[href="${money}"]`);await card.waitFor();
   await p.waitForFunction(n=>document.querySelectorAll('#services a[href]').length===n,baseline.cards.length+1);
   assert.equal(await card.count(),1);const text=await card.innerText();assert(text.includes('MONEY'));assert(text.includes('우루미와 함께하는 어린이 금융 놀이터'));assert(text.includes('용돈을 받고, 쓰고, 저축하면서 이자 보너스를 배워요.'));
   assert.equal(await card.getAttribute('target'),'_blank');assert.match(await card.getAttribute('rel'),/noopener/);
   const current=await cardData(p);assert.deepEqual(current.filter(c=>c.href!==money),baseline.cards,'Other cards changed');assert.equal(current.at(-1).href,money);
   assert.equal(await card.getAttribute('class'),baseline.cards[0].classes);
   await card.locator('img').scrollIntoViewIfNeeded();await p.waitForFunction(()=>{const e=document.querySelector('img[src="/ailab/money.svg"]');return e?.complete&&e.naturalWidth>0;});
   assert(await p.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Horizontal overflow');
   const layout=await card.evaluate(e=>{const s=getComputedStyle(e.parentElement),r=e.getBoundingClientRect();return {columns:s.gridTemplateColumns.split(' ').length,width:r.width,height:r.height,clipped:e.scrollWidth>e.clientWidth+1};});
   assert.equal(layout.columns,width<640?2:width<1024?3:4);assert(!layout.clipped);
   const peer=await p.locator(cards).first().boundingBox();assert(Math.abs(layout.width-peer.width)<1);
   await p.screenshot({path:path.join(dir,`${live?'live':'local'}-${width}.png`),fullPage:true});
   const popupPromise=p.waitForEvent('popup');await card.click();const popup=await popupPromise;await popup.waitForLoadState('domcontentloaded');assert.equal(new URL(popup.url()).origin,new URL(money).origin);await popup.getByRole('button',{name:'바로 체험하기',exact:true}).waitFor();assert.equal(await popup.evaluate(()=>window.opener===null),true);await popup.close();
   await p.getByRole('button',{name:/^Prototype/}).click();assert(await card.isVisible());assert.equal(await p.locator(cards).count(),1);await p.getByRole('button',{name:/^전체/}).click();await card.waitFor();
   assert.deepEqual(errors,[]);result.push({viewport_width:width,...layout,card:true,link:true,other_cards_unchanged:true,filter:true,js_errors:errors});await context.close();
  }
  fs.writeFileSync(path.join(dir,`${live?'live':'local'}-result.json`),JSON.stringify({ok:true,url:origin,results:result},null,2));console.log('PASS MONEY portal:',live?'public':'local',JSON.stringify(result));
 }finally{await browser.close();if(server)await new Promise(r=>server.close(r));}
})().catch(e=>{console.error(e);process.exitCode=1;});

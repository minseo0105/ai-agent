// Actual PostgreSQL SQL/permissions execution in a disposable local WASM database.
// npm install --prefix reports/analytics-browser @electric-sql/pglite
const { PGlite } = require('../reports/analytics-browser/node_modules/@electric-sql/pglite');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname,'..');
const uuid = n => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;

(async()=>{
  const db = new PGlite();
  try {
    await db.exec('CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role;');
    await db.exec(fs.readFileSync(path.join(root,'supabase/migrations/20261002_usage_events.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'supabase/migrations/20261003_usage_dashboard.sql'),'utf8'));
    const bounds = (await db.query("SELECT now() AS now, date_trunc('day', now() AT TIME ZONE 'Asia/Seoul') AT TIME ZONE 'Asia/Seoul' AS start")).rows[0];
    const start = new Date(bounds.start).getTime(), now = new Date(bounds.now).getTime();
    let sequence=0; const current = () => new Date(start+(now-start)/2+(sequence++)).toISOString();
    async function add(sid,service,event_type,action=null,route=null,at=null) {
      await db.query('INSERT INTO public.usage_events(created_at,session_id,service,route,event_type,metadata) VALUES($1,$2,$3,$4,$5,$6)',
        [at||current(),sid?uuid(sid):null,service,route||'/'+service,event_type,JSON.stringify(action?{action}:event_type==='api_error'?{status:502}:{})]);
    }
    const pv = (s,service,route) => add(s,service,'page_view',null,route);
    const search = (s,service) => add(s,service,'search',service==='realestate'?'address_search':'golf_search');
    await pv(1,'realestate'); await pv(1,'realestate'); await search(1,'realestate'); await search(1,'realestate');
    await add(1,'realestate','map_click'); await add(1,'realestate','map_click'); await add(1,'realestate','project_click');
    await add(1,'realestate','external_link_click','naver_land_click'); await add(1,'realestate','external_link_click','naver_land_click');
    await add(1,'realestate','external_link_click','official_source_click');
    await search(2,'realestate'); await pv(2,'realestate'); await add(2,'realestate','project_click');
    await add(2,'realestate','external_link_click','naver_land_click');
    await pv(3,'realestate'); await add(3,'realestate','map_click'); await search(4,'realestate'); // orphan feature event
    await pv(1,'home','/'); await pv(1,'golf'); await pv(1,'golf'); await search(1,'golf'); await pv(1,'golf','/golf/club');
    await pv(5,'golf'); await search(5,'golf'); await search(5,'golf'); await pv(6,'other');
    await add(null,'realestate','api_error',null,'/api/realestate'); await add(null,'golf','api_error',null,'/api/golf');
    const day=86400000;
    await add(7,'home','page_view',null,'/',new Date(start-1).toISOString()); // just before KST midnight
    await add(8,'home','page_view',null,'/',new Date(start-6*day).toISOString()); // inclusive seven-day boundary
    await add(9,'home','page_view',null,'/',new Date(start-6*day-1).toISOString()); // excluded from seven days
    await add(10,'home','page_view',null,'/',new Date(start-29*day).toISOString()); // inclusive 30-day boundary
    await add(11,'home','page_view',null,'/',new Date(start-29*day-1).toISOString()); // excluded from 30 days
    await add(12,'home','page_view',null,'/',new Date(now+day).toISOString()); // future excluded
    const query = async n => (await db.query('SELECT public.usage_dashboard($1) AS summary',[n])).rows[0].summary;
    const today = await query(1), week=await query(7), month=await query(30);
    assert.deepEqual(today.totals,{visits:5,page_views:10,features:7,external:4,errors:2});
    const zip=today.services.find(s=>s.service==='realestate'), golf=today.services.find(s=>s.service==='golf');
    assert.equal(zip.visits,3);assert.equal(zip.page_views,4);assert.equal(zip.features,4);assert.equal(zip.used_sessions,2);
    assert.equal(zip.map_clicks,3);assert.equal(zip.project_clicks,2);assert.equal(zip.naver,3);assert.equal(zip.errors,1);
    assert.deepEqual([zip.funnel_entered,zip.funnel_searched,zip.funnel_engaged,zip.funnel_external],[3,1,1,1]);
    assert.equal(golf.visits,2);assert.equal(golf.page_views,4);assert.equal(golf.features,3);assert.equal(golf.used_sessions,2);
    assert.equal(today.pages.find(p=>p.route==='/golf/club').page_views,1);
    assert.equal(today.pages.find(p=>p.route==='/golf').page_views,3);
    assert.equal(week.totals.page_views,12);assert.equal(month.totals.page_views,14);
    assert.equal(today.recent.length,20);
    assert(!JSON.stringify(today).includes(uuid(1)));assert(!JSON.stringify(today.recent).includes('metadata'));
    await db.exec("SET TIME ZONE 'Pacific/Honolulu'");
    assert.deepEqual((await query(1)).totals,today.totals);
    assert.equal((await db.query("SELECT relrowsecurity FROM pg_class WHERE oid='public.usage_events'::regclass")).rows[0].relrowsecurity,true);
    assert.equal((await db.query("SELECT count(*)::int AS n FROM pg_policies WHERE tablename='usage_events'")).rows[0].n,0);
    for(const role of ['anon','authenticated']) {
      await db.exec(`SET ROLE ${role}`);
      await assert.rejects(query(1),/permission denied/);
      await assert.rejects(db.query('SELECT * FROM public.usage_events'),/permission denied/);
      await db.exec('RESET ROLE');
    }
    await db.exec('SET ROLE service_role');
    await assert.rejects(db.query('SELECT * FROM public.usage_events'),/permission denied/);
    await db.exec('BEGIN READ ONLY');
    assert.deepEqual((await query(1)).totals,today.totals);
    await db.exec('COMMIT; RESET ROLE');
    await assert.rejects(query(2),/Unsupported analytics period/);
    const afterCount=(await db.query('SELECT count(*)::int AS n FROM public.usage_events')).rows[0].n;
    // Save only aggregate fixtures for Python/browser tests, no raw session/event records.
    fs.writeFileSync(path.join(root,'reports/usage-dashboard-fixture.json'),JSON.stringify({today,week,month},null,2));
    await db.exec('TRUNCATE public.usage_events');
    const empty=await query(1); assert.equal(empty.totals.visits,0);assert.equal(empty.recent.length,0);
    await db.query("INSERT INTO public.usage_events(created_at,session_id,service,route,event_type) SELECT $1,$2,'home','/','page_view' FROM generate_series(1,100001)",[current(),uuid(1)]);
    assert.equal((await query(1)).status,'too_many_events','never display a truncated sample as exact totals');
    console.log(`PASS SQL: ${afterCount} fixture rows; exact route/session/action/cohort counts; KST boundaries; recent cap; RLS; read-only execute; overload refusal`);
  } finally {await db.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});

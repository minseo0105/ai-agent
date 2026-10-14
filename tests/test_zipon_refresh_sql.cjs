// Execute the real refresh and existing ingest SQL in disposable PostgreSQL WASM.
// Spatial column stand-ins do NOT test PostGIS predicates; those need staging PostGIS.
const { PGlite } = require('../reports/analytics-browser/node_modules/@electric-sql/pglite');
const fs = require('fs');
const path = require('path');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const uuid = n => `00000000-0000-4000-8000-${String(n).padStart(12,'0')}`;

(async () => {
  const db = new PGlite();
  try {
    await db.exec(`CREATE ROLE anon; CREATE ROLE authenticated; CREATE ROLE service_role BYPASSRLS;
      CREATE SCHEMA extensions; CREATE DOMAIN extensions.geography AS jsonb;
      CREATE TABLE development_collection_runs(run_id uuid PRIMARY KEY,dry_run boolean,status text,
       source_name text,source_type text,collector_version text,started_at timestamptz DEFAULT now(),
       finished_at timestamptz,source_complete boolean,scope jsonb DEFAULT '{}',new_count int DEFAULT 0,
       changed_count int DEFAULT 0,unchanged_count int DEFAULT 0,validation_failed_count int DEFAULT 0);
      CREATE TABLE development_projects(project_id uuid PRIMARY KEY,project_name text,project_type text,
       official_authority text,external_id text,sido text,sigungu text,dong text,address text,
       stage text,stage_raw text,stage_mapping_version text,status text DEFAULT 'UNKNOWN',
       validation_status text DEFAULT 'NEEDS_REVIEW',area_m2 numeric,planned_units int,
       location extensions.geography,location_source text,geometry jsonb,geometry_verified boolean DEFAULT false,
       geometry_source text,geometry_verified_at timestamptz,location_verified_at timestamptz,
       field_evidence jsonb DEFAULT '{}',canonical_source_id uuid,last_verified_at timestamptz,
       notice_date date,source_date date,revision bigint DEFAULT 1,created_at timestamptz DEFAULT now(),
       updated_at timestamptz DEFAULT now(),UNIQUE(official_authority,external_id));
      CREATE TABLE development_project_sources(source_id uuid PRIMARY KEY,project_id uuid REFERENCES development_projects,
       collection_run_id uuid REFERENCES development_collection_runs,source_name text,source_type text,source_url text,
       is_official boolean,external_id text,collected_at timestamptz,content_hash text,raw_snapshot jsonb,
       validation_status text,verified_at timestamptz,verified_by text,evidence jsonb,published_at timestamptz,effective_at timestamptz,
       UNIQUE(project_id,source_url,content_hash,is_official,validation_status));
      ALTER TABLE development_projects ADD FOREIGN KEY(canonical_source_id) REFERENCES development_project_sources;
      CREATE TABLE development_updates(update_id uuid DEFAULT gen_random_uuid() PRIMARY KEY,
       project_id uuid REFERENCES development_projects,source_id uuid REFERENCES development_project_sources,
       collection_run_id uuid REFERENCES development_collection_runs,update_kind text,from_revision bigint,to_revision bigint,
       title text,description text,previous_snapshot jsonb,new_snapshot jsonb,changed_fields text[],event_hash text,
       previous_stage text,new_stage text,previous_status text,new_status text,recorded_at timestamptz DEFAULT now(),
       UNIQUE(project_id,to_revision),UNIQUE(project_id,event_hash));
      GRANT USAGE ON SCHEMA public,extensions TO service_role;
      GRANT SELECT,INSERT,UPDATE ON development_projects,development_collection_runs TO service_role;
      GRANT SELECT,INSERT ON development_project_sources,development_updates TO service_role;`);
    await db.exec(fs.readFileSync(path.join(root,'supabase/migrations/20260927_zipon_incremental_update_rpc.sql'),'utf8'));
    await db.exec(fs.readFileSync(path.join(root,'supabase/migrations/20261014_zipon_live_refresh.sql'),'utf8'));
    const run=uuid(1), pid=uuid(2);
    await db.query("INSERT INTO development_collection_runs(run_id,dry_run,status,collector_version) VALUES($1,false,'RUNNING','zipon-live-refresh-v1')",[run]);
    assert.equal((await db.query('SELECT zipon_refresh_lease($1) AS claimed',[run])).rows[0].claimed,true);
    assert.equal((await db.query('SELECT zipon_refresh_lease($1) AS claimed',[uuid(3)])).rows[0].claimed,false);
    const candidate={project_id:pid,project_name:'검증사업',project_type:'RECONSTRUCTION',sigungu:'강동구',sido:'서울특별시',
      official_authority:'cleanup.seoul.go.kr',external_id:'cafe1',status:'UNKNOWN',validation_status:'NEEDS_REVIEW',stage_raw:'조합설립인가'};
    const source={source_name:'Official',source_type:'OFFICIAL_WEBSITE',source_url:'https://cleanup.seoul.go.kr/list',
      is_official:true,external_id:'cafe1',content_hash:'a'.repeat(64),collected_at:new Date().toISOString(),raw_snapshot:{}};
    const call = async (c,s,o={},revision=0) => (await db.query('SELECT zipon_refresh_project($1,$2,$3,$4,$5) AS result',
      [c,{...s,raw_snapshot:{...s.raw_snapshot,detail:{current_stage:o.stage_raw,cafe_id:o.cafe_id}}},o,revision,run])).rows[0].result;
    await db.exec('SET ROLE service_role');
    let result=await call(candidate,source);
    assert.equal(result.result,'new');
    assert.equal(result.revision,2);
    let row=(await db.query('SELECT * FROM development_projects WHERE project_id=$1',[pid])).rows[0];
    assert.equal(row.stage,null);assert.equal(row.status,'UNKNOWN');
    assert.equal((await call(candidate,source)).result,'unchanged');
    const obs={stage:'IMPLEMENTATION_APPROVED',stage_raw:'사업시행인가',status:'UNKNOWN',
      stage_verified_level:'OFFICIAL_DETAIL_VERIFIED',evidence_url:'https://cleanup.seoul.go.kr/detail?cafeId=123',
      cafe_id:'123',detail_page_matched:true,content_hash:'b'.repeat(64),
      notice_date:'2026-10-01',source_date:'2026-10-01',date_basis:{notice_date:'OFFICIAL_LABEL',source_date:'OFFICIAL_LABEL'}};
    const updated={...source,content_hash:obs.content_hash,source_url:obs.evidence_url};
    result=await call(candidate,updated,obs,2);
    assert.equal(result.result,'changed');
    row=(await db.query('SELECT * FROM development_projects WHERE project_id=$1',[pid])).rows[0];
    assert.equal(row.stage,'IMPLEMENTATION_APPROVED');assert.equal(row.stage_raw,'사업시행인가');
    assert.equal(new Date(row.notice_date).toISOString().slice(0,10),'2026-10-01');
    assert.equal(new Date(row.source_date).toISOString().slice(0,10),'2026-10-01');
    assert.equal((await call(candidate,updated,obs,2)).result,'unchanged');
    const regressed={...obs,stage:'COMMITTEE',stage_raw:'추진위원회승인',content_hash:'c'.repeat(64)};
    assert.equal((await call(candidate,{...updated,content_hash:regressed.content_hash},regressed,3)).reason,'STAGE_REGRESSION_OR_UNORDERED');
    await call(candidate,{...updated,content_hash:regressed.content_hash},regressed,3);
    assert.equal((await db.query('SELECT count(*)::int AS n FROM development_review_queue')).rows[0].n,1);
    const badDate={...obs,notice_date:'26.10.01',content_hash:'d'.repeat(64)};
    assert.equal((await call(candidate,{...updated,content_hash:badDate.content_hash},badDate,3)).reason,'AMBIGUOUS_DATE');
    await db.query("UPDATE development_projects SET validation_status='VERIFIED' WHERE project_id=$1",[pid]);
    const forward={...obs,stage:'MANAGEMENT_DISPOSITION',stage_raw:'관리처분인가',content_hash:'e'.repeat(64)};
    assert.equal((await call(candidate,{...updated,content_hash:forward.content_hash},forward,3)).reason,'VERIFIED_PROTECTED');
    assert.equal((await db.query('SELECT revision::int FROM development_projects WHERE project_id=$1',[pid])).rows[0].revision,3);
    await assert.rejects(call(candidate,{...source,source_url:null}, {},3));
    await db.query("UPDATE development_projects SET validation_status='NEEDS_REVIEW' WHERE project_id=$1",[pid]);
    await assert.rejects(call(candidate,{...updated,content_hash:forward.content_hash},forward,99),/Revision conflict/);
    const duplicate={...candidate,project_id:uuid(4),external_id:'cafe2',project_name:'검증사업조합'};
    assert.equal((await call(duplicate,{...source,external_id:'cafe2'})).reason,'DUPLICATE_SUSPECTED');
    assert.equal((await db.query('SELECT count(*)::int AS n FROM development_projects')).rows[0].n,1);
    // Force a history failure after master/source changes; the whole RPC must roll back.
    await db.exec('RESET ROLE; ALTER TABLE development_updates ADD CONSTRAINT reject_next CHECK(to_revision<4); SET ROLE service_role;');
    await assert.rejects(call(candidate,{...updated,content_hash:forward.content_hash},forward,3));
    assert.equal((await db.query('SELECT stage FROM development_projects WHERE project_id=$1',[pid])).rows[0].stage,'IMPLEMENTATION_APPROVED');
    assert.equal((await db.query("SELECT count(*)::int AS n FROM development_project_sources WHERE content_hash=$1",[forward.content_hash])).rows[0].n,0);
    const dashboard=(await db.query('SELECT zipon_refresh_dashboard() AS data')).rows[0].data;
    assert.equal(dashboard.total,1);assert.equal(dashboard.pending,4);
    await db.exec('RESET ROLE; SET ROLE anon;');
    await assert.rejects(db.query('SELECT zipon_refresh_dashboard()'));
    await assert.rejects(db.query('SELECT * FROM development_review_queue'));
    console.log('PASS: PostgreSQL refresh, master update, review dedupe, VERIFIED protection, atomic rollback, lease and permissions (PostGIS not exercised)');
  } finally { await db.close(); }
})().catch(e=>{console.error(e);process.exitCode=1;});

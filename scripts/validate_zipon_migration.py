"""Offline SQL/PLpgSQL parser and compatibility checks. No DB connection or mutation.

Usage: python -B scripts/validate_zipon_migration.py --parser-path <isolated-pglast-directory>
"""
import argparse
import json
from pathlib import Path
import sys

ap=argparse.ArgumentParser()
ap.add_argument('--parser-path')
args=ap.parse_args()
if args.parser_path: sys.path.insert(0,args.parser_path)
from pglast import parser

ROOT=Path(__file__).resolve().parents[1]
MIG=ROOT/'supabase/migrations/20260926_zipon_base_and_development.sql'
ROLL=ROOT/'supabase/review/20260926_zipon_rollback_review.sql'
CHECK=ROOT/'supabase/review/20260926_zipon_postcheck.sql'
def ast(path):return json.loads(parser.parse_sql_json(path.read_text(encoding='utf-8')))['stmts']
def strip_positions(x):
    if isinstance(x,dict):return {k:strip_positions(v) for k,v in x.items() if k not in {'location','stmt_location','stmt_len'}}
    if isinstance(x,list):return [strip_positions(v) for v in x]
    return x
def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values():yield from walk(v)
    elif isinstance(x,list):
        for v in x:yield from walk(v)
def creates(stmts):return {x['stmt']['CreateStmt']['relation']['relname']:x['stmt']['CreateStmt'] for x in stmts if 'CreateStmt' in x['stmt']}

statements=ast(MIG); tables=creates(statements); base=creates(ast(ROOT/'supabase/schema.sql'))
assert len(tables)==9
for name,definition in base.items():
    assert strip_positions(definition)==strip_positions(tables[name]),f'Backend table drift: {name}'

for file in [MIG,ROLL,CHECK]:
    nodes=ast(file)
    # PostgreSQL grammar and anonymous block grammar, without any SQL execution.
    parser.parse_plpgsql_json(file.read_text(encoding='utf-8'))
    for node in walk(nodes):
        assert not ({'DropStmt','DeleteStmt','TruncateStmt','InsertStmt','UpdateStmt'} & node.keys()),f'Destructive/data statement: {file.name}'
    print(f'PASS {file.name}: PostgreSQL and PL/pgSQL syntax, {len(nodes)} statements; no DML/DROP/TRUNCATE')

seen=set()
for stmt in statements:
    create=stmt['stmt'].get('CreateStmt')
    if not create:continue
    name=create['relation']['relname'];seen.add(name)
    assert create['relation']['schemaname']=='public' and create.get('if_not_exists')
    for node in walk(create):
        con=node.get('Constraint',{})
        if con.get('contype')=='CONSTR_FOREIGN':
            ref=con['pktable'];assert ref['schemaname']=='public' and ref['relname'] in seen,(name,ref)
    for node in walk(create):
        t=node.get('typeName',{})
        names=[v['String']['sval'] for v in t.get('names',[])]
        if names and names[-1] in {'geometry','geography'}:assert names[0]=='extensions'

text=MIG.read_text(encoding='utf-8')
for name in tables:
    assert f'ALTER TABLE public.{name} ENABLE ROW LEVEL SECURITY;' in text
    assert f'REVOKE ALL PRIVILEGES ON TABLE public.{name} FROM PUBLIC, anon, authenticated, service_role;' in text
assert text.index('CREATE TABLE IF NOT EXISTS public.development_project_sources') < text.index('ADD CONSTRAINT development_projects_canonical_source_fk')
assert 'USING gist(location)' in text and 'USING gist(geometry)' in text and 'gist((geometry::extensions.geography))' in text
assert 'GRANT SELECT, INSERT ON TABLE public.development_project_sources, public.development_updates TO service_role;' in text
assert not any('TO anon' in line or 'TO authenticated' in line or 'TO PUBLIC' in line for line in text.splitlines() if line.startswith('GRANT'))
assert "source_priority smallint GENERATED ALWAYS AS (CASE WHEN is_official THEN 100 ELSE 10 END) STORED" in text
print('PASS: 4 legacy table ASTs identical; 9 public tables; FK creation order; extensions-qualified spatial types; GiST indexes; RLS; backend-only grants; append-only provenance/history')
print('LIMIT: offline parsing does not prove server object/function resolution, DDL execution, RLS enforcement, or REST write compatibility. New-project postcheck still required.')

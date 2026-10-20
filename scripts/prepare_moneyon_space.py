"""Build an allowlisted, credential-free HF upload folder. Never uploads."""
import argparse
import hashlib
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=[
    'api/__init__.py','api/access.py','api/moneyon.py','api/moneyon_trial.py',
    'services/__init__.py','services/access.py','services/config.py','services/supabase_auth.py',
    'services/moneyon.py','services/moneyon_accounts.py','services/moneyon_banking.py',
    'services/moneyon_demo.py','services/moneyon_trial.py','services/moneyon_savings.py',
]
WEB=['package.json','package-lock.json','tsconfig.json','next-env.d.ts','next.config.ts','postcss.config.mjs',
     'src/app/globals.css','src/lib/access.ts','src/lib/moneyonCoach.ts','public/moneyon/characters/izani-bee.png']
CHILD=['SavingsBooks.tsx','RewardSaving.tsx','TrialExperience.tsx','ChildExperience.tsx','WeeklyJourney.tsx','Banking.tsx','KidIcon.tsx','Woorumi.tsx','Izani.tsx','TrialSheet.tsx','blue.css','types.ts','child.css','moneyon.css','banking.css']


def prepare(destination):
    destination=Path(destination).resolve()
    if destination.exists():
        raise ValueError('Use a new empty output path; existing folders are never overwritten.')
    destination.mkdir(parents=True)
    def copy(source,target):
        source=ROOT/source
        if source.is_symlink():raise ValueError('Symlink sources are not allowed')
        target=destination/target
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,target)
    for file in RUNTIME:copy(file,file)
    for file in WEB:copy('web/'+file,'web/'+file)
    for file in CHILD:copy('web/src/app/moneyon/'+file,'web/src/app/moneyon/'+file)
    for file in ('Dockerfile','requirements.txt','README.md','space_app.py'):copy('deploy/moneyon/'+file,file)
    copy('deploy/moneyon/layout.tsx','web/src/app/layout.tsx')
    for target in ('web/src/app/page.tsx','web/src/app/moneyon/page.tsx'):copy('deploy/moneyon/page.tsx',target)
    (destination/'.dockerignore').write_text('**/node_modules\n**/.next*\n**/out\n**/__pycache__\n**/*.pyc\n**/.env*\n**/*.sqlite*\nruntime/\n.git/\n',encoding='utf-8')
    manifest={str(p.relative_to(destination)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(destination.rglob('*')) if p.is_file()}
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True)
    args=parser.parse_args()
    print(json.dumps({'files':len(prepare(args.output)),'output':str(Path(args.output).resolve()),'uploaded':False}))

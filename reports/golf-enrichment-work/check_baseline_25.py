import zipfile,os,sys,unittest,subprocess,json
from pathlib import Path
stage=Path(__file__).parent;base=stage/'baseline-5e9730c9';base.mkdir(exist_ok=True)
with zipfile.ZipFile(stage/'baseline-5e9730c9.zip') as archive:
 for name in archive.namelist():
  if not (base/name).resolve().is_relative_to(base.resolve()):raise ValueError('Invalid archive path')
 archive.extractall(base)
os.chdir(base);sys.path.insert(0,str(base))
original=subprocess.check_output
def git_root(args,*a,**kw):
 if args[:2]==['git','show']:args=['git','-C',str(Path(__file__).resolve().parents[2])]+args[1:]
 return original(args,*a,**kw)
subprocess.check_output=git_root
s=unittest.defaultTestLoader.discover('tests',pattern='test_golf*.py');r=unittest.TestResult();s.run(r)
report={'baseline_commit':'5e9730c9','tests':r.testsRun,'failures':[(str(t),e[:650]) for t,e in r.failures],'errors':[(str(t),e[:650]) for t,e in r.errors]}
(stage/'baseline-test-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))

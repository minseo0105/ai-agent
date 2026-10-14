"""Production runner; dry-run by default, ZIP-only DB and explicit write gate."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.development_refresh import refresh, RefreshError


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job',choices=['daily','weekly','monthly','canary'],default='weekly')
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--limit',type=int,default=10)
    parser.add_argument('--out',default='reports/zipon-refresh')
    args=parser.parse_args()
    try:
        report=refresh(job=args.job,apply=args.apply,limit=args.limit,directory=args.out)
        print(json.dumps({k:report[k] for k in ('run_id','status','dry_run','counts')},ensure_ascii=False))
        return 0 if report['status']=='SUCCEEDED' else 1
    except RefreshError as exc:
        report={'status':'CONFIG_REQUIRED','code':str(exc),'dry_run':not args.apply}
        out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
        (out/'report.json').write_text(json.dumps(report),encoding='utf-8')
        print(json.dumps(report))
        return 2


if __name__=='__main__':
    sys.exit(main())

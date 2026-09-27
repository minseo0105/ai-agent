"""Offline only: raw pilot -> conservative canonical/review/quality artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.development_quality import refine
ROOT=Path(__file__).resolve().parents[1]
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--input',type=Path,default=ROOT/'data/development/pilot_20260927.json')
    args=ap.parse_args()
    raw=args.input.read_bytes();original_hash=hashlib.sha256(raw).hexdigest()
    canary=json.loads((ROOT/'data/development/canary_20260927.json').read_text(encoding='utf-8'))['records']
    canonical,review,quality=refine(json.loads(raw)['records'],canary)
    quality['original_sha256']=original_hash
    for name,data in [('pilot_canonical',canonical),('pilot_duplicate_review',review),('pilot_quality_report',quality)]:
        (ROOT/f'data/development/{name}_20260927.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    assert hashlib.sha256(args.input.read_bytes()).hexdigest()==original_hash
    lines=['# ZIP:ON pilot quality — 2026-09-27','',
      f"원본 {quality['original_candidates']}건 → canonical {quality['canonical_projects']}건. 확정 중복 제거 {quality['exact_duplicates_merged']}건.",
      f"검토 대상 {quality['probable_duplicate_pairs']}쌍 / {quality['probable_canonical_projects']}개 canonical. 자동 병합하지 않음.",'',
      'Canonical은 관리용 identity 단위이며 실제 고유 사업 수가 확정되었다는 의미가 아닙니다.',
      'UNIQUE도 현재 비교 근거에서 중복을 찾지 못했다는 뜻입니다. 원본·모든 출처·원문 단계는 보존했습니다.','',
      '## 품질','']
    for key,val in quality['quality'].items():lines.append(f"- {key}: {val['count']}/{val['total']} ({val['percent']}%)")
    lines+=['','## 검토 및 import','',
      'pilot_duplicate_review_20260927.json의 후보쌍을 공식 ID/주소/사업구역 기준으로 확인하세요. 이름 유사성만으로 병합하지 않습니다.',
      'FAST_TRACK은 정제 표준명이며 기존 DB 전송 시 SHINTONG으로 매핑합니다. 기존 DB schema 변경은 없습니다.',
      'canonical_id와 기존 DB project_id는 별개입니다. import_plan.db_project_id 및 candidate_ids를 사용해 이미 import한 Canary를 재생성하지 마세요.',
      'canonical 파일은 기존 importer의 records 입력이 아닙니다. source별 관측을 보존하는 adapter와 검토를 거쳐 최대 10건씩 별도 승인 후 전달해야 합니다.',
      '프로젝트별 import_plan과 원본 raw_candidates가 있어 batch 변환이 가능하지만 이번 작업에서 import 파일 자동 제출이나 DB 접속은 하지 않았습니다.','',
      '## 공간정보 전략','',
      '공식 좌표를 우선하고, 없으면 정확한 주소 기반 geocoding을 합니다. 동일 주소/공급자/버전의 유효 cache는 재사용합니다.',
      '여러 후보가 나오거나 동 중심점만 있으면 unresolved로 남깁니다. 첫 검색 결과를 자동 확정하지 않습니다.',
      'latitude / longitude / geocode_source / geocode_confidence / geocoded_at / address_used를 저장하는 계약을 spatial_verification에 명시했습니다.',
      '공식 GIS 경계와 검증 근거가 있어야 verified polygon을 인정하며 임의 polygon은 만들지 않습니다.','',
      '원본 및 Canary 변경 없음. 외부 API 호출, DB write, migration, 운영 배포 없음.']
    (ROOT/'docs/zipon_pilot_quality_20260927.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in quality.items() if k not in ('anomalies','original_sha256')},ensure_ascii=True))
if __name__=='__main__':main()

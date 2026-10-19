from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).parent
p='web/src/components/golf/GolfSearch.tsx';s=(ROOT/p).read_text(encoding='utf-8')
s=s.replace('지역 · 주중/주말 · 인원 · 예산 · 캐디 · 야간 조건을 읽습니다.','지역 · 주중/주말 · 3·4인 · 그린피 예산 · 캐디 · 야간 조건을 읽습니다.')
s=s.replace('‘페어웨이 넓음’ 등 후기 기반 특징은 아직 확정 필터로 지원하지 않습니다.','2인 · 연습장 · PAR3 · ‘페어웨이 넓음’ 등 후기 특징은 아직 검색 필터로 지원하지 않습니다.')
(OUT/p).write_text(s,encoding='utf-8')
s=subprocess.check_output(['git','show','HEAD:CLAUDE.md'],cwd=ROOT).decode('utf-8')
s+='\nLatest changes: read docs/golf_applied_2026-09-25.md for search integrity, 25 added fields, 13 reviewed observations, 4 rejected candidates, price quarantine, regression baseline, and deployment verification. Keep the 243 recommendation record IDs; suspected duplicate identities need separate review.\n'
(OUT/'CLAUDE.md').write_text(s,encoding='utf-8')

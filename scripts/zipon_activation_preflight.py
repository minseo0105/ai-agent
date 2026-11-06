"""ZIP:ON 실시간 갱신 활성화 사전점검 (읽기 전용).

저장소 안의 준비 상태만 확인한다. DB·네트워크·GitHub 호출은 하지 않고, Secret 값도
읽거나 출력하지 않는다(이름의 설정 여부만 본다). GitHub 저장소 변수/Secret의 실제 설정은
이 스크립트가 알 수 없으므로 '사용자 확인' 항목으로 남긴다.

    python scripts/zipon_activation_preflight.py

종료 코드: 0 = 저장소 준비 완료(사용자 단계가 남아 있을 수 있음), 1 = 저장소 쪽 문제.
"""
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = '.github/workflows/zipon-development-refresh.yml'
REQUIRED_FILES = (
    WORKFLOW,
    'scripts/refresh_zipon_live.py',
    'requirements-zipon-refresh.txt',
    'supabase/migrations/20261014_zipon_live_refresh.sql',
    'supabase/review/20261014_zipon_refresh_readonly.sql',
)
# 워크플로가 실제로 지켜야 하는 안전 게이트. 하나라도 사라지면 활성화하면 안 된다.
GATE_TOKENS = ('ZIPON_REFRESH_ENABLED', 'ZIPON_CANARY_VERIFIED', 'ZIPON_REFRESH_WRITE_ENABLED',
               'workflow_dispatch')
SECRET_NAMES = ('ZIPON_IMPORT_SUPABASE_URL', 'ZIPON_IMPORT_SUPABASE_KEY')
USER_STEPS = (
    ('Supabase', '읽기 전용 SQL(20261014_zipon_refresh_readonly.sql) 실행 후 개수를 기록하고, '
                 '스테이징 검증 뒤 20261014_zipon_live_refresh.sql 설치, Storage에 비공개 버킷 '
                 'zipon-official-raw 생성'),
    ('GitHub Secrets', 'ZIPON_IMPORT_SUPABASE_URL / ZIPON_IMPORT_SUPABASE_KEY 추가 '
                       '(값은 채팅에 붙여넣지 않기). 이 단계에서는 REFRESH_ENABLED·CANARY_VERIFIED를 켜지 않기'),
    ('GitHub Actions', 'ZIP development refresh → Run workflow: job=canary, apply=false, limit=1 '
                       '(dry-run) → 결과 확인 → WRITE_ENABLED=true 후 apply=true, limit=1 → '
                       '실제 쓰기와 전후 개수·이력이 맞으면 CANARY_VERIFIED=true, REFRESH_ENABLED=true'),
)


def check(root=ROOT, env=None):
    """(저장소 문제 목록, 환경 경고 목록, 정보 목록)을 돌려준다."""
    env = os.environ if env is None else env
    problems, warnings, info = [], [], []
    for relative in REQUIRED_FILES:
        if not (root / relative).is_file():
            problems.append(f'없음: {relative}')
    workflow = root / WORKFLOW
    if workflow.is_file():
        text = workflow.read_text(encoding='utf-8')
        for token in GATE_TOKENS:
            if token not in text:
                problems.append(f'워크플로에서 안전 게이트가 사라졌어요: {token}')
        info.append('워크플로 스케줄: ' + (', '.join(
            line.split(':', 1)[1].strip().strip("'") for line in text.splitlines()
            if line.strip().startswith('- cron:')) or '없음'))
    for name in SECRET_NAMES:
        if not env.get(name):
            warnings.append(f'이 환경에는 {name}이 설정돼 있지 않아요 (로컬 실행 시에만 필요, 값은 출력하지 않음)')
    return problems, warnings, info


def main(root=ROOT, env=None, out=None):
    out = out or sys.stdout
    problems, warnings, info = check(root, env)
    print('ZIP:ON 활성화 사전점검 (읽기 전용 · DB/네트워크 호출 없음)', file=out)
    for line in info:
        print(f'  · {line}', file=out)
    print(f'\n[저장소 준비] {"문제 있음" if problems else "이상 없음"}', file=out)
    for line in problems:
        print(f'  ✗ {line}', file=out)
    for line in warnings:
        print(f'  ! {line}', file=out)
    print('\n[사용자가 직접 해야 하는 단계] 이 스크립트는 아래 설정을 확인할 수 없어요.', file=out)
    for number, (where, what) in enumerate(USER_STEPS, 1):
        print(f'  {number}. {where}: {what}', file=out)
    print('\n상세 절차: docs/zipon_live_refresh.md · 현재 상태는 LIVE_VERIFIED가 아닙니다.', file=out)
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())

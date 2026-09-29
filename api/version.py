"""배포된 판을 실행 중인 프로세스에서 읽어 온다.

commit 값을 코드에 적어 두지 않는다. 적어 두면 push는 됐는데 배포는 안 된 상태에서도
새 버전처럼 보인다. 저장소의 .git을 그대로 읽어 실제로 돌고 있는 판을 말한다.

읽을 수 없으면 만들어 내지 않는다. commit은 None이고 source가 그 이유를 말한다.
"""
import os
import time
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# 프로세스가 시작된 시각. 배포가 실제로 갈렸는지 구분하는 데 쓴다.
STARTED_AT = time.time()


def _head_commit(root):
    """.git에서 지금 체크아웃된 commit을 읽는다. 없으면 None."""
    git = root / '.git'
    if not git.is_dir():
        return None, 'NO_GIT_DIRECTORY'
    try:
        head = (git / 'HEAD').read_text(encoding='utf-8').strip()
    except OSError:
        return None, 'HEAD_UNREADABLE'
    if not head.startswith('ref:'):
        # detached HEAD. 그 자체가 commit이다.
        return (head or None), ('DETACHED_HEAD' if head else 'HEAD_EMPTY')
    ref = head.split(':', 1)[1].strip()
    try:
        return (git / ref).read_text(encoding='utf-8').strip(), 'GIT_REF'
    except OSError:
        pass
    # 느슨한 ref가 없으면 packed-refs를 본다.
    try:
        for line in (git / 'packed-refs').read_text(encoding='utf-8').splitlines():
            if line.startswith('#') or ' ' not in line:
                continue
            sha, name = line.split(' ', 1)
            if name.strip() == ref:
                return sha.strip(), 'GIT_PACKED_REFS'
    except OSError:
        pass
    return None, 'REF_UNREADABLE'


@lru_cache(maxsize=1)
def build_identity():
    """실행 중인 판. 알 수 없는 값은 None으로 두고 이유를 남긴다."""
    commit, source = _head_commit(ROOT)
    # 배포 환경이 판 번호를 직접 주면 그것을 우선한다(코드에 적는 것이 아니다).
    supplied = (os.environ.get('AILAB_BUILD_ID') or '').strip()
    return {
        'commit': (commit[:7] if commit else None),
        'commit_full': commit,
        'commit_source': 'ENVIRONMENT' if supplied else source,
        'build_id': supplied or None,
        # 이 프로세스가 언제 떴는지. 새 배포인지 같은 컨테이너인지 구분할 수 있다.
        'started_at': int(STARTED_AT),
        'uptime_seconds': None,
    }


def version_block():
    identity = dict(build_identity())
    identity['uptime_seconds'] = int(time.time() - STARTED_AT)
    return identity

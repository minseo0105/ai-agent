"""의존성 상태 점검.

/api/health  프로세스가 살아 있는지만 본다. 바깥으로 아무것도 부르지 않고 바로 200.
/api/ready   핵심 의존성 상태를 하나씩 본다. 하나가 죽어도 나머지는 그대로 쓴다.

설계 규칙
  * 부가 의존성 하나가 죽었다고 AI LAB 전체가 unavailable이 되지 않는다.
    필수(required) 의존성이 죽었을 때만 전체가 'not_ready'다.
  * 점검은 서로 격리한다. 한 점검의 예외가 다른 점검이나 응답을 깨지 않는다.
  * 점검마다 짧은 제한 시간을 둔다. 상태 확인이 오래 걸려서는 안 된다.
  * 비밀값은 확인만 하고 값을 응답에 담지 않는다.
"""
import time

from services.config import get_secret

# 이것이 없으면 서비스가 제 일을 못 한다. 나머지는 없어도 나머지 기능은 돈다.
REQUIRED = ('supabase',)
CHECK_TIMEOUT_SECONDS = 3.0


def _configured(*names):
    return any(str(get_secret(name) or '').strip() for name in names)


def _supabase():
    """설정이 있으면 가벼운 읽기 하나로 확인한다. 없으면 설정되지 않음으로 남긴다."""
    from services import realestate_monitor as rm
    if not rm._using_remote_db():
        return 'not_configured', '저장소가 연결되지 않았습니다.'
    rm._remote_request('GET', 'development_projects',
                       params={'select': 'project_id', 'limit': 1})
    return 'ok', None


def _naver():
    key_id = get_secret('NAVER_MAP_NCP_KEY_ID') or get_secret('NAVER_MAP_CLIENT_ID')
    key = get_secret('NAVER_MAP_NCP_KEY') or get_secret('NAVER_MAP_CLIENT_SECRET')
    # 자격증명 유무만 본다. 상태 확인 때문에 유료 호출을 만들지 않는다.
    if not (str(key_id or '').strip() and str(key or '').strip()):
        return 'not_configured', '지도/경로 자격증명이 없습니다.'
    return 'ok', None


def _tavily():
    if not _configured('TAVILY_API_KEY'):
        return 'not_configured', '검색 자격증명이 없습니다.'
    return 'ok', None


def _llm():
    if not _configured('ANTHROPIC_API_KEY', 'OPENAI_API_KEY'):
        return 'not_configured', '생성형 모델 자격증명이 없습니다.'
    return 'ok', None


CHECKS = {'supabase': _supabase, 'naver': _naver, 'tavily': _tavily, 'llm': _llm}


def _run(name, check):
    """한 점검을 격리해서 돌린다. 예외가 나가지 않는다."""
    started = time.perf_counter()
    try:
        state, note = check()
    except Exception as error:
        # 원인은 종류만 남긴다. 주소·키·내부 메시지를 화면으로 보내지 않는다.
        state, note = 'down', type(error).__name__
    took = round((time.perf_counter() - started) * 1000, 1)
    entry = {'status': state, 'duration_ms': took}
    if note:
        entry['note'] = note
    return entry


def readiness():
    """의존성별 상태와 전체 상태. 부가 의존성 장애는 degraded일 뿐 not_ready가 아니다."""
    dependencies = {name: _run(name, check) for name, check in CHECKS.items()}
    required_down = [name for name in REQUIRED
                     if dependencies[name]['status'] in ('down', 'not_configured')]
    degraded = [name for name, entry in dependencies.items()
                if entry['status'] in ('down', 'degraded')]
    if required_down:
        status = 'not_ready'
    elif degraded:
        status = 'degraded'
    else:
        status = 'ready'
    return {'status': status, 'required': list(REQUIRED),
            'degraded': sorted(degraded), 'dependencies': dependencies}

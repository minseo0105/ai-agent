"""부하 테스트(scripts/demo_load_test.py)가 만든 머니온 체험만 지운다. moneyon 컨테이너 안에서 실행한다.

  scp scripts/demo_load_cleanup.py ailab:/tmp/ && ssh ailab 'docker cp /tmp/demo_load_cleanup.py moneyon:/tmp/ &&
      docker exec -i -w /home/user/app moneyon python /tmp/demo_load_cleanup.py' < load_tokens.txt

토큰 원문은 출력하지 않는다. 체험마다 SHA-256(DB에 저장된 값)으로 찾아 그 체험의 통장·기록을 지운 뒤, 남은 예시 통장 수를 알려 준다.
"""
import os
import sys

sys.path.insert(0, os.getcwd())
from api.moneyon_trial import trials  # noqa: E402


def main(lines):
    service = trials()
    digests = [service.digest(t.strip()) for t in lines if t.strip()]
    removed = 0
    with service.ledger.db() as db:
        for d in digests:
            if db.execute("SELECT 1 FROM trial_visitors WHERE capability=?", (d,)).fetchone():
                removed += 1
            service._purge(db, d)
        marks = ",".join("?" * len(digests))
        left = db.execute(f"SELECT COUNT(*) FROM trial_visitors WHERE capability IN ({marks})", digests).fetchone()[0] if digests else 0
    print(f"tokens={len(digests)} removed={removed} still_there={left} pooled={service.pooled()}")


if __name__ == "__main__":
    main(sys.stdin.read().splitlines())

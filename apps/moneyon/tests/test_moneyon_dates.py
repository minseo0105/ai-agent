r"""MONEY:ON 체험 날짜 테스트(오프라인). 새 기록은 실제 한국시간 오늘 날짜·시각, 예시 기록은 이번 주 월요일.
자정 전후·UTC와 한국 날짜가 다른 시각(UTC 15:00~24:00 = 한국 다음 날 00~09시)을 포함한다.
실행: apps/moneyon에서 ..\..\..\..\.venv\Scripts\python.exe -B -m unittest tests.test_moneyon_dates -v
"""
import shutil
import tempfile
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from services import moneyon_accounts as accounts
from services import moneyon_trial as mt
from services.moneyon_trial import TrialLedger, Trials

UTC = timezone.utc


def frozen(instant: datetime):
    """datetime.now(tz)이 instant(UTC)를 그 시간대로 돌려주게."""
    class Fixed(datetime):
        @classmethod
        def now(cls, tz=None):
            return instant.astimezone(tz) if tz else instant.replace(tzinfo=None)
    return Fixed


class DatesBase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.ledger = TrialLedger(self.tmp / 'trial.sqlite3')

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def service(self, today):
        return Trials(self.ledger, today=lambda: today)

    def txs(self, snap):
        return sorted(snap['state']['transactions'], key=lambda t: t['created'])


class SeedTodayTest(DatesBase):
    def test_new_trial_day_is_today_and_examples_are_this_monday(self):
        today = date(2026, 10, 29)  # 목요일
        s = self.service(today)
        token = s.start(cleanup=0)['token']
        snap = s.snapshot(s.resolve(token))
        self.assertEqual(snap['day'], '2026-10-29')
        days = {t['created'][:10] for t in snap['state']['transactions']}
        self.assertEqual(days, {'2026-10-19', '2026-10-26'})  # 지난주 월요일 용돈 + 이번 주 월요일 예시 기록
        edu = snap['state']['education']
        self.assertEqual((edu['start'], edu['end']), ('2026-10-26', '2026-11-02'))  # 이번 주(월~일) → 4일째, D-4
        row = s.resolve(token)
        s.allowance(row, 5000, 'k1')
        s.ledger.transact(row['family'], row['child'], 'expense', 'k2', 1000, '간식', '간식', today=s.day(row))
        last = self.txs(s.snapshot(s.resolve(token)))
        self.assertEqual([t['created'][:10] for t in last[-2:]], ['2026-10-29', '2026-10-29'])  # 새 기록 = 오늘
        self.assertTrue(all(t['created'].endswith('+09:00') for t in last))
        self.assertEqual([t['created'] for t in last], sorted(t['created'] for t in last))  # 예시 → 오늘 순서

    def test_monday_seed_and_records_same_day(self):
        s = self.service(date(2026, 11, 2))  # 월요일
        token = s.start(cleanup=0)['token']
        snap = s.snapshot(s.resolve(token))
        self.assertEqual(snap['day'], '2026-11-02')
        self.assertEqual(snap['state']['education']['start'], '2026-11-02')


class MidnightTest(DatesBase):
    def test_kst_today_differs_from_utc_date(self):
        # UTC 10/29 15:30 = 한국 10/30 00:30 → 한국 날짜 10/30
        with mock.patch.object(mt, 'datetime', frozen(datetime(2026, 10, 29, 15, 30, tzinfo=UTC))):
            self.assertEqual(mt.kst_today(), date(2026, 10, 30))
        # UTC 10/29 14:59 = 한국 10/29 23:59 → 아직 10/29
        with mock.patch.object(mt, 'datetime', frozen(datetime(2026, 10, 29, 14, 59, tzinfo=UTC))):
            self.assertEqual(mt.kst_today(), date(2026, 10, 29))

    def test_record_created_after_kst_midnight_is_new_kst_day(self):
        before = datetime(2026, 10, 29, 14, 59, tzinfo=UTC)  # 한국 23:59
        after = datetime(2026, 10, 29, 15, 1, tzinfo=UTC)    # 한국 00:01 (UTC로는 아직 10/29)
        with mock.patch.object(mt, 'datetime', frozen(before)), mock.patch.object(accounts, 'datetime', frozen(before)):
            s = Trials(self.ledger)
            token = s.start(cleanup=0)['token']
            row = s.resolve(token)
            s.allowance(row, 1000, 'before')
        with mock.patch.object(mt, 'datetime', frozen(after)), mock.patch.object(accounts, 'datetime', frozen(after)):
            s = Trials(self.ledger)
            row = s.resolve(token)  # 자정을 넘겼으니 체험일도 한국 오늘로
            self.assertEqual(s.day(row), date(2026, 10, 30))
            s.allowance(row, 1000, 'after')
        with self.ledger.db() as db:
            got = dict(db.execute("SELECT request_key, created FROM transactions WHERE request_key IN ('before','after')").fetchall())
        self.assertTrue(got['before'].startswith('2026-10-29T23:59'), got)
        self.assertTrue(got['after'].startswith('2026-10-30T00:01'), got)
        self.assertTrue(got['after'].endswith('+09:00'))


class CatchUpTest(DatesBase):
    def test_trial_left_open_across_week_follows_real_today(self):
        token = self.service(date(2026, 10, 29)).start(cleanup=0)['token']
        s = self.service(date(2026, 11, 3))  # 다음 주 화요일
        snap = s.snapshot(s.resolve(token))
        self.assertEqual(snap['day'], '2026-11-03')
        edu = snap['state']['education']
        self.assertEqual((edu['start'], edu['end']), ('2026-11-02', '2026-11-09'))  # 2일째, D-6
        with self.ledger.db() as db:
            closed = db.execute('SELECT COUNT(*) FROM trial_closings WHERE child=?', (s.resolve(token)['child'],)).fetchone()[0]
        self.assertGreater(closed, 0)  # 지난주 이자 마감(받을 이자)

    def test_time_travel_ahead_and_old_fixed_trials_stay(self):
        s = self.service(date(2026, 10, 29))
        token = s.start(cleanup=0)['token']
        s.advance(s.resolve(token), date(2026, 11, 5))  # '일주일 뒤 보기'
        self.assertEqual(s.day(s.resolve(token)), date(2026, 11, 5))  # 실제 오늘보다 앞이면 그대로
        # 예전 고정 날짜 체험(실제 날짜 표시 없음)은 따라가지 않는다
        row = s.resolve(token)
        with self.ledger.db() as db:
            db.execute('DELETE FROM trial_clock WHERE family=?', (row['family'],))
            db.execute('UPDATE moneyon_demo_workspaces SET business_date=? WHERE family=?', ('2026-10-12', row['family']))
        self.assertEqual(self.service(date(2026, 10, 29)).day(s.resolve(token)), date(2026, 10, 12))


class PoolTest(DatesBase):
    def test_only_this_weeks_samples_are_handed_out(self):
        self.service(date(2026, 10, 22)).refill(1)  # 지난주 예시
        s = self.service(date(2026, 10, 29))
        self.assertEqual(s.pooled(), 0)  # 지난주 예시는 정리
        s.refill(1)  # 이번 주 화요일에 만든 것처럼
        with self.ledger.db() as db:
            db.execute('UPDATE moneyon_demo_workspaces SET business_date=? WHERE owner=?', ('2026-10-27', mt.POOL))
        snap = s.start(cleanup=0)
        self.assertEqual(snap['day'], '2026-10-29')  # 받으면 체험일 = 오늘
        self.assertEqual(s.pooled(), 0)
        self.assertEqual(mt.POOL, 'pool:v3')
        self.assertIn('pool:v2', mt.LEGACY_POOLS)  # 고정 날짜(10/12) 예시는 쓰지 않고 정리


if __name__ == '__main__':
    unittest.main()

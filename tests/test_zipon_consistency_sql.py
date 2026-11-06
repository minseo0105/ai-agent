"""1차 대시보드 정합성 SQL은 읽기 전용이어야 한다(운영 DB 변경 금지)."""
import re
import unittest
from pathlib import Path

SQL = Path(__file__).resolve().parent.parent / "supabase/review/20261106_zipon_dashboard_consistency_readonly.sql"


class ConsistencySqlTests(unittest.TestCase):
    def setUp(self):
        text = SQL.read_text(encoding="utf-8")
        self.code = "\n".join(line.split("--", 1)[0] for line in text.splitlines())

    def test_read_only_transaction_and_rollback(self):
        self.assertRegex(self.code, r"BEGIN TRANSACTION READ ONLY;")
        self.assertTrue(self.code.strip().endswith("ROLLBACK;"))

    def test_no_write_or_ddl_or_rpc(self):
        for word in ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE", "GRANT", "REVOKE", "COPY"):
            self.assertNotRegex(self.code, rf"\b{word}\b", word)
        self.assertNotRegex(self.code, r"zipon_(ingest|set_project|refresh)", "쓰기 RPC 호출 금지")

    def test_every_statement_is_select_or_txn(self):
        for stmt in [s.strip() for s in self.code.split(";") if s.strip()]:
            self.assertRegex(stmt, r"^(SELECT|BEGIN TRANSACTION READ ONLY|ROLLBACK)\b")


if __name__ == "__main__":
    unittest.main()

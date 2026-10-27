"""Replaceable banking boundary; the only implementation is an offline mock."""
from typing import Protocol

from services import moneyon_accounts as accounts

MERCHANTS = {'편의점': ('간식', 2000), '문구점': ('문구', 4000), '서점': ('책', 5000), '게임': ('게임', 3000)}


class BankingAdapter(Protocol):
    def get_accounts(self, family: str, child: str | None = None) -> list[dict]: ...
    def get_account_balance(self, family: str, account_id: str, child: str | None = None) -> int: ...
    def get_transactions(self, family: str, account_id: str, child: str | None = None) -> list[dict]: ...
    def transfer_allowance(self, family: str, child: str, key: str, today=None): ...
    def simulate_purchase(self, family: str, child: str, key: str, merchant: str, amount: int, today=None): ...
    def transfer_to_savings(self, family: str, child: str, key: str, amount: int, today=None): ...
    def transfer_from_savings(self, family: str, child: str, key: str, amount: int, today=None): ...
    def settle_reward_interest(self, family: str, child: str, key: str, cycle_id: str, today=None): ...


class MockBankingAdapter:
    def __init__(self, ledger):
        self.ledger = ledger

    def get_accounts(self, family, child=None):
        with self.ledger.db() as db:
            if child:
                self.ledger._child(db, family, child)
            return accounts.accounts(db, family, child)

    def get_account_balance(self, family, account_id, child=None):
        visible = self.get_accounts(family, child)
        account = next((a for a in visible if a['id'] == account_id), None)
        if not account:
            raise PermissionError('이 가상 계좌를 조회할 수 없어요.')
        return account['balance']

    def get_transactions(self, family, account_id, child=None):
        with self.ledger.db() as db:
            if child:
                self.ledger._child(db, family, child)
            return accounts.transactions(db, family, account_id, child)

    def transfer_allowance(self, family, child, key, today=None):
        return self.ledger.transact(family, child, 'payment', key, today=today)

    def simulate_purchase(self, family, child, key, merchant, amount, today=None):
        if merchant not in MERCHANTS:
            raise ValueError('시연할 가상 가맹점을 선택해 주세요.')
        return self.ledger.transact(family, child, 'expense', key, amount=amount,
                                    category=MERCHANTS[merchant][0], note=merchant,
                                    today=today, metadata={'merchant': merchant})

    def transfer_to_savings(self, family, child, key, amount, today=None):
        return self.ledger.transact(family, child, 'deposit', key, amount=amount, today=today)

    def transfer_from_savings(self, family, child, key, amount, today=None):
        return self.ledger.transact(family, child, 'withdraw', key, amount=amount, today=today)

    def settle_reward_interest(self, family, child, key, cycle_id, today=None):
        return self.ledger.transact(family, child, 'interest', key, cycle_id=cycle_id, today=today)

    def change_category(self, family, child, transaction_id, category):
        with self.ledger.db() as db:
            self.ledger._child(db, family, child, active=True)
            if category not in ('간식', '문구', '장난감', '게임', '책', '선물', '기타'):
                raise ValueError('소비 분류를 선택해 주세요.')
            row = db.execute("SELECT id FROM transactions WHERE id=? AND child=? AND kind='expense'", (transaction_id, child)).fetchone()
            if not row:
                raise ValueError('수정할 소비 거래를 찾을 수 없어요.')
            db.execute('INSERT INTO bank_category_changes(transaction_id,family,child,category,occurred_at) VALUES(?,?,?,?,?)', (transaction_id, family, child, category, accounts.now(db, family)))

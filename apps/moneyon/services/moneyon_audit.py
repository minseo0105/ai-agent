"""장부 맞추기 점검. 읽기 전용이며 어떤 데이터도 고치지 않는다.

거래표(transactions)와 계좌 장부(bank_postings), 저축통장(moneyon_book_entries)은 따로 저장된다.
이 셋이 서로 맞는지 아이 한 명 단위로 확인한다.
"""
import sqlite3

WALLET_IN = ('payment', 'interest', 'allowance_bonus', 'expense_cancel', 'withdraw')


def _sum(db, sql, *args):
    return db.execute(sql, args).fetchone()[0] or 0


def audit_child(db, child):
    """문제를 한국어 문장 목록으로 돌려준다. 빈 목록이면 장부가 맞는 것."""
    problems = []
    kind = lambda k: _sum(db, 'SELECT SUM(wallet) FROM transactions WHERE child=? AND kind=?', child, k)
    vault_kind = lambda k: _sum(db, 'SELECT SUM(vault) FROM transactions WHERE child=? AND kind=?', child, k)

    accounts = {r['kind']: r for r in db.execute("SELECT * FROM bank_accounts WHERE child=? AND kind IN ('wallet','vault')", (child,))}
    bank = {}
    for name, account in accounts.items():
        bank[name] = _sum(db, 'SELECT SUM(amount) FROM bank_postings WHERE account_id=?', account['id'])
        running = 0
        for seq, row in enumerate(db.execute('SELECT amount,balance_after FROM bank_postings WHERE account_id=? ORDER BY rowid', (account['id'],)), 1):
            running += row['amount']
            if row['balance_after'] != running:
                problems.append(f'{name} 계좌 {seq}번째 기록의 거래 후 잔액이 누적과 달라요.')
                break
            if running < 0:
                problems.append(f'{name} 계좌가 {seq}번째 기록에서 음수({running:,}원)가 됐어요.')
                break
    wallet, vault = bank.get('wallet', 0), bank.get('vault', 0)
    if wallet < 0:
        problems.append(f'남은 용돈이 음수({wallet:,}원)예요.')
    if vault < 0:
        problems.append(f'저축통장 합계가 음수({vault:,}원)예요.')

    # 받은 용돈 − 쓴 돈 − 저금 + 꺼낸 돈 + 받은 이자 (+ 취소·회수 같은 나머지) = 남은 용돈
    known = ('payment', 'interest', 'allowance_bonus', 'expense', 'expense_cancel', 'deposit', 'withdraw')
    other = _sum(db, f"SELECT SUM(wallet) FROM transactions WHERE child=? AND kind NOT IN ({','.join('?' * len(known))})", child, *known)
    formula = (kind('payment') - -kind('expense') - -kind('deposit') + kind('withdraw')
               + kind('interest') + kind('allowance_bonus') + kind('expense_cancel') + other)
    if formula != wallet:
        problems.append(f'용돈 장부({formula:,}원)와 남은 용돈 계좌({wallet:,}원)가 달라요.')

    # 저축통장: 저금 − 꺼낸 돈 + 통장 이자 = 통장 잔액, 통장별 합 = 저축 계좌
    if _sum(db, 'SELECT SUM(vault) FROM transactions WHERE child=?', child) != vault:
        problems.append('거래표의 저축 합계와 저축 계좌가 달라요.')
    has_books = _sum(db, "SELECT COUNT(*) FROM sqlite_master WHERE name IN ('moneyon_books','moneyon_book_entries')") == 2
    books = [] if not has_books else list(db.execute('SELECT b.id,COALESCE(SUM(e.amount),0) balance FROM moneyon_books b LEFT JOIN moneyon_book_entries e ON e.book=b.id WHERE b.child=? GROUP BY b.id', (child,)))
    for b in books:
        if b['balance'] < 0:
            problems.append(f"저축통장 {b['id'][:8]}의 잔액이 음수({b['balance']:,}원)예요.")
    if books and sum(b['balance'] for b in books) != vault:
        problems.append(f"저축통장별 잔액 합({sum(b['balance'] for b in books):,}원)과 저축 계좌({vault:,}원)가 달라요.")
    # 저축통장에 배정되지 않았거나 금액이 다른 저축 거래
    for t in (db.execute('SELECT id,vault FROM transactions WHERE child=? AND vault!=0', (child,)).fetchall() if books else []):
        assigned = _sum(db, 'SELECT SUM(amount) FROM moneyon_book_entries WHERE transaction_id=?', t['id'])
        if books and assigned != t['vault']:
            problems.append(f"저축 거래 {t['id'][:8]}가 통장에 {assigned:,}원만 배정됐어요(거래 {t['vault']:,}원).")
    return problems


def audit_database(path):
    """DB 파일 하나의 모든 아이를 점검한다. 파일은 읽기 전용으로 열고, 결과는 개수와 문제 목록."""
    db = sqlite3.connect(f'file:{path}?mode=ro', uri=True)
    db.row_factory = sqlite3.Row
    try:
        children = [r['id'] for r in db.execute('SELECT id FROM children')]
        report = {'children': len(children), 'mismatched': 0, 'negative': 0, 'unreadable': 0, 'problems': {}}
        for child in children:
            try:
                found = audit_child(db, child)
            except sqlite3.OperationalError:  # 저축통장 표가 없는 옛 구조 등: 맞다/틀리다를 말할 수 없다
                report['unreadable'] += 1
                continue
            if found:
                report['problems'][child] = found
                report['mismatched'] += 1
                report['negative'] += any('음수' in p for p in found)
        return report
    finally:
        db.close()


if __name__ == '__main__':
    import json
    import sys
    result = audit_database(sys.argv[1])
    result['problems'] = {k[:8]: v for k, v in result['problems'].items()}
    print(json.dumps(result, ensure_ascii=False, indent=1))

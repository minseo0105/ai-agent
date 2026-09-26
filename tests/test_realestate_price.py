import asyncio
import unittest
from unittest.mock import patch
from services import realestate_monitor as rm
with patch.object(rm, 'init_db'):
    from api.realestate import TradeQuery, trades
from pydantic import ValidationError

class PriceTests(unittest.TestCase):
    def test_inclusive_ceiling_and_unknowns(self):
        rows=[{'price_100m':p} for p in [4.9999,5,5.0001,0,None,'bad',float('nan'),float('inf')]]
        self.assertEqual([r['price_100m'] for r in rm.filter_trade_price(rows,5)],[4.9999,5])
        self.assertEqual(len(rm.filter_trade_price(rows)),len(rows))

    def test_api_counts_and_compatibility(self):
        rows=[{'price_100m':p,'property_type':'아파트','date':'2026-09-01'} for p in [4,5,6,0]]
        for ceiling,expected in [(None,4),(5,2),(3,0)]:
            q=TradeQuery(regions=['서울 > 송파구'],property_types=['아파트'],month='202609',max_price_100m=ceiling)
            with patch.object(rm,'fetch_trades_multi',return_value=(rows,[])), patch.object(rm,'build_naver_land_url',return_value='https://land.naver.com'):
                result=asyncio.run(trades(q))
            self.assertEqual(len(result['items']),expected)
            self.assertEqual(sum(result['counts'].values()),expected)

    def test_invalid_ceiling_rejected(self):
        for price in [-1,0,float('nan'),float('inf'),10001]:
            with self.assertRaises(ValidationError):
                TradeQuery(regions=['서울 > 송파구'],property_types=['아파트'],month='202609',max_price_100m=price)

if __name__=='__main__': unittest.main()

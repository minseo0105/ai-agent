import asyncio
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch
from services import realestate_monitor as rm
with patch.object(rm,'init_db'):
    from api.realestate import TradeQuery, trades
from pydantic import ValidationError

class AreaTests(unittest.TestCase):
    def test_boundary_unknown_and_land(self):
        rows=[{'area':a,'area_basis':'전용면적'} for a in [84.99,85,85.001,0,None,float('nan')]]
        rows += [{'area':60,'area_basis':'대지면적'},{'area':60}]
        self.assertEqual([x['area'] for x in rm.filter_trade_area(rows,85)],[84.99,85])
        self.assertEqual(len(rm.filter_trade_area(rows)),8)

    def test_parser_basis(self):
        for kind,xml,basis in [('아파트','<excluUseAr>85</excluUseAr>','전용면적'),('단독·다가구','<totalFloorAr>85</totalFloorAr><plottageAr>50</plottageAr>','연면적'),('단독·다가구','<plottageAr>85</plottageAr>','대지면적')]:
            item=rm._trade_item_to_common(ET.fromstring('<item>'+xml+'</item>'),kind,'11710','202609')
            self.assertEqual(item['area_basis'],basis)
            self.assertEqual(item['area'],85)

    def test_combined_filters_and_counts(self):
        rows=[{'price_100m':p,'area':a,'area_basis':'전용면적','property_type':'아파트','date':'2026-09-01'} for p,a in [(5,85),(6,60),(4,86),(3,60)]]
        q=TradeQuery(regions=['서울 > 송파구'],property_types=['아파트'],month='202609',max_price_100m=5,max_area=85)
        with patch.object(rm,'fetch_trades_multi',return_value=(rows,[])),patch.object(rm,'build_naver_land_url',return_value='https://land.naver.com'):
            result=asyncio.run(trades(q))
        self.assertEqual(len(result['items']),2)
        self.assertEqual(result['counts'],{'아파트':2})

    def test_invalid_area(self):
        for area in [-1,0,float('nan'),float('inf'),100001]:
            with self.assertRaises(ValidationError):
                TradeQuery(regions=['서울 > 송파구'],property_types=['아파트'],month='202609',max_area=area)

if __name__=='__main__': unittest.main()

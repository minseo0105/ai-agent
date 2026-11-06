"""HTTP 200이어도 공공데이터포털 게이트웨이 오류 응답이면 '거래 없음'이 아니라 오류로 올린다."""
import unittest
from unittest import mock

from services import realestate_monitor as rm

GATEWAY = b"""<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE ERROR</errMsg>
<returnAuthMsg>SERVICE_KEY_IS_NOT_REGISTERED_ERROR</returnAuthMsg><returnReasonCode>30</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"""
EMPTY = b"""<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header><body><items/><totalCount>0</totalCount></body></response>"""


def fake(content):
    r = mock.Mock(status_code=200, content=content)
    r.raise_for_status = lambda: None
    return r


class GatewayErrorTests(unittest.TestCase):
    def run_fetch(self, content):
        with mock.patch.object(rm, 'get_public_data_key', return_value='k'), \
             mock.patch.object(rm.requests, 'get', return_value=fake(content)):
            return rm.fetch_trade('아파트', '11740', '202610')

    def test_gateway_error_with_http_200_raises(self):
        with self.assertRaisesRegex(RuntimeError, '인증 오류 30'):
            self.run_fetch(GATEWAY)

    def test_genuinely_empty_month_returns_empty_list(self):
        self.assertEqual(self.run_fetch(EMPTY), [])


if __name__ == '__main__':
    unittest.main()

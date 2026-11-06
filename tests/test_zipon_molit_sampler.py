import importlib.util, unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("sampler", Path(__file__).resolve().parent.parent / "scripts/sample_molit_trade_apis.py")
sampler = importlib.util.module_from_spec(spec); spec.loader.exec_module(sampler)

XML = """<response><header><resultCode>000</resultCode><resultMsg>OK</resultMsg></header><body><totalCount>2</totalCount><items>
<item><umdNm>천호동</umdNm><jibun>423-1</jibun><dealAmount>10,000</dealAmount><cdealType>O</cdealType></item>
<item><umdNm>천호동</umdNm><jibun> </jibun><dealAmount>9,000</dealAmount><cdealType></cdealType></item>
</items></body></response>"""


class SamplerTests(unittest.TestCase):
    def test_fill_rate_and_distribution(self):
        s = sampler.summarize(XML)
        self.assertEqual(s["items"], 2)
        self.assertEqual(s["field_fill_rate"]["jibun"], 0.5)
        self.assertEqual(s["field_fill_rate"]["umdNm"], 1.0)
        self.assertEqual(s["value_distribution"]["cdealType"], {"O": 1, "(빈값)": 1})

    def test_gateway_error_is_reported_not_raised(self):
        err = "<OpenAPI_ServiceResponse><cmmMsgHeader><errMsg>SERVICE_KEY_IS_NULL</errMsg><returnReasonCode>20</returnReasonCode></cmmMsgHeader></OpenAPI_ServiceResponse>"
        s = sampler.summarize(err)
        self.assertEqual((s["result_code"], s["items"]), ("20", 0))

    def test_key_is_masked(self):
        text = "GET https://x/y?serviceKey=SECRET123&LAWD_CD=11110 failed"
        self.assertNotIn("SECRET123", sampler.mask(text, "SECRET123"))
        self.assertNotIn("SECRET123", sampler.mask("token SECRET123 here", "SECRET123"))

    def test_script_never_prints_key_source(self):
        src = (Path(sampler.__file__)).read_text(encoding="utf-8")
        self.assertIn("assert key not in text", src)
        self.assertNotIn("print(key", src)


if __name__ == "__main__":
    unittest.main()

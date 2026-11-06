"""기존 네이버부동산 연결 URL이 사업 좌표(해당 지역)를 정확히 여는지. 생성 로직은 바꾸지 않는다."""
import re
import unittest

from services.development_presentation import naver_real_estate_link

ALPHABET = '0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ'


def decode(token):
    value = 0
    for ch in token:
        value = value * 62 + ALPHABET.index(ch)
    return (value - 2_000_000_000) / 10_000_000


# 자치구별 대표 지점(서울 범위 안의 실제 좌표 예시): 천호(강동), 신반포(서초), 미아(강북), 신길(영등포)
SAMPLES = [(37.5386, 127.1238), (37.5049, 127.0007), (37.6264, 127.0260), (37.5036, 126.9136)]


class NaverLinkTests(unittest.TestCase):
    def test_center_decodes_back_to_the_project_coordinates(self):
        for lat, lon in SAMPLES:
            link = naver_real_estate_link({'latitude': lat, 'longitude': lon})
            m = re.fullmatch(r'https://fin\.land\.naver\.com/map\?center=([0-9A-Za-z]+)-([0-9A-Za-z]+)&zoom=17', link['url'])
            self.assertIsNotNone(m, link['url'])
            self.assertAlmostEqual(decode(m.group(1)), lon, places=6)
            self.assertAlmostEqual(decode(m.group(2)), lat, places=6)
            self.assertTrue(126.7 < decode(m.group(1)) < 127.3 and 37.4 < decode(m.group(2)) < 37.8)

    def test_no_link_without_valid_coordinates(self):
        for row in ({}, {'latitude': None, 'longitude': 127.0}, {'latitude': 91, 'longitude': 127.0},
                    {'latitude': True, 'longitude': 127.0}, {'latitude': float('nan'), 'longitude': 127.0}):
            self.assertIsNone(naver_real_estate_link(row))

    def test_label_and_destination_unchanged(self):
        link = naver_real_estate_link({'latitude': 37.5386, 'longitude': 127.1238})
        self.assertEqual((link['label'], link['destination'], link['basis']), ('네이버부동산에서 보기', 'NPAY_MAP', 'PROJECT_COORDINATES'))


if __name__ == '__main__':
    unittest.main()

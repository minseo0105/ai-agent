"""배포 구성: 경기 지오코딩 캐시가 컨테이너 재생성 후에도 남는지, 기존 볼륨은 그대로인지."""
import re
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
DOCKERFILE = (ROOT / "Dockerfile").read_text(encoding="utf-8")
APP = "/home/user/app"


def mounts(service):
    return [v for v in COMPOSE["services"][service].get("volumes", []) if isinstance(v, str)]


class GyeonggiCacheVolumeTests(unittest.TestCase):
    def test_cache_path_matches_the_code(self):
        import api.realestate as api
        rel = api.GG_GEOCODE_CACHE.relative_to(api.BASE_DIR).as_posix()
        self.assertEqual(rel, "data/development/cache/geocode-gyeonggi")
        self.assertIn(f"gyeonggi-geocode-cache:{APP}/{rel}", mounts("ailab"))
        self.assertIn("WORKDIR /home/user/app", DOCKERFILE)

    def test_dockerfile_precreates_the_folder_as_app_user(self):
        # 이미지에 폴더가 있어야 새 named volume이 user(1000) 소유로 만들어져 앱이 쓸 수 있다.
        user_at = DOCKERFILE.index("USER user")
        mkdir = re.search(r"RUN mkdir -p [^\n]*data/development/cache/geocode-gyeonggi", DOCKERFILE)
        self.assertIsNotNone(mkdir)
        self.assertGreater(mkdir.start(), user_at)

    def test_volume_is_declared_and_only_ailab_uses_it(self):
        self.assertIn("gyeonggi-geocode-cache", COMPOSE["volumes"])
        users = [s for s in COMPOSE["services"] if any(m.startswith("gyeonggi-geocode-cache:") for m in mounts(s))]
        self.assertEqual(users, ["ailab"])

    def test_existing_volumes_are_unchanged(self):
        for name in ("ailab-admin", "moneyon-runtime", "caddy-data", "caddy-config"):
            self.assertIn(name, COMPOSE["volumes"])
        self.assertIn(f"ailab-admin:{APP}/data/admin", mounts("ailab"))
        self.assertTrue(any(m.startswith(f"ailab-admin:{APP}/data/admin") for m in mounts("stockon-collector")))

    def test_mount_does_not_cover_seoul_caches(self):
        # 서울 캐시(data/development/cache/geocode, official_* 등)는 이미지에 들어 있다. 상위 폴더를 덮으면 사라진다.
        target = f"{APP}/data/development/cache/geocode-gyeonggi"
        for service in COMPOSE["services"]:
            for m in mounts(service):
                path = m.split(":")[1]
                self.assertFalse(path in (f"{APP}/data", f"{APP}/data/development", f"{APP}/data/development/cache"), m)
        self.assertTrue((ROOT / "data/development/cache/README.md").exists())  # 서울 캐시는 저장소(이미지)에 그대로 있다
        self.assertIn(f"gyeonggi-geocode-cache:{target}", mounts("ailab"))


if __name__ == "__main__":
    unittest.main()

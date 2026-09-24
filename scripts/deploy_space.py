"""GitHub 저장소 → Hugging Face Space 업로드 (배포).

환경변수
  HF_TOKEN  : Hugging Face 쓰기 권한 토큰 (GitHub Secrets)
  HF_SPACE  : 사용자명/스페이스이름 (예: minseo/digital-ai-lab, GitHub Variables)

서버에 필요한 파일만 올린다. 비밀값(.streamlit/secrets.toml 등)은 올리지 않는다.
"""

import os
import sys
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]

# 서버 실행에 필요한 파일
ALLOW = [
    "Dockerfile",
    "requirements-api.txt",
    "corp_codes.json",
    "sample_cars_v2.xlsx",
    "sample_cars_v3.xlsx",
    "api/**",
    "services/**",
    "web/**",
    "data/golf/**",
    "car_images_mobile_39/**",
    "car_images_cutout/**",
    "car_images_real/**",
    "dreamcar_assets/**",
]
IGNORE = [
    "**/__pycache__/**",
    "**/*.pyc",
    "web/node_modules/**",
    "web/.next/**",
    "web/out/**",
    "web/.env*",
    "data/golf/backups/**",
    "data/golf/runtime/**",
    "data/admin/**",
    ".streamlit/**",
    "**/secrets.toml",
]


def main():
    token, space = os.environ.get("HF_TOKEN"), os.environ.get("HF_SPACE")
    if not token or not space:
        print("HF_TOKEN 또는 HF_SPACE가 설정되지 않아 배포를 건너뜁니다.")
        return 0

    api = HfApi(token=token)
    api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(
        folder_path=str(ROOT),
        repo_id=space,
        repo_type="space",
        allow_patterns=ALLOW,
        ignore_patterns=IGNORE,
        # 저장소에서 지운 파일은 Space에서도 지운다 (README 등 Space 전용 파일은 유지)
        delete_patterns=ALLOW,
        commit_message=f"Deploy {os.environ.get('GITHUB_SHA', 'local')[:7]}",
    )
    api.upload_file(
        path_or_fileobj=str(ROOT / "deploy" / "space_README.md"),
        path_in_repo="README.md",
        repo_id=space,
        repo_type="space",
        commit_message="Space 설정(README) 갱신",
    )
    owner, name = space.split("/", 1)
    print(f"배포 요청 완료: https://huggingface.co/spaces/{space}")
    print(f"사이트 주소: https://{owner.lower()}-{name.lower().replace('_', '-').replace('.', '-')}.hf.space")
    return 0


if __name__ == "__main__":
    sys.exit(main())

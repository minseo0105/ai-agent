# 디지털전략부 AI LAB 배포 이미지 (Hugging Face Spaces · Docker)
# 한 컨테이너에서 FastAPI가 API와 화면(Next.js 정적 빌드)을 같은 주소로 제공한다.

# ---- 1) 화면(Next.js) 정적 빌드 ----
FROM node:22-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# 같은 주소에서 API를 부르므로 API 주소는 빈 값(상대 경로)
ENV STATIC_EXPORT=1 NEXT_PUBLIC_API_URL="" NEXT_TELEMETRY_DISABLED=1
RUN npm run build

# ---- 2) API 서버 ----
FROM python:3.12-slim
# 보고서 차트의 한글 글꼴
RUN apt-get update && apt-get install -y --no-install-recommends fonts-nanum && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces는 uid 1000 사용자로 실행한다
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    REMBG_HOME=/home/user/app/.rembg \
    MPLCONFIGDIR=/home/user/.cache/matplotlib
WORKDIR /home/user/app

COPY --chown=user requirements-api.txt .
RUN pip install --no-cache-dir --user -r requirements-api.txt

COPY --chown=user . .
COPY --from=web --chown=user /web/out ./web/out

# 배경 제거 모델을 미리 받아 첫 요청이 느려지지 않게 한다
RUN python -c "from rembg import new_session; new_session('u2net')"

EXPOSE 7860
# --proxy-headers: 프록시 뒤에서 실제 방문자 IP로 로그인 시도 횟수를 센다
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860", "--proxy-headers", "--forwarded-allow-ips", "*"]

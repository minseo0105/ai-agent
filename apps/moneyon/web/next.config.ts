import type { NextConfig } from "next";

// STATIC_EXPORT=1 로 빌드하면 web/out 에 정적 파일이 생기고, FastAPI가 같은 주소에서 화면까지 제공한다(배포용).
// 개발(npm run dev)은 기존처럼 Next 서버로 띄운다.
const staticExport = process.env.STATIC_EXPORT === "1";
// 오라클처럼 하위 경로(/moneyon)에서 서비스할 때만 설정한다. 비우면 HF Space와 같다(루트).
const basePath = process.env.NEXT_BASE_PATH || undefined;

const nextConfig: NextConfig = {
  ...(basePath ? { basePath } : {}),
  distDir: process.env.NEXT_BUILD_DIR || ".next",
  reactStrictMode: true,
  ...(staticExport ? { output: "export" as const, images: { unoptimized: true } } : {}),
};

export default nextConfig;

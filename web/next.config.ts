import type { NextConfig } from "next";

// STATIC_EXPORT=1 로 빌드하면 web/out 에 정적 파일이 생기고, FastAPI가 같은 주소에서 화면까지 제공한다(배포용).
// 개발(npm run dev)은 기존처럼 Next 서버로 띄운다.
const staticExport = process.env.STATIC_EXPORT === "1";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  ...(staticExport ? { output: "export" as const, images: { unoptimized: true } } : {}),
};

export default nextConfig;

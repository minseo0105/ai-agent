import type { Metadata, Viewport } from "next";
import AccessProvider from "@/components/access/AccessProvider";
import SiteFooter from "@/components/SiteFooter";
import { SITE_NAME } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  title: SITE_NAME,
  description: "디지털전략부 AI LAB — AI Agent · API · Vibe Coding으로 만든 서비스들을 직접 체험해보세요.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <head>
        <link
          rel="stylesheet"
          href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css"
        />
      </head>
      <body className="flex min-h-dvh flex-col">
        <AccessProvider>
          <div className="flex-1">{children}</div>
          <SiteFooter />
        </AccessProvider>
      </body>
    </html>
  );
}

import type { Metadata, Viewport } from "next";
import AccessProvider from "@/components/access/AccessProvider";
import SiteFooter from "@/components/SiteFooter";
import UsageTracker from "@/components/UsageTracker";
import { SITE_NAME, SITE_SLOGAN, SITE_SUB, SITE_URL } from "@/lib/site";
import "./globals.css";

const TITLE = `${SITE_NAME} — 아이디어를 서비스로 만드는 곳`;
const DESCRIPTION = `${SITE_NAME} · ${SITE_SUB}. ${SITE_SLOGAN} AI에게 묻고, 직접 실험하고, 서비스로 구현합니다.`;

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: TITLE,
  description: DESCRIPTION,
  openGraph: {
    type: "website",
    url: SITE_URL,
    siteName: SITE_NAME,
    title: TITLE,
    description: DESCRIPTION,
    locale: "ko_KR",
    images: [{ url: "/og.png", width: 1200, height: 630, alt: `${SITE_NAME} · ${SITE_SLOGAN}` }],
  },
  twitter: { card: "summary_large_image", title: TITLE, description: DESCRIPTION, images: ["/og.png"] },
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
        <UsageTracker />
        <AccessProvider>
          <div className="flex-1">{children}</div>
          <SiteFooter />
        </AccessProvider>
      </body>
    </html>
  );
}

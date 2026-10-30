import type {Metadata,Viewport} from "next";
import "./globals.css";
// 파비콘(icon.png)·앱 아이콘(apple-icon.png)·공유 미리보기(opengraph-image.png)는 이 폴더의 파일로 Next가 붙인다(꿀벌 '이자니').
// 공유 미리보기 주소가 절대 주소여야 해서 사이트 주소를 둔다(도메인을 바꾸면 MONEYON_SITE_URL로).
const SITE=process.env.MONEYON_SITE_URL||"https://wai-labs.com";
// og:url에는 basePath가 붙지 않아 직접 붙인다(오라클 /moneyon/, HF는 루트)
const PAGE_URL=`${SITE}${process.env.NEXT_BASE_PATH||""}/`;
export const metadata:Metadata={metadataBase:new URL(SITE),title:"MONEY — 어린이 용돈 체험",description:"PIN 없이 통장에서 받고 쓰고 모으며 배우는 금융 놀이터",
  openGraph:{title:"MONEY:ON — 어린이 용돈 체험",description:"용돈을 관리하고, 남은 돈에 이자까지!",url:PAGE_URL,type:"website",locale:"ko_KR"}};
export const viewport:Viewport={width:"device-width",initialScale:1};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="ko"><body>{children}</body></html>;}

import type {Metadata,Viewport} from "next";
import "./globals.css";
export const metadata:Metadata={title:"MONEY — 어린이 용돈 체험",description:"PIN 없이 통장에서 받고 쓰고 모으며 배우는 금융 놀이터"};
export const viewport:Viewport={width:"device-width",initialScale:1};
export default function Layout({children}:{children:React.ReactNode}){return <html lang="ko"><body>{children}</body></html>;}

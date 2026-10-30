// 메인('/')으로 가는 버튼. 같은 주소(wai-labs.com, sslip.io 등)의 루트로 가고, 체험 데이터(sessionStorage)는 건드리지 않는다.
export default function WaiLabsLink() {
  return <div className="mk-wai-row"><a className="mk-wai-link" href="/" aria-label="WAI LABS 메인으로 가기"><svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><path d="M12.5 4 6.5 10l6 6" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"/></svg><span>WAI LABS</span></a></div>;
}

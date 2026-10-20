import ServiceGrid from "@/components/ServiceGrid";
import styles from "@/components/home/Home.module.css";

export default function Home() {
  return <main className={styles.portal}>
    <header className={styles.header}>
      <a href="/" className={styles.brand} aria-label="디지털전략부 AI LAB 홈">
        <span className={styles.brandMark} aria-hidden="true"><i /><i /><i /><i /></span>
        <span><small>DIGITAL STRATEGY</small><strong>AI LAB<span> / </span></strong></span>
      </a>
      <nav aria-label="메인 탐색"><a href="#services">서비스</a><a href="#agent">AI 에이전트</a></nav>
    </header>
    <section className={styles.hero} aria-labelledby="home-heading">
      <div className={styles.heroCopy}>
        <p className={styles.eyebrow}><span aria-hidden="true" /> 디지털전략부</p>
        <h1 id="home-heading"><span>아이디어를 서비스로</span><span>만드는 <em>AI LAB</em></span></h1>
        <p className={styles.heroDescription}>직접 써 보는 AI 서비스를 모았어요.</p>
      </div>
      {/* 핵심 행동 하나. 모바일에서는 히어로 아래쪽(엄지 닿는 곳)에 놓인다. */}
      <a href="#services" className={styles.heroAction}>서비스 둘러보기 <span aria-hidden="true">↓</span></a>
      <div className={styles.heroArt} aria-hidden="true">
        <svg viewBox="0 0 420 240" fill="none"><defs><linearGradient id="hero-prism" x1="120" y1="60" x2="290" y2="220" gradientUnits="userSpaceOnUse"><stop stopColor="#b8e4f9" /><stop offset="1" stopColor="#398ac8" /></linearGradient></defs>
          <path d="m65 160 150-82 151 82-151 82z" stroke="#d8e6f0" /><path d="m99 141 116-64 118 64-118 63z" stroke="#d8e6f0" /><path d="m134 122 81-45 82 45-82 45z" stroke="#d8e6f0" />
          <path d="M215 10v198M47 152l168-92 168 92" stroke="#e3edf5" strokeDasharray="3 6" />
          <path d="m144 86 71-40 72 40v83l-72 40-71-40z" fill="url(#hero-prism)" fillOpacity=".78" /><path d="m144 86 71 40 72-40m-72 40v83" stroke="white" strokeWidth="2" /><path d="m144 86 71-40 72 40-72 40z" fill="#e2f4ff" />
          <path d="m215 76 4 10 11 4-11 4-4 10-4-10-10-4 10-4z" fill="#2786c2" />
          <rect x="301" y="50" width="47" height="47" rx="14" transform="rotate(12 301 50)" fill="white" /><path d="m318 68-7 5 7 7m13-8 6 7-9 4" stroke="#4b9bcb" strokeWidth="2" strokeLinecap="round" />
          <rect x="82" y="175" width="37" height="37" rx="11" transform="rotate(-12 82 175)" fill="white" /><path d="m96 184 5 4-5 5m6-12 5 4-5 5" stroke="#6e9cba" strokeWidth="2" strokeLinecap="round" />
          <circle cx="324" cy="181" r="5" fill="#8bbdda" /><circle cx="111" cy="74" r="4" fill="#8bbdda" />
        </svg>
      </div>
      <span className={styles.heroNote} aria-hidden="true">THINK. BUILD. EXPERIENCE.</span>
    </section>
    <section id="services" className={styles.explore} aria-labelledby="explore-heading">
      <div className={styles.sectionHeading}><div><p className={styles.sectionKicker}>IDEAS IN ACTION</p><h2 id="explore-heading">Explore AI LAB<span aria-hidden="true">.</span></h2></div><span className={styles.liveLabel}><i aria-hidden="true" />서비스 쇼케이스</span></div>
      <p className={styles.sectionDescription}>아이디어에서 시작된 다양한 AI 서비스를 경험해보세요.</p>
      <ServiceGrid />
    </section>
  </main>;
}

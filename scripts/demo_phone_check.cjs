// 휴대폰 환경 자동 확인(11/17 시연): 아이폰 사파리(WebKit) · 카카오톡 인앱(아이폰 WebKit / 안드로이드 Chrome + KAKAOTALK UA).
// 주요 화면이 열리는지, JS 오류·가로 넘침이 없는지, 머니온 '체험 시작하기'가 통장 화면으로 가는지.
// 만든 머니온 체험 토큰은 TOKENS 파일에 남긴다(scripts/demo_load_cleanup.py로 지운다). 토큰은 출력하지 않는다.
//   PLAYWRIGHT=경로/node_modules/playwright BASE=https://... TOKENS=phone_tokens.txt node scripts/demo_phone_check.cjs
const fs = require("fs");
const { webkit, chromium, devices } = require(process.env.PLAYWRIGHT || "playwright");

const BASE = process.env.BASE || "https://wai-labs.com";
const KAKAO_IOS = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 KAKAOTALK 10.8.0";
const KAKAO_AND = "Mozilla/5.0 (Linux; Android 14; SM-S921N Build/UP1A.231005.007; wv) AppleWebKit/537.36 (KHTML, like Gecko) Version/4.0 Chrome/130.0.0.0 Mobile Safari/537.36 KAKAOTALK 10.8.0";
const ENVS = [
  { name: "아이폰 사파리", engine: webkit, ctx: { ...devices["iPhone 15"] } },
  { name: "카카오톡 인앱(아이폰)", engine: webkit, ctx: { ...devices["iPhone 15"], userAgent: KAKAO_IOS } },
  { name: "카카오톡 인앱(안드로이드)", engine: chromium, launch: { channel: "chrome" }, ctx: { ...devices["Galaxy S9+"], userAgent: KAKAO_AND } },
];
const PAGES = [
  { path: "/", expect: "MONEY:ON" },
  { path: "/stock", expect: "뉴스 속 숨은 종목" },
  { path: "/stock?tab=market", expect: "오늘 시장" },
  { path: "/moneyon/", expect: "체험 시작하기", moneyon: true },
];

(async () => {
  const rows = [], tokens = [];
  for (const env of ENVS) {
    const browser = await env.engine.launch(env.launch || {});
    for (const p of PAGES) {
      const ctx = await browser.newContext(env.ctx);
      const page = await ctx.newPage();
      const errors = [];
      page.on("pageerror", (e) => errors.push(String(e.message).slice(0, 120)));
      const t0 = Date.now();
      let status = 0, ok = false, overflow = null, extra = "";
      try {
        const r = await page.goto(BASE + p.path, { waitUntil: "networkidle", timeout: 30000 });
        status = r ? r.status() : 0;
        await page.getByText(p.expect, { exact: false }).first().waitFor({ timeout: 15000 });
        ok = true;
        if (p.moneyon) {
          await page.getByRole("button", { name: "체험 시작하기" }).click();
          await page.waitForFunction(() => !!sessionStorage.getItem("moneyon-trial-v1"), null, { timeout: 15000 });
          tokens.push(await page.evaluate(() => sessionStorage.getItem("moneyon-trial-v1")));
          await page.waitForTimeout(1500);
          extra = (await page.locator("body").innerText()).includes("이자") ? "통장 화면 열림" : "통장 화면 확인 못 함";
        }
        overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      } catch (e) {
        extra = String(e.message).split("\n")[0].slice(0, 100);
      }
      rows.push({ env: env.name, path: p.path, status, ok, ms: Date.now() - t0, overflow_px: overflow, js_errors: errors.length, first_error: errors[0] || "", note: extra });
      await ctx.close();
    }
    await browser.close();
  }
  if (process.env.TOKENS) fs.writeFileSync(process.env.TOKENS, tokens.join("\n"));
  console.log(JSON.stringify(rows, null, 1));
})();

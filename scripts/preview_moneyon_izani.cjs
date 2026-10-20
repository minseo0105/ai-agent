// Preview the single user-supplied Canva bee. No generated poses or expressions.
const fs=require('node:fs'),path=require('node:path');
const root=path.resolve(__dirname,'..'),output=path.join(root,'reports/moneyon-izani-bee/izani');
fs.mkdirSync(output,{recursive:true});
fs.copyFileSync(path.join(root,'web/public/moneyon/characters/izani-bee.png'),path.join(output,'izani-bee.png'));
fs.writeFileSync(path.join(output,'index.html'),`<!doctype html><html lang="ko"><meta charset="utf-8"><title>이자니 · MONEY 전용 꿀벌</title><style>body{font:16px/1.8 system-ui;background:#F5FAFF;color:#084A86;max-width:650px;margin:40px auto;padding:24px}figure{background:#fff;border-radius:24px;padding:30px;text-align:center}img{width:200px;height:200px;object-fit:contain}p{color:#526d83}</style><h1>이자니 · MONEY 전용 꿀벌</h1><figure><img src="izani-bee.png" alt="이자니"><figcaption>첨부된 원본의 모습 그대로, 배경만 투명하게</figcaption></figure><p>홈 · 용돈 받기 · 소비 안내 · 이자 계산 · 저축 · 지급 완료에서 같은 기본 이미지를 사용합니다. 표정이나 포즈를 새로 만들지 않았습니다.</p></html>`);
console.log('Single-bee preview:',output);

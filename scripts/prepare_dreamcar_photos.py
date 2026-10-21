"""드림카 공식 차량 사진 → 화면용 이미지.

reports/car-images-incoming/ 의 13장(브랜드_차종.jpg)을 읽어
1) 원본을 dreamcar_assets/originals/cars/ 에 그대로 보관하고
2) 차를 가운데 둔 16:10으로 자른 뒤(여백이 모자라면 흐린 확대 대신 사진 가장자리 색으로 채움)
3) 색상 3종(화이트·블랙·그레이)을 만든다. 대표 사진 1장의 차체만 밝기를 바꾸고
   유리·타이어·그릴처럼 어두운 부분과 배경은 그대로 둔다.
4) dreamcar_assets/cars/w800/, w1200/ 에 {엑셀 이미지 이름}.webp 로 저장하고
5) 13종 × 3색 비교판을 reports/car-images-audit/ 에 만든다.

차 영역은 이미 받아 둔 로컬 모델(.rembg/models/u2net)로 찾는다. 인터넷에서 아무것도 받지 않는다.
--only-board: 파일은 쓰지 않고 비교판만 만든다. --keep-color 모델들: 색 변형 없이 대표 사진을 3색에 그대로 쓴다.
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / 'reports' / 'car-images-incoming'
ORIGINALS = ROOT / 'dreamcar_assets' / 'originals' / 'cars'
OUT = ROOT / 'dreamcar_assets' / 'cars'
BOARD = ROOT / 'reports' / 'car-images-audit'
# 엑셀(sample_cars_v3.xlsx)의 이미지 이름 앞부분 ← 받은 파일 이름
CARS = [('avante', 'hyundai_avante', '아반떼'), ('sonata', 'hyundai_sonata', '쏘나타'), ('k5', 'kia_k5', 'K5'),
        ('grandeur', 'hyundai_grandeur', '디 올 뉴 그랜저'), ('k8', 'kia_k8', 'K8'), ('tucson', 'hyundai_tucson', '투싼'),
        ('sportage', 'kia_sportage', '스포티지'), ('santafe', 'hyundai_santafe', '싼타페'), ('sorento', 'kia_sorento', '쏘렌토'),
        ('palisade', 'hyundai_palisade', '디 올 뉴 팰리세이드'), ('carnival', 'kia_carnival', '더 뉴 카니발'),
        ('gv70', 'genesis_gv70', 'GV70'), ('gv80', 'genesis_gv80', 'GV80')]
COLORS = {'white': 0.93, 'gray': 0.55, 'black': 0.16}  # 차체 목표 밝기(0~1)
RATIO, WIDTHS = 16 / 10, (800, 1200)


def find(name):
    for ext in ('.jpg', '.jpeg', '.png', '.webp', '.JPG', '.JPEG', '.PNG'):
        p = INCOMING / f'{name}{ext}'
        if p.exists():
            return p
    return None


def car_mask(im):
    os.environ.setdefault('REMBG_HOME', str(ROOT / '.rembg'))
    from rembg import new_session, remove
    session = car_mask.session = getattr(car_mask, 'session', None) or new_session('u2net')
    cut = remove(im, session=session, only_mask=True)
    return np.asarray(cut.convert('L'), dtype=np.float32) / 255


def frame(im, mask):
    """차를 가운데 둔 16:10. 배경을 양옆·위아래에서 잘라 맞추고, 차가 들어가지 않을 때만 가장자리 색으로 채운다(블러 확대 없음)."""
    ys, xs = np.where(mask > 0.5)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    W, H = im.size
    w, h = (x1 - x0) * 1.12, (y1 - y0) * 1.25
    w, h = (h * RATIO, h) if w / h < RATIO else (w, w / RATIO)
    if h > H:  # 사진 높이를 넘으면 배경을 더 잘라 맞춘다(차 폭은 지킨다)
        h = max(H, (y1 - y0) * 1.05); w = max(h * RATIO, (x1 - x0) * 1.02); h = w / RATIO
    if w > W:
        w = max(W, (x1 - x0) * 1.02); h = w / RATIO
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    left = min(max(cx - w / 2, 0), max(W - w, 0)) if w <= W else cx - w / 2
    top = min(max(cy - h / 2, 0), max(H - h, 0)) if h <= H else cy - h / 2
    box = [int(round(v)) for v in (left, top, left + w, top + h)]
    a = np.asarray(im)
    edge = tuple(int(v) for v in np.median(np.concatenate([a[0], a[-1], a[:, 0], a[:, -1]]), axis=0))
    canvas = Image.new('RGB', (box[2] - box[0], box[3] - box[1]), edge)
    src = (max(box[0], 0), max(box[1], 0), min(box[2], W), min(box[3], H))
    canvas.paste(im.crop(src), (src[0] - box[0], src[1] - box[1]))
    m = Image.new('L', canvas.size, 0)
    m.paste(Image.fromarray((mask * 255).astype(np.uint8)).crop(src), (src[0] - box[0], src[1] - box[1]))
    return canvas, np.asarray(m, dtype=np.float32) / 255


def studio(rgba):
    """배경이 투명한 사진(제조사 구성기 이미지 등): 투명도를 차 영역으로 쓰고, 13종이 같은 크기·위치로 보이게
    밝은 스튜디오 바탕(16:10)에 놓는다. 차 폭은 화면 폭의 84%, 차 높이는 화면 높이의 72%를 넘지 않게, 바닥선은 아래 12%."""
    alpha = np.asarray(rgba.getchannel('A'))
    ys, xs = np.where(alpha > 8)
    car = rgba.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))
    W, H = 1600, 1000
    scale = min(W * 0.84 / car.width, H * 0.72 / car.height)
    car = car.resize((round(car.width * scale), round(car.height * scale)), Image.Resampling.LANCZOS)
    y = np.linspace(0, 1, H)[:, None]
    bg = np.repeat(np.repeat(244 - 14 * y, W, axis=1)[..., None], 3, axis=2)  # 위는 밝고 아래는 조금 어두운 바탕
    canvas = Image.fromarray(bg.astype(np.uint8)).convert('RGBA')
    pos = ((W - car.width) // 2, round(H * 0.88) - car.height)
    shadow = Image.new('L', (W, H), 0)  # 바닥 그림자: 차 아래 납작한 타원
    ImageDraw.Draw(shadow).ellipse((pos[0] + car.width * 0.06, H * 0.88 - car.height * 0.06, pos[0] + car.width * 0.94, H * 0.88 + car.height * 0.04), fill=70)
    shadow = shadow.filter(ImageFilter.GaussianBlur(18))
    canvas = Image.composite(Image.new('RGBA', (W, H), (40, 46, 56, 255)), canvas, shadow)
    canvas.alpha_composite(car, pos)
    m = Image.new('L', (W, H), 0)
    m.paste(car.getchannel('A'), pos)
    return canvas.convert('RGB'), np.asarray(m, dtype=np.float32) / 255


def recolor(im, mask, target):
    """차체만 밝기를 옮긴다: 차 영역(경계를 또렷하게) 안에서 차체 밝기 근처인 넓은 면.
    유리·타이어·그릴처럼 훨씬 어두운 곳, 램프처럼 아주 밝은 점, 배경은 그대로. 반사·음영의 상대 차이는 유지."""
    a = np.asarray(im, dtype=np.float32) / 255
    lum = a @ np.array([0.299, 0.587, 0.114], dtype=np.float32)
    car = np.clip((mask - 0.5) * 6 + 0.5, 0, 1)                       # 배경 쪽 옅은 값 제거
    car = np.asarray(Image.fromarray((car * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(5)), dtype=np.float32) / 255
    body_lum = np.percentile(lum[car > 0.5], 70)                      # 대표 차체 밝기
    near = np.clip(1 - np.abs(lum - body_lum) / 0.45, 0, 1) ** 0.5
    weight = Image.fromarray((car * near * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.5))
    weight = np.asarray(weight, dtype=np.float32)[..., None] / 255
    contrast = 0.55 if target < 0.4 else 0.8 if target < 0.8 else 1.0
    shifted = np.clip(target + (lum - body_lum) * contrast, 0, 1)
    out = a * (1 - weight) + np.repeat(shifted[..., None], 3, axis=2) * weight
    return Image.fromarray((out * 255).astype(np.uint8))


def board(rows, path):
    cw, ch, pad = 360, 225, 28
    sheet = Image.new('RGB', (cw * 4 + 20, (ch + pad) * len(rows) + 10), 'white')
    d = ImageDraw.Draw(sheet)
    for r, (label, images) in enumerate(rows):
        y = r * (ch + pad) + 6
        d.text((6, y), label, fill='black')
        for c, img in enumerate(images):
            sheet.paste(img.resize((cw, ch)), (c * (cw + 5), y + 18))
    sheet.save(path, quality=88)


def main():
    global INCOMING
    ap = argparse.ArgumentParser()
    ap.add_argument('--only-board', action='store_true')
    ap.add_argument('--keep-color', nargs='*', default=[], help='색 변형 대신 대표 사진을 그대로 쓸 차종(엑셀 이름, 예: k5)')
    ap.add_argument('--incoming', default=str(INCOMING))
    args = ap.parse_args()
    INCOMING = Path(args.incoming)
    missing = [f for _, f, _ in CARS if not find(f)]
    if missing:
        sys.exit(f'사진이 없어요({len(missing)}개): ' + ', '.join(missing))
    rows = []
    for stem, file, name in CARS:
        src = find(file)
        raw = Image.open(src)
        if raw.width < 1600:
            print(f'주의: {src.name} 가로 {raw.width}px (1600px 미만)')
        rgba = raw.convert('RGBA')
        transparent = (np.asarray(rgba.getchannel('A')) < 8).mean() > 0.1
        im = raw.convert('RGB')
        framed, m = studio(rgba) if transparent else frame(im, car_mask(im))
        variants = {c: (framed if stem in args.keep_color else recolor(framed, m, v)) for c, v in COLORS.items()}
        rows.append((f'{name} ({src.name}, 원본 {im.width}x{im.height})', [framed] + [variants[c] for c in ('white', 'black', 'gray')]))
        if args.only_board:
            continue
        ORIGINALS.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, ORIGINALS / src.name)
        for color, img in variants.items():
            for w in WIDTHS:
                (OUT / f'w{w}').mkdir(parents=True, exist_ok=True)
                img.resize((w, round(w / RATIO)), Image.Resampling.LANCZOS).save(OUT / f'w{w}' / f'{stem}_{color}.webp', 'WEBP', quality=82, method=6)
    board(rows, BOARD / 'board_13_colors.jpg')
    print('비교판:', BOARD / 'board_13_colors.jpg', '(왼쪽부터 대표 사진 · 화이트 · 블랙 · 그레이)')


if __name__ == '__main__':
    main()

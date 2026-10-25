"""make_test_anim.py : パイプライン確認用のテストアニメ（PNG 連番）を作る

使い方:  python make_test_anim.py [出力フォルダ] [コマ数] [--static]
  既定は samples/anim1/、32 コマ。256x256。
  ゆっくり色が変わるグラデーション背景の上を、円が一周する。左上にコマ番号の目盛り（白い四角）。
  --static を付けると背景は止まったまま（前フレーム差分が効く、アニメらしい素材）。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent


def make_layers(out: Path, n_bg=8, n_ch=12):
    """重ね合わせのテスト素材：out/bg（背景、n_bg 枚、色が変わる縞）と out/chara（キャラ、n_ch 枚、透明な背景の上で円が一周）"""
    (out / "bg").mkdir(parents=True, exist_ok=True)
    (out / "chara").mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:256, 0:256].astype(np.float64)
    for i in range(n_bg):
        t = i / n_bg
        r = 128 + 90 * np.sin(yy / 40 + 2 * np.pi * t)
        g = 128 + 90 * np.sin(xx / 50)
        b = 128 + 90 * np.cos(2 * np.pi * t + yy / 70)
        im = Image.fromarray(np.stack([r, g, b], -1).clip(0, 255).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(im)
        d.rectangle([4 + i * 12, 240, 12 + i * 12, 248], fill=(255, 255, 255))  # 背景のコマ番号（下）
        im.save(out / "bg" / f"b{i:03d}.png")
    for i in range(n_ch):
        t = i / n_ch
        im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        cx = 128 + 70 * np.cos(2 * np.pi * t)
        cy = 120 + 70 * np.sin(2 * np.pi * t)
        d.ellipse([cx - 30, cy - 30, cx + 30, cy + 30], fill=(250, 240, 40, 255), outline=(0, 0, 0, 255), width=3)
        d.ellipse([cx - 12, cy - 10, cx - 4, cy - 2], fill=(0, 0, 0, 255))
        d.ellipse([cx + 4, cy - 10, cx + 12, cy - 2], fill=(0, 0, 0, 255))
        d.rectangle([4 + i * 8, 4, 9 + i * 8, 9], fill=(255, 255, 255, 255))  # キャラのコマ番号（上）
        im.save(out / "chara" / f"c{i:03d}.png")
    # テキスト面用（16 色以内）：上下の帯（字幕の枠のようなもの）と、その中を左右に動く色の四角。ほかは透明
    (out / "text").mkdir(parents=True, exist_ok=True)
    n_tx = 6
    cols = [(255, 255, 255, 255), (255, 80, 80, 255), (80, 200, 255, 255), (255, 220, 60, 255)]
    for i in range(n_tx):
        im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rectangle([8, 196, 247, 247], fill=(20, 20, 60, 255), outline=(255, 255, 255, 255), width=2)
        x = 20 + i * 36
        d.rectangle([x, 208, x + 28, 236], fill=cols[i % 4])
        d.rectangle([0, 0, 255, 5], fill=cols[(i + 1) % 4])  # 上の細い帯
        im.save(out / "text" / f"t{i:03d}.png")
    # スプライト用（16 色以内、小さい絵）：spr1＝画面を横切る星（8 枚）、spr2＝その場で羽ばたくコウモリ（4 枚）
    (out / "spr1").mkdir(parents=True, exist_ok=True)
    (out / "spr2").mkdir(parents=True, exist_ok=True)
    for i in range(8):
        im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        cx, cy = 20 + i * 30, 40 + int(20 * np.sin(i / 8 * 2 * np.pi))
        pts = []
        for k in range(10):
            r = 14 if k % 2 == 0 else 6
            ang = -np.pi / 2 + k * np.pi / 5
            pts.append((cx + r * np.cos(ang), cy + r * np.sin(ang)))
        d.polygon(pts, fill=(255, 230, 0, 255), outline=(200, 80, 0, 255))
        im.save(out / "spr1" / f"s{i:03d}.png")
    for i in range(4):
        im = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        up = [10, 4, -2, 4][i]
        d.ellipse([196, 112, 212, 128], fill=(90, 40, 140, 255))
        d.polygon([(196, 120), (176, 120 - up), (184, 128)], fill=(140, 80, 200, 255))
        d.polygon([(212, 120), (232, 120 - up), (224, 128)], fill=(140, 80, 200, 255))
        d.point([(201, 117), (207, 117)], fill=(255, 0, 0, 255))
        im.save(out / "spr2" / f"b{i:03d}.png")
    # BG 用（8x8 のタイルで作る。同じタイルが多いほど良い）：
    #   bgt0＝レンガの壁（下半分）と、点滅する窓（4 枚）。上半分は透明。bgt1＝空の横縞（1 枚、BG0 の後ろ）
    (out / "bgt0").mkdir(parents=True, exist_ok=True)
    (out / "bgt1").mkdir(parents=True, exist_ok=True)
    brick = np.zeros((8, 8, 4), np.uint8)
    brick[:] = (170, 60, 40, 255)
    brick[3, :] = (220, 210, 200, 255)
    brick[7, :] = (220, 210, 200, 255)
    brick[0:3, 3] = (220, 210, 200, 255)
    brick[4:7, 7] = (220, 210, 200, 255)
    win_on = np.zeros((8, 8, 4), np.uint8)
    win_on[:] = (255, 230, 90, 255)
    win_off = np.zeros((8, 8, 4), np.uint8)
    win_off[:] = (30, 30, 70, 255)
    for i in range(4):
        a = np.zeros((256, 256, 4), np.uint8)
        for ty in range(16, 32):
            for tx in range(32):
                a[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8] = brick
        for k, (wy, wx) in enumerate([(20, 4), (20, 12), (20, 20), (20, 27), (26, 8), (26, 16), (26, 24)]):
            lit = (k + i) % 4 != 0  # 窓がひとつずつ消えていく
            for dy in range(2):
                for dx in range(2):
                    a[(wy + dy) * 8:(wy + dy) * 8 + 8, (wx + dx) * 8:(wx + dx) * 8 + 8] = win_on if lit else win_off
        Image.fromarray(a, "RGBA").save(out / "bgt0" / f"w{i:03d}.png")
    sky = np.zeros((256, 256, 4), np.uint8)
    cols = [(40, 60, 160), (60, 90, 190), (90, 130, 210), (130, 170, 230)]
    for ty in range(32):
        sky[ty * 8:ty * 8 + 8, :, :3] = cols[min(ty // 4, 3)]
    sky[..., 3] = 255
    Image.fromarray(sky, "RGBA").save(out / "bgt1" / "s000.png")
    print(f"{out} に bg {n_bg} 枚、chara {n_ch} 枚、text {n_tx} 枚、spr1 8 枚、spr2 4 枚、bgt0 4 枚、bgt1 1 枚を作成")


def main(argv):
    if "--layers" in argv:
        argv = [a for a in argv if a != "--layers"]
        make_layers(Path(argv[1]) if len(argv) > 1 else ROOT / "samples" / "layer1")
        return 0
    static = "--static" in argv
    argv = [a for a in argv if a != "--static"]
    out = Path(argv[1]) if len(argv) > 1 else ROOT / "samples" / "anim1"
    n = int(argv[2]) if len(argv) > 2 else 32
    out.mkdir(parents=True, exist_ok=True)
    yy, xx = np.mgrid[0:256, 0:256].astype(np.float64)
    for i in range(n):
        t = i / n
        tb = 0.0 if static else t  # 背景の時刻
        r = 128 + 100 * np.sin(xx / 60 + 2 * np.pi * tb)
        g = 128 + 100 * np.sin(yy / 50)
        b = np.full_like(xx, 128 + 100 * np.cos(2 * np.pi * tb))
        im = Image.fromarray(np.stack([r, g, b], -1).clip(0, 255).astype(np.uint8), "RGB")
        d = ImageDraw.Draw(im)
        cx = 128 + 80 * np.cos(2 * np.pi * t)
        cy = 128 + 80 * np.sin(2 * np.pi * t)
        d.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=(250, 240, 40), outline=(0, 0, 0), width=3)
        for k in range(i + 1):  # コマ番号の目盛り
            x = 4 + (k % 16) * 7
            y = 4 + (k // 16) * 7
            d.rectangle([x, y, x + 4, y + 4], fill=(255, 255, 255))
        im.save(out / f"f{i:03d}.png")
    print(f"{out} に {n} コマ作成")


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

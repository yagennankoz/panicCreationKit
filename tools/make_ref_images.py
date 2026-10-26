"""make_ref_images.py : bpica.x の正解データ作り用のテスト画像を作る

使い方:  pt make_ref_images

出力:
  samples/reference/src/rN.png  … 確認用の PNG（X68000 の色に丸めた後の色）
  x68/ref/rN.raw                … gload.x で表示する生データ
                                   256x256、1ドット1ワード（GRB 5:5:5:1、ビッグエンディアン）
各画像は a_enc の各モードが出やすい内容にしてある。色数はすべて 256 以下。
"""
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
PNG_DIR = ROOT / "samples" / "reference" / "src"
RAW_DIR = ROOT / "x68" / "ref"
W = H = 256


def rgb5(r, g, b):
    """0〜31 の RGB を 1つの色（タプル）にする"""
    return (int(r) & 31, int(g) & 31, int(b) & 31)


def palette_ramp(n, seed):
    """重ならない n 色（RGB 各5ビット）を作る。黒 (0,0,0) は含めない"""
    rng = np.random.default_rng(seed)
    cols = set()
    out = []
    while len(out) < n:
        c = tuple(int(v) for v in rng.integers(0, 32, 3))
        if c == (0, 0, 0) or c in cols:
            continue
        cols.add(c)
        out.append(c)
    return out


def img_r1():
    """塗りつぶし・行コピー・ランレングスが出る絵（黒を含む）"""
    img = np.zeros((H, W, 3), np.uint8)
    pal = palette_ramp(40, 1)
    img[0:1] = pal[0]                    # 1行だけの塗りつぶし ($02)
    img[1:40] = pal[1]                   # 複数行の塗りつぶし ($04)
    for y in range(40, 80):              # 横方向の帯（ランレングス $18）、奇数・偶数長を混ぜる
        x = 0
        k = y % 7
        while x < W:
            ln = 1 + (x * 7 + y * 3) % 23
            img[y, x : x + ln] = pal[2 + (k % 10)]
            x += ln
            k += 1
    for y in range(80, 160):             # 周期 2,3,4 の繰り返し行（1〜4行前コピー $06〜$0C）
        period = 2 + (y - 80) // 27
        src = 80 + (y - 80) % period
        for x in range(W):
            img[y, x] = pal[12 + ((x // (3 + src % 5)) + src) % 8]
    for y in range(160, 224):            # 1行前をコピーして数ドット修正 ($0E)
        img[y] = img[y - 1] if y > 160 else pal[20]
        if y > 160:
            n = (y - 160) % 9
            for i in range(n):
                x = (y * 37 + i * 53) % W
                img[y, x] = pal[21 + (i % 10)]
    img[224:] = (0, 0, 0)                # 黒（色0 の扱いを見る）
    for y in range(232, 256, 4):
        img[y, ::5] = pal[31]
    return img


def img_r2():
    """ランダムノイズ（ベタ $1A/$1C が出る）。黒以外の 255 色"""
    rng = np.random.default_rng(2)
    pal = np.array(palette_ramp(255, 2), np.uint8)
    return pal[rng.integers(0, 255, (H, W))]


def img_r3():
    """なめらかなグラデーション＋ディザ（写真に近いもの）。255 色以下"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
    r = 15.5 + 15.5 * np.sin(xx / 23.0) * np.cos(yy / 31.0)
    g = 15.5 + 15.5 * np.sin((xx + yy) / 40.0)
    b = 15.5 + 15.5 * np.cos(np.hypot(xx - 128, yy - 128) / 18.0)
    img = np.stack([r, g, b], -1)
    # 各成分を 6 段階（6^3=216色）にしてディザ
    bayer = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16.0
    th = bayer[yy.astype(int) % 4, xx.astype(int) % 4][..., None]
    lv = np.floor(img / 31.0 * 5 + th).clip(0, 5)
    out = (lv * 31 / 5).round().astype(np.uint8)
    out[(out == 0).all(-1)] = (1, 1, 1)  # 黒を避ける
    return out


def img_r4():
    """修正系の境界条件：左右ブロック片側だけの修正、128 箇所の修正、奇数・偶数位置"""
    pal = palette_ramp(16, 4)
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = pal[0]
    for y in range(1, H):
        img[y] = img[y - 1]
        kind = y % 8
        if kind == 1:                     # 左ブロックだけ1ドット
            img[y, y % 128] = pal[1 + y % 15]
        elif kind == 2:                   # 右ブロックだけ1ドット
            img[y, 128 + y % 128] = pal[1 + y % 15]
        elif kind == 3:                   # 左端と右端
            img[y, 0] = pal[1 + y % 15]
            img[y, 255] = pal[1 + (y + 3) % 15]
        elif kind == 4:                   # 左ブロック 128 箇所すべて
            img[y, 0:128] = pal[1 + (y // 8) % 15]
        elif kind == 5:                   # ブロック境界 127/128
            img[y, 127] = pal[1 + y % 15]
            img[y, 128] = pal[1 + (y + 5) % 15]
        elif kind == 6:                   # 塗りつぶして修正 ($16) が出やすい行
            img[y] = pal[(y // 8) % 16]
            img[y, (y * 13) % 256] = pal[(y // 8 + 1) % 16]
        # kind 0, 7 は変更なし（1行前コピー）
    return img


def img_r5():
    """黒以外ちょうど 254 色（bpica の上限の確認）。先頭3行を塗りつぶし（$04 で3バイト）にして
    以降のベタが奇数位置（$1A）になるようにする"""
    rng = np.random.default_rng(5)
    pal = np.array(palette_ramp(254, 5), np.uint8)
    idx = rng.integers(0, 254, (H, W))
    idx[0:3] = 0
    idx[3, :254] = np.arange(254)  # 254 色すべてを確実に使う
    return pal[idx]


def img_r7():
    """パレット追記（r1 のパレットを使って -p なしでエンコード）、輝度ビット、長いランの分割。
    戻り値は (RGB 画像, 輝度ビットを立てるマスク)"""
    r1 = img_r1()
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = r1[40]                      # r1 にある色の行
    newpal = palette_ramp(60, 7)
    runs = [113, 114, 115, 225, 226, 227, 112, 111, 1, 2, 3, 255, 256, 128, 127, 129]
    for y in range(16, 16 + len(runs) * 2):
        n = runs[(y - 16) // 2]
        img[y] = newpal[0]
        img[y, :n] = newpal[1 + (y % 2)]  # 先頭 n ドットを別の色に
        if n < 256:
            img[y, n:] = newpal[3 + (y % 3)]
    for y in range(64, 128):             # 新しい色を多めに（パレットへの追記）
        for x in range(0, W, 8):
            img[y, x : x + 8] = newpal[6 + ((x // 8 + y) % 50)]
    mask = np.zeros((H, W), bool)
    mask[130:140, 10:200] = True         # 輝度ビットを立てる（bpica は透明=番号0にする）
    mask[141, ::3] = True
    return img, mask


# ---- テキスト面・スプライト用（bpic.x 1.08 の -t -h／-s の正解データ用。16 色以内、透明は輝度ビット）----

def _pal16(seed, n=12):
    return palette_ramp(n, seed)


def img_t1():
    """横の帯と四角（ランや同じ行の繰り返しが出る）。左右の余白は透明"""
    pal = _pal16(11)
    img = np.zeros((H, W, 3), np.uint8)
    for y in range(H):
        img[y] = pal[(y // 12) % 12]
    img[60:120, 40:200] = pal[3]
    img[140:200, 80:120] = pal[7]
    img[150:160, 0:256:2] = (0, 0, 0)
    mask = np.zeros((H, W), bool)
    mask[:, :16] = True
    mask[:, 240:] = True
    return img, mask


def img_t2():
    """ノイズ（12 色）、3 割が透明"""
    rng = np.random.default_rng(12)
    pal = np.array(_pal16(12), np.uint8)
    img = pal[rng.integers(0, 12, (H, W))]
    mask = rng.random((H, W)) < 0.3
    return img, mask


def img_t3():
    """透明な背景の上の円（キャラのようなもの）。黒い縁取り"""
    pal = _pal16(13)
    yy, xx = np.mgrid[0:H, 0:W]
    r = np.hypot(xx - 128, yy - 128)
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = pal[0]
    for k in range(6):
        img[r < 90 - k * 14] = pal[1 + k]
    img[(r >= 90) & (r < 94)] = (0, 0, 0)
    mask = r >= 94
    return img, mask


def img_t4():
    """縦縞と市松（ビットプレーンの並びが分かりやすい）。透明なし"""
    pal = _pal16(14)
    yy, xx = np.mgrid[0:H, 0:W]
    idx = np.where(yy < 128, (xx // 4) % 12, ((xx // 8) + (yy // 8)) % 12)
    return np.array(pal, np.uint8)[idx], None


def img_s1():
    """スプライト用：左上の 64x48 に小さなキャラ、ほかは透明"""
    pal = _pal16(15)
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = pal[0]
    mask = np.ones((H, W), bool)
    yy, xx = np.mgrid[0:48, 0:64]
    body = ((xx - 32) / 30) ** 2 + ((yy - 24) / 22) ** 2 < 1
    sub = img[:48, :64]
    sub[body] = pal[2]
    sub[body & (yy < 20)] = pal[5]
    sub[(abs(xx - 22) < 3) & (abs(yy - 18) < 3)] = (0, 0, 0)
    sub[(abs(xx - 42) < 3) & (abs(yy - 18) < 3)] = (0, 0, 0)
    mask[:48, :64] = ~body
    return img, mask


def to_x68_words(img):
    """RGB 各5ビット → GRB 5:5:5:1 のワード（I=0）"""
    r = img[..., 0].astype(np.uint16)
    g = img[..., 1].astype(np.uint16)
    b = img[..., 2].astype(np.uint16)
    return (g << 11) | (r << 6) | (b << 1)


def main():
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    for name, fn in [("r1", img_r1), ("r2", img_r2), ("r3", img_r3), ("r4", img_r4),
                     ("r5", img_r5), ("r7", img_r7),
                     ("t1", img_t1), ("t2", img_t2), ("t3", img_t3), ("t4", img_t4), ("s1", img_s1)]:
        img = fn()
        mask = None
        if isinstance(img, tuple):
            img, mask = img
        assert img.shape == (H, W, 3) and img.max() <= 31
        ncol = len(np.unique(img.reshape(-1, 3), axis=0))
        assert ncol <= 256, (name, ncol)
        png = (img.astype(np.uint16) * 255 // 31).astype(np.uint8)
        Image.fromarray(png, "RGB").save(PNG_DIR / f"{name}.png")
        words = to_x68_words(img)
        if mask is not None:
            words = words | mask.astype(np.uint16)  # 輝度ビット
        (RAW_DIR / f"{name}.raw").write_bytes(words.astype(">u2").tobytes())
        print(f"{name}: {ncol} 色")


if __name__ == "__main__":
    import sys

    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(lambda argv: main()))

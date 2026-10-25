"""spr_enc.py : panic のスプライトセル（SPCG／SPON に渡すデータ、bpic.x -s の出力と同じ形）

形式（panic.x V1.38 の逆アセンブル text+$2AF2〜、bpic.x 1.08 の出力 samples/reference/text/s1 で確認）:
  +0  .w キャラ数 N（横×縦）
  +2  .b パレット番号  （SPCG が書き込む）
  +3  .b 先頭の PCG 番号（SPCG が書き込む）
  +4  .w 優先度        （SPCG が 3 を書き込む）
  +6  .w 横のキャラ数 − 1（0〜15）
  +8  .w 縦のキャラ数 − 1
  +10 .w X、+12 .w Y   （左上のキャラの位置。画面の (0,0) は 16,16）
  +14 PCG データ N × 128 バイト（左上から横へ。1 キャラ＝8x8 を 左上・左下・右上・右下 の順、1 バイト 2 ドット、上位が左）
SPCG は N 個の PCG を続けて定義する（1 つの .pan で合計 256 まで）。SPON は N 枚のスプライトを使う（同時に 128 枚まで）。
"""
import struct

import numpy as np

BLOCKS = [(0, 0), (1, 0), (0, 1), (1, 1)]  # 8x8 の並び：左上、左下、右上、右下


class SprError(ValueError):
    pass


def pcg_bytes(tile):
    """16x16 の色番号（0〜15）→ 128 バイト"""
    out = bytearray()
    for by, bx in BLOCKS:
        b = tile[by * 8:by * 8 + 8, bx * 8:bx * 8 + 8]
        for r in range(8):
            for c in range(4):
                out.append((int(b[r, c * 2]) << 4) | int(b[r, c * 2 + 1]))
    return bytes(out)


def pcg_tile(data):
    """128 バイト → 16x16 の色番号"""
    t = np.zeros((16, 16), np.uint8)
    for k, (by, bx) in enumerate(BLOCKS):
        for r in range(8):
            for c in range(4):
                v = data[k * 32 + r * 4 + c]
                t[by * 8 + r, bx * 8 + c * 2] = v >> 4
                t[by * 8 + r, bx * 8 + c * 2 + 1] = v & 15
    return t


def encode(idx):
    """256x256 の色番号（0＝透明、1〜15）→ スプライトセル。透明でない所を囲む最小の長方形を 16 ドット単位で切り出す。
    全部透明なら None"""
    if idx.max() > 15:
        raise SprError("スプライトは 16 色まで")
    ys, xs = np.nonzero(idx)
    if len(ys) == 0:
        return None
    x0, y0 = int(xs.min()), int(ys.min())
    cols = (int(xs.max()) - x0) // 16 + 1
    rows = (int(ys.max()) - y0) // 16 + 1
    if cols > 16:
        raise SprError(f"スプライトの横幅が 16 キャラ（256 ドット）を超えます（{cols}）")
    if cols * rows > 128:
        raise SprError(f"1 コマのキャラ数が 128 を超えます（{cols}×{rows}）")
    pad = np.zeros((rows * 16, cols * 16), np.uint8)
    h = min(rows * 16, 256 - y0)
    w = min(cols * 16, 256 - x0)
    pad[:h, :w] = idx[y0:y0 + h, x0:x0 + w]
    out = bytearray(struct.pack(">7H", cols * rows, 0, 0, cols - 1, rows - 1, x0 + 16, y0 + 16))
    for r in range(rows):
        for c in range(cols):
            out += pcg_bytes(pad[r * 16:r * 16 + 16, c * 16:c * 16 + 16])
    return bytes(out)


def header(cel):
    n, attr, prio, xc, yc, x, y = struct.unpack_from(">7H", cel, 0)
    return n, xc + 1, yc + 1, x, y


def decode(cel):
    """スプライトセル → 256x256 の色番号（表示したときの見た目）"""
    n, cols, rows, x, y = header(cel)
    img = np.zeros((256 + 512, 256 + 512), np.uint8)
    for k in range(n):
        r, c = divmod(k, cols)
        t = pcg_tile(cel[14 + 128 * k:14 + 128 * (k + 1)])
        px, py = x - 16 + c * 16 + 256, y - 16 + r * 16 + 256
        img[py:py + 16, px:px + 16] = t
    return img[256:512, 256:512]

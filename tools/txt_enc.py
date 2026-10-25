"""txt_enc.py : panic の高速テキスト形式（TDRW の code #2、bpic.x -t -h の出力）

  decode(data) -> (256,256) uint8 の色番号（0〜15）

形式（panic.x V1.38 の逆アセンブル：TDRW の処理 text+$75A、デコーダ text+$214E、分岐表 text+$2188。
bpic.x 1.08 の出力 samples/reference/text/t1〜t4 で確認）:
  +0 .w $0002
  以降、テキスト VRAM の 4 つのプレーンを、プレーン 0 から順に、各プレーン上の行から 256 行。
  1 行 = 256 ドット = 32 バイト（左のドットが上位ビット）。命令は 1 バイト（偶数）で、多くは 1 行ぶん：
    $00 j   0 の行を n 行（n = 32 - j/8）       $02     0 の行を 1 行
    $04 j   $FF の行を n 行（n = 32 - j/8）     $06     $FF の行を 1 行
    $08 j   1 行前と同じ行を n 行（n = 32 - j/8）$0A     1 行前と同じ
    $0C/$0E/$10   2/3/4 行前と同じ               $12/$14/$16   1/2/3 プレーン前の同じ行と同じ
    $18 (値, j)... (x, $48)   バイトのランレングス（値を 32 - j/2 個）。合計 32 バイトの後に j=$48 で終わり
    $1A j (位置, 値)...       0 の行にして n か所を書き換え（n = 32 - j/6）
    $1C j (位置, 値)...       $FF の行にして n か所を書き換え
    $1E/$20/$22/$24 j (…)     1/2/3/4 行前をコピーして n か所を書き換え
    $26/$28/$2A j (…)         1/2/3 プレーン前の同じ行をコピーして n か所を書き換え
    $2C + 32 バイト           そのまま
    $2E                       次のプレーンへ（256 行の後）
    $30                       終わり
  色番号 = プレーン0 のビット + プレーン1×2 + プレーン2×4 + プレーン3×8。色 0 は透明（下の面が見える）。
"""
import numpy as np

W = H = 256
ROWB = 32


class TxtError(ValueError):
    pass


def decode_planes(data: bytes, planes=None, y0=0, p0=0):
    """セルをプレーンの配列 (4, 行数, 32) の、プレーン p0・y0 行目から描く（テキスト VRAM の縦の帯など。既定は (4, 256, 32)）。
    p0 はプレーンごとのセル（plane_cel）を描くとき。前のプレーンを参照する命令は planes の前のプレーンを読む"""
    d = data
    if d[0:2] != b"\x00\x02":
        raise TxtError("先頭が $0002 ではありません")
    pl = np.zeros((4, H, ROWB), np.uint8) if planes is None else planes
    Hp = pl.shape[1]
    p, r, i = p0, y0, 2

    def row_n(j):
        if j % 8 or not 0 <= j < 256:
            raise TxtError(f"行数の指定が変（j=${j:02X}、+${i:X}）")
        return 32 - j // 8

    def mods(i):
        j = d[i]
        i += 1
        if j % 6:
            raise TxtError(f"書き換え数の指定が変（j=${j:02X}）")
        n = 32 - j // 6
        for _ in range(n):
            pos, val = d[i], d[i + 1]
            i += 2
            if pos >= ROWB:
                raise TxtError(f"書き換え位置が範囲外（{pos}）")
            pl[p, r, pos] = val
        return i

    while True:
        c = d[i]
        i += 1
        if c == 0x30:
            break
        if c == 0x2E:
            if r != y0 + H:
                raise TxtError(f"プレーン {p} が {r - y0} 行で次へ")
            p, r = p + 1, y0
            continue
        if p > 3 or r >= Hp:
            raise TxtError(f"範囲外（プレーン {p}、行 {r}、+${i - 1:X}）")
        if c in (0x00, 0x04, 0x08):
            n = row_n(d[i])
            i += 1
            for _ in range(n):
                if c == 0x00:
                    pl[p, r] = 0
                elif c == 0x04:
                    pl[p, r] = 0xFF
                else:
                    pl[p, r] = pl[p, r - 1]
                r += 1
            continue
        if c == 0x02:
            pl[p, r] = 0
        elif c == 0x06:
            pl[p, r] = 0xFF
        elif c in (0x0A, 0x0C, 0x0E, 0x10):
            pl[p, r] = pl[p, r - (c - 0x08) // 2]
        elif c in (0x12, 0x14, 0x16):
            pl[p, r] = pl[p - (c - 0x10) // 2, r]
        elif c == 0x18:
            x = 0
            while True:
                val, j = d[i], d[i + 1]
                i += 2
                if j == 0x48:
                    break
                n = 32 - j // 2
                pl[p, r, x:x + n] = val
                x += n
            if x != ROWB:
                raise TxtError(f"ランレングスの合計が {x}")
        elif c in (0x1A, 0x1C):
            pl[p, r] = 0 if c == 0x1A else 0xFF
            i = mods(i)
        elif c in (0x1E, 0x20, 0x22, 0x24):
            pl[p, r] = pl[p, r - (c - 0x1C) // 2]
            i = mods(i)
        elif c in (0x26, 0x28, 0x2A):
            pl[p, r] = pl[p - (c - 0x24) // 2, r]
            i = mods(i)
        elif c == 0x2C:
            pl[p, r] = np.frombuffer(d[i:i + ROWB], np.uint8)
            i += ROWB
        else:
            raise TxtError(f"未知の命令 ${c:02X}（+${i - 1:X}）")
        r += 1
    return pl, i


def planes_to_index(pl):
    bits = np.unpackbits(pl, axis=2)  # (4, 256, 256)、左のドットが上位ビット
    return (bits[0] | (bits[1] << 1) | (bits[2] << 2) | (bits[3] << 3)).astype(np.uint8)


def index_to_planes(idx):
    return np.stack([np.packbits((idx >> k) & 1, axis=1) for k in range(4)])


def decode(data: bytes):
    pl, end = decode_planes(data)
    return planes_to_index(pl), end


# ---------------------------------------------------------------------------
# 描画時間の見積もり（TDRW、高速テキスト）
#   時間 = Σ 特徴量 × 係数。係数は tools/timing.json の "text_<クロック>"（XM6 で測った値から求めたもの）
# ---------------------------------------------------------------------------
FEATURES = [
    "zN",     # $00 で描く行の数
    "z1",     # $02 の行
    "oN",     # $04 で描く行
    "o1",     # $06 の行
    "cN",     # $08 で描く行
    "c1",     # $0A の行
    "ck",     # $0C〜$10 の行
    "pl",     # $12〜$16 の行
    "rle",    # $18 の行
    "runs",   # $18 のランの数
    "zm",     # $1A／$1C の行
    "cm",     # $1E〜$24 の行
    "pm",     # $26〜$2A の行
    "mods",   # 書き換えの数
    "raw",    # $2C の行
]


def features(data: bytes) -> dict:
    f = dict.fromkeys(FEATURES, 0)
    d = data
    i = 2
    while True:
        c = d[i]
        i += 1
        if c == 0x30:
            return f
        if c == 0x2E:
            continue
        if c in (0x00, 0x04, 0x08):
            f[{0x00: "zN", 0x04: "oN", 0x08: "cN"}[c]] += 32 - d[i] // 8
            i += 1
        elif c in (0x02, 0x06, 0x0A):
            f[{0x02: "z1", 0x06: "o1", 0x0A: "c1"}[c]] += 1
        elif c in (0x0C, 0x0E, 0x10):
            f["ck"] += 1
        elif c in (0x12, 0x14, 0x16):
            f["pl"] += 1
        elif c == 0x18:
            f["rle"] += 1
            while d[i + 1] != 0x48:
                f["runs"] += 1
                i += 2
            i += 2
        elif 0x1A <= c <= 0x2A:
            f["zm" if c <= 0x1C else "cm" if c <= 0x24 else "pm"] += 1
            m = 32 - d[i] // 6
            f["mods"] += m
            i += 1 + 2 * m
        elif c == 0x2C:
            f["raw"] += 1
            i += ROWB
        else:
            raise TxtError(f"未知の命令 ${c:02X}")


PROVISIONAL_US_PER_ROW = 25.0  # 係数がまだ無いとき（XM6 で未計測）の仮の値
provisional_used = False


def estimate_us(data: bytes, clock: str = "10mhz") -> float:
    """描画時間の見積もり [us]（係数は clock.py：timing.json の text_<クロック>。測っていないクロックは計算）"""
    import clock as _clk
    coef = _clk.coef("text", clock)
    return sum(coef[k] * v for k, v in features(data).items())


# ---------------------------------------------------------------------------
# エンコーダ（各行で最も小さくなる命令を選ぶ。bpic.x と同じ出力ではない）
# ---------------------------------------------------------------------------

def _mods(row, base):
    """base の行を row にするための (位置, 値) の列"""
    diff = np.nonzero(row != base)[0]
    out = bytearray()
    for x in diff.tolist():
        out += bytes((x, int(row[x])))
    return len(diff), bytes(out)


def _rle(row):
    out = bytearray()
    x = 0
    while x < ROWB:
        v = row[x]
        e = x
        while e < ROWB and row[e] == v:
            e += 1
        out += bytes((int(v), 2 * (32 - (e - x))))
        x = e
    out += b"\x00\x48"
    return bytes(out)


ZERO = np.zeros(ROWB, np.uint8)
ONES = np.full(ROWB, 0xFF, np.uint8)


def encode_planes(pl) -> bytes:
    """プレーンの配列 (4, 256, 32) → 高速テキストのセル"""
    out = bytearray(b"\x00\x02")
    for p in range(4):
        out += encode_plane_ops(pl, p)
        out.append(0x2E if p < 3 else 0x30)
    return bytes(out)


def plane_cel(pl, p) -> bytes:
    """プレーン p だけを描くセル（分割描画用）。テキスト VRAM のプレーン p の位置（+p*$20000）に描く。
    プレーン前の同じ行を参照する命令は、テキスト VRAM の前のプレーン（先に描いておく）を読む"""
    c = b"\x00\x02" + encode_plane_ops(pl, p) + b"\x30"
    return c + (b"\x00" if len(c) % 2 else b"")


def encode_plane_ops(pl, p) -> bytes:
    """プレーン p の 256 行ぶんの命令（$2E／$30 は含まない）"""
    out = bytearray()
    if True:
        r = 0
        while r < H:
            row = pl[p, r]
            # 同じ種類の行が続くもの（0 の行、$FF の行、1 行前と同じ行）は回数つきでまとめる
            for code1, coden, test in ((0x02, 0x00, lambda rr: (pl[p, rr] == 0).all()),
                                       (0x06, 0x04, lambda rr: (pl[p, rr] == 0xFF).all()),
                                       (0x0A, 0x08, lambda rr: rr > 0 and (pl[p, rr] == pl[p, rr - 1]).all())):
                if test(r):
                    n = 1
                    while n < 32 and r + n < H and (pl[p, r + n] == pl[p, r + n - 1]).all():
                        n += 1
                    out += bytes((code1,)) if n == 1 else bytes((coden, 8 * (32 - n)))
                    r += n
                    break
            else:
                cands = []
                for k, code in ((2, 0x0C), (3, 0x0E), (4, 0x10)):  # k 行前と同じ
                    if r - k >= 0 and (row == pl[p, r - k]).all():
                        cands.append(bytes((code,)))
                for k, code in ((1, 0x12), (2, 0x14), (3, 0x16)):  # k プレーン前の同じ行と同じ
                    if p - k >= 0 and (row == pl[p - k, r]).all():
                        cands.append(bytes((code,)))
                cands.append(b"\x18" + _rle(row))
                bases = [(0x1A, ZERO), (0x1C, ONES)]
                bases += [(0x1C + 2 * k, pl[p, r - k]) for k in range(1, 5) if r - k >= 0]
                bases += [(0x24 + 2 * k, pl[p - k, r]) for k in range(1, 4) if p - k >= 0]
                for code, base in bases:
                    m, md = _mods(row, base)
                    if 0 < m <= 32:
                        cands.append(bytes((code, 6 * (32 - m))) + md)
                cands.append(b"\x2c" + row.tobytes())
                out += min(cands, key=len)
                r += 1
    return bytes(out)


def encode(idx) -> bytes:
    """色番号画像 (256,256)、0〜15 → 高速テキストのセル"""
    if idx.max() > 15:
        raise TxtError("テキスト面は 16 色まで")
    return encode_planes(index_to_planes(idx.astype(np.uint8)))

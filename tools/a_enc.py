"""a_enc.py : panic の a_enc 形式（新々グラフィック / code #4）のデコーダ

  decode(data, prev=None) -> (256,256) uint8 の色番号配列、使ったモードの列

形式は panic の付属ドキュメント docs/panic/a_enc.doc。bpica.x の出力（samples/reference/）と一致することを tools/test_a_enc.py で確かめられる。
"""
import json
from pathlib import Path

import numpy as np

W = H = 256
MODE_LETTER = {code: chr(ord("A") + code // 2) for code in range(0, 0x24, 2)}


class AEncError(ValueError):
    pass


def _modify(row, d, i):
    """修正データ（左右ブロックそれぞれ count,pos,color...）を row に適用。新しい i を返す"""
    for base in (0, 128):
        count = d[i]
        i += 1
        if count == 0:
            continue
        if count % 2 == 0:
            raise AEncError(f"修正件数が偶数: ${count:02X}")
        n = 128 - (count - 1) // 2
        for _ in range(n):
            pos, color = d[i], d[i + 1]
            i += 2
            row[base + pos // 2] = color
    return i


def _rle(row, d, i):
    x = 0
    while True:
        color, ln = d[i], d[i + 1]
        i += 2
        if ln == 0x7E:
            break
        if ln >= 0x80:  # 奇数ドット: len = -(dot + 15)
            dots = 256 - ln - 15
        else:  # 偶数ドット: len = 112 - dot
            dots = 112 - ln
        row[x : x + dots] = color
        x += dots
    if x != W:
        raise AEncError(f"ランレングスの合計が {x} ドット")
    return i


def decode(data: bytes, prev=None):
    """256 行そろったセルをデコードする。prev は描画先にある絵（差分モード用）"""
    img = np.zeros((H, W), np.uint8)
    pv = np.zeros((H, W), np.uint8) if prev is None else prev
    _, modes, end, rows = decode_rows(data, img, 0, pv)
    if rows != H:
        raise AEncError(f"行数が {rows}")
    return img, modes, end


def decode_rows(data: bytes, canvas: np.ndarray, y0: int, prev: np.ndarray | None = None):
    """セルを canvas（縦は何行でもよい、横 256）の y0 行目から描く。行の数は終端（$00）まで。
    panic.x と同じく、行コピー（D〜K）は canvas の上の行を、差分（P〜R）は prev（無ければ canvas の今の内容）を読む。
    途中の行までのセル（分割描画）も描ける。戻り値：(canvas, モードの列, 終端の次の位置, 描いた行数)"""
    d = data
    if d[0:2] != b"\x00\x04":
        raise AEncError("先頭が $0004 ではありません")
    img = canvas
    if prev is None:
        prev = canvas.copy()
    Hc = img.shape[0]
    modes = []
    i = 2
    y = y0
    while True:
        code = d[i]
        i += 1
        modes.append(MODE_LETTER.get(code, "?"))
        if code == 0x00:
            break
        if y >= Hc:
            raise AEncError("描画先の範囲を超えました")
        if code == 0x02:  # 1行 FILL
            img[y] = d[i]
            i += 1
            y += 1
        elif code == 0x04:  # 複数行 FILL
            color, n = d[i], d[i + 1] + 1
            i += 2
            img[y : y + n] = color
            y += n
        elif code in (0x06, 0x08, 0x0A, 0x0C):  # k 行前コピー
            img[y] = img[y - (code - 4) // 2]
            y += 1
        elif code in (0x0E, 0x10, 0x12, 0x14):  # k 行前コピー＋修正
            img[y] = img[y - (code - 0x0C) // 2]
            i = _modify(img[y], d, i)
            y += 1
        elif code == 0x16:  # FILL＋修正
            img[y] = d[i]
            i = _modify(img[y], d, i + 1)
            y += 1
        elif code == 0x18:  # ランレングス
            i = _rle(img[y], d, i)
            y += 1
        elif code in (0x1A, 0x1C):  # ベタ（$1C はパディング 1 バイトの後）
            if code == 0x1C:
                i += 1
            if i % 2:
                raise AEncError(f"ベタのデータが奇数位置 (+${i:X})")
            img[y] = np.frombuffer(d[i : i + W], np.uint8)
            i += W
            y += 1
        elif code == 0x1E:  # 前フレームの1行
            img[y] = prev[y]
            y += 1
        elif code == 0x20:  # 前フレームの複数行
            n = d[i] + 1
            i += 1
            img[y : y + n] = prev[y : y + n]
            y += n
        elif code == 0x22:  # 前フレーム＋修正
            img[y] = prev[y]
            i = _modify(img[y], d, i)
            y += 1
        else:
            raise AEncError(f"未知のモード ${code:02X}（+${i - 1:X}）")
    return img, "".join(modes), i, y - y0


# ---------------------------------------------------------------------------
# 描画時間の見積もり（panic.x V1.38 の GDRW）
#   描画時間 [µs] = Σ 特徴量 × 係数。特徴量は features() が数える。
#   係数は MPU クロックごとに tools/timing.json にある（XM6 で測った値から求めたもの）。
#   目標の対象機は 10MHz の X68000 なので、既定は "10mhz"。
# ---------------------------------------------------------------------------
FEATURES = [
    "fill",       # $02 の行数
    "filln",      # $04 で塗る行数
    "copy",       # 行コピーする行数（$06〜$0C と $0E〜$14）
    "fillmod",    # $16 の行数
    "rle",        # $18 の行数
    "runs",       # $18 のランの数（112 ドットごとの切り出しを含む）
    "beta",       # $1A/$1C の行数
    "skip",       # $1E の行数
    "skipn",      # $20 で飛ばす行数
    "remod",      # $22 の行数
    "mods",       # 修正の数（$0E〜$16、$22 の合計）
    "modblocks",  # 修正のある左右ブロックの数
]
DEFAULT_CLOCK = "10mhz"
_TIMING_FILE = Path(__file__).resolve().parent / "timing.json"
_timing_cache = {}


def timing(clock: str = DEFAULT_CLOCK) -> dict:
    """描画時間の係数 [us]（clock.py：XM6 で測ったクロックはその値、ほかは測った値から計算）"""
    import clock as _clk
    key = _clk.parse(clock)
    if key not in _timing_cache:
        _timing_cache[key] = _clk.coef("graphic", key)
    return _timing_cache[key]


def _count_mods(d, i, f):
    for _ in range(2):
        c = d[i]
        i += 1
        if c:
            a = 128 - (c - 1) // 2
            f["mods"] += a
            f["modblocks"] += 1
            i += 2 * a
    return i


def features(data: bytes) -> dict:
    """a_enc データから描画時間の特徴量を数える"""
    f = dict.fromkeys(FEATURES, 0)
    d = data
    i = 2
    while True:
        code = d[i]
        i += 1
        if code == 0x00:
            return f
        if code == 0x02:
            f["fill"] += 1
            i += 1
        elif code == 0x04:
            f["filln"] += d[i + 1] + 1
            i += 2
        elif code in (0x06, 0x08, 0x0A, 0x0C):
            f["copy"] += 1
        elif code in (0x0E, 0x10, 0x12, 0x14):
            f["copy"] += 1
            i = _count_mods(d, i, f)
        elif code == 0x16:
            f["fillmod"] += 1
            i = _count_mods(d, i + 1, f)
        elif code == 0x18:
            f["rle"] += 1
            while d[i + 1] != 0x7E:
                f["runs"] += 1
                i += 2
            i += 2
        elif code in (0x1A, 0x1C):
            f["beta"] += 1
            i += W + (1 if code == 0x1C else 0)
        elif code == 0x1E:
            f["skip"] += 1
        elif code == 0x20:
            f["skipn"] += d[i] + 1
            i += 1
        elif code == 0x22:
            f["remod"] += 1
            i = _count_mods(d, i, f)
        else:
            raise AEncError(f"未知のモード ${code:02X}")


def estimate_us(data: bytes, clock: str = DEFAULT_CLOCK) -> float:
    """a_enc データの描画時間の見積もり [マイクロ秒]"""
    coef = timing(clock)
    f = features(data)
    return sum(coef[k] * v for k, v in f.items())


def read_palette(data: bytes):
    """bpica のパレットファイル（514 バイト）→ (最大番号, 256 ワードの配列)"""
    a = np.frombuffer(data, ">u2")
    return int(a[0]), a[1:257].copy()


# ---------------------------------------------------------------------------
# エンコーダ（bpica.x 互換）
#   bpica.x を逆アセンブルして処理を再現したもの。
#   bpica の出力とバイト単位で一致することを samples/reference/ で確認している。
# ---------------------------------------------------------------------------

class Palette:
    """bpica のパレット。番号0=透明($0001)、番号1=黒($0000) は予約。新しい色は出現順に追加。"""

    def __init__(self, data: bytes | None = None):
        if data is None:
            self.last = 1
            self.colors = [0x0001, 0x0000]
        else:
            last, words = read_palette(data)
            self.last = last
            self.colors = [int(v) for v in words[: last + 1]]
        self.index = {}
        for i, c in enumerate(self.colors):
            self.index.setdefault(c, i)

    def lookup(self, word: int) -> int:
        if word & 1:  # 輝度ビットが立っている色は透明扱い
            word = 0x0001
        i = self.index.get(word)
        if i is None:
            if self.last >= 255:
                raise AEncError("使用パレット数が限界値を超えました（256色以上）")
            self.last += 1
            self.colors.append(word)
            self.index[word] = i = self.last
        return i

    def to_bytes(self) -> bytes:
        words = self.colors + [0] * (256 - len(self.colors))
        return np.array([self.last] + words, ">u2").tobytes()


def quantize(words: np.ndarray, pal: Palette) -> np.ndarray:
    """(256,256) の GRB ワード画像 → 色番号画像（ラスター順にパレットへ登録）"""
    out = np.empty(words.shape, np.uint8)
    flat = words.reshape(-1)
    o = out.reshape(-1)
    for k, w in enumerate(flat.tolist()):
        o[k] = pal.lookup(w)
    return out


def _mod_blocks(row, ref):
    """修正データ（左右ブロック）を作る"""
    out = bytearray()
    for base in (0, 128):
        diff = np.nonzero(row[base : base + 128] != ref[base : base + 128])[0]
        a = len(diff)
        out.append((128 - a) * 2 + 1 if a else 0)
        for b in diff.tolist():
            out += bytes((b * 2, int(row[base + b])))
    return bytes(out)


def _rle_bytes(row):
    out = bytearray()
    x = 0
    while x < W:
        c = int(row[x])
        e = x
        while e < W and row[e] == c:
            e += 1
        n = e - x
        while n > 0x71:  # 114 ドット以上は 112 ドットずつ切り出す
            out += bytes((c, 0x00))
            n -= 0x70
        if n & 1:
            out += bytes((c, (-(n + 15)) & 0xFF))
        else:
            out += bytes((c, 0x70 - n))
        x = e
    out += b"\x00\x7e"
    return bytes(out)


def _row_us(cand: bytes, clock: str) -> float:
    """1 行ぶんの候補の描画時間の見積もり"""
    return estimate_us(b"\x00\x04" + cand + b"\x00", clock)


def encode(img: np.ndarray, prev: np.ndarray | None = None, time_weight: float = 0.0,
           clock: str = DEFAULT_CLOCK) -> bytes:
    """色番号画像 (256,256) uint8 → a_enc データ

    prev=None かつ time_weight=0 のときは bpica.x と同じ出力（バイト単位で一致）。
    time_weight > 0 のとき、各行の候補を「バイト数 + time_weight × 描画時間[us]」の小さい順で選ぶ
    （描画時間は estimate_us の実測モデル）。大きくするほど速く描けるがデータは大きくなる。
    prev を渡すと時間軸モード（$1E/$20/$22）も使う。prev は「描画先の GRAM に今ある絵」
    （panic.x の $1E/$20 は GRAM の行を書き換えずに飛ばし、$22 は GRAM の行をその場で修正する。
    panic.x V1.38 の逆アセンブルで確認）。
    """
    segs = encode_segments(img, prev, 0, H, time_weight, clock)
    return b"\x00\x04" + b"".join(s for _, _, s in segs) + b"\x00"


def encode_segments(img: np.ndarray, prev: np.ndarray | None, r0: int, r1: int,
                    time_weight: float = 0.0, clock: str = DEFAULT_CLOCK):
    """img の r0〜r1-1 行を符号化し、[(先頭の行, 行数, バイト列), ...] を返す（ヘッダと終端は含まない）。
    先頭から何個か取ったもの（＋終端）も、それだけで正しいセルになる（分割描画：残りの行は別のセルで続きから描く）。
    r0 > 0 のとき、r0 より上の行は img の内容がすでに描かれているものとする（行コピーで参照する）。"""
    segs = []
    pos = 2  # セルの先頭からの位置（ベタの $1A/$1C の選び分けに使う）

    def put(y, n, b):
        nonlocal pos
        segs.append((y, n, bytes(b)))
        pos += len(b)

    y = r0
    while y < r1:
        if prev is not None:
            # 描画先と同じ行が続く間は飛ばす（P / Q）。最速なので最優先
            n = 0
            while y + n < r1 and (img[y + n] == prev[y + n]).all():
                n += 1
            if n:
                put(y, n, b"\x1e" if n == 1 else bytes((0x20, n - 1)))
                y += n
                continue
        # 同じ色だけの行が続く間はまとめる（色は最初の行の色）
        c = img[y, 0]
        n = 0
        while y + n < r1 and (img[y + n] == c).all():
            n += 1
        if n == 1:
            put(y, 1, bytes((0x02, int(c))))
        elif n > 1:
            put(y, n, bytes((0x04, int(c), n - 1)))
        y += n
        if y >= r1:
            break
        # ↑ の直後の行は塗りつぶし判定をせず、以下で処理する
        row = img[y]
        # k 行前と同じなら D〜G（1行前から順に調べ、最初に一致したもの）
        same = 0
        for k in range(1, 5):
            if y - k < 0:
                break
            if (row == img[y - k]).all():
                same = k
                break
        if same and not time_weight:
            put(y, 1, bytes((0x04 + 2 * same,)))
            y += 1
            continue
        cand = []
        if same:  # 時間も考えるときは、行コピー（遅い）も候補の一つとして比べる
            cand.append(bytes((0x04 + 2 * same,)))
        for k in range(1, 5):  # H〜K
            if y - k < 0:
                break
            cand.append(bytes((0x0C + 2 * k,)) + _mod_blocks(row, img[y - k]))
        while len(cand) < 4:
            cand.append(None)
        counts = np.bincount(row, minlength=256)
        fill = int(np.argmax(counts))  # 同数なら小さい番号
        cand.append(bytes((0x16, fill)) + _mod_blocks(row, np.full(W, fill, np.uint8)))
        cand.append(b"\x18" + _rle_bytes(row))
        if pos % 2:
            cand.append(b"\x1a" + row.tobytes())
        else:
            cand.append(b"\x1c\x00" + row.tobytes())
        if prev is not None:  # 描画先の行をその場で修正（R）。行のコピーが無いぶん速いので同サイズなら優先
            cand.append(b"\x22" + _mod_blocks(row, prev[y]))
        best = None
        if time_weight:
            best_cost = None
            for cnd in cand:
                if cnd is None:
                    continue
                cost = len(cnd) + time_weight * _row_us(cnd, clock)
                if best_cost is None or cost <= best_cost:
                    best, best_cost = cnd, cost
        else:
            for cnd in cand:  # 同じサイズなら後の候補を採る（bpica と同じ）
                if cnd is not None and (best is None or len(cnd) <= len(best)):
                    best = cnd
        put(y, 1, best)
        y += 1
    return segs


def cel_from_segments(segs) -> bytes:
    return b"\x00\x04" + b"".join(s for _, _, s in segs) + b"\x00"

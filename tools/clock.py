"""clock.py : 対象機の MPU クロック（名前の決まりと、描画時間・命令時間の係数）

- クロックは "10mhz"、"16.7mhz" のような名前で扱う。設定では 16.7、"16.7MHz"、"16.7mhz" のどれでも書ける（parse）。
- 係数は tools/timing.json：XM6 で測ったクロックごとに、グラフィック（"<n>mhz"）、テキスト面（"text_<n>mhz"）、
  命令（"cmd_<n>mhz"：IKEY と SPOF の時間）。測ったクロックはその値をそのまま使う。
- 測っていないクロックは計算する。XM6 の実測（10／12／15／16.7／17.4／20／24／25MHz）では：
  - 15MHz 以下では、時間はクロックにほぼ正確に反比例する。
  - 16.7MHz 以上では、反比例より一段遅い（塗り 1.12 倍、行コピー 1.03 倍、SPOF 1.6 倍。VRAM やスプライトへの
    アクセスのウェイトが増えるため）。その中ではまた反比例する。
  そこでクロックを GROUP_SPLIT で 2 つに分け、同じ側の測った点の間は「1/クロック」で直線につなぎ、
  測った範囲の外は、いちばん近い点から反比例で延ばす。
- X68030（68030）は CPU もバスも違うので、この計算の外（XM6 の「25MHz (X68030標準)」は 68000 を 25MHz で動かしたもの）。
"""
import json
import re
from pathlib import Path

TIMING_FILE = Path(__file__).resolve().parent / "timing.json"
GROUP_SPLIT = 16.0   # これ以上は XVI 系（ウェイトが増える）。XM6 では 15MHz と 16.7MHz の間で変わる
MIN_MHZ, MAX_MHZ = 1.0, 100.0
DEFAULT = "10mhz"

_data = None


def _load():
    global _data
    if _data is None:
        _data = json.loads(TIMING_FILE.read_text(encoding="utf-8"))
    return _data


def parse(value, where="設定", key="clock") -> str:
    """16.7／"16.7MHz"／"16.7mhz" → "16.7mhz"。おかしな値はエラーのメッセージで止める"""
    if value is None:
        return DEFAULT
    s = str(value).strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:mhz)?", s)
    if not m or isinstance(value, bool):
        raise SystemExit(f"{where}：{key} は MPU クロック（例：10、16.7、\"24mhz\"）で書いてください（今は {value!r}）")
    f = float(m.group(1))
    if not MIN_MHZ <= f <= MAX_MHZ:
        raise SystemExit(f"{where}：{key} は {MIN_MHZ:g}〜{MAX_MHZ:g}MHz で書いてください（今は {value!r}）")
    return f"{f:g}mhz"


def mhz(clock) -> float:
    return float(parse(clock)[:-3])


def _table(prefix):
    """{クロック[MHz]: 係数の dict}（測ったものだけ）"""
    out = {}
    for k, v in _load().items():
        m = re.fullmatch(re.escape(prefix) + r"(\d+(?:\.\d+)?)mhz", k)
        if m:
            out[float(m.group(1))] = v["coef"]
    return out


def measured(prefix=""):
    return sorted(_table(prefix))


def _interp(table, f):
    """同じ側（GROUP_SPLIT のどちらか）の測った点から、クロック f の係数を作る"""
    if f in table:
        return dict(table[f])
    side = [x for x in table if (x >= GROUP_SPLIT) == (f >= GROUP_SPLIT)] or list(table)
    lo = [x for x in side if x < f]
    hi = [x for x in side if x > f]
    if lo and hi:  # 間：1/クロックで直線につなぐ
        f1, f2 = max(lo), min(hi)
        w = (1 / f - 1 / f2) / (1 / f1 - 1 / f2)
        return {k: w * table[f1][k] + (1 - w) * table[f2][k] for k in table[f1]}
    near = max(lo) if lo else min(hi)  # 外：近い点から反比例で延ばす
    return {k: v * near / f for k, v in table[near].items()}


def coef(kind, clock) -> dict:
    """描画時間の係数 [us]。kind："graphic"（a_enc）／"text"（高速テキスト）"""
    table = _table("text_" if kind == "text" else "")
    if not table:
        raise SystemExit(f"tools/timing.json に {kind} の係数がありません")
    return _interp(table, mhz(clock))


def scale(clock, what="cpu") -> float:
    """命令の時間の、10MHz に対する倍率。what："cpu"（IKEY など CPU の処理）／"spof"（SPOF などスプライトの I/O）"""
    table = {f: {"cpu": c["ikey"], "spof": c["spof"]} for f, c in _table("cmd_").items()}
    if not table:
        return 10.0 / mhz(clock)
    base = _interp(table, 10.0)
    return _interp(table, mhz(clock))[what] / base[what]


def describe(clock) -> str:
    """測ったクロックか、計算したクロックかの説明"""
    f = mhz(clock)
    pts = measured()
    if f in pts:
        return f"{f:g}MHz（エミュレータで測った値）"
    side = [x for x in pts if (x >= GROUP_SPLIT) == (f >= GROUP_SPLIT)] or pts
    lo = [x for x in side if x < f]
    hi = [x for x in side if x > f]
    if lo and hi:
        return f"{f:g}MHz（測っていないので、{max(lo):g}MHz と {min(hi):g}MHz の測定から計算）"
    near = max(lo) if lo else min(hi)
    if min(pts) < f < max(pts):  # 15MHz と 16.7MHz の間（ウェイトが変わる所）
        return (f"{f:g}MHz（測っていないので、{near:g}MHz の測定から反比例で計算。"
                f"{GROUP_SPLIT:g}MHz 以上は XVI 系のウェイトがあるものとして扱う）")
    return f"{f:g}MHz（測った範囲の外なので、{near:g}MHz の測定から反比例で推定。誤差が大きいかもしれません）"

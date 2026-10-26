"""predict_time.py : mkanim.py が作ったアニメの再生時間を、MPU クロックごとに予測する

使い方:  pt predict_time <名前> [<名前> ...] [--clock 10mhz]
  x68/anim/<名前>/<名前>.s のスケジュール（DRW0 と TMWA の並び、SETR/LOOP）と各セルの描画時間の見積もりから、
  --timelog の T1−T0（1/100 秒）を予測する。

TMWA の動き（panic.x V1.38 の逆アセンブルと XM6 の実測で確認）：
  V-Sync ごとに増えるカウンタが待ちカウント w 以上になるまで待ち、0 に戻す。描画が終わった時点ですでに w 以上なら
  次の V-Sync まで待つ。よって 1 コマ＝ w カウント（描画中の V-Sync が w 未満のとき）、そうでなければ「描画中の V-Sync の数＋1」。
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import a_enc  # noqa: E402

TICK_US = 18030


def frame_ticks(draw_us, w):
    n = int(draw_us // TICK_US)
    return w if n < w else n + 1


def parse(src: Path):
    """スケジュールから「タイマー開始（tl_t0）以降の (描画するセル or None, 待ち)」の並びを、ループを展開して返す"""
    lines = src.read_bytes().decode("cp932").splitlines()
    body, loop_body, loops, in_loop, started = [], [], 1, False, False
    pending = None
    for ln in lines:
        if "タイマーの基準" in ln:  # 最初のコマを表示した直後の TMWA 1（--timelog の T0 はこの直後）
            started = True
            continue
        s = ln.split("*")[0].strip()
        if not s:
            continue
        if s.startswith("BSUB") and "tl_t0" in s:
            continue
        if not started:
            continue
        if s.startswith("BSUB") and "tl_t1" in s:
            break
        m = re.match(r"SETR\s+(\d+)-1", s)
        if m:
            loops = int(m.group(1))
            continue
        if s == "loop:":
            in_loop = True
            continue
        if s.startswith("LOOP"):
            body += loop_body * loops
            loop_body, in_loop = [], False
            continue
        m = re.match(r"DRW0\s+\d+,\d+,(c\d+)", s)
        if m:
            pending = m.group(1)
            continue
        m = re.match(r"TMWA\s+(\d+)", s)
        if m:
            (loop_body if in_loop else body).append((pending, int(m.group(1))))
            pending = None
    return body


def predict(name, clock):
    d = ROOT / "x68" / "anim" / name
    seq = parse(d / f"{name}.s")
    cache = {}
    total = 0
    for cel, w in seq:
        us = 0.0
        if cel:
            if cel not in cache:
                cache[cel] = a_enc.estimate_us((d / f"{cel}.cel").read_bytes(), clock)
            us = cache[cel]
        total += frame_ticks(us, w)
    nominal = sum(w for _, w in seq)
    return round(nominal * 1.803), round(total * 1.803)


def main(argv):
    clock = a_enc.DEFAULT_CLOCK
    if "--clock" in argv:
        k = argv.index("--clock")
        if k + 1 >= len(argv):
            raise SystemExit("--clock の後に MPU クロック（例 10、16.7、24mhz）を書いてください")
        import clock as clk
        argv[k + 1] = clk.parse(argv[k + 1], "オプション", "--clock")
        clock = argv[k + 1]
        argv = argv[:k] + argv[k + 2:]
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    for name in argv[1:]:
        nominal, pred = predict(name, clock)
        print(f"{name:8s} 予定 {nominal:5d}  予測 {pred:5d}  （{clock}、1/100 秒）")
    return 0


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

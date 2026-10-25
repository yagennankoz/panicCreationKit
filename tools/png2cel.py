"""png2cel.py : 256x256 の画像から a_enc セルとパレットを作る（bpica.x 互換）

使い方:  python png2cel.py [-p] [-a] <in.png> <out.cel> <pal>

  -p   パレットを新しく作る（付けなければ <pal> を読み込み、新しい色を後ろに追加して上書き）
       bpica.x と同じ動作。
  -a   X68000 の横長のドット（縦 2：横 3）で正しい形に見えるよう、横を 2/3 に縮めてから 256x256 に収める
       （左右の余白は透明＝色番号 0）。-a のときは 256x256 以外の大きさの画像も使える。
  -t 色  この色のドットを透明（色番号 0）にする。"#FF00FF" など、または corner（左上 (0,0) の色＝当時の方法）
  -c   -a と一緒に使う：余白を付けずに 256x256 を埋めるように拡大し、はみ出た上下（左右）を切る。
  画像は X68000 の色（RGB 各5ビット）に丸める。アルファ値が 128 未満のドットは透明（色番号0）。
  色数は黒以外 254 色まで（番号0=透明、1=黒は予約）。超えるとエラー。
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a_enc  # noqa: E402
import animcommon  # noqa: E402


def load_words(path, aspect=None, fit=None, key=()) -> np.ndarray:
    im = animcommon.key_transparent(Image.open(path).convert("RGBA"), key)
    if aspect:
        im = animcommon.fit_256(im, aspect, fit)
    if im.size != (256, 256):
        raise SystemExit(f"画像は 256x256 にしてください（{im.size[0]}x{im.size[1]}）")
    a = np.asarray(im).astype(np.uint16)
    r, g, b = ((a[..., k] * 31 + 127) // 255 for k in range(3))
    words = (g << 11) | (r << 6) | (b << 1)
    words[a[..., 3] < 128] = 0x0001  # 透明
    return words


def main(argv):
    args = argv[1:]
    new_pal = "-p" in args
    aspect = animcommon.PIXEL_ASPECT if "-a" in args else None
    fit = "crop" if "-c" in args else None
    key = []
    if "-t" in args:
        i = args.index("-t")
        if i + 1 >= len(args):
            print(__doc__, file=sys.stderr)
            return 1
        key = animcommon.parse_key_colors(args[i + 1])
        del args[i:i + 2]
    args = [a for a in args if a not in ("-p", "-a", "-c")]
    if len(args) != 3:
        print(__doc__, file=sys.stderr)
        return 1
    src, cel_path, pal_path = map(Path, args)
    import cli
    cli.need_file(src, "画像ファイル")
    if not new_pal and not pal_path.is_file():
        raise SystemExit(f"パレットファイルが見つかりません：{pal_path}（新しく作るときは -p を付けてください）")
    pal = a_enc.Palette(None if new_pal else pal_path.read_bytes())
    idx = a_enc.quantize(load_words(src, aspect, fit, key), pal)
    cel = a_enc.encode(idx)
    cel_path.write_bytes(cel)
    pal_path.write_bytes(pal.to_bytes())
    print(f"{cel_path}: {len(cel)} バイト / パレット {pal.last + 1} 色使用")
    return 0


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

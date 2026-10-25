"""test_a_enc.py : a_enc.py が bpica.x の正解データと一致するかを確かめる

使い方:  python tools/test_a_enc.py
  samples/reference/rN.cel / rN.pal（bpica.x の出力）がある画像すべてについて、
  1) デコード結果が元画像（x68/ref/rN.raw）と一致する
  2) エンコード結果（セル・パレット）がバイト単位で一致する
  を確認する。rN.raw が無ければ先に tools/make_ref_images.py を実行すること。
"""
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import a_enc  # noqa: E402

REF = ROOT / "samples" / "reference"
RAW = ROOT / "x68" / "ref"
# -p なしで作ったもの（使ったパレットの元）
BASE_PAL = {"r7": "r1"}


def main():
    ok = True
    cels = sorted(REF.glob("r*.cel"))
    if not cels:
        print("正解データがありません")
        return 1
    for cel_path in cels:
        n = cel_path.stem
        cel = cel_path.read_bytes()
        pal_bytes = (REF / f"{n}.pal").read_bytes()
        words = np.frombuffer((RAW / f"{n}.raw").read_bytes(), ">u2").reshape(256, 256)
        _, pal_words = a_enc.read_palette(pal_bytes)
        img, _, _ = a_enc.decode(cel)
        dec_ok = bool((pal_words[img] == np.where(words & 1, 1, words)).all())
        base = BASE_PAL.get(n)
        pal = a_enc.Palette((REF / f"{base}.pal").read_bytes() if base else None)
        enc = a_enc.encode(a_enc.quantize(words, pal))
        enc_ok = enc == cel and pal.to_bytes() == pal_bytes
        print(f"{n}: デコード {'OK' if dec_ok else 'NG'} / エンコード {'OK' if enc_ok else 'NG'}")
        ok &= dec_ok and enc_ok
    print("すべて一致" if ok else "不一致があります")
    return 0 if ok else 1


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(lambda argv: main()))

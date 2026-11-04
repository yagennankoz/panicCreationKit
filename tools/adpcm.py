"""adpcm.py : X68000 の ADPCM（OKI MSM6258、4 ビット）のエンコーダ／デコーダ

使い方:
  pt adpcm enc <入力（wav/mp3 など）> <出力.pcm> [--gain dB] [--rate レート]
      ffmpeg でモノラルにしてから ADPCM にする
  pt adpcm dec <入力.pcm> <出力.wav> [--rate レート]
      確認用に WAV に戻す

  --rate  サンプリングレート [kHz]：15.6（既定）、10.4、7.8、5.2、3.9。
          panic.x の PCMP は 15.6kHz だけ。ほかのレートの音は x68/lib/adpcm.h の PCMR で鳴らす

形式（MAME の msm6258 と同じ方式）:
  - 1 バイトに 2 サンプル。**下位 4 ビットが先**（実機の .PCM で確認）。
  - 12 ビットの予測値と 49 段階のステップ表。初期値は予測値 0、ステップ番号 0。
"""
import os
import shutil
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np

RATE = 15625
# サンプリングレートの番号（IOCS _ADPCMOUT などの D1 の上のバイト）→ 周波数 [Hz]。8MHz か 4MHz を 512／768／1024 で割る
RATES = {4: 15625.0, 3: 8e6 / 768, 2: 7812.5, 1: 4e6 / 768, 0: 3906.25}
RATE_NAMES = {4: "15.6kHz", 3: "10.4kHz", 2: "7.8kHz", 1: "5.2kHz", 0: "3.9kHz"}
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

# ffmpeg の場所：環境変数 FFMPEG → setup で置いた runtime/ffmpeg/ffmpeg.exe → PATH → C:\tools の下（tools/paths.py）
FFMPEG = paths.ffmpeg()

STEPS = [16, 17, 19, 21, 23, 25, 28, 31, 34, 37, 41, 45, 50, 55, 60, 66, 73, 80, 88, 97, 107, 118,
         130, 143, 157, 173, 190, 209, 230, 253, 279, 307, 337, 371, 408, 449, 494, 544, 598, 658,
         724, 796, 876, 963, 1060, 1166, 1282, 1411, 1552]
INDEX_SHIFT = [-1, -1, -1, -1, 2, 4, 6, 8]


def _diff(step, nib):
    d = step >> 3
    if nib & 1:
        d += step >> 2
    if nib & 2:
        d += step >> 1
    if nib & 4:
        d += step
    return -d if nib & 8 else d


def decode(data: bytes, low_first=True) -> np.ndarray:
    """ADPCM → 12 ビットの値（-2048〜2047）の配列"""
    out = np.empty(len(data) * 2, np.int16)
    sig, idx = 0, 0
    k = 0
    for b in data:
        for nib in ((b & 15, b >> 4) if low_first else (b >> 4, b & 15)):
            sig = max(-2048, min(2047, sig + _diff(STEPS[idx], nib)))
            idx = max(0, min(48, idx + INDEX_SHIFT[nib & 7]))
            out[k] = sig
            k += 1
    return out


def encode(samples: np.ndarray) -> bytes:
    """12 ビットの値の配列 → ADPCM（デコーダと同じ状態を追いかけて最も近い値を選ぶ）"""
    sig, idx = 0, 0
    nibs = []
    for x in samples.tolist():
        step = STEPS[idx]
        best, best_err, best_sig = 0, None, 0
        for nib in range(16):
            s = max(-2048, min(2047, sig + _diff(step, nib)))
            e = abs(x - s)
            if best_err is None or e < best_err:
                best, best_err, best_sig = nib, e, s
        nibs.append(best)
        sig = best_sig
        idx = max(0, min(48, idx + INDEX_SHIFT[best & 7]))
    if len(nibs) % 2:
        nibs.append(0)
    a = np.array(nibs, np.uint8)
    return (a[0::2] | (a[1::2] << 4)).tobytes()


def parse_rate(v, what="audio_rate") -> int:
    """サンプリングレートの指定（kHz の 15.6／10.4／7.8／5.2／3.9、または Hz の 15625 など）→ 番号（0〜4）。None なら 4"""
    if v is None:
        return 4
    try:
        f = float(str(v).strip().lower().removesuffix("khz").removesuffix("hz"))
    except ValueError:
        f = -1.0
    if 0 < f < 100:
        f *= 1000  # kHz で書いたもの
    code = min(RATES, key=lambda c: abs(RATES[c] - f))
    if f <= 0 or abs(RATES[code] - f) > RATES[code] * 0.01:
        raise SystemExit(f"{what}：サンプリングレートは 15.6、10.4、7.8、5.2、3.9（kHz）のどれかにしてください（今は {v!r}）")
    return code


def load_audio(path, gain_db=0.0, start=None, duration=None, rate=RATE) -> np.ndarray:
    """ffmpeg でモノラル 16 ビット（rate [Hz]）にして、12 ビットの範囲に縮める（start/duration は秒）"""
    af = f"lowpass={round(rate * 0.448)}"  # 15625Hz で 7000Hz
    if gain_db:
        af += f",volume={gain_db}dB"
    cmd = [FFMPEG, "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(round(rate)), "-af", af, "-f", "s16le", "-"]
    r = subprocess.run(cmd, capture_output=True, check=True)
    return (np.frombuffer(r.stdout, "<i2").astype(np.int32) >> 4).astype(np.int16)


def save_wav(path, samples, rate=RATE):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(round(rate))
        w.writeframes((samples.astype(np.int16) << 4).astype("<i2").tobytes())


def main(argv):
    if len(argv) < 4 or argv[1] not in ("enc", "dec"):
        print(__doc__, file=sys.stderr)
        return 1
    import cli
    cli.need_file(argv[2], "入力ファイル")
    rate = RATE
    if "--rate" in argv:
        k = argv.index("--rate")
        rate = RATES[parse_rate(argv[k + 1] if k + 1 < len(argv) else "", "--rate")]
    if argv[1] == "enc":
        gain = 0.0
        if "--gain" in argv:
            k = argv.index("--gain")
            try:
                gain = float(argv[k + 1])
            except (IndexError, ValueError):
                raise SystemExit("--gain の後に音量の調整 [dB] を数で書いてください（例 --gain -3）")
        data = encode(load_audio(argv[2], gain, rate=rate))
        Path(argv[3]).write_bytes(data)
        print(f"{argv[3]}: {len(data)} バイト（{len(data) * 2 / rate:.2f} 秒）")
    else:
        save_wav(argv[3], decode(Path(argv[2]).read_bytes()), rate)
    return 0


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

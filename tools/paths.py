"""paths.py : 外部のプログラム（ffmpeg、run68、HAS、HLK）の場所を探す

探す順：環境変数 → setup で置いた場所（runtime/、x68/bin/）→ PATH → C:\\tools の下（自分で置いた場合）。
見つからなければ、いちばん望ましい場所（setup で置く所）を返す（使うときに「見つからない」と分かる）。
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
X68 = ROOT / "x68"
RUNTIME = ROOT / "runtime"


def _find(env, candidates, which=None):
    v = os.environ.get(env)
    if v:
        return v
    for c in candidates:
        if Path(c).is_file():
            return str(c)
    if which and shutil.which(which):
        return shutil.which(which)
    return str(candidates[0])


def ffmpeg():
    return _find("FFMPEG", [RUNTIME / "ffmpeg" / "ffmpeg.exe",
                            Path(r"C:\tools\ffmpeg-7.0.1-full_build\bin\ffmpeg.exe")], "ffmpeg")


def run68():
    return _find("RUN68", [RUNTIME / "run68" / "run68.exe", Path(r"C:\tools\run68x\run68.exe")], "run68")


def has():
    """アセンブラ：HAS060X（setup で置く）、無ければ x68/bin/has.x（HAS v3.09 などを自分で置いたもの）"""
    return _find("PANTOOL_HAS", [X68 / "bin" / "has060x.x", X68 / "bin" / "has.x"])


def hlk():
    """リンカ：HLK evolution（hlk.r、setup で置く）、無ければ x68/bin/hlk.x（HLK v3.01 などを自分で置いたもの）"""
    return _find("PANTOOL_HLK", [X68 / "bin" / "hlk.r", X68 / "bin" / "hlk.x"])

"""paths.py : 外部のプログラム（ffmpeg、run68、HAS、HLK、Z-MUSIC）の場所を探す。OS ごとの違いもここにまとめる

探す順：環境変数 → setup で置いた場所（runtime/、x68/bin/）→ PATH → C:\\tools の下（Windows で自分で置いた場合）。
見つからなければ、いちばん望ましい場所（setup で置く所）を返す（使うときに「見つからない」と分かる）。
Windows 以外（Linux、mac）では、ffmpeg と run68 は自分で入れて PATH に置くか、環境変数 FFMPEG・RUN68 で場所を書く
（docs/MANUAL.md の 2 章「Linux・mac で使う」）。
"""
import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
X68 = ROOT / "x68"
RUNTIME = ROOT / "runtime"
WINDOWS = os.name == "nt"
EXE = ".exe" if WINDOWS else ""
SETUP = "setup.bat" if WINDOWS else "./setup.sh"  # 準備のコマンド（メッセージに使う）


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
    return _find("FFMPEG", [RUNTIME / "ffmpeg" / f"ffmpeg{EXE}",
                            Path(r"C:\tools\ffmpeg-7.0.1-full_build\bin\ffmpeg.exe")], "ffmpeg")


def run68():
    return _find("RUN68", [RUNTIME / "run68" / f"run68{EXE}", Path(r"C:\tools\run68x\run68.exe")], "run68")


def has():
    """アセンブラ：Windows は HAS060X（has060x.x）、Linux・mac は HAS v3.09（has.x）を先に探す（どちらも setup で置く）。
    HAS v3.09 は run68x でも run68mac でも動き（run68mac は HAS060X を動かせない）、HAS060X と同じ .o を作る"""
    c = [X68 / "bin" / "has060x.x", X68 / "bin" / "has.x"]
    return _find("PANTOOL_HAS", c if WINDOWS else c[::-1])


def hlk():
    """リンカ：Windows は HLK evolution（hlk.r）、Linux・mac は HLK v3.01（hlk.x）を先に探す（どちらも setup で置く）"""
    c = [X68 / "bin" / "hlk.r", X68 / "bin" / "hlk.x"]
    return _find("PANTOOL_HLK", c if WINDOWS else c[::-1])


def zmusic():
    """Z-MUSIC ver2 の ZMUSIC.X（MML → ZMD のコンパイルに使う。setup で x68/zmusic/ に置く）"""
    return _find("PANTOOL_ZMUSIC", [X68 / "zmusic" / "zmusic.x", X68 / "bin" / "zmusic.x"])


def here(name: str) -> str:
    """作業フォルダに写した X68000 のプログラムを run68 に渡すときの名前（Windows は .\\名前、ほかは ./名前）"""
    return f".{os.sep}{name}"

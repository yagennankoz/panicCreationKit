"""pt.py : ツールを名前で呼ぶ入口（Windows は pt.bat、Linux・mac は pt から使う）

使い方:  pt <ツール> [引数…]      例：pt mkscene samples\\layer1\\scene4.toml
        pt                       ツールの一覧
"""
import runpy
import sys
from pathlib import Path

if sys.version_info < (3, 11):  # tomllib などを使う
    sys.exit(f"エラー：Python 3.11 以上が要ります（今は {sys.version.split()[0]}）。"
             "Linux・mac では、環境変数 PYTHON に Python 3.11 以上の場所を書けます")

TOOLS = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLS))  # 埋め込み版の Python は、スクリプトのフォルダを sys.path に入れないため

MAIN = [  # よく使うもの（一覧の上に出す）
    ("mkanim", "PNG 連番・動画 1 本から .pan を作る"),
    ("mkscene", "層を重ねたアニメを設定ファイルから作る"),
    ("mkbench", "ベンチ動画を作る"),
    ("mkparts", "画像・音声からセル（グラフィック・テキスト・スプライト）・パレット・ADPCM と .s のひな形を作る"),
    ("buildPan", ".s から .pan を作る（素材の一覧 .json があれば素材もつなげる）"),
    ("pansim", ".pan を PC 上で動かして確かめる"),
    ("png2cel", "PNG → セル（bpica.x 互換）"),
    ("adpcm", "音声 → ADPCM"),
    ("mml2zmd", "FM 音源の MML（Z-MUSIC ver2）→ 曲（.zmd）・効果音（.zse）"),
    ("setup", "使うツールのダウンロード（setup.bat と同じ）"),
]


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        print("ツール：")
        for name, what in MAIN:
            print(f"  {name:10s} {what}")
        others = sorted(p.stem for p in TOOLS.glob("*.py")
                        if p.stem not in {n for n, _ in MAIN} | {"pt", "cli", "paths"} and not p.stem.startswith("_"))
        print("  そのほか：" + "、".join(others))
        print("詳しくは docs/MANUAL.md、各ツールは  pt <ツール> -h")
        return 0
    name = argv[1].removesuffix(".py")
    path = TOOLS / "setup" / "setup.py" if name == "setup" else TOOLS / f"{name}.py"
    if not path.is_file():
        print(f"エラー：ツール {name} がありません（pt だけで一覧を表示）", file=sys.stderr)
        return 1
    sys.argv = [str(path)] + argv[2:]
    runpy.run_path(str(path), run_name="__main__")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

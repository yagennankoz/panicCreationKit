"""buildPan.py : スケジュールのソース（.s）から .pan を作る（手で作るときのビルド）

使い方:  python buildPan.py <名前>.s [--sim] [--clock 10mhz]       素材の一覧（<名前>.json）があれば素材もつなげる
        python buildPan.py <フォルダ または <名前>.json> [--sim] [--clock 10mhz]
        python buildPan.py <名前>.s [追加の .o ...]                 素材の一覧が無い .s（素材を .s に直接書いたもの）

  素材の一覧（<名前>.json、mkparts が作る）が .s と同じフォルダにあるとき：
    <名前>_d.h（素材のラベル）を作り、.s をアセンブル・リンクして、一覧の素材（セル・パレット・ADPCM）を .pan の後ろにつなげる。
    panbuild.py と同じ処理（docs/MANUAL.md の「手で作る」の章）。
  無いとき：.s をそのままアセンブル・リンクして .pan にする。
  --sim    できた .pan を pansim で動かし、再生時間と処理落ちを表示する（キーで終わるものは 60 秒で止める）
  --clock  --sim に使う MPU クロック（既定は一覧に書かれたもの、無ければ 10mhz）

処理: run68 で HAS (as -u) → HLK (lk -x) を実行し、mkpan.py で .pan に変換する。
  - ビルドは短いパスの作業フォルダ（x68/work/<名前>/。長すぎれば %LOCALAPPDATA% や TEMP の下、環境変数 PANTOOL_WORK）
    で行う。x68/lib/ のライブラリ、ソースのフォルダの .s と .h、x68/sch.h、アセンブラとリンカをそこへ写し、「.\\名前」で動かす。
    run68 上の HAS／HLK は、プログラムのパスや 65 文字を超えるカレントを扱えないため。できた .pan はソースと同じフォルダに書く。
  - ソースは Shift-JIS・CRLF で書くこと。
  - run68・アセンブラ・リンカの場所は tools/paths.py で探す（環境変数 RUN68／PANTOOL_HAS／PANTOOL_HLK →
    setup で置いた runtime/run68/run68.exe、x68/bin/has060x.x（HAS060X）、x68/bin/hlk.r（HLK evolution）→ C:\\tools の下）。
"""
import os
import shutil
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
X68 = ROOT / "x68"
LIB = X68 / "lib"  # panicCreationKitForWin のライブラリ（docs/LIBRARY.md）
BIN = X68 / "bin"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

RUN68 = paths.run68()
from mkpan import x_to_pan  # noqa: E402


def run(args, cwd):
    if not Path(RUN68).is_file():
        raise SystemExit(f"run68 が見つかりません（{RUN68}）。setup.bat を実行するか、環境変数 RUN68 に run68.exe の場所を書いてください")
    r = subprocess.run([RUN68, *map(str, args)], cwd=cwd, capture_output=True)
    out = (r.stdout + r.stderr).decode("cp932", errors="replace").strip()
    if out:
        print(out)
    if r.returncode != 0:
        raise SystemExit(f"失敗しました（終了コード {r.returncode}）: {' '.join(map(str, args))}")


def blk(blk_file):
    """blk.x でリンクリスト（.blk）から .o を作る。.o のパスを返す"""
    blk_file = Path(blk_file).resolve()
    run([BIN / "blk.x", blk_file.name], blk_file.parent)
    return blk_file.with_suffix(".o")


WORK = X68 / "work"
WORK_MAX = 60  # 作業フォルダのパスの長さの上限（run68 上の HLK は 65 文字を超えるカレントで失敗する）


def _short_path(p: Path) -> str:
    """Windows の短い名前（8.3 形式）。取れなければそのまま"""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        if ctypes.windll.kernel32.GetShortPathNameW(str(p), buf, 1024):
            return buf.value
    except (AttributeError, OSError):
        pass
    return str(p)


def work_dir(stem: str) -> Path:
    """ビルドの作業フォルダ。run68 は長いパスを扱えないので、短い所を選ぶ：
    環境変数 PANTOOL_WORK → x68/work → %LOCALAPPDATA%\\pckwin\\work → TEMP（それぞれ短い名前も試す）"""
    env = os.environ.get("PANTOOL_WORK")
    bases = [Path(env)] if env else [WORK]
    if not env:
        if os.environ.get("LOCALAPPDATA"):
            bases.append(Path(os.environ["LOCALAPPDATA"]) / "pckwin" / "work")  # パスを短く（panicCreationKitForWin の略）
        bases.append(Path(tempfile.gettempdir()) / "pckwin")
    tried = []
    for base in bases:
        base.mkdir(parents=True, exist_ok=True)
        for b in (str(base.resolve()), _short_path(base.resolve())):
            d = Path(b) / stem
            if len(str(d)) <= WORK_MAX:
                return d
            tried.append(str(d))
    raise SystemExit("ビルドの作業フォルダに使える短いパスがありません（run68 は 60 文字くらいまでしか扱えない）。\n"
                     "  環境変数 PANTOOL_WORK に短いフォルダ（例 C:\\ptwork）を指定してください。試した所：" + "、".join(tried))


def build(src, objs=(), blob=b""):
    """スケジュールソースから .pan を作る。.pan のパス（ソースと同じフォルダ）を返す
    blob：text+data の直後につなげる素材データ（mkpan.x_to_pan を参照）"""
    src = Path(src).resolve()
    if not (X68 / "sch.h").is_file():
        raise SystemExit(f"sch.h が見つかりません（{X68 / 'sch.h'}）。setup.bat を実行してください")
    cwd = work_dir(src.stem)  # run68 のため、短いパスで作業する
    cwd.mkdir(parents=True, exist_ok=True)
    for f in cwd.iterdir():
        if f.is_file():
            f.unlink()
    # x68/lib/（panicCreationKitForWin のライブラリ。vwait.h など）を先に写し、ソースのフォルダのもので上書きできるようにする
    for f in (sorted(LIB.glob("*.s")) + sorted(LIB.glob("*.h"))) if LIB.is_dir() else []:
        shutil.copyfile(f, cwd / f.name)
    for f in list(src.parent.glob("*.s")) + list(src.parent.glob("*.h")):  # ソースと、.include するヘッダ
        shutil.copyfile(f, cwd / f.name)
    shutil.copyfile(X68 / "sch.h", cwd / "sch.h")
    work_objs = []
    for o in objs:
        o = Path(o).resolve()
        shutil.copyfile(o, cwd / o.name)
        work_objs.append(o.name)
    # アセンブラとリンカも作業フォルダに写して「.\\名前」で呼ぶ（run68 はプログラムのパスが長いと動かない）
    progs = []
    for prog in (paths.has(), paths.hlk()):
        if not Path(prog).is_file():
            raise SystemExit(f"{Path(prog).name} が見つかりません（{prog}）。setup.bat を実行してください")
        shutil.copyfile(prog, cwd / Path(prog).name)
        progs.append(".\\" + Path(prog).name)
    run([progs[0], "-u", src.name], cwd)
    run([progs[1], "-x", src.with_suffix(".o").name, *work_objs], cwd)
    xfile = cwd / src.with_suffix(".x").name
    pan = src.with_suffix(".pan")
    pan.write_bytes(x_to_pan(xfile.read_bytes(), blob))
    print(f"-> {pan} ({pan.stat().st_size} bytes)")
    return pan


def parts_list(target: Path):
    """target（.s・フォルダ・.json）に対応する素材の一覧（.json）。無ければ None"""
    if target.suffix.lower() == ".json":
        return target
    if target.is_dir():
        return next(iter(sorted(target.glob("*.json"))), None)
    js = target.with_suffix(".json")
    return js if js.is_file() else None


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__, file=sys.stderr)
        return 1
    import clock as clk
    sim = "--sim" in argv
    argv = [x for x in argv if x != "--sim"]
    clock = None
    if "--clock" in argv:
        k = argv.index("--clock")
        if k + 1 >= len(argv):
            raise SystemExit("--clock の後に MPU クロック（例 10、16.7、24mhz）を書いてください")
        clock = clk.parse(argv[k + 1], "オプション", "--clock")
        argv = argv[:k] + argv[k + 2:]
    target = Path(argv[1])
    if not target.exists():
        raise SystemExit(f"見つかりません：{target}（.s、フォルダ、.json のどれかを指定してください）")
    js = parts_list(target)
    if js is not None:  # 素材の一覧がある → 素材をつなげて作る（panbuild と同じ）
        if len(argv) > 2:
            raise SystemExit("素材の一覧（.json）があるときは、追加の .o は指定できません（素材は .json に書き足してください）")
        import panbuild
        panbuild.build_dir(js, clock, sim=sim)
        return 0
    if target.is_dir():
        raise SystemExit(f"{target} に素材の一覧（.json）がありません。.s を指定してください")
    pan = build(target, argv[2:])
    if sim:
        import panbuild
        import pansim
        clock = clock or "10mhz"
        print(pansim.start_message(pansim.inspect(pan), clock, None, "再生時間"))
        panbuild.report(pansim.simulate(pan, clock, max_us=60e6), clock)
    return 0


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

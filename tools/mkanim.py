r"""mkanim.py : PNG 連番または動画 1 本から panic の .pan を作る（1 枚の層だけの mkscene）

使い方:  pt mkanim <PNGフォルダ|動画ファイル> <名前> [オプション]
        pt mkanim --config 設定.toml [オプション]   （設定ファイルの例：samples/bbb/bbb.toml。キーはオプション名）

  <名前>     出力名（Human68k の 8.3 形式を考えて英数字 8 文字以内）。<出力先>/<名前>.pan ができる
  --out      出力先のフォルダ（省略すると x68/anim/<名前>/）
  --fps      1 秒あたりのコマ数（既定 12）。1 カウント＝18.03ms（TMWA の実測値）で待ち時間を割り振る
  --loop N   N 回くり返す（既定 1）
  --forever  永久ループ（キーが押されるまでくり返す。ESC でも終わる）
  --exit-key 永久ループを終わらせるキー：any（既定）／space／return／none（ESC だけ）
  --dither   none（既定）／fs（Floyd-Steinberg、滑らかだが差分が効きにくい）／ordered（決まった模様、差分が効く）
  --dither-strength  ordered の強さ（既定 24）
  --diff     前フレーム差分（時間軸モード $1E/$20/$22）を使う。描画先に残っている絵との差分にする
  --stabilize T  前のコマとの色の差が T 以下のドットは前のコマの色のままにする（実写などのゆらぎ対策。目安 16〜24）
  --audio    音声ファイル（wav/mp3 など）。動画を渡したときは、指定しなければ動画の音を使う（--no-audio で音なし）
  --gain     音声の音量調整 [dB]（既定 0）
  --audio-offset 秒  音を鳴らし始める時刻（負なら音の頭を削る）
  --audio-every N    永久ループで N 周ごとに音を鳴らし直す（既定は音の長さから自動、0 で最初に 1 回だけ）
  --start 秒     （動画のときだけ）動画の何秒目から使うか。省略すると頭（0 秒）から。動画の音も同じ所から
  --duration 秒  （動画のときだけ）--start から何秒分を使うか。省略すると最後まで
  --clock    対象機の MPU クロック（10、16.7、24mhz など。既定 10mhz）
  --no-drop  間に合わないコマを飛ばさない（遅らせる）
  --adjust-every 秒 --adjust-frames N  何秒ごとに何カウント（V-Sync 1 回＝約 18ms）待ちを足すか。負＝早める、正＝遅らせる。
             音とのわずかなずれを直す（--wait vwait のときだけ）
  --no-fixed-cels  分割描画の区切りをその時の空き時間で決める（既定は絵ごとに決めた区切りのセルを使い回す）
  --wait tmwa   待ちを panic.x の TMWA にする（遅れは取り戻さない）。既定 vwait＝再生の頭からの予定の時刻で待ち、遅れたコマの分を後の待ちで取り戻す
  --sim      できた .pan を pansim（PC 上のシミュレータ）で動かし、再生時間と画面が予定どおりかを確かめる（既定はしない）
  --stop-at-s  素材と .s を作った所で止める。.s を編集したら pt buildPan x68/anim/<名前>/<名前>.s で続き
  --timelog  再生時間を anim\<名前>\time.txt に書く（処理落ちの確認用。H:\ で実行すること）
  --sequence 順番  画像を表示する順番（画像の番号は PNG をファイル名順に並べて先頭を 0 番と数える＝0 始まり）。例 "0-7,6-1"、"0,1,2:3,(3-5)*4"
             a-b＝a から b まで（逆順も可）、:x＝表示時間を既定のコマの x 倍（"0.5s" なら秒）、*k＝k 回くり返す
  --hold 指定      画像ごとの表示時間の既定を変える。例 "5:3,7:0.5s"（画像 5 は 3 コマ分、画像 7 は 0.5 秒）
  --transparent 色  この色のドットを透明（色番号 0）にする。"#FF00FF"、"corner"（各画像の左上 (0,0) の色＝当時の方法）、
             ";" 区切りで複数。--transparent-tolerance N で RGB 各 N までの差を許す（動画など色がゆれる素材用）
  --split 秒   長い素材を、この長さごとの .pan に分けて作る（<名前>00.pan、<名前>01.pan …、名前は 6 文字まで）。
             出力先（--out、省略すると x68/anim/<名前>/）に全部の .pan と play.bat（ワイルドカードで連続再生）を置く。
             部分ごとにパレットを作り、音もその区間を切り出す。--forever／--loop とは一緒に使えない

中身は mkscene.py の build（G0 に 1 枚の層を置いたシーン）。分割描画・コマの間引き・永久ループなどは mkscene と共通。
"""
import argparse
import math
import shutil
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a_enc  # noqa: E402
import cli  # noqa: E402

# 共通の部品（ほかのツールが mkanim から参照するもの。中身は animcommon）
from animcommon import (BAYER8, BUDGET_RATIO, TIME_WEIGHTS, VSYNC_HZ, extract_video,  # noqa: E402,F401
                        frame_words, stabilize, to5, write_sjis)


def apply_config(ap, a, argv):
    """設定ファイル（TOML）の値を入れる。キーはオプション名（--fps → fps、--dither-strength → dither_strength、
    src、name も可）。ファイル名（src、audio）は設定ファイルのある場所からの相対でよい。
    コマンドラインで指定したものはそちらを優先する。"""
    cfg = tomllib.loads(cli.need_file(a.config, "設定ファイル").read_text(encoding="utf-8"))
    base = a.config.resolve().parent
    known = {act.dest: act for act in ap._actions}
    given = set()  # コマンドラインで指定したもの
    for tok in argv:
        if tok.startswith("--"):
            given.add(tok[2:].split("=")[0].replace("-", "_"))
    positional = [t for t in argv if not t.startswith("--")]
    for key, val in cfg.items():
        dest = key.replace("-", "_")
        if dest not in known or dest == "config":
            cli.check_keys("設定ファイル", {key: val}, [k for k in known if k not in ("config", "help")])
        if dest in given or (dest in ("src", "name") and getattr(a, dest) is not None and positional):
            continue
        if dest in ("src", "audio"):
            if not isinstance(val, str):
                raise SystemExit(f"設定ファイル：{key} はファイル名を文字列で書いてください（今は {val!r}）")
            val = (base / val).resolve()
        setattr(a, dest, val)


def scene_config(a) -> dict:
    """mkanim のオプション → mkscene の設定（G0 に 1 枚の層）"""
    layer = {"name": "main", "plane": "g0", "src": str(Path(a.src).resolve()), "base": True, "fps": a.fps}
    if a.sequence is not None:
        layer["sequence"] = a.sequence
    if a.hold is not None:
        layer["hold"] = a.hold
    if a.start is not None:
        layer["start"] = a.start
    if a.duration is not None:
        layer["duration"] = a.duration
    cfg = {"name": a.name, "clock": a.clock, "loops": a.loop, "diff": a.diff, "dither": a.dither,
           "dither_strength": a.dither_strength, "stabilize": a.stabilize, "no_drop": a.no_drop,
           "timelog": a.timelog, "gain": a.gain, "layer": [layer],
           "aspect": a.aspect, "pixel_aspect": a.pixel_aspect, "fit": a.fit,
           "transparent": a.transparent, "transparent_tolerance": a.transparent_tolerance, "sim": a.sim,
           "wait": a.wait, "fixed_cels": not a.no_fixed_cels}
    if a.adjust_every is not None or a.adjust_frames is not None:
        cfg["adjust_every"], cfg["adjust_frames"] = a.adjust_every, a.adjust_frames
    if a.out:
        cfg["out"] = str(Path(a.out).resolve())
    if a.forever:
        cfg["loop"] = "forever"
        cfg["exit_key"] = a.exit_key
    cfg["audio_offset"] = a.audio_offset
    if a.audio_every is not None:
        cfg["audio_every"] = a.audio_every
    if not a.no_audio:
        if a.audio:
            cfg["audio"] = str(Path(a.audio).resolve())
        elif Path(a.src).is_file():  # 動画の音を使う（同じ区間）
            cfg["audio"] = str(Path(a.src).resolve())
            if a.start is not None:
                cfg["audio_start"] = a.start
            if a.duration is not None:
                cfg["audio_duration"] = a.duration
    return cfg


def build_split(a, argv):
    """--split：素材を split 秒ごとの部分に分け、それぞれを mkscene.build で .pan にする"""
    import animcommon
    import mkscene
    name = a.name
    if not (name.isalnum() and len(name) <= 6):
        raise SystemExit("--split のときの名前は英数字 6 文字以内（後ろに 2 桁の番号を付けるため）")
    if a.forever or a.loop != 1:
        raise SystemExit("--split は --forever／--loop と一緒に使えません")
    if a.sequence is not None or a.hold is not None:
        raise SystemExit("--split は --sequence／--hold と一緒に使えません")
    if a.stop_at_s:
        raise SystemExit("--split は --stop-at-s と一緒に使えません（部分ごとに mkanim を使ってください）")
    top = Path(a.out).resolve() if a.out else mkscene.ROOT / "x68" / "anim" / name
    top.mkdir(parents=True, exist_ok=True)
    for f in top.glob(f"{name}[0-9][0-9].pan"):
        f.unlink()
    src = Path(a.src).resolve()
    base_cfg = scene_config(a)
    video = src.is_file()
    if video:  # 動画は 1 回だけ切り出して、PNG 連番として分ける（縦横比の補正も切り出しで済ませる）
        folder = top / "frames"
        aspect = animcommon.pixel_aspect(a.aspect, a.pixel_aspect)
        print(f"動画を切り出しています：{src.name}")
        animcommon.extract_video(src, folder, a.fps, a.start, a.duration, aspect, a.fit)
        base_cfg.update(aspect=False, fit="crop")
    else:
        folder = src
    n_all = len(sorted(folder.glob("*.png")))
    if not n_all:
        raise SystemExit(f"{folder} に PNG がありません")
    per = max(1, round(a.split * a.fps))
    parts = math.ceil(n_all / per)
    if parts > 100:
        raise SystemExit(f"{parts} 個に分かれます（100 まで）。--split を長くしてください")
    print(f"{n_all} コマを {per} コマ（{per / a.fps:.1f} 秒）ずつ、{parts} 個の .pan に分けます")
    # 音：動画の音（区間の頭 a.start から）または --audio。アニメの時刻 t の音は、音のファイルの base + t - offset
    audio_base = (a.start or 0.0) if (video and "audio" in base_cfg and Path(base_cfg["audio"]) == src) else 0.0
    offset = a.audio_offset
    made = []
    for k in range(parts):
        first = k * per
        count = min(per, n_all - first)
        t0, length = first / a.fps, count / a.fps
        cfg = dict(base_cfg)
        cfg["name"] = f"{name}{k:02d}"
        cfg["out"] = str(top / "parts" / cfg["name"])  # 部分ごとの作業フォルダ（.pan は top にまとめる）
        layer = dict(base_cfg["layer"][0])
        layer.pop("start", None)
        layer.pop("duration", None)
        layer.update(src=str(folder), first=first, count=count)
        cfg["layer"] = [layer]
        for key in ("audio_start", "audio_duration", "audio_offset"):
            cfg.pop(key, None)
        if "audio" in cfg:
            s = t0 - offset
            if s >= 0:
                cfg["audio_start"], cfg["audio_offset"] = audio_base + s, 0.0
                cfg["audio_duration"] = length
            elif -s < length:
                cfg["audio_start"], cfg["audio_offset"] = audio_base, -s
                cfg["audio_duration"] = length + s
            else:  # この部分ではまだ鳴らない
                del cfg["audio"]
        print(f"\n==== {cfg['name']}：コマ {first}〜{first + count - 1}（{t0:.2f}〜{t0 + length:.2f} 秒）====")
        r = mkscene.build(cfg, Path.cwd(), False, f"mkanim {' '.join(argv[1:])}（{k + 1}/{parts}）")
        if r:
            return r
        pan = Path(cfg["out"]) / f"{cfg['name']}.pan"
        shutil.copyfile(pan, top / pan.name)
        made.append(pan.name)
    try:  # x68 の中なら H:\ からの相対で、外なら .pan のあるフォルダで実行する前提で書く
        rel = "\\".join(top.resolve().relative_to((mkscene.ROOT / "x68").resolve()).parts)
        where, wild = "H:\\ で", f"{rel}\\{name}??.pan"
    except ValueError:
        where, wild = f"{top} を X68000 から見える所に写し、そのフォルダで", f"{name}??.pan"
    animcommon.write_sjis(top / "play.bat", f"panic {wild}\n")
    size = sum((top / f).stat().st_size for f in made)
    print(f"\n-> {top}：{', '.join(made)}（合計 {size} バイト）")
    print(f"   再生：{where}  panic {wild}  （または play.bat）")
    print("   ワイルドカードの順番はディレクトリの並び順。Windrv（Windows のフォルダ）では名前順になる")
    return 0


def main(argv):
    ap = cli.ArgumentParser(description="PNG 連番または動画から .pan を作る")
    ap.add_argument("src", type=Path, nargs="?", help="PNG 連番のフォルダ、または動画ファイル")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--config", type=Path, help="設定ファイル（TOML）。コマンドラインの指定が優先")
    ap.add_argument("--fps", type=float, default=12)
    ap.add_argument("--dither", choices=["none", "fs", "ordered"], default="none")
    ap.add_argument("--dither-strength", type=float, default=24.0)
    ap.add_argument("--loop", type=int, default=1)
    ap.add_argument("--forever", action="store_true", help="永久ループ（キーが押されるまでくり返す）")
    ap.add_argument("--exit-key", choices=["any", "space", "return", "none"], default="any")
    ap.add_argument("--timelog", action="store_true")
    ap.add_argument("--out", type=Path, help="出力先のフォルダ（省略すると x68/anim/<名前>/）")
    ap.add_argument("--wait", choices=["tmwa", "vwait"], default="vwait",
                    help="待ち方：vwait（既定。予定の時刻で待ち、遅れを後で取り戻す）／tmwa（panic.x の TMWA）")
    ap.add_argument("--adjust-every", type=float, help="補正の間隔 [秒]（--adjust-frames と一緒に。VWAIT のときだけ）")
    ap.add_argument("--adjust-frames", type=int,
                    help="補正の量 [カウント＝V-Sync 1 回]。負＝早める、正＝遅らせる（音とのずれを直す）")
    ap.add_argument("--sim", action="store_true", help="できた .pan を pansim で動かして確かめる（既定はしない）")
    ap.add_argument("--stop-at-s", action="store_true",
                    help="素材と .s を作った所で止める（.s を編集してから pt buildPan で続きを行う）")
    ap.add_argument("--no-drop", action="store_true", help="間に合わないコマを飛ばさず、遅らせる")
    ap.add_argument("--no-fixed-cels", action="store_true",
                    help="分割描画の区切りをその時の空き時間で決める（既定は絵ごとに決めた区切りのセルを使い回す）")
    ap.add_argument("--diff", action="store_true")
    ap.add_argument("--aspect", action="store_true",
                    help="X68000 の横長のドット（縦 2：横 3）で正しい形に見えるよう、横を 2/3 に縮めてから 256x256 にする")
    ap.add_argument("--pixel-aspect", type=float, help="--aspect で使う 1 ドットの横÷縦（既定 1.5）")
    ap.add_argument("--fit", choices=["crop", "pad"],
                    help="256x256 への収め方。crop＝埋めてはみ出た所を切る、pad＝全体を収めて余白を付ける"
                         "（既定は --aspect なら pad、なしなら crop）")
    ap.add_argument("--clock", default=a_enc.DEFAULT_CLOCK,
                    help="対象機の MPU クロック（tools/timing.json にあるもの。既定 10mhz）")
    ap.add_argument("--stabilize", type=float, default=0.0,
                    help="前のコマとの色の差がこれ以下のドットは前のコマの色のままにする（0〜255 の RGB 各成分の差。0 で無効）")
    ap.add_argument("--audio", type=Path)
    ap.add_argument("--no-audio", action="store_true")
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--audio-offset", type=float, default=0.0, help="音を鳴らし始める時刻 [秒]（負なら音の頭を削る）")
    ap.add_argument("--audio-every", type=int, help="永久ループで何周ごとに音を鳴らし直すか（0 なら最初に 1 回だけ）")
    ap.add_argument("--transparent", help="透明にする色。\"#FF00FF\" など、\"corner\"＝各画像の左上 (0,0) の色、"
                                           "\";\" 区切りで複数")
    ap.add_argument("--transparent-tolerance", type=int, default=0, help="透明色の許す差（RGB 各 0〜255、既定 0＝ぴったり）")
    ap.add_argument("--sequence", help="画像を表示する順番（例 \"0-7,6-1\"、\"0,1,2:3,(3-5)*4\"）")
    ap.add_argument("--hold", help="画像ごとの表示時間（例 \"5:3,7:0.5s\"＝画像 5 は 3 コマ分、画像 7 は 0.5 秒）")
    ap.add_argument("--split", type=float, help="この長さ [秒] ごとの .pan に分けて作る（ワイルドカードで連続再生）")
    ap.add_argument("--start", type=float, help="動画の切り出し開始 [秒]")
    ap.add_argument("--duration", type=float, help="動画の切り出し長さ [秒]")
    a = ap.parse_args(argv[1:])
    if a.config:
        apply_config(ap, a, argv[1:])
    if a.src is None or a.name is None:
        ap.error("素材（src）と名前（name）を、コマンドラインか設定ファイルで指定してください")
    if not Path(a.src).exists():
        raise SystemExit(f"素材（PNG のフォルダか動画）が見つかりません：{a.src}")
    if a.audio is not None:
        cli.need_file(a.audio, "音のファイル（--audio）")
    cli.check_number("オプション", "--fps", a.fps, above=0, maximum=60)
    cli.check_number("オプション", "--loop", a.loop, integer=True, minimum=1)
    cli.check_number("オプション", "--split", a.split, above=0)
    cli.check_number("オプション", "--pixel-aspect", a.pixel_aspect, above=0)
    if a.split:
        return build_split(a, argv)
    import mkscene  # mkscene は animcommon を使う（循環を避けてここで読み込む）
    return mkscene.build(scene_config(a), Path.cwd(), a.stop_at_s, f"mkanim {' '.join(argv[1:])}")


if __name__ == "__main__":
    sys.exit(cli.run(main))

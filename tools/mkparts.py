"""mkparts.py : 画像・音声から、セル（.cel）・パレット（.pal）・ADPCM（.pcm）と、.s のひな形を作る

使い方:  pt mkparts <画像・音声・画像のフォルダ…> --name 名前 [オプション]
  例：pt mkparts title.png bg.png se.wav --name demo
      pt mkparts frames/ voice.wav --name anim1 --fps 8 --build
      pt mkparts logo.png --name logo --make cel,pal          （.s は作らず、セルとパレットだけ）

  入力：画像（png、bmp、jpg、gif など）、音声（wav、mp3、ogg、flac など）、画像の入ったフォルダ（名前順）。いくつでも並べてよい。
  出力（--out、省略すると x68/anim/<名前>/）。--plane で、どの面に使う形にするかを選ぶ（既定 g0）：
    --plane g0／g1（グラフィック、256 色）
      <画像>.cel   a_enc のセル（code #4、256x256、差分なしの 1 枚まるごと。bpica.x と同じ形）。DRW0／DRW1 で描く
      <名前>.pal   パレット（全部の画像で共通。GPAL で使う。--pal-each なら画像ごとに <画像>.pal）
    --plane text（テキスト面、16 色）
      <画像>.cel   高速テキストのセル（TDRW の code #2、4 プレーン）。DRWT で描く
      <名前>.pal   16 色のパレット（34 バイト。TPAL 0 で使う）
    --plane sprite（スプライト、16 色）
      <画像>.spr   スプライトのセル（bpic -s と同じ形。透明でない所を囲む 16 ドット単位の長方形を切り出し、位置も入る）。
                   SPCG でパターンを登録し、SPON で表示する（全部の画像で PCG は 256 個まで）
      <名前>.pal   16 色のパレット（34 バイト。TPAL <--sprite-pal の番号> で使う）
    <音声>.pcm     ADPCM（MSM6258、15.625kHz、下位 4 ビットが先。PCMP で使う）
    <名前>.s       スケジュールのひな形（音を鳴らし、画像を --fps の速さで順に表示する。選んだ面の命令で）。自由に書き換えてよい
    <名前>.json    素材の一覧（buildPan.py が使う）。.s と一緒に作る
  ファイル名は Human68k に合わせて英数字 8 文字までに縮める（重なるときは番号を付ける）。

オプション:
  --name 名前          出力名（英数字 8 文字以内。.s・.json・.pal の名前）。必須
  --out フォルダ        出力先
  --make 対象          作るもの：cel、pal、pcm、s をカンマ区切りで（既定は全部）。例 --make cel,pal
                       （cel はスプライトのセル .spr も指す）
  --plane 面           g0（既定）／g1／text／sprite
  --sprite-pal N       スプライトのパレットの番号（1〜15、既定 1）
  --pal-in ファイル     このパレットを読み、足りない色を後ろに足して使う（bpica.x の -p なしと同じ）。
                       作るパレットは、この中身に新しい色を足したもの（テキスト・スプライトは 16 色の 34 バイトのもの）
  --pal-each           画像ごとに別のパレットを作る（既定は全部の画像で 1 つ。G0 と G1 は 1 つのパレットを分け合う）
  --dither none／fs／ordered、--dither-strength N   減色のディザ（既定 none）
  --fast               描く速さを優先して符号化する（既定は bpica.x と同じ符号化）
  --aspect、--pixel-aspect R、--fit crop／pad       ドットの縦横比の補正、256x256 への収め方（mkanim と同じ）
  --transparent 色、--transparent-tolerance N      透明にする色（"#FF00FF"、"corner" など。mkanim と同じ）
  --gain dB、--start 秒、--duration 秒             音量の調整、音の何秒目から何秒分を使うか（全部の音声に）
  --fps N              ひな形の .s で、画像を何枚／秒で切り替えるか（既定 2）
  --wait tmwa          ひな形の待ちを panic.x の TMWA にする。既定は vwait（VWAIT：再生の頭からの予定の時刻で待ち、
                       遅れたコマの分を後で取り戻す）
  --clock 10mhz        対象機の MPU クロック（10、16.7 など。--fast の符号化と、--build のとき）
  --build              ひな形の .s から、すぐに .pan も作る（buildPan と同じ）
"""
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a_enc  # noqa: E402
import adpcm  # noqa: E402
import spr_enc  # noqa: E402
import txt_enc  # noqa: E402
import animcommon  # noqa: E402
import cli  # noqa: E402
import mkscene  # noqa: E402
import clock as clk  # noqa: E402

IMAGE_EXT = {".png", ".bmp", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".webp"}
AUDIO_EXT = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".aif", ".aiff", ".wma", ".opus"}
TARGETS = ("cel", "pal", "pcm", "s")
TICK_HZ = animcommon.VSYNC_HZ


class _Frames:
    """mkscene.make_palette／quantize_layer に渡すための入れ物"""

    def __init__(self, frames):
        self.frames, self.idx = frames, []


def short_name(stem, used):
    """Human68k 向けの英数字 8 文字までの名前（重なれば番号を付ける）"""
    base = re.sub(r"[^A-Za-z0-9_]", "", stem).lower() or "x"
    base = base[:8]
    name, k = base, 1
    while name in used:
        tail = str(k)
        name = base[:8 - len(tail)] + tail
        k += 1
    used.add(name)
    return name


def collect(inputs):
    """入力を画像と音声に分ける（フォルダは中の画像を名前順に）"""
    images, audios = [], []
    for s in inputs:
        p = Path(s)
        if p.is_dir():
            found = sorted(f for f in p.iterdir() if f.suffix.lower() in IMAGE_EXT)
            if not found:
                raise SystemExit(f"フォルダに画像がありません：{p}")
            images += found
        elif p.is_file():
            ext = p.suffix.lower()
            if ext in IMAGE_EXT:
                images.append(p)
            elif ext in AUDIO_EXT:
                audios.append(p)
            else:
                raise SystemExit(f"画像でも音声でもないファイルです（拡張子 {ext}）：{p}")
        else:
            raise SystemExit(f"見つかりません：{p}")
    return images, audios


def load_image(path, a):
    im = Image.open(path).convert("RGBA")
    im = animcommon.key_transparent(im, animcommon.parse_key_colors(a.transparent), a.transparent_tolerance)
    aspect = animcommon.pixel_aspect(a.aspect, a.pixel_aspect)
    return np.asarray(animcommon.fit_256(im, aspect, a.fit))


def make_cels(frames, a, base_pal, top):
    """色番号の画像とパレットを作る。base_pal（既存のパレット）があれば、その後ろに色を足す。
    top：使える最大の番号（グラフィック 255、テキスト・スプライト 15。0 番＝透明、1 番＝黒は予約）"""
    pal = a_enc.Palette(base_pal)
    room = top - pal.last  # まだ使える番号の数
    if room <= 0:
        raise SystemExit("パレットがいっぱいで、新しい色を足せません（--pal-in のパレット）")
    F = _Frames(frames)
    mkscene.quantize_layer(F, mkscene.make_palette([F], ncolors=min(top - 1, room)), pal,
                           a.dither, a.dither_strength, 0)
    if pal.last > top:
        raise SystemExit(f"色が {top + 1} 色に入りません（{pal.last + 1} 色）")
    return F.idx, pal


def template(name, images, audios, pal_labels, fps, has_cel, has_pcm, plane="g0", sprite_pal=1, wait_mode="vwait"):
    """スケジュールのひな形：音を鳴らし、画像を順に表示する。
    グラフィック・テキストは 2 か所を交互に描いてスクロールで切り替え、スプライトは SPOF／SPON で切り替える"""
    wait = max(1, round(TICK_HZ / fps))
    L = [f"* {name}.s : mkparts.py が作ったひな形。自由に書き換えてよい（最後の .include は消さないこと）",
         f"*   画像 {len(images)} 枚を {fps:g} 枚／秒（{wait} カウント ＝ 約 {wait * 18.03:.0f} ms ごと）で順に表示し、最初に音を鳴らす",
         "*   命令の説明は docs/panic/ の付属ドキュメント（sch.h、a_enc.doc など）", "",
         "\t.include\tsch.h", "", "\tTMON"]
    if has_cel and images:
        if plane in ("g0", "g1"):
            L.append(f"\tGPAL\t{pal_labels[0]}\t\t\t* パレット（グラフィック）")
        elif plane == "text":
            L.append(f"\tTPAL\t0,{pal_labels[0]}\t\t* パレット（テキスト面）")
        else:
            L.append(f"\tTPAL\t{sprite_pal},{pal_labels[0]}\t\t* パレット（スプライト。パレットの番号 {sprite_pal}）")
            L.append("*\tSPIN\t\t\t\t* PCG の登録を最初からやり直すときは SPIN")
            for path, lab in images:
                L.append(f"\tSPCG\t{sprite_pal},{lab}\t\t* {path.name} のパターンを登録")
    vw = wait_mode == "vwait"
    if vw:  # VWAIT：再生の頭からの予定の時刻で待つ（遅れたコマの分を後の待ちで取り戻す）
        L += ["\tTMWA\t1\t\t\t* タイマーの基準", animcommon.VWAIT_INIT]
    if has_pcm and audios:
        lab = audios[0][1]
        L.append(f"\tPCMP\t{lab},{lab}_end-{lab}\t* 音（{audios[0][0].name}）")
        for _, other in audios[1:]:
            L.append(f"*\tPCMP\t{other},{other}_end-{other}\t* ほかの音（鳴らす所に移して使う）")
    if has_cel:
        each = len(set(pal_labels)) > 1  # 画像ごとのパレット（--pal-each）
        draw, scl = {"g0": ("DRW0", "SCL0"), "g1": ("DRW1", "SCL1"), "text": ("DRWT", "SCLT")}.get(plane, (None, None))
        for k, (path, lab) in enumerate(images):
            x = 0 if k % 2 == 0 else 256
            if each and k > 0:
                if plane in ("g0", "g1"):
                    L.append(f"\tGPAL\t{pal_labels[k]}\t\t\t* {path.name} のパレット（表示中の絵の色も変わる）")
                else:
                    num = 0 if plane == "text" else sprite_pal
                    L.append(f"\tTPAL\t{num},{pal_labels[k]}\t\t* {path.name} のパレット（表示中の絵の色も変わる）")
            if plane == "sprite":
                L += ["\tSPOF\t\t\t\t* スプライトを全部消して",
                      f"\tSPON\t{lab}\t\t* {path.name} を表示（位置はセルに入っている）",
                      f"\tTMWA\t{wait}"]
                continue
            where = "最初の 1 枚" if k == 0 else "見えていない側に描く"
            L += [f"\t{draw}\t{x},0,{lab}\t\t* {path.name}（{where}）",
                  f"\t{scl}\t{x},0\t\t\t* {'表示する所' if k == 0 else '表示を切り替える'}",
                  f"\tTMWA\t{wait}"]
    else:
        L.append(f"\tTMWA\t{wait}")
    if vw:
        L = [animcommon.vwait_line(wait) if ln == f"\tTMWA\t{wait}" else ln for ln in L]
    L += ["\tPCMS\t\t\t\t* 音を止める" if has_pcm and audios else "*\tPCMS", "\tDEND", "\tEXIT"]
    if vw:
        L = animcommon.with_vwait_head(L) + animcommon.VWAIT_CODE.split("\n")
    L += ["",
          "* ---- 素材のラベル（buildPan.py が作る。この .include はソースの最後に置くこと）----",
          f"\t.include\t{name}_d.h", "", "\t.end", ""]
    return "\n".join(L)


def main(argv):
    ap = cli.ArgumentParser(description="画像・音声から cel・pal・pcm と .s のひな形を作る")
    ap.add_argument("inputs", nargs="+", help="画像・音声のファイル、画像の入ったフォルダ")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--make", default="cel,pal,pcm,s")
    ap.add_argument("--pal-in", type=Path)
    ap.add_argument("--pal-each", action="store_true")
    ap.add_argument("--plane", choices=["g0", "g1", "text", "sprite"], default="g0")
    ap.add_argument("--sprite-pal", type=int, default=1)
    ap.add_argument("--dither", choices=["none", "fs", "ordered"], default="none")
    ap.add_argument("--dither-strength", type=float, default=24.0)
    ap.add_argument("--fast", action="store_true")
    ap.add_argument("--aspect", action="store_true")
    ap.add_argument("--pixel-aspect", type=float)
    ap.add_argument("--fit", choices=["crop", "pad"])
    ap.add_argument("--transparent")
    ap.add_argument("--transparent-tolerance", type=int, default=0)
    ap.add_argument("--gain", type=float, default=0.0)
    ap.add_argument("--start", type=float)
    ap.add_argument("--duration", type=float)
    ap.add_argument("--fps", type=float, default=2.0)
    ap.add_argument("--wait", choices=["tmwa", "vwait"], default="vwait")
    ap.add_argument("--clock", default=a_enc.DEFAULT_CLOCK)
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args(argv[1:])

    name = a.name
    if not (name.isascii() and name.isalnum() and len(name) <= 8):
        raise SystemExit(f"--name は英数字 8 文字以内にしてください（今は {name!r}）")
    make = {t.strip() for t in a.make.split(",") if t.strip()}
    if not make or make - set(TARGETS):
        raise SystemExit(f"--make は {', '.join(TARGETS)} をカンマ区切りで（今は {a.make!r}）")
    cli.check_number("オプション", "--fps", a.fps, above=0, maximum=60)
    a.clock = clk.parse(a.clock, "オプション", "--clock")
    cli.check_number("オプション", "--transparent-tolerance", a.transparent_tolerance, minimum=0, maximum=255)
    cli.check_number("オプション", "--sprite-pal", a.sprite_pal, integer=True, minimum=1, maximum=15)
    if a.pal_in:
        cli.need_file(a.pal_in, "パレットファイル（--pal-in）")
    if a.pal_each and a.pal_in:
        raise SystemExit("--pal-each と --pal-in は一緒に使えません")
    if a.build and "s" not in make:
        raise SystemExit("--build には .s が要ります（--make に s を入れてください）")
    animcommon.parse_key_colors(a.transparent)  # 書き方の確認

    images, audios = collect(a.inputs)
    if not images and make & {"cel", "pal"}:
        make -= {"cel", "pal"}
    if not audios:
        make.discard("pcm")
    if not make:
        raise SystemExit("作るものがありません（画像も音声も無いか、--make に合う入力がありません）")
    # 出力先。mkparts はファイルを消さないので、すでに素材のあるフォルダへ足してもよい（同じ名前のファイルは上書き）
    out = a.out.resolve() if a.out else mkscene.ROOT / "x68" / "anim" / name
    if out.exists() and not out.is_dir():
        raise SystemExit(f"出力先がフォルダではありません：{out}")
    out.mkdir(parents=True, exist_ok=True)
    used = {name.lower()}
    img_items = [(p, short_name(p.stem, used)) for p in images]
    aud_items = [(p, short_name(p.stem, used)) for p in audios]
    parts = []

    # ---- 画像：パレットとセル ----
    pal_labels, cel_labels = [], {}
    plane = a.plane
    graphic = plane in ("g0", "g1")
    prefix = {"g0": "c_", "g1": "c_", "text": "t_", "sprite": "s_"}[plane]
    ext = ".spr" if plane == "sprite" else ".cel"
    pcg_total = 0
    if images and make & {"cel", "pal", "s"}:
        frames = [load_image(p, a) for p in images]
        w = animcommon.TIME_WEIGHTS[-1] if a.fast else 0
        groups = [[k] for k in range(len(images))] if a.pal_each else [list(range(len(images)))]
        for g in groups:
            idx, pal = make_cels([frames[k] for k in g], a, a.pal_in.read_bytes() if a.pal_in else None,
                                 255 if graphic else 15)
            pal_file = f"{img_items[g[0]][1]}.pal" if a.pal_each else f"{name}.pal"
            pal_lab = f"pal_{img_items[g[0]][1]}" if a.pal_each else "pal"
            pal_labels += [pal_lab] * len(g)
            if "pal" in make or "s" in make:
                (out / pal_file).write_bytes(pal.to_bytes() if graphic else pal.to_bytes()[:34])
                parts.append([pal_lab, pal_file])
                print(f"  パレット {pal_file}：{pal.last + 1} 色" + ("" if graphic else "（16 色用、34 バイト）"))
            for k, im in zip(g, idx):
                path, short = img_items[k]
                if not ("cel" in make or "s" in make):
                    continue
                if plane == "sprite":
                    try:
                        cel = spr_enc.encode(im)
                    except spr_enc.SprError as e:
                        raise SystemExit(f"{path.name}：{e}")
                    if cel is None:
                        print(f"  {path.name} は全部透明なので、スプライトのセルを作りません")
                        continue
                    n, cols, rows, x, y = spr_enc.header(cel)
                    pcg_total += n
                    info = f"16x16 の PCG {n} 個（横 {cols}×縦 {rows}、位置 {x - 16},{y - 16}）"
                elif plane == "text":
                    cel = txt_enc.encode(im)
                    info = f"描く時間の見積もり {txt_enc.estimate_us(cel, a.clock) / 1000:.1f} ms（{a.clock}）"
                else:
                    cel = a_enc.encode(im, None, w, a.clock)
                    info = f"描く時間の見積もり {a_enc.estimate_us(cel, a.clock) / 1000:.1f} ms（{a.clock}）"
                if len(cel) % 2:
                    cel += b"\x00"
                (out / f"{short}{ext}").write_bytes(cel)
                cel_labels[k] = f"{prefix}{short}"
                parts.append([f"{prefix}{short}", f"{short}{ext}"])
                print(f"  {'スプライトのセル' if plane == 'sprite' else 'セル'} {short}{ext}：{len(cel)} バイト、{info} ← {path.name}")
        if pcg_total > 256:
            raise SystemExit(f"スプライトの PCG が全部で {pcg_total} 個あります（256 個まで）。画像を減らすか小さくしてください")
    # ---- 音声：ADPCM ----
    if audios and ("pcm" in make or "s" in make):
        for path, short in aud_items:
            data = adpcm.encode(adpcm.load_audio(path, a.gain, a.start, a.duration))
            if len(data) % 2:
                data += b"\x88"
            (out / f"{short}.pcm").write_bytes(data)
            parts.append([f"pcm_{short}", f"{short}.pcm"])
            print(f"  ADPCM {short}.pcm：{len(data)} バイト（{len(data) * 2 / adpcm.RATE:.2f} 秒）← {path.name}")

    # ---- .s のひな形と素材の一覧 ----
    if "s" in make:
        src = out / f"{name}.s"
        if src.exists():
            print(f"  {src.name} はもうあるので書き換えません（作り直すなら消してから）")
        else:
            shown = [(img_items[k][0], cel_labels[k]) for k in range(len(img_items)) if k in cel_labels]
            labs = [pal_labels[k] for k in range(len(img_items)) if k in cel_labels]
            text = template(name, shown, [(p, f"pcm_{s}") for p, s in aud_items],
                            labs, a.fps, bool(shown), bool(audios), plane, a.sprite_pal, a.wait)
            animcommon.write_sjis(src, text)
            print(f"  ひな形 {src.name}")
        (out / f"{name}.json").write_text(json.dumps(
            {"name": name, "clock": a.clock, "nominal": None, "parts": parts,
             "scene": "mkparts " + " ".join(argv[1:]), "forever": False, "cycle": None},
            ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"-> {out}")
    if a.build:
        import panbuild
        panbuild.build_dir(out, a.clock)
    elif "s" in make:
        print(f"   .s を書き換えたら：pt buildPan {out / (a.name + '.s')}")
    return 0


if __name__ == "__main__":
    sys.exit(cli.run(main))

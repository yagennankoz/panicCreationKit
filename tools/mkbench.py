r"""mkbench.py : ベンチ動画（描画の速さを数える .pan）を設定ファイルから作る

使い方:  pt mkbench <設定.toml> [--out フォルダ] [--stop-at-s]
  例：samples/bench/bench.toml

流れ（できる .pan の動き）:
  1. 導入部分を再生する（[intro]。省略可）
  2. キーが押されるまで待つ
  3. ベンチ部分（[bench] の PNG 連番、G0）を、待たずに（ノーウェイトで）描いては切り替えることをくり返す
     - 1 コマ描いて表示を切り替えるのを 1 ステップと数え、count_every ステップごとにカウントを 1 上げる
     - カウントはテキスト面に数字で表示する（毎回書き直す。字は X68000 の ROM フォント）
     - ループの中の sound_step コマ目で効果音（ADPCM）を鳴らす
  4. seconds 秒たったらベンチを止める
  5. 結果の画面（[result] の静止画）とカウントを表示して、キーが押されるまで待つ
  6. キーが押されたら終わる（ESC はいつでも終わる）

設定ファイル（全体）:
  name = "bench1"         出力名（英数字 8 文字以内）
  out = "フォルダ"         出力先（省略すると x68/anim/<名前>/）
  clock = "10mhz"         対象機の MPU クロック（10、16.7 など。導入部分の描画時間の見積もり、ベンチの予想）
  dither／dither_strength／stabilize   減色（mkscene と同じ。全部の絵に共通）
[intro]（省略可）           導入部分。G0 に 1 枚の層として再生する
  src = "intro"           PNG 連番のフォルダか動画（設定ファイルからの相対）
  fps = 12                1 秒に何コマ（必須）
  diff = true             前フレーム差分（既定 true）
  audio = "intro.wav"     導入部分の音（任意。gain、audio_start、audio_duration も可）
  start／duration／first／count／sequence／hold／aspect／fit／transparent など   mkscene の層と同じ
[bench]                   ベンチ部分（必須）
  src = "bench"           PNG 連番のフォルダか動画
  seconds = 10            何秒数えるか（既定 10）
  count_every = 1         何ステップごとにカウントを 1 上げるか（既定 1）
  diff = true             前フレーム差分（既定 true。描く先には 2 ステップ前の絵が残っている）
  fast = false            true：描く速さを優先して符号化する（既定 false＝bpica.x と同じ符号化）
  sound = "se.wav"        効果音（任意）。gain も可
  sound_step = 0          ループの何コマ目（0 始まり）を描いた後に効果音を鳴らすか（既定 0）
  first／count／aspect／fit／transparent など                       mkscene の層と同じ
[count]                   カウントの数字（テキスト面、ROM フォントの 8x16）
  x = 8                   ベンチ中の表示位置（ドット。左上が 0,0。x は 8 の倍数）
  y = 8
  scale = 1               1＝8x16、2＝16x32
  digits = 6              桁数（右詰め）
  zero_pad = false        true なら左を 0 で埋める（既定は空白）
  color = "#FFFFFF"       数字の色
  result_x／result_y／result_scale   結果の画面での位置と大きさ（省略するとベンチ中と同じ）
[result]（省略可）          結果の画面。省略するとベンチの最後の絵のまま
  src = "result.png"      静止画（PNG 1 枚、またはそのフォルダ）
  aspect／fit／transparent など
"""
import json
import sys
import tomllib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a_enc  # noqa: E402
import adpcm  # noqa: E402
import animcommon  # noqa: E402
import cli  # noqa: E402
import mkscene  # noqa: E402
import clock as clk  # noqa: E402
import panbuild  # noqa: E402

TOP_KEYS = {"name", "out", "clock", "dither", "dither_strength", "stabilize", "intro", "bench", "count", "result"}
IMAGE_KEYS = {"src", "start", "duration", "first", "count", "sequence", "hold", "aspect", "pixel_aspect", "fit",
              "transparent", "transparent_tolerance", "diff"}
INTRO_KEYS = IMAGE_KEYS | {"fps", "audio", "gain", "audio_start", "audio_duration"}
BENCH_KEYS = IMAGE_KEYS | {"seconds", "count_every", "fast", "sound", "gain", "sound_step"}
COUNT_KEYS = {"x", "y", "scale", "digits", "zero_pad", "color", "result_x", "result_y", "result_scale"}
RESULT_KEYS = IMAGE_KEYS - {"diff"}
SLOT = [(0, 0), (256, 0)]
IOCS_FNTADR = 0x16
IOCS_ONTIME = 0x7F


def validate(a, base_dir):
    cli.check_keys("設定", a, TOP_KEYS)
    name = a.get("name")
    if not (isinstance(name, str) and name.isascii() and name.isalnum() and len(name) <= 8):
        raise SystemExit(f"設定：name は英数字 8 文字以内にしてください（今は {name!r}）")
    clk.parse(a.get("clock"), "設定")
    if "bench" not in a or not isinstance(a["bench"], dict):
        raise SystemExit("設定：[bench]（ベンチ部分）を書いてください")
    for sec, keys in (("intro", INTRO_KEYS), ("bench", BENCH_KEYS), ("count", COUNT_KEYS), ("result", RESULT_KEYS)):
        if sec not in a:
            continue
        d = a[sec]
        if not isinstance(d, dict):
            raise SystemExit(f"設定：{sec} は [{sec}] の形で書いてください")
        W = f"[{sec}]"
        cli.check_keys(W, d, keys)
        if sec != "count":
            if not isinstance(d.get("src"), str):
                raise SystemExit(f"{W}：src を文字列で指定してください")
            src = Path(d["src"])
            src = src if src.is_absolute() else base_dir / src
            if not src.exists():
                raise SystemExit(f"{W}：src が見つかりません：{src}")
        for k in ("audio", "sound"):
            if d.get(k) is not None:
                p = Path(d[k])
                cli.need_file(p if p.is_absolute() else base_dir / p, f"{W} の {k}")
    i = a.get("intro", {})
    if i:
        cli.check_number("[intro]", "fps", i.get("fps"), above=0, maximum=60, allow_none=False)
    b = a["bench"]
    cli.check_number("[bench]", "seconds", b.get("seconds"), above=0, maximum=3600)
    cli.check_number("[bench]", "count_every", b.get("count_every"), integer=True, minimum=1)
    cli.check_number("[bench]", "sound_step", b.get("sound_step"), integer=True, minimum=0)
    for k in ("diff", "fast"):
        cli.check_bool("[bench]", k, b.get(k))
    c = a.get("count", {})
    for k in ("x", "result_x"):
        v = cli.check_number("[count]", k, c.get(k), integer=True, minimum=0, maximum=255)
        if v is not None and v % 8:
            raise SystemExit(f"[count]：{k} は 8 の倍数にしてください（テキスト面に 1 バイト単位で書くため。今は {v}）")
    for k in ("y", "result_y"):
        cli.check_number("[count]", k, c.get(k), integer=True, minimum=0, maximum=255)
    for k in ("scale", "result_scale"):
        cli.check_choice("[count]", k, c.get(k), (1, 2))
    cli.check_number("[count]", "digits", c.get("digits"), integer=True, minimum=1, maximum=10)
    cli.check_bool("[count]", "zero_pad", c.get("zero_pad"))
    if c.get("color") is not None:
        cols = animcommon.parse_key_colors(c["color"])
        if len(cols) != 1 or cols[0] == "corner":
            raise SystemExit(f"[count]：color は \"#RRGGBB\" で書いてください（今は {c['color']!r}）")


def load_layer(sec, cfg, base_dir, out, q):
    """1 枚の層として読み込み、その層だけのパレットで色番号の画像にする"""
    lc = {k: v for k, v in cfg.items() if k in IMAGE_KEYS | {"fps"}}
    lc.update(name=sec, plane="g0", base=True)
    src = Path(lc["src"])
    src = src if src.is_absolute() else base_dir / src
    if src.is_file() and src.suffix.lower() == ".png":  # PNG 1 枚：フォルダに写して読む（ファイルは動画として扱われるため）
        import shutil
        folder = out / f"still_{sec}"
        folder.mkdir(parents=True, exist_ok=True)
        for f in folder.glob("*.png"):
            f.unlink()
        shutil.copyfile(src, folder / "f0000.png")
        lc["src"] = str(folder)
    lc.setdefault("fps", 1)
    aspect = animcommon.pixel_aspect(cfg.get("aspect", False), cfg.get("pixel_aspect"))
    L = mkscene.Layer(lc, base_dir, out, aspect, cfg.get("fit"),
                      animcommon.parse_key_colors(cfg.get("transparent")), int(cfg.get("transparent_tolerance", 0)))
    pal = a_enc.Palette()
    mkscene.quantize_layer(L, mkscene.make_palette([L]), pal, *q)
    return L, pal


def load_pcm(path, base_dir, gain, start=None, duration=None):
    p = Path(path)
    p = p if p.is_absolute() else base_dir / p
    data = adpcm.encode(adpcm.load_audio(p, gain or 0.0, start, duration))
    return data + (b"\x88" if len(data) % 2 else b"")


def word_color(spec):
    r, g, b = animcommon.parse_key_colors(spec)[0]
    r5, g5, b5 = ((v * 31 + 127) // 255 for v in (r, g, b))
    return (g5 << 11) | (r5 << 6) | (b5 << 1)


def asm_routines(every, centis, pos_bench, pos_result, digits, zero_pad):
    """68000 のルーチン（BSUB で呼ぶ）。パニックはスーパーバイザ状態で動くので、テキスト VRAM に直接書ける"""
    def draw(label, x, y, scale):
        """カウント（bn_cnt）を、テキスト面のプレーン 0 の (x, y) に digits 桁で書く"""
        cw = scale  # 1 文字の横バイト数
        lines = [f"{label}:",
                 "\tmovem.l\td0-d7/a0-a6,-(sp)",
                 "\tmove.w\t$E8002A,-(sp)\t\t* テキストの同時アクセス・マスクの設定を覚えて、止める",
                 "\tclr.w\t$E8002A",
                 "\tmove.l\tbn_cnt,d0",
                 f"\tlea\tbn_buf+{digits},a0",
                 f"\tmoveq.l\t#{digits}-1,d3",
                 f"{label}_d:",
                 "\tmoveq.l\t#0,d2\t\t\t* d0 を 10 で割る（32 ビット）。d2.w＝余り",
                 "\tswap\td0",
                 "\tmove.w\td0,d2",
                 "\tdivu\t#10,d2",
                 "\tmove.w\td2,d0",
                 "\tswap\td0",
                 "\tmove.w\td0,d2",
                 "\tdivu\t#10,d2",
                 "\tmove.w\td2,d0",
                 "\tswap\td2",
                 "\tmove.b\td2,-(a0)",
                 f"\tcmp.w\t#{digits}-1,d3\t\t* 一の位は必ず数字"]
        if zero_pad:
            lines += [f"\tbra\t{label}_n"]
        else:
            lines += [f"\tbeq\t{label}_n",
                      "\ttst.l\td0",
                      f"\tbne\t{label}_n",
                      "\ttst.w\td2",
                      f"\tbne\t{label}_n",
                      "\tmove.b\t#10,(a0)\t\t* 上の桁の 0 は空白"]
        lines += [f"{label}_n:",
                  f"\tdbra\td3,{label}_d",
                  f"\tlea\t$E00000+{y}*128+{x // 8},a2\t* テキスト VRAM（プレーン 0）",
                  "\tlea\tbn_buf,a0",
                  f"\tmoveq.l\t#{digits}-1,d3",
                  f"{label}_c:",
                  "\tmoveq.l\t#0,d0",
                  "\tmove.b\t(a0)+,d0",
                  "\tlsl.w\t#4,d0",
                  "\tlea\tbn_font,a1",
                  "\tadda.l\td0,a1",
                  "\tmovea.l\ta2,a3",
                  "\tmoveq.l\t#16-1,d4"]
        if scale == 1:
            lines += [f"{label}_r:",
                      "\tmove.b\t(a1)+,(a3)",
                      "\tlea\t128(a3),a3",
                      f"\tdbra\td4,{label}_r"]
        else:  # 2 倍：1 バイトをビットを 2 つずつにした 1 ワードにし、2 行ずつ書く
            lines += [f"{label}_r:",
                      "\tmoveq.l\t#0,d0",
                      "\tmove.b\t(a1)+,d0",
                      "\tadd.w\td0,d0",
                      "\tlea\tbn_dbl,a4",
                      "\tmove.w\t(a4,d0.w),d1",
                      "\tmove.b\td1,1(a3)",
                      "\tmove.b\td1,129(a3)",
                      "\tlsr.w\t#8,d1",
                      "\tmove.b\td1,(a3)",
                      "\tmove.b\td1,128(a3)",
                      "\tlea\t256(a3),a3",
                      f"\tdbra\td4,{label}_r"]
        lines += [f"\taddq.l\t#{cw},a2",
                  f"\tdbra\td3,{label}_c",
                  "\tmove.w\t(sp)+,$E8002A",
                  "\tmovem.l\t(sp)+,d0-d7/a0-a6",
                  "\trts"]
        return lines

    L = ["", "* ---- ベンチのルーチン（mkbench.py が作る。BSUB で呼ぶ）----",
         f"_FNTADR\t.equ\t${IOCS_FNTADR:02x}", f"_ONTIME\t.equ\t${IOCS_ONTIME:02x}",
         "* bn_init：テキスト面（256x256 の所、4 プレーン）を消し、ROM フォントから 0〜9 と空白の形を写す",
         "bn_init:",
         "\tmovem.l\td0-d7/a0-a6,-(sp)",
         "\tmove.w\t$E8002A,-(sp)",
         "\tclr.w\t$E8002A",
         "\tlea\t$E00000,a0",
         "\tmoveq.l\t#4-1,d2",
         "bn_i1:\tmovea.l\ta0,a1",
         "\tmove.w\t#256-1,d1",
         "bn_i2:\tmovea.l\ta1,a2",
         "\tmoveq.l\t#8-1,d0",
         "bn_i3:\tclr.l\t(a2)+",
         "\tdbra\td0,bn_i3",
         "\tlea\t128(a1),a1",
         "\tdbra\td1,bn_i2",
         "\tadda.l\t#$20000,a0",
         "\tdbra\td2,bn_i1",
         "\tmove.w\t(sp)+,$E8002A",
         "\tlea\tbn_chars,a2",
         "\tlea\tbn_font,a3",
         "\tmoveq.l\t#11-1,d3",
         "bn_i4:\tmoveq.l\t#0,d1",
         "\tmove.b\t(a2)+,d1",
         "\tmoveq.l\t#8,d2\t\t\t* 16 ドットのフォント（半角は 8x16）",
         "\tmoveq.l\t#_FNTADR,d0",
         "\ttrap\t#15",
         "\tmovea.l\td0,a1",
         "\tmoveq.l\t#16-1,d4",
         "bn_i5:\tmove.b\t(a1)+,(a3)+",
         "\tdbra\td4,bn_i5",
         "\tdbra\td3,bn_i4",
         "\tmovem.l\t(sp)+,d0-d7/a0-a6",
         "\trts",
         "* bn_start：時刻を覚え、カウントを 0 にして表示する。D7＝0",
         "bn_start:",
         "\tmovem.l\td0-d6/a0-a6,-(sp)",
         "\tmoveq.l\t#_ONTIME,d0",
         "\ttrap\t#15",
         "\tmove.l\td0,bn_t0",
         "\tclr.l\tbn_cnt",
         "\tclr.l\tbn_steps",
         "\tbsr\tbn_draw_b",
         "\tmoveq.l\t#0,d7",
         "\tmovem.l\t(sp)+,d0-d6/a0-a6",
         "\trts",
         f"* bn_step：1 ステップ。{every} ステップごとにカウントを 1 上げて表示し直す。{centis / 100:g} 秒たったら D7＝1",
         "bn_step:",
         "\tmovem.l\td0-d6/a0-a6,-(sp)",
         "\taddq.l\t#1,bn_steps",
         f"\tcmpi.l\t#{every},bn_steps",
         "\tbcs\tbn_s1",
         "\tclr.l\tbn_steps",
         "\taddq.l\t#1,bn_cnt",
         "\tbsr\tbn_draw_b",
         "bn_s1:\tmoveq.l\t#_ONTIME,d0",
         "\ttrap\t#15",
         "\tsub.l\tbn_t0,d0",
         "\tbpl\tbn_s2",
         "\tadd.l\t#8640000,d0\t\t* 0 時をまたいだとき",
         "bn_s2:\tmoveq.l\t#0,d7",
         f"\tcmpi.l\t#{centis},d0",
         "\tbcs\tbn_s3",
         "\tmoveq.l\t#1,d7",
         "bn_s3:\tmovem.l\t(sp)+,d0-d6/a0-a6",
         "\trts",
         "* bn_result：テキスト面を消して、結果の位置にカウントを書く",
         "bn_result:",
         "\tmovem.l\td0-d7/a0-a6,-(sp)",
         "\tmove.w\t$E8002A,-(sp)",
         "\tclr.w\t$E8002A",
         "\tlea\t$E00000,a1",
         "\tmove.w\t#256-1,d1",
         "bn_r1:\tmovea.l\ta1,a2",
         "\tmoveq.l\t#8-1,d0",
         "bn_r2:\tclr.l\t(a2)+",
         "\tdbra\td0,bn_r2",
         "\tlea\t128(a1),a1",
         "\tdbra\td1,bn_r1",
         "\tmove.w\t(sp)+,$E8002A",
         "\tbsr\tbn_draw_r",
         "\tmovem.l\t(sp)+,d0-d7/a0-a6",
         "\trts"]
    L += draw("bn_draw_b", *pos_bench)
    L += draw("bn_draw_r", *pos_result)
    dbl = []
    for v in range(256):  # ビットを 2 つずつにする表（2 倍の字用）
        w = 0
        for bit in range(8):
            if v >> bit & 1:
                w |= 3 << (bit * 2)
        dbl.append(w)
    L += ["\t.even", "bn_t0:\t.dc.l\t0", "bn_cnt:\t.dc.l\t0", "bn_steps:\t.dc.l\t0",
          "bn_chars:\t.dc.b\t'0123456789 '", "\t.even", "bn_font:\t.ds.b\t11*16",
          f"bn_buf:\t.ds.b\t{digits + 1}", "\t.even", "bn_dbl:"]
    for i in range(0, 256, 16):
        L.append("\t.dc.w\t" + ",".join(f"${w:04X}" for w in dbl[i:i + 16]))
    return L


def build(a, base_dir, stop=False, src_desc=""):
    validate(a, base_dir)
    name = a["name"]
    clock = clk.parse(a.get("clock"))
    out = mkscene.output_dir(a, base_dir, name)
    for f in list(out.glob("*.cel")) + list(out.glob("pcm*.dat")):
        f.unlink()
    q = (a.get("dither", "none"), a.get("dither_strength", 24.0), a.get("stabilize", 0))
    parts, cels = [], {}

    def cel_label(prefix, data):
        if len(data) % 2:
            data += b"\x00"
        if data not in cels:
            lab = f"{prefix}{sum(1 for v in cels.values() if v.startswith(prefix)):03d}"
            cels[data] = lab
            (out / f"{lab}.cel").write_bytes(data)
            parts.append([lab, f"{lab}.cel"])
        return cels[data]

    S = ["* " + name + ".s : mkbench.py が自動生成（ベンチ動画）", "", "\t.include\tsch.h", "",
         "\tTMON", "\tBSUB\tbn_init\t\t\t* テキスト面を消し、数字の形を用意する", "\tTPAL\t0,tpal"]
    c = a.get("count", {})
    # テキストのパレット：数字はプレーン 0 に書くので色番号 1 に数字の色を入れる（0 番は透明）。
    # a_enc.Palette は 1 番を黒に予約しているので使わない（使うと数字が黒になって見えない）
    tpal = np.array([1, 0, word_color(c.get("color", "#FFFFFF"))] + [0] * 14, ">u2")
    (out / "tpal.dat").write_bytes(tpal.tobytes())
    parts.append(["tpal", "tpal.dat"])

    # ---- 1. 導入部分（mkscene の時間の割り振りをそのまま使う）----
    intro = a.get("intro")
    if intro:
        L, pal = load_layer("intro", intro, base_dir, out, q)
        end = mkscene.plan_timeline([L], 1, 0)
        L.slots = mkscene.POS
        L.diff = bool(intro.get("diff", True))
        head, body, tail, order, _, info = mkscene.schedule([L], end, {"diff": L.diff}, clock)
        for lab, data in order:  # schedule のラベル c000… はそのまま使う（ベンチは b、結果は r）
            (out / f"{lab}.cel").write_bytes(data)
            parts.append([lab, f"{lab}.cel"])
        (out / "pal_i.dat").write_bytes(pal.to_bytes())
        parts.append(["pal_i", "pal_i.dat"])
        S += ["* ---- 1. 導入部分 ----", "\tRDRB\t$E82601\t\t\t* 準備の間は画面を消す", "\tMOVB\t0,$E82601", "\tGPAL\tpal_i"]
        S += head + ["\tWTRB\t$E82601", "\tTMWA\t1"]
        if intro.get("audio"):
            data = load_pcm(intro["audio"], base_dir, intro.get("gain"), intro.get("audio_start"), intro.get("audio_duration"))
            (out / "pcm.dat").write_bytes(data)
            parts.append(["pcm", "pcm.dat"])
            S.append("\tPCMP\tpcm,pcm_end-pcm\t\t* 導入部分の音")
        S += body + tail
        print(f"導入：{L.n} 枚、{end * 18.03 / 1000:.2f} 秒"
              + (f"（間に合わないので飛ばすコマ {len(info['dropped'])} 個）" if info["dropped"] else ""))

    # ---- 2. キー待ち ----
    S += ["* ---- 2. キーが押されるまで待つ ----", "bn_wait1:", "\tTMWA\t1", "\tRTOK", "\tIFEQ\t0,bn_wait1", "\tPCMS"]

    # ---- 3. ベンチ部分 ----
    b = a["bench"]
    B, bpal = load_layer("bench", b, base_dir, out, q)
    n = B.n
    seq = [k for k, _ in B.steps]  # sequence があればその順（同じ画像が続く所はまとめてある）
    m = len(seq) if len(seq) % 2 == 0 else 2 * len(seq)  # 2 か所を交互に使うので、ループは偶数コマに
    diff = bool(b.get("diff", True))
    w = animcommon.TIME_WEIGHTS[-1] if b.get("fast") else 0
    (out / "pal_b.dat").write_bytes(bpal.to_bytes())
    parts.append(["pal_b", "pal_b.dat"])
    se_step = int(b.get("sound_step", 0))
    if b.get("sound"):
        if se_step >= len(seq):
            raise SystemExit(f"[bench]：sound_step は 0〜{len(seq) - 1}（ベンチは {len(seq)} コマ）")
        (out / "pcmse.dat").write_bytes(load_pcm(b["sound"], base_dir, b.get("gain")))
        parts.append(["pcmse", "pcmse.dat"])
    every = int(b.get("count_every", 1))
    centis = round(float(b.get("seconds", 10)) * 100)
    # 準備：入れ物 0 に ループの最後から 2 コマ目、入れ物 1 に最後のコマを描いておく（どちらも差分なしの全部）
    pre = [seq[(m - 2) % len(seq)], seq[(m - 1) % len(seq)]]
    S += ["* ---- 3. ベンチ部分：待たずに描いては切り替える ----",
          "\tRDRB\t$E82601", "\tMOVB\t0,$E82601", "\tGPAL\tpal_b"]
    for s, k in enumerate(pre):
        x, y = SLOT[s]
        S.append(f"\tDRW0\t{x},{y},{cel_label('b', a_enc.encode(B.idx[k], None, w, clock))}\t\t* bench {B.img_no[k]}")
    S += ["\tSCL0\t256,0", "\tWTRB\t$E82601", "\tBSUB\tbn_start\t\t* 時刻を覚え、カウントを 0 に", "bn_loop:"]
    content = [B.idx[pre[0]], B.idx[pre[1]]]
    times = []
    for j in range(m):
        k = seq[j % len(seq)]
        s = j % 2
        cel = a_enc.encode(B.idx[k], content[s] if diff else None, w, clock)
        times.append(a_enc.estimate_us(cel, clock))
        content[s] = B.idx[k]
        x, y = SLOT[s]
        S += [f"\tDRW0\t{x},{y},{cel_label('b', cel)}\t\t* bench {B.img_no[k]}", f"\tSCL0\t{x},{y}"]
        if b.get("sound") and j % len(seq) == se_step:
            S.append("\tPCMP\tpcmse,pcmse_end-pcmse\t* 効果音")
        S += ["\tBSUB\tbn_step\t\t\t* 1 ステップ（カウントと時間）", "\tIFNE\t0,bn_end"]
    S += ["\tGOTO\tbn_loop", "bn_end:"]

    # ---- 4・5. 結果の画面 ----
    r = a.get("result")
    S.append("* ---- 4・5. 結果の画面とカウントを表示して、キーが押されるまで待つ ----")
    if r:
        R, rpal = load_layer("result", r, base_dir, out, q)
        (out / "pal_r.dat").write_bytes(rpal.to_bytes())
        parts.append(["pal_r", "pal_r.dat"])
        S += ["\tRDRB\t$E82601", "\tMOVB\t0,$E82601", "\tGPAL\tpal_r",
              f"\tDRW0\t0,256,{cel_label('r', a_enc.encode(R.idx[0], None, 0, clock))}\t\t* 結果の画面（下半分の場所）",
              "\tSCL0\t0,256", "\tWTRB\t$E82601"]
    S += ["\tBSUB\tbn_result\t\t* カウントを結果の位置に", "bn_wait2:", "\tTMWA\t1", "\tRTOK", "\tIFEQ\t0,bn_wait2",
          "\tPCMS\t\t\t\t* 音を止める", "\tDEND", "\tEXIT"]
    pos_b = (int(c.get("x", 8)), int(c.get("y", 8)), int(c.get("scale", 1)))
    pos_r = (int(c.get("result_x", pos_b[0])), int(c.get("result_y", pos_b[1])), int(c.get("result_scale", pos_b[2])))
    digits = int(c.get("digits", 6))
    for nm, (x, y, sc) in (("ベンチ中", pos_b), ("結果", pos_r)):
        if x + 8 * sc * digits > 256 or y + 16 * sc > 256:
            raise SystemExit(f"[count]：{nm}の数字（{digits} 桁、{sc} 倍）が画面からはみ出します（x={x}, y={y}）")
    S += asm_routines(every, centis, pos_b, pos_r, digits, bool(c.get("zero_pad", False)))
    S += ["", "* ---- 素材のラベル（buildPan.py が作る。この .include はソースの最後に置くこと）----",
          f"\t.include\t{name}_d.h", "", "\t.end", ""]
    animcommon.write_sjis(out / f"{name}.s", "\n".join(S))
    (out / f"{name}.json").write_text(json.dumps(
        {"name": name, "clock": clock, "nominal": None, "parts": parts, "scene": src_desc, "forever": True, "cycle": None},
        ensure_ascii=False, indent=1), encoding="utf-8")

    avg = sum(times) / len(times) / 1000
    over = 0.2  # SCL0・BSUB（時刻の読み出し）・IFNE などのおおよその時間 [ms]
    print(f"ベンチ：{n} 枚（ループ {m} コマ）、差分{'あり' if diff else 'なし'}、{float(b.get('seconds', 10)):g} 秒、"
          f"{every} ステップごとにカウント")
    print(f"  予想（{clock}）：1 ステップ 約 {avg + over:.1f} ms → {float(b.get('seconds', 10)):g} 秒で約 "
          f"{int(centis * 10 / (avg + over))} ステップ（カウント 約 {int(centis * 10 / (avg + over)) // every}）")
    print(f"セル {len(cels)} 個 {sum(len(k) for k in cels) } バイト")
    if stop:
        print(f"-> {out / (name + '.s')} まで作って止めました。続きは：pt buildPan {out / (name + '.s')}")
        return 0
    panbuild.build_dir(out, clock)
    return 0


def main(argv):
    args = argv[1:]
    out = None
    if "--out" in args:
        k = args.index("--out")
        if k + 1 >= len(args) or args[k + 1].startswith("--"):
            raise SystemExit("--out の後に出力先のフォルダを書いてください")
        out = str(Path(args[k + 1]).resolve())
        args = args[:k] + args[k + 2:]
    pos = cli.check_args(args, ["--stop-at-s"], 1)
    if pos is None:
        print(__doc__, file=sys.stderr)
        return 1
    cfg_path = cli.need_file(pos[0], "設定ファイル")
    a = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    if out:
        a["out"] = out
    return build(a, cfg_path.resolve().parent, "--stop-at-s" in args, str(cfg_path.resolve()))


if __name__ == "__main__":
    sys.exit(cli.run(main))

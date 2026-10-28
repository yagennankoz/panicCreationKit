r"""mkscene.py : 層（グラフィック 0／1、テキスト面、スプライト）を重ねたアニメを、設定ファイルから作る

使い方:  pt mkscene <設定.toml> [--out フォルダ] [--stop-at-s] [--sim]
  --out で出力先のフォルダ（省略すると設定の out、それも無ければ x68/anim/<名前>/）。
  --sim で、できた .pan を pansim（PC 上のシミュレータ）で動かし、再生時間と、各切り替えの画面が予定どおりかを確かめる
  （既定はしない。設定ファイルに sim = true と書いてもよい）。
  例は samples/layer1/scene*.toml、samples/layer1/forever.toml（永久ループ＋キーで終了）。
  --stop-at-s で .s まで作って止め、編集後は pt buildPan x68/anim/<名前>/<名前>.s。
  1 枚もの（PNG 連番や動画 1 本）は mkanim.py でも作れる（中身はこのファイルの build を呼んでいる）。

設定ファイル（全体）:
  name = "lay1"           出力名（英数字 8 文字以内）→ <出力先>/<名前>.pan
  out = "build/lay1"      出力先のフォルダ（設定ファイルからの相対。省略すると x68/anim/<名前>/）。
                          セル・パレット・.s・.json・.pan などをここに作る。エミュレータで見るには x68 の中（H:）に置くか、.pan を写す
  clock = "10mhz"         対象機の MPU クロック。10、16.7、"24mhz" のように書く（1〜100MHz）。描画時間の見積もりに使う（tools/clock.py）
  loops = 2               基準の層を何ループで 1 回分にするか（シーンの長さ。永久ループのときは 1 周の長さ）
  loop = "forever"        永久ループ（省略時は 1 回で終わる）。終わるのは exit_key か ESC
  exit_key = "any"        永久ループを終わらせるキー：any（どれでも）／space／return／none（ESC だけ）。既定 any
  diff = true             前フレーム差分（描画先に残っている絵との差分）
  dither = "none"         none / fs / ordered（全層共通）
  dither_strength = 24
  stabilize = 0           前のコマと近い色は前のままにする（全層共通。実写向け、目安 16〜24）
  audio = "x.wav"         音（任意）。最初の表示と同時に鳴らす（動画のファイルを書けば動画の音）
  audio_start = 3.0       音のファイルの何秒目から使うか。省略すると頭（0 秒）から
  audio_duration = 8.0    audio_start から何秒分を使うか。省略すると最後まで
  gain = -3.0             音量の調整 [dB]。省略すると 0（そのまま）
  audio_offset = 0.5      音を鳴らし始める時刻 [秒]（アニメの始まりから。負なら音の頭を削って早める）
  audio_every = 3         永久ループで何周ごとに音を鳴らし直すか（既定：音が鳴り終わる周の数。0 なら最初に 1 回だけ）。
                          永久ループのくり返しの単位はこの周の数になる（音と絵が毎回同じ関係でくり返す）
  fm = "bgm.zms"          FM 音源の曲（Z-MUSIC ver2 の MML（.zms／.opm）か ZMD）。再生には Z-MUSIC（ZMSC.X）の常駐が要る
  fm_offset = 0.5         曲を鳴らし始める時刻 [秒]（アニメの始まりから。0 以上）
  fm_every = 2            永久ループで何周ごとに曲を頭から鳴らし直すか（止めてから鳴らす）。既定 0＝最初に 1 回だけ
                          （曲の中の [do]〜[loop] でくり返す曲なら 0 のままでよい）。永久ループでないときは使わない
  [[se]]                  FM 音源の効果音（いくつでも。Z-MUSIC ver2 の MML か ZMD。共通コマンドは音色の定義だけ）
  src = "shot.zms"
  offset = 1.0            鳴らす時刻 [秒]（アニメの始まりから。0 以上）
  every = 1               永久ループで何周ごとに鳴らすか（既定 1＝毎周。0＝最初に 1 回だけ）
  track = 8               割り込ませる曲のトラック（既定：効果音の最初のトラックのチャンネル。FM3 なら 3）。
                          曲のそのトラックは、効果音の間だけ休む。効果音のチャンネルと、曲のそのトラックのチャンネルは同じにすること
  no_drop = false         描画が間に合わないコマを飛ばさない（遅らせる）
  timelog = true          再生時間を anim\<名前>\time.txt に書く（永久ループではキーで終えた時までの時間）
  order = ["sprite", "text", "graphic"]   重なり順（手前から。既定は panic.x と同じ）。BG はスプライトの層の中（BG1＜BG0＜スプライト）
  graphic_order = ["g0", "g1"]            グラフィックの中の順（手前から）
  wait = "tmwa"           待ち方。vwait（既定）＝再生の頭からの予定の時刻で待つ（遅れたコマの分を後の待ちで取り戻すので、遅い機械でも長さが変わりにくい）、
                          tmwa＝panic.x の TMWA（前の待ちからの V-Sync を数える。遅れは取り戻さない）
  adjust_every = 10.0     一定時間ごとの補正（vwait のときだけ）：adjust_every 秒ごとに、待ちを adjust_frames カウント
  adjust_frames = -1      （V-Sync 1 回＝約 18ms）足す。負＝早める、正＝遅らせる。音とのわずかなずれを直す
  buffers = 4             グラフィック（G0／G1）の描画先の数。4（既定）＝512x512 の面を全部（256x256 の 4 か所）使う、
                          2＝面の上半分の 2 か所を交互に。4 では同じ画像が入っていれば描かずにスクロールだけで切り替え、
                          空いていれば先のコマを前もって描く。4 枚以下の画像の層は最初に全部描いておくので、あとは描画時間 0。
                          省略したとき、永久ループで 4 では 6 周の中にくり返しが見つからなければ、自動で 2 にして作り直す。
                          層ごとにも書ける（層の buffers）
  fixed_cels = true       区切りを決めたセル（既定 true。層の項目の fixed_cels を参照）
  aspect = true           ドットの縦横比の補正（横を 2/3 に縮める）。pixel_aspect＝1 ドットの横÷縦（既定 1.5）
  fit = "pad"             256x256 への収め方：pad（全体を収めて余白）／crop（埋めてはみ出しを切る）。既定は aspect なら pad
  transparent = "#FF00FF" 透明にする色。"corner"＝各画像の左上 (0,0) の色、";" 区切りで複数。transparent_tolerance＝許す差
                          （aspect／fit／transparent は全層の既定。層の中に書けばその層だけ変えられる）
設定ファイル（層。[[layer]] を並べる）:
  name = "bg"
  plane = "g1"            g0／g1（グラフィック）／text（テキスト面）／sprite（スプライト）／bg0／bg1（BG 面、8x8 のタイル）
  src = "bg"              PNG 連番のフォルダ、または動画ファイル（設定ファイルからの相対）。アルファ 128 未満は透明（色0）
  start = 12.5            （動画のときだけ）動画の何秒目から使うか。省略すると頭（0 秒）から
  duration = 4.0          （動画のときだけ）start から何秒分を使うか。省略すると最後まで
  base = true             基準の層（全部の層の中でちょうど 1 つ）。この層の fps が全体の速さの基準になる
  fps = 8                 1 秒に何コマ進めるか。基準の層には必ず書く。ほかの層は fps か loop_ratio のどちらかを書く
  loop_ratio = 2.0        （基準でない層）この層の 1 ループを、基準の層の 1 ループの何倍の長さにするか（fps の代わり）。
                          この層のコマは、その長さを等分して切り替わる（1 コマの時間は自動で決まる）。
                          → 下の「層の速さの決め方」も参照
  first = 10             （PNG 連番のとき）使い始める画像の番号。PNG をファイル名順に並べ、先頭を 0 番と数える（0 始まり）。
                          この例では 11 枚目の画像から使う。省略すると 0（先頭から）
  count = 24              （PNG 連番のとき）first から何枚使うか。省略すると最後まで。
                          例：first = 10、count = 24 なら 10 番〜33 番（11 枚目〜34 枚目）の 24 枚
  sequence = "0-7,6-1"    表示する順番。画像の番号は 0 始まり（first を書いたときは、使う範囲の先頭が 0 番）。
                          a-b＝範囲（逆順も可）、:x＝表示時間 x 倍（"0.5s" なら秒）、*k＝くり返し、かっこでまとめる："(0-3)*4"
  hold = "5:3,7:0.5s"     画像ごとの表示時間の既定（番号は sequence と同じ 0 始まり。その画像が出てくる所すべてに効く）
  diff = false            この層だけ前フレーム差分を使う／使わない（省略すると全体の diff）。背景の写真など、
                          コマごとに大きく変わる絵は差分がほとんど効かず、差分なしの方がセルを使い回せる
  buffers = 2             この層だけ描画先の数を変える（省略すると全体の buffers）。例：コマが多く差分の効くキャラは 2
                          （描く先が交互に決まるので、差分の元の絵がいつも同じになり、差分のセルが 1 枚に 1 組で済む）、
                          枚数の少ない背景は 4（同じ絵が入っていれば描かずにスクロールだけ）
  fixed_cels = false      区切りを決めたセルを使わない（省略すると全体の fixed_cels。既定 true）。true では、1 枚の絵を
                          「絵と描画先の絵だけで決まる区切り」のセルの列にし、どの周でも同じセルを使う（永久ループで本体を
                          何周並べてもセルが増えない）。false は区切りをその時の空き時間で決める

層の速さの決め方（fps・loop_ratio・loops）:
  「1 ループ」＝その層の画像を（sequence があればその順に）最後まで 1 回見せる長さ。
  - 基準の層：1 ループ ＝ コマ数 ÷ fps 秒。例：chara が 12 枚で fps = 12 なら 1 ループ 1 秒。
    （hold や sequence の :x で長くしたコマは、その分を足して数える。例：1 枚を 3 コマ分にすると 14 コマ分 ÷ 12 ＝ 1.17 秒）
  - fps を書いた層：その層だけの速さで動く（基準と関係なく、コマ数 ÷ fps 秒で 1 ループ）。
  - loop_ratio を書いた層：1 ループ ＝ 基準の 1 ループ × loop_ratio。コマ数は関係ない。上の chara（1 秒）が基準のとき、
      bg（6 枚）に loop_ratio = 1.0 → bg も 1 秒で 1 ループ（1 コマ 1/6 秒）。chara と bg は毎回同時に頭に戻る
      bg に loop_ratio = 2.0 → bg は 2 秒で 1 ループ（chara が 2 回ループする間に bg が 1 回）
      bg に loop_ratio = 0.5 → bg は 0.5 秒で 1 ループ（chara が 1 回ループする間に bg が 2 回）
    枚数の違う層どうしでも、ループの頭をそろえたいときに使う。
  - loops（全体の設定）：シーン全体の長さ ＝ 基準の 1 ループ × loops。永久ループ（loop = "forever"）では、これが「1 周」。
  - 永久ループでは、1 周の中で各層がちょうど整数回ループする必要がある（途中で切れると、つなぎ目で絵が飛ぶため）。
    loop_ratio の層なら loops ÷ loop_ratio が整数になるように決める。例：loops = 2 なら loop_ratio は 2／1／0.5／0.25 などが使え、
    1.5 は使えない（2 ÷ 1.5 ＝ 1.33 回）。fps の層なら、(基準の 1 ループ × loops) ÷ (その層のコマ数 ÷ fps) が整数になるように。

しくみ:
  - G0 と G1 はパレットを共有（黒以外 254 色）、テキスト面は 16 色、スプライトは層ごとに 16 色。色0 は透明。
  - 各層のコマの切り替え時刻を V-Sync 単位で並べ、切り替えの間に、次に変わる層の絵を見えていない側
    （各面の (0,0) と (256,0) を交互に使う）へ描く。締め切りの早い層から、待ち時間（の 95%）に収まるよう符号化を調整し、
    収まらなければ分割して描く（グラフィックは行、テキストはプレーン単位）。間に合わないコマは飛ばす。
  - スプライトは最初に全コマのパターンを定義し、切り替えのたびに表示し直す。
  - 最初の準備（各層のコマ 0 を描く）の間は画面を消しておき、終わったら元に戻す。
  - 永久ループ：何周か作ってみて、周の終わりの状態（描画先の中身など）が前の周と同じになった所を「ループの本体」にして
    GOTO で繰り返す（それより前は 1 回だけの前置き）。待ち（TMWA）のたびにキーを調べ、押されたら終わる。
  - 最後に pansim.py で .pan を実行し、各切り替えの画面が予定どおりの重ね合わせになっているかを確かめる。
"""
import hashlib
import json
import struct
import subprocess
import sys
import tomllib
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a_enc  # noqa: E402
import adpcm  # noqa: E402
import animcommon  # noqa: E402
import cli  # noqa: E402
import mml2zmd  # noqa: E402
import panbuild  # noqa: E402
import pansim  # noqa: E402
from pansim import KEY_US, MOVE_US, SPOF_US  # noqa: E402
import clock as clk  # noqa: E402
import spr_enc  # noqa: E402
import txt_enc  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
VSYNC_HZ = animcommon.VSYNC_HZ
TICK_US = 18030
POS = [(0, 0), (256, 0)]                                  # 入れ物 2 つ（面の上半分を交互に）
POS4 = [(0, 0), (256, 0), (0, 256), (256, 256)]             # 入れ物 4 つ（512x512 の面を全部使う。グラフィックだけ）
PLANES = {"g0": 0, "g1": 1, "text": "T", "sprite": None, "bg0": None, "bg1": None}  # SCL0／SCL1／SCLT の番号
BG_SCROLL = {"bg0": 0xEB0800, "bg1": 0xEB0804}  # BG の X スクロール（Y は +2）
DEFAULT_ORDER = ["sprite", "text", "graphic"]   # 手前から。panic.x の初期設定（$E82500＝$06E4）
EXIT_KEYS = {"space": 0x20, "return": 0x0D}
FOREVER_MAX_CYCLES = 6  # 永久ループの周期を探すときに何周まで作ってみるか


class Layer:
    def __init__(self, cfg, base_dir, out, aspect=None, fit=None, key=None, key_tol=0):
        self.name = cfg["name"]
        self.plane = cfg.get("plane", "g0")
        if self.plane not in PLANES:
            raise SystemExit(f"層 {self.name}：plane は g0／g1／text／sprite／bg0／bg1")
        self.text = self.plane == "text"
        self.sprite = self.plane == "sprite"
        self.bg = self.plane in ("bg0", "bg1")
        self.units = 4 if self.text else 32 if self.bg else 256  # 分割の単位：テキストはプレーン、BG はタイルの行、グラフィックは行
        self.base = bool(cfg.get("base", False))
        self.cfg_diff = cfg.get("diff")  # 層ごとの差分の指定（無ければ全体の diff）
        self.cfg_buffers = cfg.get("buffers")  # 層ごとの入れ物の数（無ければ全体の buffers）
        self.cfg_fixed = cfg.get("fixed_cels")  # 層ごとの「区切りを決めたセル」の指定（無ければ全体の fixed_cels）
        self.fixed = False  # build が決める（schedule を直接呼ぶ mkbench などは、区切りを決めたセルを使わない）
        self.fps = cfg.get("fps")
        self.loop_ratio = cfg.get("loop_ratio")
        src = Path(cfg["src"])
        self.src = src if src.is_absolute() else (base_dir / src).resolve()
        if "aspect" in cfg:  # 層ごとに上書きできる
            aspect = animcommon.pixel_aspect(cfg["aspect"], cfg.get("pixel_aspect"))
        fit = animcommon.fit_mode(cfg.get("fit", fit), aspect)
        self.aspect = aspect
        if self.src.is_file():  # 動画：ffmpeg で PNG 連番を切り出す（横の補正も ffmpeg で済ませる）
            folder = out / f"frames_{self.name}"
            animcommon.extract_video(self.src, folder, self.fps or 12, cfg.get("start"), cfg.get("duration"), aspect, fit)
            self.src = folder
            aspect, fit = None, "crop"  # 切り出した PNG は 256x256 なのでそのまま
        # 透明色：層の transparent が全体の指定より優先（"none" で無し）
        key = animcommon.parse_key_colors(cfg["transparent"]) if "transparent" in cfg else (key or [])
        key_tol = int(cfg.get("transparent_tolerance", key_tol))
        self.frames = load_rgba(self.src, aspect, fit, int(cfg.get("first", 0)), cfg.get("count"), key, key_tol)
        # 順番（sequence）と表示時間（hold）。使う画像だけを、最初に出てくる順に 0, 1, … と番号を付け直す
        used, self.steps = parse_sequence(cfg.get("sequence"), len(self.frames), cfg.get("hold"), self.fps, self.name)
        self.frames = [self.frames[i] for i in used]
        self.img_no = used   # 付け直した番号 → 元の画像の番号（PNG の名前順、0 から）
        self.n = len(self.frames)
        if self.n > 1000:
            raise SystemExit(f"層 {self.name}：コマ数は 1000 まで")
        self.total_w = sum(w for _, w in self.steps)  # 1 ループの長さ（既定のコマの時間＝1）
        self.idx = []        # 各コマの色番号画像
        self.events = []     # [(tick, コマ番号)]（tick 0 のコマ 0 を除く）


def _weight(v, fps, layer):
    """表示時間の指定：数なら既定のコマの何倍、"0.5s" なら秒"""
    v = str(v).strip()
    if v.endswith("s"):
        if not fps:
            raise SystemExit(f"層 {layer}：秒での指定（{v}）は fps のある層だけ")
        w = float(v[:-1]) * fps
    else:
        w = float(v)
    if w <= 0:
        raise SystemExit(f"層 {layer}：表示時間は正の値（{v}）")
    return w


def _split_top(spec):
    """カンマで区切る（かっこの中は区切らない）"""
    out, depth, cur = [], 0, ""
    for ch in spec:
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
            continue
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            raise ValueError("かっこが合いません")
        cur += ch
    if depth:
        raise ValueError("かっこが合いません")
    return out + [cur]


def parse_sequence(spec, n, hold=None, fps=None, layer=""):
    """順番の指定を (使う画像の番号のリスト, [(付け直した番号, 重み)]) にする。

    spec：None なら 0〜n-1 を順に。文字列（"0-7,6-1"）または要素のリスト（[0, 1, "2:3", "4-6*2"]）。
      n        画像 n（PNG の名前順、0 から）
      a-b      a から b まで（b < a なら逆順）
      :x       表示時間を既定のコマの x 倍（"0.5s" なら秒）。a-b:x は全部に
      *k       k 回くり返す。かっこでまとめられる："(0-3)*4"
    hold：{画像の番号: 表示時間} または "5:3,7:0.5s"。その画像が出てくる所すべての既定を変える（:x の方が優先）。
    続けて同じ画像が並んだら 1 つにまとめる（時間は足す）。"""
    import re
    holds = {}
    if hold:
        items = hold.items() if isinstance(hold, dict) else (h.split(":", 1) for h in _split_top(str(hold)) if h.strip())
        for k, v in items:
            k = int(str(k).strip())
            if not 0 <= k < n:
                raise SystemExit(f"層 {layer}：hold の画像 {k} がありません（画像は 0〜{n - 1}）")
            holds[k] = _weight(v, fps, layer)
    simple = re.compile(r"^(\d+)(?:-(\d+))?(?::([\d.]+s?))?(?:\*(\d+))?$")
    group = re.compile(r"^\((.*)\)(?:\*(\d+))?$")

    def expand(items):
        res = []
        for it in items:
            it = str(it).replace(" ", "")
            if not it:
                continue
            m = group.match(it)
            if m:
                res += expand(_split_top(m.group(1))) * int(m.group(2) or 1)
                continue
            m = simple.match(it)
            if not m:
                raise SystemExit(f"層 {layer}：sequence の書き方が違います：{it}")
            a = int(m.group(1))
            b = int(m.group(2)) if m.group(2) is not None else a
            rng = range(a, b + 1) if b >= a else range(a, b - 1, -1)
            for k in (a, b):
                if not 0 <= k < n:
                    raise SystemExit(f"層 {layer}：sequence の画像 {k} がありません（画像は 0〜{n - 1}）")
            one = [(k, _weight(m.group(3), fps, layer) if m.group(3) else holds.get(k, 1.0)) for k in rng]
            res += one * int(m.group(4) or 1)
        return res

    if spec is None:
        seq = [(k, holds.get(k, 1.0)) for k in range(n)]
    else:
        try:
            seq = expand(_split_top(spec) if isinstance(spec, str) else list(spec))
        except ValueError as e:
            raise SystemExit(f"層 {layer}：sequence の{e}")
    if not seq:
        raise SystemExit(f"層 {layer}：sequence が空です")
    merged = []
    for k, w in seq:
        if merged and merged[-1][0] == k:
            merged[-1] = (k, merged[-1][1] + w)
        else:
            merged.append((k, w))
    used = list(dict.fromkeys(k for k, _ in merged))
    remap = {k: i for i, k in enumerate(used)}
    return used, [(remap[k], w) for k, w in merged]


def load_rgba(folder: Path, aspect=None, fit=None, first=0, count=None, key=(), key_tol=0):
    """フォルダの PNG（名前順）を読む。first／count で一部だけ（長い素材を分割するとき）。
    key の色は透明にする（縮める前に。縮めた後のふちの半端なドットはアルファ 128 で分ける）"""
    if not folder.is_dir():
        raise SystemExit(f"PNG のフォルダが見つかりません：{folder}")
    all_files = sorted(folder.glob("*.png"))
    if not all_files:
        raise SystemExit(f"{folder} に PNG がありません")
    files = all_files[first:] if count is None else all_files[first:first + int(count)]
    if not files:
        raise SystemExit(f"first = {first} ですが、{folder} の PNG は {len(all_files)} 枚（0〜{len(all_files) - 1} 番）しかありません")
    return [np.asarray(animcommon.fit_256(animcommon.key_transparent(Image.open(f).convert("RGBA"), key, key_tol),
                                          aspect, fit)) for f in files]


def make_palette(layers, ncolors=254):
    """全層の不透明なドットから共通パレットを作る（P モード画像）"""
    px = []
    for L in layers:
        for f in L.frames:
            px.append(f[f[..., 3] >= 128][:, :3])
    px = np.concatenate(px)
    if len(px) == 0:
        px = np.zeros((1, 3), np.uint8)
    if len(px) > 4_000_000:  # 大きすぎるときは間引く
        px = px[:: len(px) // 4_000_000 + 1]
    w = 1024
    h = (len(px) + w - 1) // w
    buf = np.zeros((h * w, 3), np.uint8)
    buf[: len(px)] = animcommon.to5(px)
    buf[len(px):] = buf[0]
    # ncolors は黒以外の色の数（パレットの 0 番＝透明、1 番＝黒は予約）。黒が使われていれば、黒の分を 1 つ足して減色する
    # （足さないと、黒＋黒以外 254 色の絵が黒以外 253 色に減らされてしまう）
    has_black = bool((buf[: len(px)] == 0).all(axis=1).any())
    return Image.fromarray(buf.reshape(h, w, 3)).quantize(colors=ncolors + has_black, method=Image.Quantize.MEDIANCUT,
                                                          dither=Image.Dither.NONE)


def quantize_layer(L, pal_img, pal, dither, strength, stab):
    prev = None
    for f in L.frames:
        rgb = f[..., :3]
        words = animcommon.frame_words(Image.fromarray(rgb), pal_img, dither, strength)
        words = words.copy()
        words[f[..., 3] < 128] = 0x0001  # 透明 → 色0
        idx = a_enc.quantize(words, pal)
        if stab and prev is not None:
            s = animcommon.stabilize(idx, prev, Image.fromarray(rgb), pal, stab)
            idx = np.where(idx == 0, 0, s)  # 透明はそのまま
        L.idx.append(idx)
        prev = idx


def plan_timeline(layers, loops, cycles=0):
    """各層の切り替え時刻を決める。戻り値：シーン（永久ループでは 1 周）の長さ E（カウント）。
    cycles=0：1 回だけ（0 < t < E の切り替え）。cycles>0：永久ループ用に cycles 周ぶん（0 < t <= cycles×E）。
    永久ループでは、どの周も同じ時刻の並びになるように、各層の 1 周の中の切り替えを E の等分で決める。"""
    bases = [L for L in layers if L.base]
    if len(bases) != 1:
        raise SystemExit("基準の層（base = true）をちょうど 1 つ指定してください")
    B = bases[0]
    if not B.fps:
        raise SystemExit(f"基準の層 {B.name} に fps を指定してください")
    base_len = B.total_w * VSYNC_HZ / B.fps
    end = round(loops * base_len)
    for L in layers:
        if L.loop_ratio:
            length = L.loop_ratio * base_len
        elif L.fps:
            length = L.total_w * VSYNC_HZ / L.fps
        else:
            raise SystemExit(f"層 {L.name}：fps か loop_ratio を指定してください")
        L.loop_len = length
        ev = {}
        cum = [0.0]  # 各ステップの始まり（重みの累計）
        for _, w in L.steps:
            cum.append(cum[-1] + w)
        if cycles:
            reps = loops * base_len / length  # 1 周の中で、この層が何ループするか
            if abs(reps - round(reps)) > 1e-6 or round(reps) < 1:
                raise SystemExit(f"層 {L.name}：永久ループでは、1 周（基準の層 × loops）の中で各層がちょうど整数回ループする必要が"
                                 f"あります（今は {reps:.3f} 回）。loop_ratio を調整してください")
            reps = round(reps)
            span = reps * L.total_w
            for c in range(cycles):
                for r in range(reps):
                    for j, (k, _) in enumerate(L.steps):
                        t = c * end + round((r * L.total_w + cum[j]) * end / span)
                        if 0 < t <= cycles * end:
                            ev[t] = k
            ev[cycles * end] = L.steps[0][0]
        else:
            m = 0
            while m * length < end:
                for j, (k, _) in enumerate(L.steps):
                    t = round(m * length + cum[j] * length / L.total_w)
                    if 0 < t < end:
                        ev[t] = k  # 同じ時刻に丸められたら後のコマ
                m += 1
        L.events = sorted(ev.items())
    return end


class Sound:
    """鳴らす音（ADPCM・FM 音源の曲・効果音）1 つ。off_t＝鳴らす時刻（カウント）、every＝永久ループで何周ごとに鳴らすか（0＝1 回だけ）"""

    def __init__(self, key, prefix, play, us, off_t, every, end):
        self.key, self.prefix, self.play, self.us, self.off_t = key, prefix, play, us, off_t
        self.once = every == 0
        self.every = max(1, every)
        self.pos, self.c0 = off_t % end, off_t // end  # 鳴らす周の中の時刻と、最初に鳴らす周
        self.ticks = set()
        self.what = {"pcm": "音", "fm": "FM 音源の曲"}.get(key, f"効果音（{key}）")

    def code(self, n):
        """周を数えて鳴らす：<key>_cnt が 0 なら鳴らして every に戻す（1 回だけなら、もう鳴らない大きな数）。そして 1 減らす"""
        again = 0x7FFFFFFF if self.once else self.every
        return [f"\tRDRL\t{self.key}_cnt\t\t\t* {self.what}：何周ごとに鳴らすかを数える",
                f"\tIFNE\t0,{self.prefix}{n}"] + list(self.play) + [
                f"\tSETR\t{again}",
                f"{self.prefix}{n}:",
                "\tADDR\t$FFFFFFFF\t\t* 1 減らす（SUBR は sch.h に 2 つあるので使わない）",
                f"\tWTRL\t{self.key}_cnt"]


def schedule(layers, end, a, clock, sprites=(), boundaries=(), key_check=False, sounds=(), counted=False):
    """切り替えの間に描くものを決め、スケジュールの命令の行とセルを作る。

    - 各層は L.slots の入れ物（面の中の 256x256 の場所）を使う。2 つなら (0,0) と (256,0) を交互に、4 つなら下半分も使う。
      最初に入れ物を埋めておく（タイマー開始前なので予算外。2 つならどちらもコマ 0、4 つなら使う順に別々の画像）。
    - 次に表示する画像がどこかの入れ物にそのまま入っていれば、描かずにスクロールだけで切り替える。
      入れ物が空いていれば、先のコマを前もって描いておく（先回り）。書きつぶす入れ物は、中身が次に使われるのがいちばん先のもの。
    - 切り替えの間ごとに、締め切り（そのコマを表示する時刻）の早いものから、待ち時間の 95% に収まるだけ描く。
      1 コマが収まらなければ一部だけ描き（分割描画）、残りは次の間に続きから描く。
    - 締め切りまでに描き終わらなかったコマは飛ばす（no_drop なら遅れても描き切る）。
    - 差分（diff）は、描画先に今ある絵（content、実際の GRAM の内容）に対して作る。
    - boundaries の時刻（永久ループの周の区切り）で、状態とそこまでの行数を記録する。
    - 音（sounds の各 Sound）を S.ticks の時刻に鳴らす（PCMP・ZMPL・ZSEP。counted なら周を数えて鳴らすか決める命令の列）。
      0 のときは呼び出し側が最初に置く。
    - 切り替えの直後に実行する命令（キーの確認、スプライトの SPOF／SPON、BG の切り替え、PCMP）の時間は、次の間の予算から引く。
    """
    diff = bool(a.get("diff", False))  # 全体の既定。層の diff があればそちらを使う
    drop = not a.get("no_drop", False)
    slow = clk.scale(clock, "cpu")    # 命令の時間の、10MHz に対する倍率（clock.py）
    slow_io = clk.scale(clock, "spof")  # スプライトの I/O（SPOF など。16.7MHz 以上ではウェイトで遅くなる）
    cels = {}       # bytes → ラベル
    order = []      # [(ラベル, bytes)]

    def cel_label(data):
        if len(data) % 2:
            data += b"\x00"
        if data not in cels:
            lab = f"c{len(cels):03d}"
            cels[data] = lab
            order.append((lab, data))
        return cels[data]

    seg_cache = {}

    def segments(L, k, r, content, w):
        """コマ k の r 行目（テキストは r プレーン目）からの符号化（セグメントと各セグメントの時間）"""
        if L.bg:  # BG：タイルの行ごとに、描画先のマップと違う所だけ書く（MOVL／MOVW）
            key = (L.name, k, r, hashlib.md5(content.tobytes()).hexdigest())
            if key not in seg_cache:
                segs, times = [], []
                for row in range(r, 32):
                    writes = bg_row_writes(L.maps[k][row], content[row])
                    segs.append((row, 1, writes))
                    times.append(len(writes) * MOVE_US * slow)
                seg_cache[key] = (segs, times)
            return seg_cache[key]
        if L.text:  # テキスト：プレーンごと。差分は無い（高速テキストには「そのまま」の命令が無い）
            key = (L.name, k, r)
            if key not in seg_cache:
                pl = txt_enc.index_to_planes(L.idx[k])
                segs = [(p, 1, txt_enc.encode_plane_ops(pl, p)) for p in range(r, 4)]
                times = [txt_enc.estimate_us(b"\x00\x02" + s + b"\x30", clock) for _, _, s in segs]
                seg_cache[key] = (segs, times)
            return seg_cache[key]
        prev = content if L.diff else None
        key = (L.name, k, r, w, hashlib.md5(prev.tobytes()).hexdigest() if prev is not None else None)
        if key not in seg_cache:
            segs = a_enc.encode_segments(L.idx[k], prev, r, 256, w, clock)
            times = [a_enc.estimate_us(b"\x00\x04" + s + b"\x00", clock) for _, _, s in segs]
            seg_cache[key] = (segs, times)
        return seg_cache[key]

    def plan_draw(L, k, r, content, room):
        """r から、room [us] に収まるだけ描く計画。(セグメントの列, 時間, 描き終わるか)。何も描けなければ None"""
        best = None
        for w in animcommon.TIME_WEIGHTS:
            segs, times = segments(L, k, r, content, w)
            total = sum(times)
            if total <= room:
                return segs, total, True
            acc, n = 0.0, 0
            for t in times:
                if acc + t > room:
                    break
                acc += t
                n += 1
            rows = sum(c for _, c, _ in segs[:n])
            if n and (best is None or rows > best[3]):
                best = (segs[:n], acc, False, rows)
        return None if best is None else best[:3]

    def draw_all(L, k, r, content):
        """残りを全部描く（間に合わなくても）。最も速い符号化で"""
        segs, times = segments(L, k, r, content, animcommon.TIME_WEIGHTS[-1])
        return segs, sum(times)

    # ---- 区切りを決めたセル（fixed_cels）----
    # 分割描画の区切りをその時の空き時間で決めると、同じ絵でも周ごとに区切りが変わって別のセルになり、
    # 永久ループで本体を何周も並べたときにセルが増える。fixed_cels の層では、1 枚の絵を「絵と描画先の絵だけで決まる」
    # 区切り（1 つ CHUNK_US ほど）のセルの列にしておき、描くときはそのセルを丸ごと何個か描く（DRW を何回か）。
    # 同じ絵を同じ描画先の絵の上に描くなら、どの周でも同じセルになる（差分なしの層なら絵ごとに 1 組だけ）。
    CHUNK_US = TICK_US * animcommon.BUDGET_RATIO / 2
    DRW_US = 100 * slow  # DRW 1 回ぶんの余分の見込み（命令の読み出し・セルの頭の処理）
    chunk_cache = {}
    # 符号化の重みを選ぶ目安：この層の切り替えの間（中央値）を、描く層の数で分けたもの（ほかの層も同じ間に描くため）
    n_draw = max(1, sum(1 for L in layers if L.n > 1))
    for L in layers:
        ts = [0] + [t for t, _ in L.events]
        gaps = sorted(b - a_ for a_, b in zip(ts, ts[1:]) if b > a_) or [1]
        L.room_us = gaps[len(gaps) // 2] * TICK_US * animcommon.BUDGET_RATIO / n_draw

    def chunks(L, k, content):
        """画像 k を描画先の絵 content の上に描くセルの列 [(先頭の行, 行数, セル, 時間)]（差分なしなら content は見ない）"""
        prev = content if L.diff else None
        key = (L.name, k, hashlib.md5(prev.tobytes()).hexdigest() if prev is not None else None)
        if key in chunk_cache:
            return chunk_cache[key]
        # 符号化の重み：丸ごとが切り替えの間に収まる、いちばん小さい（データが小さい）もの。収まらなければ最速
        w = next((tw for tw in animcommon.TIME_WEIGHTS if sum(segments(L, k, 0, content, tw)[1]) <= L.room_us),
                 animcommon.TIME_WEIGHTS[-1])
        out, r = [], 0
        while r < L.units:
            segs, times = segments(L, k, r, content, w)
            acc, n = 0.0, 0
            for t in times:
                if n and acc + t > CHUNK_US:
                    break
                acc += t
                n += 1
            part = segs[:n]
            rows = sum(c for _, c, _ in part)
            out.append((r, rows, a_enc.cel_from_segments(part), acc + DRW_US))
            r += rows
        chunk_cache[key] = out
        return out

    def rest_chunks(L, k, p, content):
        """切り替えの予定 p の、まだ描いていないセルの列（最初に描く時に、その時の描画先の絵で区切りを決める）"""
        if p.get("chunks") is None:
            assert p["r"] == 0
            p["chunks"] = chunks(L, k, content)
        return [c for c in p["chunks"] if c[0] >= p["r"]]

    def plan_draw_fixed(L, k, p, content, room):
        acc, take = 0.0, []
        for c in rest_chunks(L, k, p, content):
            if acc + c[3] > room:
                break
            acc += c[3]
            take.append(c)
        if not take:
            return None
        return take, acc, take[-1][0] + take[-1][1] >= L.units

    def emit_fixed(L, s, parts):
        x, y = L.slots[s]
        p = PLANES[L.plane]
        return [f"\tDRW{p}\t{x},{y + r0},{cel_label(cel)}\t\t* {L.name} {L.img_no[L.cur_k]} 行 {r0}〜{r0 + n - 1}"
                for r0, n, cel, _ in parts]

    def apply_fixed(L, s, parts):
        canvas = L.st["content"][s]
        for r0, n, cel, _ in parts:
            a_enc.decode_rows(cel, canvas, r0, canvas.copy())
        return sum(n for _, n, _, _ in parts)

    def text_cel(segs):
        return b"\x00\x02" + b"\x2e".join(s for _, _, s in segs) + b"\x30"

    def emit(L, s, segs):
        x, y = L.slots[s]
        if L.bg:  # マップ（$EBC000／$EBE000、64x64 ワード）の (x/8, 行) に書く
            out = []
            for row, _, writes in segs:
                for col, val, size in writes:
                    addr = L.map_base + (row * 64 + x // 8 + col) * 2
                    out.append(f"\tMOV{'L' if size == 4 else 'W'}\t${val:0{size * 2}X},${addr:06X}")
            if out:
                out[0] += f"\t\t* {L.name} {L.img_no[L.cur_k]} タイル行 {segs[0][0]}〜{segs[-1][0]}"
            return out
        if L.text:
            p0 = segs[0][0]
            lab = cel_label(text_cel(segs))
            return [f"\tDRWT\t{x},{y + 1024 * p0},{lab}\t\t* {L.name} {L.img_no[L.cur_k]} プレーン {p0}〜{p0 + len(segs) - 1}"]
        p = PLANES[L.plane]
        y0 = segs[0][0]
        lab = cel_label(a_enc.cel_from_segments(segs))
        rows = sum(c for _, c, _ in segs)
        return [f"\tDRW{p}\t{x},{y + y0},{lab}\t\t* {L.name} {L.img_no[L.cur_k]} 行 {y0}〜{y0 + rows - 1}"]

    def apply(L, s, k, segs):
        """描画先（入れ物 s）の内容を更新（デコードして確かめる）。戻り値：描いた単位（行／プレーン／タイルの行）の数"""
        canvas = L.st["content"][s]
        if L.bg:
            for row, _, writes in segs:
                for col, val, size in writes:
                    if size == 4:
                        canvas[row, col], canvas[row, col + 1] = val >> 16, val & 0xFFFF
                    else:
                        canvas[row, col] = val
                assert (canvas[row] == L.maps[k][row]).all()
            return len(segs)
        if L.text:
            txt_enc.decode_planes(text_cel(segs), canvas, 0, segs[0][0])
            return len(segs)
        a_enc.decode_rows(a_enc.cel_from_segments(segs), canvas, segs[0][0], canvas.copy())
        return sum(c for _, c, _ in segs)

    def holds_image(L, s, k):
        """入れ物 s の中身が画像 k そのものか"""
        c = L.st["content"][s]
        if L.bg:
            return bool((c == L.maps[k]).all())
        if L.text:
            return bool((txt_enc.planes_to_index(c) == L.idx[k]).all())
        return bool((c == L.idx[k]).all())

    # ---- 入れ物（描画先）の割り当て ----
    # 各層は L.slots の入れ物（面の中の 256x256 の場所）を持つ。st["holds"][s]＝入れ物 s にまるごと入っている画像（無ければ None）。
    # st["plan"][j]＝これから表示する切り替え j（events の番号）に使う入れ物：{"slot", "r"（描いた単位の数）, "done", "hit"}。
    # hit＝その画像がすでに入れ物に入っていて、描かずにスクロールだけで済む。
    # 入れ物が 3 つ以上あると、表示中と、それより前の切り替えに使う入れ物以外へ、先のコマを前もって描ける（先回り）。

    def next_use(L, img, after):
        evs = L.events
        for i in range(after + 1, min(len(evs), after + 2 + 2 * max(1, len(L.steps)))):
            if evs[i][1] == img:
                return i
        return 10 ** 9

    def make_slot_plan(L, fill):
        """どのコマをどの入れ物に入れるかを、画像の並びだけから前もって決める（描く時間は考えない）。
        すでに入っている画像ならその入れ物（スクロールだけ）、無ければ表示中以外で、中身が次に使われるのがいちばん先の入れ物。
        前もって決めておくと、コマを飛ばしても割り当てが周ごとにずれないので、永久ループのくり返しが見つかりやすく、
        差分の元の絵もそろうのでセルを使い回せる。"""
        holds, out = list(fill), [0]
        # 入れ物が 4 つなら、直前 2 コマの入れ物は使わない（1 コマ前に先回りして描けるように。表示中と、次に表示するものを避ける）
        keep = 2 if len(L.slots) >= 4 else 1
        for j, (_, k) in enumerate(L.events):
            hit = next((x for x in range(len(L.slots)) if holds[x] == k), None)
            if hit is not None:
                out.append(hit)
                continue
            cand = [x for x in range(len(L.slots)) if x not in out[-keep:]]
            v = max(cand, key=lambda x: (next_use(L, holds[x], j), -x))
            holds[v] = k
            out.append(v)
        return out[1:]  # 先頭の 0 は最初に表示している入れ物

    def assign(L, j):
        """切り替え j に入れ物を割り当てる（すでにあれば何もしない）。割り当てられたら True。
        入れ物は前もって決めたもの（make_slot_plan）。それが今使えない（表示中や、先の切り替えで使う）なら、まだ割り当てない。"""
        st = L.st
        plan = st["plan"]
        if j in plan:
            return True
        if j >= len(L.events) or any(i not in plan for i in range(st["ev"], j)):
            return False  # 順番に割り当てる
        k = L.events[j][1]
        earlier = [plan[i] for i in range(st["ev"], j)]
        drawing = {p["slot"] for p in earlier if not p["hit"]}
        s = L.slot_plan[j]
        if st["holds"][s] == k and s not in drawing:  # すでに入っている → スクロールだけ
            plan[j] = {"slot": s, "r": L.units, "done": True, "hit": True}
            return True
        if s == st["shown"] or s in {p["slot"] for p in earlier}:
            if j > st["ev"]:
                return False  # 先回りはまだできない
            # 今の切り替えなのに予定の入れ物が表示中（前にコマを飛ばしたため）→ 空いている入れ物を代わりに使う
            cand = [x for x in range(len(L.slots)) if x != st["shown"]]
            s = max(cand, key=lambda x: (10 ** 9 + 1) if st["holds"][x] is None else next_use(L, st["holds"][x], j))
        plan[j] = {"slot": s, "r": 0, "done": False, "hit": False}
        return True

    def drop_plan(L, j):
        p = L.st["plan"].pop(j, None)
        if p is not None and not p["done"] and p["r"] > 0:
            L.st["holds"][p["slot"]] = None  # 描きかけ

    def snapshot(e):
        """周の区切りでの状態（これが前の周と同じなら、そこから先は同じことのくり返し）"""
        s = []
        for L in list(layers) + list(sprites):
            n_le = sum(1 for t, _ in L.events if t <= e)
            st = L.st
            if L.sprite:
                s.append((st["ev"] - n_le, st["cur"]))
            else:
                s.append((st["shown"], tuple(hashlib.md5(c.tobytes()).hexdigest() for c in st["content"]),
                          tuple(st["holds"]), st["ev"] - n_le,
                          tuple(sorted((j - st["ev"], p["slot"], p["r"], p["done"], p["hit"])
                                       for j, p in st["plan"].items()))))
        return tuple(s)

    head = []
    for L in layers:  # 最初に入れ物を埋めておく（タイマー開始前なので予算外）
        n = len(L.slots)
        if L.bg:  # BG：両方の描画先のマップにコマ 0 を全部書く
            blank = np.full((32, 32), -1, np.int64)  # 中身が分からない（必ず書く）
            for s in range(n):
                L.st = {"content": [blank.copy() for _ in range(n)]}
                L.cur_k = 0
                head += emit(L, s, [(row, 1, bg_row_writes(L.maps[0][row], blank[row])) for row in range(32)])
            content = [L.maps[0].astype(np.int64) for _ in range(n)]
            fill = [0] * n
        else:
            # 入れ物が 3 つ以上なら、使う順に別々の画像を入れておく（4 枚以下の層は、あとは描かずにスクロールだけ）
            first_use = list(dict.fromkeys([0] + [k for _, k in L.events]))
            fill = [first_use[s] if (n > 2 and s < len(first_use)) else 0 for s in range(n)]
            content = []
            for s, (x, y) in enumerate(L.slots):
                k = fill[s]
                if L.text:
                    lab = cel_label(txt_enc.encode(L.idx[k]))
                    content.append(txt_enc.index_to_planes(L.idx[k]))
                    draw = "DRWT"
                elif L.fixed and not L.diff:  # 差分なしの区切りを決めたセルは、後で描くときと同じセルを使う
                    L.cur_k = k
                    head += emit_fixed(L, s, chunks(L, k, L.idx[k]))
                    content.append(L.idx[k].copy())
                    continue
                else:
                    lab = cel_label(a_enc.encode(L.idx[k]))
                    content.append(L.idx[k].copy())
                    draw = f"DRW{PLANES[L.plane]}"
                head.append(f"\t{draw}\t{x},{y},{lab}\t\t* {L.name} {L.img_no[k]}")
        L.st = {"shown": 0, "content": content, "holds": list(fill), "ev": 0, "plan": {}}
        L.slot_plan = make_slot_plan(L, fill)
        L.cur_k = None
    for L in layers:
        if L.bg:
            head.append(f"\tMOVL\t$00000000,${BG_SCROLL[L.plane]:06X}\t\t* {L.name} スクロール (0,0)")
        else:
            head.append(f"\tSCL{PLANES[L.plane]}\t0,0")
    # スプライト：全部のコマのパターンを最初に定義し（SPCG）、コマ 0 を表示する
    for S in sprites:
        for lab in S.labels_defined:
            head.append(f"\tSPCG\t{S.palno},{lab}\t\t* {S.name}")
        S.st = {"ev": 0, "cur": 0}
    if sprites:
        head += spr_show(sprites)

    W_FAST = animcommon.TIME_WEIGHTS[-1]
    body = []
    ticks = sorted({t for L in list(layers) + list(sprites) for t, _ in L.events} | {t for S in sounds for t in S.ticks}
                   | set(boundaries))  # 周の区切りも（コマが 1 枚だけで切り替えが無いときのため）
    dropped, late, splits, hits = [], [], 0, 0
    n_sound = {S.key: 0 for S in sounds}
    expected = [(0, {L.name: 0 for L in list(layers) + list(sprites)})]  # (時刻, 各層のコマ)
    marks = [(0, 0, snapshot(0))] if boundaries else []  # (時刻, body の行数, 状態)
    prev_t = 0
    carry = KEY_US * slow if key_check else 0.0  # 前の切り替えの直後に実行した命令の時間（次の間で使ってしまう分）
    for e in ticks:
        cap = (e - prev_t) * TICK_US * animcommon.BUDGET_RATIO - carry
        used = 0.0
        blocked = set()  # この間ではもう描けない層
        while True:
            # 各層の「次に描く切り替え」（描き終わっている・スクロールだけのものは飛ばす）のうち、締め切りの早いものから
            best = None
            for i, L in enumerate(layers):
                if L.name in blocked:
                    continue
                st = L.st
                j = st["ev"]
                # 先回りは入れ物の数まで（それより先は予約しない。予約の数が周ごとに変わると永久ループにできない）
                while (j < len(L.events) and j - st["ev"] < len(L.slots) and assign(L, j)
                       and st["plan"][j]["done"]):
                    j += 1
                if j >= len(L.events) or j - st["ev"] >= len(L.slots) or j not in st["plan"]:
                    continue
                key = (L.events[j][0], i)
                if best is None or key < best[0]:
                    best = (key, L, j)
            if best is None:
                break
            (dl, _), L, j = best
            st = L.st
            p = st["plan"][j]
            k = L.events[j][1]
            s = p["slot"]
            # 今の締め切りのコマが、締め切りまでの時間を全部使っても描き切れないなら、描き始める前に飛ばす（時間を無駄にしない）
            if j == st["ev"] and drop and j + 1 < len(L.events):
                if L.fixed:
                    need = sum(c[3] for c in rest_chunks(L, k, p, st["content"][s]))
                else:
                    need = sum(segments(L, k, p["r"], st["content"][s], W_FAST)[1])
                window = (dl - prev_t) * TICK_US * animcommon.BUDGET_RATIO - used
                if need > window:
                    dropped.append((L.name, k, dl))
                    drop_plan(L, j)
                    st["ev"] += 1
                    continue
            L.cur_k = k
            if L.fixed:
                pl = plan_draw_fixed(L, k, p, st["content"][s], cap - used)
            else:
                pl = plan_draw(L, k, p["r"], st["content"][s], cap - used)
            if pl is None:
                blocked.add(L.name)
                continue
            segs, t, finished = pl
            st["holds"][s] = None
            if L.fixed:
                body += emit_fixed(L, s, segs)
                p["r"] += apply_fixed(L, s, segs)
            else:
                body += emit(L, s, segs)
                p["r"] += apply(L, s, k, segs)
            used += t
            if p["r"] >= L.units:
                p["done"] = True
                st["holds"][s] = k
            if not finished:
                splits += 1
                blocked.add(L.name)
        # 締め切りが今の層で、描き終わっていないもの
        for L in layers:
            st = L.st
            j = st["ev"]
            if j >= len(L.events) or L.events[j][0] != e:
                continue
            assign(L, j)
            p = st["plan"][j]
            if p["done"]:
                continue
            k = L.events[j][1]
            L.cur_k = k
            if drop and j + 1 < len(L.events):
                dropped.append((L.name, k, e))  # 飛ばす（描きかけの入れ物は「中身なし」になり、次に使うときは描き直す）
                drop_plan(L, j)
                st["ev"] += 1
                continue
            s = p["slot"]
            st["holds"][s] = None
            if L.fixed:  # 遅れても描き切る
                segs = rest_chunks(L, k, p, st["content"][s])
                body += emit_fixed(L, s, segs)
                p["r"] += apply_fixed(L, s, segs)
            else:
                segs, t = draw_all(L, k, p["r"], st["content"][s])
                body += emit(L, s, segs)
                p["r"] += apply(L, s, k, segs)
            p["done"] = True
            st["holds"][s] = k
            late.append((L.name, k, e))
        body.append(f"\tTMWA\t{e - prev_t}")
        flips = {}
        for L in layers:
            st = L.st
            j = st["ev"]
            if j < len(L.events) and L.events[j][0] == e and j in st["plan"] and st["plan"][j]["done"]:
                p = st["plan"].pop(j)
                k = L.events[j][1]
                s = p["slot"]
                assert holds_image(L, s, k)
                if p["hit"]:
                    hits += 1
                if s != st["shown"]:
                    x, y = L.slots[s]
                    if L.bg:
                        body.append(f"\tMOVW\t{x},${BG_SCROLL[L.plane]:06X}\t\t* {L.name} の表示を切り替え")
                    else:
                        body.append(f"\tSCL{PLANES[L.plane]}\t{x},{y}")
                st["shown"] = s
                st["ev"] += 1
                flips[L.name] = k
        if any(S.st["ev"] < len(S.events) and S.events[S.st["ev"]][0] == e for S in sprites):
            for S in sprites:  # スプライトは描画先が無いので、切り替えの瞬間に表示し直す（SPOF で全部消えるので全層）
                if S.st["ev"] < len(S.events) and S.events[S.st["ev"]][0] == e:
                    S.st["cur"] = S.events[S.st["ev"]][1]
                    S.st["ev"] += 1
                    flips[S.name] = S.st["cur"]
            body += spr_show(sprites)
        if flips:
            cur = dict(expected[-1][1])
            cur.update(flips)
            expected.append((e, cur))
        carry = KEY_US * slow if key_check else 0.0
        carry += sum(MOVE_US * slow for ln in body[-len(layers) - 1:] if ln.startswith("\tMOVW") and "表示を切り替え" in ln)
        if any(f in flips for f in [S.name for S in sprites]):
            carry += SPOF_US * slow_io + sum(7 * S.frame_chars[S.st["cur"]] for S in sprites) * slow_io
        for S in sounds:  # 音。周を数えるときも、鳴らすかもしれないので時間は必ず見込む
            if e in S.ticks:  # PCMP は pantime.txt の最大 2.4ms、Z-MUSIC の命令は pansim.ZM_US（実測。一部は仮の値）
                carry += S.us * slow
                body += S.code(n_sound[S.key]) if counted else list(S.play)
                n_sound[S.key] += 1
        if e in boundaries:
            marks.append((e, len(body), snapshot(e)))
        prev_t = e
    tail = [f"\tTMWA\t{end - prev_t}\t\t\t* 最後の表示時間"] if not boundaries else []
    info = {"dropped": dropped, "late": late, "splits": splits, "hits": hits, "marks": marks}
    return head, body, tail, order, expected, info


def spr_show(sprites):
    """スプライトを全部消して、各層の今のコマを表示する命令（後の層ほど手前）"""
    lines = ["\tSPOF"]
    for S in sprites:
        lab = S.frame_label[S.st["cur"]]
        if lab:
            lines.append(f"\tSPON\t{lab}\t\t* {S.name} {S.st['cur']}")
    return lines


def compose(layers, state, pal_words, tpal_words=None, sprites=(), order=DEFAULT_ORDER, g1_front=False, bgs=()):
    """予定の画面。重なり順は order（手前から sprite／text／graphic）、グラフィックの中は G0 が手前（g1_front なら G1）。
    スプライトの層の中は BG1 → BG0 → スプライト の順に手前。色0 は透明"""
    by = {PLANES[L.plane]: L.idx[state[L.name]] for L in layers if not (L.sprite or L.bg)}
    g0 = by.get(0, np.zeros((256, 256), np.uint8))
    g1 = by.get(1, np.zeros((256, 256), np.uint8))
    front, back = (g1, g0) if g1_front else (g0, g1)
    gidx = np.where(front != 0, front, back)
    groups = {"graphic": (pal_words[gidx], gidx != 0)}
    if "T" in by:
        t = by["T"]
        groups["text"] = (tpal_words[t], t != 0)
    sw = np.zeros((256, 256), np.uint16)
    sm = np.zeros((256, 256), bool)
    for B in sorted(bgs, key=lambda B: B.plane, reverse=True):  # bg1 が奥
        img, pw = B.bgimg[state[B.name]]
        sw = np.where(img != 0, pw, sw)
        sm |= img != 0
    for S in sprites:
        img = S.sprimg[state[S.name]]
        sw = np.where(img != 0, S.pal_words[img], sw)
        sm |= img != 0
    groups["sprite"] = (sw, sm)
    w = np.zeros((256, 256), np.uint16)
    for g in reversed(order):  # 奥から
        if g in groups:
            lw, lm = groups[g]
            w = np.where(lm, lw, w)
    return (np.stack([(w >> 6) & 31, (w >> 11) & 31, (w >> 1) & 31], -1) * 255 // 31).astype(np.uint8)


def bg_row_writes(want, have):
    """BG のマップ 1 行（32 ワード）で、have と違う所を書く命令の列 [(列, 値, 2 か 4)]。隣り合う 2 つは MOVL でまとめる"""
    out = []
    c = 0
    while c < 32:
        if want[c] == have[c]:
            c += 1
            continue
        if c + 1 < 32 and c % 2 == 0 and want[c + 1] != have[c + 1]:
            out.append((c, (int(want[c]) << 16) | int(want[c + 1]), 4))
            c += 2
        else:
            out.append((c, int(want[c]), 2))
            c += 1
    return out


def key_check(exit_key):
    """待ち（TMWA）の後に入れるキーの確認（押されていたら quit へ）"""
    if exit_key == "none":
        return []
    if exit_key == "any":
        return ["\tRTOK\t\t\t\t* キーが押されていれば終わる", "\tIFNE\t0,quit"]
    return [f"\tIKEY\t${EXIT_KEYS[exit_key]:02X},quit\t\t* {exit_key} キーで終わる"]


def with_key_checks(lines, exit_key):
    out = []
    for ln in lines:
        out.append(ln)
        if ln.startswith("\tTMWA") or ln.startswith("\tVWAIT\t"):
            out += key_check(exit_key)
    return out


SCENE_KEYS = {"name", "clock", "loops", "loop", "exit_key", "diff", "dither", "dither_strength", "stabilize",
              "audio", "audio_start", "audio_duration", "gain", "audio_offset", "audio_every", "audio_loop",
              "no_drop", "timelog", "order", "graphic_order", "aspect", "pixel_aspect", "fit",
              "transparent", "transparent_tolerance", "sim", "buffers", "out", "wait", "fixed_cels",
              "adjust_every", "adjust_frames", "fm", "fm_offset", "fm_every", "se", "layer"}
SE_KEYS = {"src", "offset", "every", "track"}
LAYER_KEYS = {"name", "plane", "src", "start", "duration", "base", "fps", "loop_ratio", "first", "count",
              "sequence", "hold", "aspect", "pixel_aspect", "fit", "transparent", "transparent_tolerance", "diff",
              "buffers", "fixed_cels"}


def validate(a: dict, base_dir: Path):
    """設定の値を確かめる（書き間違い、型、範囲、ファイルがあるか）。おかしければ説明を付けて止める。
    値が None のものは「指定なし」（mkanim が渡す）として扱う。"""
    W = "設定"
    if not isinstance(a, dict):
        raise SystemExit("設定の形が違います")
    cli.check_keys(W, a, SCENE_KEYS, LAYER_KEYS - SCENE_KEYS, "層（[[layer]]）の中")
    name = a.get("name")
    if name is None:
        raise SystemExit("設定：name（出力名）を指定してください")
    if not (isinstance(name, str) and name.isascii() and name.isalnum() and len(name) <= 8):
        raise SystemExit(f"設定：name は英数字 8 文字以内にしてください（今は {name!r}）")
    clk.parse(a.get("clock"), W)
    cli.check_number(W, "loops", a.get("loops"), integer=True, minimum=1)
    cli.check_choice(W, "loop", a.get("loop"), ("forever",))
    cli.check_choice(W, "exit_key", a.get("exit_key"), ("any", "space", "return", "none"))
    for k in ("diff", "no_drop", "timelog", "audio_loop", "sim", "fixed_cels"):
        cli.check_bool(W, k, a.get(k))
    cli.check_choice(W, "dither", a.get("dither"), ("none", "fs", "ordered"))
    cli.check_choice(W, "buffers", a.get("buffers"), (2, 4))
    cli.check_choice(W, "wait", a.get("wait"), ("tmwa", "vwait"))
    cli.check_number(W, "adjust_every", a.get("adjust_every"), above=0)
    cli.check_number(W, "adjust_frames", a.get("adjust_frames"), integer=True)
    if (a.get("adjust_every") is None) != (a.get("adjust_frames") is None):
        raise SystemExit("設定：adjust_every（何秒ごと）と adjust_frames（何カウント足すか）は 2 つ一緒に書いてください")
    if a.get("adjust_every") is not None and (a.get("wait") or "vwait") != "vwait":
        raise SystemExit("設定：adjust_every／adjust_frames は wait = \"vwait\"（既定）のときだけ使えます")
    if a.get("adjust_frames") == 0:
        raise SystemExit("設定：adjust_frames は 0 以外（負＝早める、正＝遅らせる）")
    if a.get("out") is not None and not (isinstance(a["out"], str) and a["out"]):
        raise SystemExit(f"設定：out は出力先のフォルダ名を文字列で書いてください（今は {a['out']!r}）")
    cli.check_number(W, "dither_strength", a.get("dither_strength"), minimum=0)
    cli.check_number(W, "stabilize", a.get("stabilize"), minimum=0)
    if a.get("audio") is not None:
        if not isinstance(a["audio"], str):
            raise SystemExit(f"設定：audio は音のファイル名を文字列で書いてください（今は {a['audio']!r}）")
        ap = Path(a["audio"])
        cli.need_file(ap if ap.is_absolute() else base_dir / ap, "音のファイル（audio）")
    cli.check_number(W, "audio_start", a.get("audio_start"), minimum=0)
    cli.check_number(W, "audio_duration", a.get("audio_duration"), above=0)
    cli.check_number(W, "gain", a.get("gain"))
    cli.check_number(W, "audio_offset", a.get("audio_offset"))
    cli.check_number(W, "audio_every", a.get("audio_every"), integer=True, minimum=0)
    if a.get("fm") is not None:
        if not isinstance(a["fm"], str):
            raise SystemExit(f"設定：fm は曲のファイル名（.zms／.opm／.zmd）を文字列で書いてください（今は {a['fm']!r}）")
        fp = Path(a["fm"])
        cli.need_file(fp if fp.is_absolute() else base_dir / fp, "FM 音源の曲（fm）")
    cli.check_number(W, "fm_offset", a.get("fm_offset"), minimum=0)
    cli.check_number(W, "fm_every", a.get("fm_every"), integer=True, minimum=0)
    ses = a.get("se")
    if ses is not None:
        if not isinstance(ses, list) or not all(isinstance(s, dict) for s in ses):
            raise SystemExit("設定：se は [[se]] の形で書いてください")
        if len(ses) > 9:
            raise SystemExit(f"設定：効果音（[[se]]）は 9 個までにしてください（今は {len(ses)} 個）")
        for i, s in enumerate(ses, 1):
            WS = f"効果音（{i} 番目の [[se]]）"
            cli.check_keys(WS, s, SE_KEYS, set(), "")
            if not isinstance(s.get("src"), str) or not s.get("src"):
                raise SystemExit(f"{WS}：src に効果音のファイル名（.zms／.opm／.zmd）を書いてください")
            sp = Path(s["src"])
            cli.need_file(sp if sp.is_absolute() else base_dir / sp, f"{WS} の src")
            cli.check_number(WS, "offset", s.get("offset"), minimum=0)
            cli.check_number(WS, "every", s.get("every"), integer=True, minimum=0)
            cli.check_number(WS, "track", s.get("track"), integer=True, minimum=1)
            if s.get("track") is not None and s["track"] > 32:
                raise SystemExit(f"{WS}：track は 1〜32 にしてください（今は {s['track']}）")
    for k, allowed in (("order", DEFAULT_ORDER), ("graphic_order", ["g0", "g1"])):
        v = a.get(k)
        if v is not None and (not isinstance(v, list) or sorted(map(str, v)) != sorted(allowed)):
            raise SystemExit(f"設定：{k} は {allowed} を並べ替えたリストで書いてください（手前から。今は {v!r}）")
    check_shape(W, a)
    layers = a.get("layer")
    if not layers:
        raise SystemExit("設定：層（[[layer]]）が 1 つもありません")
    if not isinstance(layers, list) or not all(isinstance(c, dict) for c in layers):
        raise SystemExit("設定：layer は [[layer]] の形で書いてください")
    names = []
    for i, c in enumerate(layers, 1):
        W = f"層 {c.get('name', f'{i} 番目')}"
        cli.check_keys(W, c, LAYER_KEYS, SCENE_KEYS - LAYER_KEYS, "全体（[[layer]] より前）")
        for k in ("name", "src"):
            if not isinstance(c.get(k), str) or not c.get(k):
                raise SystemExit(f"{W}：{k} を文字列で指定してください")
        names.append(c["name"])
        cli.check_choice(W, "plane", c.get("plane"), tuple(PLANES))
        src = Path(c["src"])
        src = src if src.is_absolute() else base_dir / src
        if not src.exists():
            raise SystemExit(f"{W}：src（PNG のフォルダか動画）が見つかりません：{src}")
        cli.check_number(W, "start", c.get("start"), minimum=0)
        cli.check_number(W, "duration", c.get("duration"), above=0)
        cli.check_bool(W, "base", c.get("base"))
        cli.check_bool(W, "diff", c.get("diff"))
        cli.check_choice(W, "buffers", c.get("buffers"), (2, 4))
        cli.check_bool(W, "fixed_cels", c.get("fixed_cels"))
        cli.check_number(W, "fps", c.get("fps"), above=0, maximum=60)
        cli.check_number(W, "loop_ratio", c.get("loop_ratio"), above=0)
        cli.check_number(W, "first", c.get("first"), integer=True, minimum=0)
        cli.check_number(W, "count", c.get("count"), integer=True, minimum=1)
        if c.get("sequence") is not None and not isinstance(c["sequence"], (str, list)):
            raise SystemExit(f"{W}：sequence は文字列かリストで書いてください（今は {c['sequence']!r}）")
        if c.get("hold") is not None and not isinstance(c["hold"], (str, dict)):
            raise SystemExit(f"{W}：hold は文字列か {{ \"5\" = 3 }} の形で書いてください（今は {c['hold']!r}）")
        check_shape(W, c)
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise SystemExit(f"層の name が重なっています：{', '.join(dup)}")


def check_shape(W, d):
    """aspect／pixel_aspect／fit／transparent／transparent_tolerance（全体と層で共通）"""
    if d.get("aspect") is not None and not isinstance(d["aspect"], bool):
        raise SystemExit(f"{W}：aspect は true か false で書いてください（今は {d['aspect']!r}）")
    cli.check_number(W, "pixel_aspect", d.get("pixel_aspect"), above=0)
    cli.check_choice(W, "fit", d.get("fit"), animcommon.FITS)
    if d.get("transparent") is not None and not isinstance(d["transparent"], (str, list, bool)):
        raise SystemExit(f"{W}：transparent は \"#FF00FF\" のような文字列で書いてください（今は {d['transparent']!r}）")
    animcommon.parse_key_colors(d.get("transparent"))
    cli.check_number(W, "transparent_tolerance", d.get("transparent_tolerance"), integer=True, minimum=0, maximum=255)


def output_dir(a, base_dir, name):
    """出力先のフォルダを決めて作る。前にこのツールが作った物（<名前>.json）が無いのに、
    消すことになるファイル（cNNN.cel／sNNN.spr）があるフォルダは使わない（ほかの物を消さないため）"""
    if a.get("out"):
        out = Path(a["out"])
        out = (out if out.is_absolute() else base_dir / out).resolve()
    else:
        out = ROOT / "x68" / "anim" / name
    if out.exists() and not out.is_dir():
        raise SystemExit(f"出力先がフォルダではありません：{out}")
    if out.is_dir() and not (out / f"{name}.json").exists():
        import re
        mine = [f.name for f in out.iterdir() if re.fullmatch(r"[cs]\d{3}\.(cel|spr)", f.name)]
        if mine:
            raise SystemExit(f"出力先 {out} に、このツールが作ったものでないかもしれないファイル（{mine[0]} など）があります。"
                             "別のフォルダを指定してください")
    out.mkdir(parents=True, exist_ok=True)
    return out


def timelog_path(out, name):
    """--timelog の time.txt の場所（panic.x から見た名前）。x68 の中なら H: の一番上からの相対、外なら実行したフォルダ"""
    try:
        rel = out.resolve().relative_to((ROOT / "x68").resolve())
        return "\\".join(rel.parts + ("time.txt",))
    except ValueError:
        return f"{name}.txt"


def build(a: dict, base_dir: Path, stop=False, src_desc="", sim=None):
    """設定（dict）から .pan を作る。mkanim.py もこれを呼ぶ。
    sim：pansim で再生時間と画面を確かめるか（None なら設定の sim、既定 false）"""
    validate(a, base_dir)
    name = a["name"]
    clock = clk.parse(a.get("clock"))
    print(f"対象機：{clk.describe(clock)}")
    loops = int(a.get("loops") or 1)
    forever = a.get("loop") == "forever"
    exit_key = a.get("exit_key") or "any"
    if exit_key not in ("any", "none", *EXIT_KEYS):
        raise SystemExit(f"exit_key は any／space／return／none（{exit_key}）")
    out = output_dir(a, base_dir, name)
    for f in list(out.glob("c*.cel")) + list(out.glob("s*.spr")):
        f.unlink()
    aspect = animcommon.pixel_aspect(a.get("aspect", False), a.get("pixel_aspect"))
    key = animcommon.parse_key_colors(a.get("transparent"))
    layers = [Layer(c, base_dir, out, aspect, a.get("fit"), key, int(a.get("transparent_tolerance", 0))) for c in a["layer"]]
    planes_used = [L.plane for L in layers if not L.sprite]
    if len(set(planes_used)) != len(planes_used):
        raise SystemExit("1 つの面（g0／g1／text）に置ける層は 1 つです（スプライトは何層でも可）")

    # パレット：グラフィック（G0・G1 共通、黒以外 254 色）、テキスト（16 色）、スプライト（層ごとに 16 色）は別
    g_layers = [L for L in layers if not L.text and not L.sprite and not L.bg]
    t_layers = [L for L in layers if L.text]
    s_layers = [L for L in layers if L.sprite]
    b_layers = [L for L in layers if L.bg]
    # 重なり順：order（手前から sprite／text／graphic。BG はスプライトの層に入る）、graphic_order（g0／g1 の手前・奥）
    layer_order = list(a.get("order", DEFAULT_ORDER))
    if sorted(layer_order) != sorted(DEFAULT_ORDER):
        raise SystemExit(f"order は sprite／text／graphic の並び（手前から）です：{layer_order}")
    g_order = list(a.get("graphic_order", ["g0", "g1"]))
    if sorted(g_order) != ["g0", "g1"]:
        raise SystemExit(f"graphic_order は g0／g1 の並び（手前から）です：{g_order}")
    g1_front = g_order[0] == "g1"
    prio = (layer_order.index("graphic") | (layer_order.index("text") << 2) | (layer_order.index("sprite") << 4)) << 8
    prio |= 0x4E if g1_front else 0xE4  # 256 色モードのページの順（$E4＝G0 が手前、$4E＝G1 が手前）
    pal = a_enc.Palette()
    tpal = a_enc.Palette()
    q = (a.get("dither", "none"), a.get("dither_strength", 24.0), a.get("stabilize", 0))
    if g_layers:
        pal_img = make_palette(g_layers)
        for L in g_layers:
            quantize_layer(L, pal_img, pal, *q)
    if t_layers:
        tpal_img = make_palette(t_layers, ncolors=14)
        for L in t_layers:
            quantize_layer(L, tpal_img, tpal, *q)
        if tpal.last > 15:
            raise SystemExit(f"テキスト面の色が 16 を超えました（{tpal.last + 1}）")
    if len(s_layers) + len(b_layers) > 15:
        raise SystemExit("スプライトと BG の層は合わせて 15 まで（パレット 1〜15）")
    pcg_total = 0
    sprite_cels = []
    for no, S in enumerate(s_layers, start=len(b_layers) + 1):
        S.palno = no
        S.spal = a_enc.Palette()
        quantize_layer(S, make_palette([S], ncolors=14), S.spal, *q)
        if S.spal.last > 15:
            raise SystemExit(f"スプライト {S.name} の色が 16 を超えました")
        S.frame_label, S.labels_defined, S.sprimg = [], [], []
        seen = {}
        for idx in S.idx:
            c = spr_enc.encode(idx)
            S.sprimg.append(spr_enc.decode(c) if c else np.zeros((256, 256), np.uint8))
            if c is None:
                S.frame_label.append(None)
                continue
            if c not in seen:  # SPCG がセルの中にパレットと PCG 番号を書き込むので、層ごとに別のセルにする
                lab = f"s{len(sprite_cels):03d}"
                seen[c] = lab
                sprite_cels.append((lab, c))
                S.labels_defined.append(lab)
                pcg_total += spr_enc.header(c)[0]
            S.frame_label.append(seen[c])
        pw = np.array(S.spal.colors + [0] * (16 - len(S.spal.colors)), np.uint16)
        pw[0] = 0
        pw[1] |= 1
        S.pal_words = pw
    # BG：層ごとに 16 色のパレット（番号 1〜）。8x8 のタイルに分け、同じタイルは 1 つにまとめる（タイル 0 は全部透明）
    tiles = {bytes(32): 0}
    for no, B in enumerate(b_layers, start=1):
        B.palno = no
        B.spal = a_enc.Palette()
        quantize_layer(B, make_palette([B], ncolors=14), B.spal, *q)
        if B.spal.last > 15:
            raise SystemExit(f"BG {B.name} の色が 16 を超えました")
        pw = np.array(B.spal.colors + [0] * (16 - len(B.spal.colors)), np.uint16)
        pw[0] = 0
        pw[1] |= 1
        B.pal_words = pw
        B.maps, B.bgimg = [], []
        for idx in B.idx:
            mp = np.zeros((32, 32), np.int64)
            for ty in range(32):
                for tx in range(32):
                    t = idx[ty * 8:ty * 8 + 8, tx * 8:tx * 8 + 8]
                    b = bytes(((t[:, 0::2] << 4) | t[:, 1::2]).astype(np.uint8).reshape(-1))
                    if b not in tiles:
                        tiles[b] = len(tiles)
                    tid = tiles[b]
                    mp[ty, tx] = (B.palno << 8) | tid if tid else 0
            B.maps.append(mp)
            B.bgimg.append((idx, pw[idx]))
    if len(tiles) > 256:
        raise SystemExit(f"BG のタイルが {len(tiles)} 種類（8x8 で 256 まで）。絵を単純にするか、コマを減らしてください")
    bg_pcg = (len(tiles) + 3) // 4 if b_layers else 0  # 16x16 の PCG にして 4 個ずつ（$EB8000 から）
    # BG のマップは PCG の後ろ半分と同じメモリ：1 面なら $EBE000（PCG 192〜255 が使えない）、2 面なら $EBC000 も（128〜）
    if len(b_layers) == 1:
        b_layers[0].map_area = 1
    else:
        for B in b_layers:
            B.map_area = 0 if B.plane == "bg0" else 1
    for B in b_layers:
        B.map_base = 0xEBC000 + 0x2000 * B.map_area
    pcg_limit = 256 - 64 * len(b_layers)
    if pcg_total + bg_pcg > pcg_limit:
        raise SystemExit(f"PCG（16x16）が {bg_pcg}（BG のタイル）＋ {pcg_total}（スプライト）＝ {bg_pcg + pcg_total} 個。"
                         f"BG {len(b_layers)} 面を使うときは {pcg_limit} 個まで")
    spr_by_label = dict(sprite_cels)
    max_on = sum(max((spr_enc.header(spr_by_label[lb])[0] for lb in S.frame_label if lb), default=0) for S in s_layers)
    if max_on > 128:
        raise SystemExit(f"同時に表示するスプライトが最大 {max_on} 枚になります（128 まで）")

    # 音：先に読んで長さを知る。audio_offset [秒] だけ遅らせて鳴らす（負なら音の頭を削る）
    pcm = b""
    offset = float(a.get("audio_offset", 0.0))
    if a.get("audio"):
        ap = Path(a["audio"])
        ap = ap if ap.is_absolute() else base_dir / ap
        try:
            samples = adpcm.load_audio(ap, a.get("gain", 0.0), a.get("audio_start"), a.get("audio_duration"))
        except subprocess.CalledProcessError as e:
            samples = None
            err = (e.stderr or b"").decode("cp932", "replace").strip().splitlines()
            print(f"音声を読めませんでした（音の無い動画？）。音なしで作ります（{ap.name}"
                  + (f"：{err[-1]}" if err else "") + "）")
        if samples is not None and offset < 0:
            samples = samples[round(-offset * adpcm.RATE):]
            offset = 0.0
        if samples is not None and len(samples):
            pcm = adpcm.encode(samples)
            if len(pcm) % 2:
                pcm += b"\x88"
            (out / "pcm.dat").write_bytes(pcm)
    off_t = round(offset * VSYNC_HZ)
    pcm_len_t = (len(pcm) * 2 / adpcm.RATE) * VSYNC_HZ if pcm else 0

    # タイミング。永久ループで音（ADPCM・FM 音源の曲・効果音）があるときは、音ごとに周を数えて（カウンタ <名前>_cnt）
    # every 周ごとに鳴らす。ループの本体は音の間隔と関係なく、状態がくり返す最短の周の数にできる（音のために何十周も並べなくてよい）。
    base_end = plan_timeline(layers, loops, 0)  # 1 周の長さを知るため
    end = base_end
    sounds = []
    if pcm:
        if "audio_every" in a:
            ev = int(a["audio_every"])
        elif a.get("audio_loop", True) is False:
            ev = 0
        else:  # 音が鳴り終わるまでの周の数（音の途中で鳴らし直さない）
            ev = int(max(1, -(-(off_t + pcm_len_t) // base_end)))
        sounds.append(Sound("pcm", "pcs", ["	PCMP	pcm,pcm_end-pcm		* 音"], 2400, off_t, ev, end))
    zm_parts, zm_voices = [], []  # FM 音源（Z-MUSIC）の素材と、最初に登録する音色の表
    if a.get("fm"):
        fp = Path(a["fm"])
        fp = fp if fp.is_absolute() else base_dir / fp
        zm_parts += mml2zmd.convert(fp, out, "fm", se=False)
        sounds.append(Sound("fm", "fms", ["	ZMPL	fm			* FM 音源の曲を頭から鳴らす（鳴っていれば止めてから）"],
                            pansim.ZM_US[b"PTZP"], round(float(a.get("fm_offset", 0.0)) * VSYNC_HZ),
                            int(a.get("fm_every", 0)), end))
    for i, s in enumerate(a.get("se") or []):
        sp = Path(s["src"])
        sp = sp if sp.is_absolute() else base_dir / sp
        lab = f"se{i}"
        zse, zmv, chs = mml2zmd.to_se(mml2zmd.load(sp), sp)
        (out / f"{lab}.zse").write_bytes(zse)
        zm_parts.append((lab, f"{lab}.zse"))
        if zmv:
            (out / f"{lab}v.zmv").write_bytes(zmv)
            zm_parts.append((f"{lab}v", f"{lab}v.zmv"))
            zm_voices.append(f"{lab}v")
        track = int(s.get("track") or chs[0] + 1)
        print(f"効果音 {lab}：{sp.name}（トラック {len(chs)} 本：{' '.join(mml2zmd.channel_name(c) for c in chs)}）を"
              f"曲のトラック {track} から鳴らす")
        sounds.append(Sound(lab, f"s{i}s", [f"	ZSEP	{lab},{track}		* FM 音源の効果音 {sp.name}"],
                            pansim.ZM_US[b"PTZE"], round(float(s.get("offset", 0.0)) * VSYNC_HZ),
                            int(s.get("every", 1)), end))
    for S in sounds:
        if S.key == "pcm":
            msg = f"音 {len(pcm) * 2 / adpcm.RATE:.2f} 秒、{S.off_t / VSYNC_HZ:.2f} 秒後に鳴らす"
        else:
            msg = f"{'FM 音源の曲' if S.key == 'fm' else '効果音 ' + S.key}：{S.off_t / VSYNC_HZ:.2f} 秒後に鳴らす"
        if forever:
            msg += "（最初に 1 回だけ）" if S.once else f"、{S.every} 周（{end * S.every * 18.03 / 1000:.2f} 秒）ごとに鳴らし直す"
            if S.key == "pcm" and not S.once and off_t + pcm_len_t > end * S.every + 1:
                msg += "  ← 鳴り終わる前に鳴らし直すので、音の終わりが切れます"
        elif S.off_t >= end:
            msg += "  ← アニメが終わった後なので鳴りません"
        print(msg)
        if S.key == "fm" and (S.off_t > 0 or (forever and not S.once)):
            print("  注意：曲を鳴らす命令（ZMPL）は、Z-MUSIC を zmsc -n（初期化なし）で常駐させたときは一瞬ですが、"
                  "ふつうの常駐では 10MHz で約 0.12 秒かかり、その間は描けません（その後のコマが飛ぶことがあります）。"
                  "見積もりは zmsc -n の値です")
    d_layers = [L for L in layers if not L.sprite]  # 描画先のある層（G0／G1／テキスト／BG）
    for S in s_layers:  # 各コマのキャラ数（SPON の時間）
        S.frame_chars = [spr_enc.header(spr_by_label[lb])[0] if lb else 0 for lb in S.frame_label]

    for L in d_layers:  # 差分を使うか：層の diff、無ければ全体の diff
        L.diff = bool(L.cfg_diff if L.cfg_diff is not None else a.get("diff", False))
        # 区切りを決めたセル（グラフィックだけ）：層の fixed_cels、無ければ全体の fixed_cels（既定 true）
        L.fixed = (not L.text and not L.bg
                   and bool(L.cfg_fixed if L.cfg_fixed is not None else a.get("fixed_cels", True)))
    # 永久ループ：何周か作ってみて、周の区切りの状態がくり返す所を探す。見つからなければ周を増やして作り直す。
    # 最後の 1 周は「その先の予定が無い」ので選び方が変わる → 1 周余分に作って、比べる対象から外す。
    # 入れ物の数：設定の buffers。省略したら 4（XM6 で確認済み）。ただし永久ループで、4 では 6 周の中に
    # くり返しが見つからないとき（画像の数と入れ物の回り方の周期が合わない）は、2 で作り直す（2 の方が短い周期になりやすい）。
    F = FOREVER_MAX_CYCLES
    if a.get("buffers"):
        b = int(a["buffers"])
        tries = [(b, F), (b, 2 * F), (b, 4 * F)] if forever else [(b, 0)]
    else:
        tries = [(4, F), (2, F), (2, 2 * F), (2, 4 * F), (4, 2 * F), (4, 4 * F)] if forever else [(4, 0)]
    loop_from = loop_to = None
    for n_try, (buffers, cycles) in enumerate(tries):
        for L in d_layers:  # 入れ物（描画先）：グラフィックは buffers 個（層の buffers があればそちら）、テキスト・BG は 2 個
            nb = int(L.cfg_buffers) if L.cfg_buffers else buffers
            L.slots = POS4 if (nb == 4 and not L.text and not L.bg) else POS
        end = plan_timeline(layers, loops, cycles + 1 if forever else 0)
        boundaries = [k * end for k in range(1, cycles + 1)]  # 永久ループ：周ごとに状態を記録する
        for S in sounds:  # 鳴らす時刻（0 の分は呼び出し側が最初に置く）
            if not forever:
                S.ticks = {S.off_t} if 0 < S.off_t < end else set()
            elif S.once:  # 1 回だけ：鳴らす周にだけ置く（ほかの周の予算から鳴らす時間を引かない）
                S.ticks = {S.off_t} if 0 < S.off_t <= cycles * end else set()
            else:  # 毎周、同じ時刻に「鳴らすかどうか」を調べる
                S.ticks = {c * end + S.pos for c in range(cycles + 1) if 0 < c * end + S.pos <= cycles * end}
        head, body, tail, order, expected, info = schedule(d_layers, end, a, clock, s_layers, boundaries,
                                                           key_check=forever and exit_key != "none",
                                                           sounds=sounds, counted=forever)

        if forever:  # 区切りの状態が前の区切りと同じになった所から先がくり返し
            # コマ数が奇数だと、周ごとに表示している側（2 か所）が入れ替わるので、2 単位で元に戻ることもある
            marks = info["marks"]
            min_i = 1
            found = next(((j, i) for i in range(max(1, min_i), len(marks))
                          for j in range(i - 1, max(0, min_i - 1) - 1, -1) if marks[i][2] == marks[j][2]), None)
            if found:
                n_pre, i = found
                per = i - n_pre  # ループの本体は何周か
                loop_from, loop_to = marks[n_pre][1], marks[i][1]
            else:
                if n_try + 1 < len(tries):
                    nb, nc = tries[n_try + 1]
                    print(f"  入れ物 {buffers} つ・{cycles} 周ではくり返しが見つからないので、"
                          f"入れ物 {nb} つ・{nc} 周で作り直します")
                    continue
                raise SystemExit(f"{len(marks) - 1} 回くり返して作っても同じ状態にならず、永久ループにできません（描画が間に合っていない？）")
        break


    (out / "pal.dat").write_bytes(pal.to_bytes())
    parts = [["pal", "pal.dat"]]
    if t_layers:  # テキストのパレットは 34 バイト（先頭 .w ＋ 16 色）
        (out / "tpal.dat").write_bytes(tpal.to_bytes()[:34])
        parts.append(["tpal", "tpal.dat"])
    for S in s_layers:
        (out / f"spal{S.palno}.dat").write_bytes(S.spal.to_bytes()[:34])
        parts.append([f"spal{S.palno}", f"spal{S.palno}.dat"])
    for B in b_layers:
        (out / f"spal{B.palno}.dat").write_bytes(B.spal.to_bytes()[:34])
        parts.append([f"spal{B.palno}", f"spal{B.palno}.dat"])
    if b_layers:  # BG のタイルを 16x16 の PCG 4 個ずつにまとめたセル（SPCG で $EB8000 から定義する）
        tdata = bytearray(len(tiles) * 32)
        for b, i in tiles.items():
            tdata[i * 32:i * 32 + 32] = b
        tdata += bytes(bg_pcg * 128 - len(tdata))
        (out / "bgtile.spr").write_bytes(struct.pack(">7H", bg_pcg, 0, 0, 0, 0, 0, 0) + bytes(tdata))
        parts.append(["bgtile", "bgtile.spr"])
    for lab, data in sprite_cels:
        (out / f"{lab}.spr").write_bytes(data + (b"\x00" if len(data) % 2 else b""))
        parts.append([lab, f"{lab}.spr"])
    for lab, data in order:
        (out / f"{lab}.cel").write_bytes(data)
    parts += ([["pcm", "pcm.dat"]] if pcm else []) + [list(x) for x in zm_parts] + [[lab, f"{lab}.cel"] for lab, _ in order]
    # 一定時間ごとの補正（VWADJ）：予定の時刻が adj_every カウント進むごとに adj_delta カウント足す
    adj_every = round(float(a["adjust_every"]) * animcommon.VSYNC_HZ) if a.get("adjust_every") is not None else 0
    adj_delta = int(a.get("adjust_frames") or 0)
    if forever:  # 1 周の長さを整数カウントに丸めた分は、周ごとに積み重なる（音とずれる）。直すための補正を示す
        B = next(L for L in layers if L.base)
        exact = loops * B.total_w * animcommon.VSYNC_HZ / B.fps
        drift = end - exact  # 1 周あたり [カウント]。正なら絵が遅れる
        if abs(drift) > 1e-3:
            sec = end / abs(drift) / animcommon.VSYNC_HZ
            print(f"  1 周を {exact:.3f} → {end} カウントに丸めたので、絵は {sec:.1f} 秒ごとに 1 カウント"
                  f"{'遅れ' if drift > 0 else '進み'}ます（fps どおりにするなら adjust_every = {sec:.1f}、"
                  f"adjust_frames = {-1 if drift > 0 else 1}）")
    if adj_every:
        print(f"補正：{adj_every} カウント（{adj_every / animcommon.VSYNC_HZ:.2f} 秒）ごとに "
              f"{abs(adj_delta)} カウント{'早める' if adj_delta < 0 else '遅らせる'}")
    nominal = None if forever else round((end + adj_delta * (end // adj_every if adj_every else 0)) * 1.803)
    (out / f"{name}.json").write_text(json.dumps(
        {"name": name, "clock": clock, "nominal": nominal, "parts": parts, "scene": src_desc,
         "forever": forever, "cycle": end if forever else None},
        ensure_ascii=False, indent=1), encoding="utf-8")

    timelog = a.get("timelog", False)
    pcmp = []  # 頭で鳴らす音
    zm_pre = []  # 頭で鳴らす FM 音源の曲（ZMPL は常駐のしかたによっては重い（10MHz で約 118ms）ので、タイマーの基準より前に置く）
    for S in sounds:
        dst = zm_pre if (S.key == "fm" and S.off_t == 0) else pcmp
        if forever:  # 周のカウンタを用意し、最初の周の頭で鳴らすかを調べる
            dst += [f"\tSETR\t{S.c0}", f"\tWTRL\t{S.key}_cnt\t\t\t* {S.what}：最初に鳴らすのは何周目か"]
            dst += S.code("s") if S.pos == 0 else []
        elif S.off_t == 0:
            dst += list(S.play)
    zm = any(S.key != "pcm" for S in sounds)
    stop_snd = (["\tPCMS\t\t\t\t* 音を止める"] if pcm else []) + (["\tZMST\t\t\t\t* FM 音源を止める"] if zm else [])
    L_ = [f"* {name}.s : mkscene.py が自動生成（{', '.join(f'{L.name}={L.plane} {L.n}枚' for L in layers)}、"
          f"{'1 周 ' if forever else ''}{end} カウント）", "", "\t.include\tsch.h", "",
          "\tTMON",
          "\tRDRB\t$E82601\t\t\t* 準備の間は画面を消す（今の表示の設定をシステム変数に覚えておく）",
          "\tMOVB\t0,$E82601",
          "\tGPAL\tpal"]
    if t_layers:
        L_.append("\tTPAL\t0,tpal")
    for S in s_layers + b_layers:
        L_.append(f"\tTPAL\t{S.palno},spal{S.palno}")
    if prio != 0x06E4:
        L_.append(f"\tMOVW\t${prio:04X},$E82500\t\t* 重なり順（手前から {'＞'.join(layer_order)}、{'＞'.join(g_order)}）")
    if b_layers:
        ctrl = 0x0200  # 表示
        for B in b_layers:
            ctrl |= (0x01 | (B.map_area << 1)) if B.plane == "bg0" else (0x08 | (B.map_area << 4))
        L_ += ["\tSPIN\t\t\t\t* PCG の定義を最初から（BG のタイルを $EB8000 から置く）",
               "\tSPCG\t0,bgtile\t\t* BG のタイル",
               f"\tMOVW\t${ctrl:04X},$EB0808\t\t* BG の表示とマップの場所"]
    L_ += head
    for v in zm_voices:
        L_.append(f"\tZMVS\t{v}\t\t\t* 効果音の音色を登録する")
    if b_layers:
        L_.append("\tOR_R\t$40\t\t\t* BG／スプライトを表示（$E82601 の bit6）")
    L_.append("\tWTRB\t$E82601\t\t\t* 画面を元に戻す")
    L_ += zm_pre  # 頭で鳴らす曲（D7 を使うので、$E82601 を D7 から書き戻した後に置く）
    L_.append("\tTMWA\t1\t\t\t* タイマーの基準")
    vw = (a.get("wait") or "vwait") == "vwait"
    if vw:  # 待ちを VWAIT（予定の時刻で待つ）にする。遅れたコマの分を後の待ちで取り戻す
        L_.append(animcommon.VWAIT_INIT)
        if adj_every:
            L_.append(animcommon.vwadj_line(adj_every, adj_delta))
        conv = (lambda lines: [animcommon.vwait_line(ln.split("\t")[2], "最後の表示時間" if "最後" in ln else "")
                               if ln.startswith("\tTMWA\t") else ln for ln in lines])
        body, tail = conv(body), conv(tail)
    if forever:
        if timelog:
            L_.append("\tBSUB\ttl_t0")
        pre, loop_body = body[:loop_from], body[loop_from:loop_to]
        L_ += pcmp
        if n_pre:
            L_.append(f"* ---- 前置き（{n_pre} 周。1 回だけ）----")
            L_ += with_key_checks(pre, exit_key)
        L_ += [f"* ---- ループの本体（{per} 周。キーが押されるまでくり返す）----", "loop:"]
        L_ += with_key_checks(loop_body, exit_key)
        L_ += ["\tGOTO\tloop", "quit:"]
        L_ += stop_snd  # 音を止める（キーで終えたときは EXIT で終わるので自分で止める。ESC のとき ADPCM は panic.x が止める）
        if timelog:
            L_.append("\tBSUB\ttl_t1")
        L_ += ["\tDEND", "\tEXIT"]
        if sounds:
            L_ += ["", "\t.even"] + [f"{S.key}_cnt:\t.dc.l\t0\t\t* {S.what}を鳴らすまでの周の数（実行中に書き換える）"
                                     for S in sounds]
    else:
        L_ += pcmp
        if timelog:
            L_.append("\tBSUB\ttl_t0")
        L_ += body + tail
        L_ += stop_snd  # 音を止める（キーで終えたときは EXIT で終わるので自分で止める。ESC のとき ADPCM は panic.x が止める）
        if timelog:
            L_.append("\tBSUB\ttl_t1")
        L_ += ["\tDEND", "\tEXIT"]
    if vw:
        L_ = animcommon.with_vwait_head(L_) + animcommon.VWAIT_CODE.split("\n")
    if zm:
        L_ = animcommon.with_zmusic_head(L_) + animcommon.ZMUSIC_CODE.split("\n")
    if timelog:
        tlpath = timelog_path(out, name)
        L_ += animcommon.timelog_code(tlpath, nominal if nominal is not None else 0)
    L_ += ["", "* ---- 素材のラベル（buildPan.py が作る。この .include はソースの最後に置くこと）----",
           f"\t.include\t{name}_d.h", "", "\t.end", ""]
    animcommon.write_sjis(out / f"{name}.s", "\n".join(L_))

    total = sum(len(d) for _, d in order)
    print(f"層：{', '.join(f'{L.name}（{L.plane}、{L.n} 枚' + (f'を {len(L.steps)} 回表示' if len(L.steps) != L.n else '')
                            + f'、1 ループ {L.loop_len * 18.03 / 1000:.2f} 秒）' for L in layers)}")
    if forever:
        n_loop_flips = sum(1 for t, _ in expected if marks[n_pre][0] < t <= marks[n_pre + per][0])
        print(f"永久ループ：1 周 {end * 18.03 / 1000:.2f} 秒、前置き {n_pre} 周＋ループの本体 {per} 周"
              f"（切り替え {n_loop_flips} 回）、終わるキー：{exit_key}")
    else:
        print(f"シーン {end * 18.03 / 1000:.2f} 秒、切り替え {len(expected) - 1} 回")
    print(f"セル {len(order)} 個 {total} バイト、パレット {pal.last + 1} 色"
          + (f"、テキストのパレット {tpal.last + 1} 色" if t_layers else ""))
    if s_layers:
        print(f"  スプライト：{len(s_layers)} 層、パターン {pcg_total} キャラ（256 まで）、同時に最大 {max_on} 枚（128 まで）")
    if txt_enc.provisional_used:
        print("  注意：テキスト面の描画時間は仮の値で見積もっています")
    dropped, late, splits = info["dropped"], info["late"], info["splits"]
    if buffers == 4:
        print(f"  入れ物 4 つ（G0／G1 の 512x512 を全部使う）：描かずにスクロールだけで済んだ切り替え {info['hits']} 回")
    if forever:  # 前置き＋ループ 1 周ぶんだけ数える
        lim = marks[n_pre + per][0]
        dropped = [x for x in dropped if x[2] <= lim]
        late = [x for x in late if x[2] <= lim]
    # 層ごとに、予定の切り替えのうちどれだけ飛ばしたか・一度も表示されない画像があるかを調べて、目立つように知らせる
    t_from = marks[n_pre][0] if forever else 0
    t_to = lim if forever else end
    for L in d_layers:
        planned = sum(1 for t, _ in L.events if t_from < t <= t_to)
        n_drop = sum(1 for nm, _, t in info["dropped"] if nm == L.name and t_from < t <= t_to)
        shown = {s[L.name] for t, s in expected if t_from <= t <= t_to} | ({0} if t_from == 0 else set())
        never = [L.img_no[k] for k in range(L.n) if k not in shown]
        if planned and (n_drop * 10 >= planned * 3 or never):
            msg = (f"  警告：層 {L.name} は描画が間に合わず、予定の切り替え {planned} 回のうち {n_drop} 回を飛ばします"
                   f"（{L.n} 枚のうち表示されるのは {L.n - len(never)} 枚")
            if never:
                msg += f"。表示されない画像：{', '.join(map(str, never[:12]))}{' …' if len(never) > 12 else ''}"
            print(msg + "）")
            print(f"    → {clock} では、切り替えの間（この層は平均 {L.loop_len / max(1, len(L.steps)) * 18.03:.0f} ms ごと）に"
                  "ほかの層と合わせて描き切れません。この層をゆっくりにする（loop_ratio を大きく／fps を下げる）、"
                  "ほかの層の fps を下げる、絵を単純にする（diff、dither = \"none\"、stabilize）などで直ります")
    if dropped:
        print(f"  間に合わないので飛ばしたコマ {len(dropped)} 個：" +
              ", ".join(f"{n} {k}" for n, k, _ in dropped[:10]) + (" …" if len(dropped) > 10 else ""))
    if splits:
        print(f"  分割して描いた回数 {splits}（1 コマを何回かの待ちに分けて描く）")
    if late:
        print(f"  警告：遅れて描くコマ {len(late)} 個（処理落ち）")
    if stop:
        print(f"-> {out / (name + '.s')} まで作って止めました。続きは：pt buildPan {out / (name + '.s')}")
        return 0

    if sim is None:
        sim = bool(a.get("sim", False))
    pan, _ = panbuild.build_dir(out, clock, sim=sim)
    if not sim:
        print("pansim での確認はしていません（再生時間と画面を確かめるときは --sim を付けてください）")
        return 0
    # 検証：TMWA に入る時点の画面（＝各切り替えの後に見えている絵）の並びが、予定どおりの重ね合わせと一致するか
    if forever:  # 前置き＋ループ 2 周ぶん動かして比べる
        limit_tick = marks[n_pre + 2 * per][0] if n_pre + 2 * per < len(marks) else marks[-1][0]
        print(f"pansim の画面を予定の重ね合わせと比べます（キーは押されないものとして、前置き＋ループ 2 周＝"
              f"{(limit_tick + 1) * TICK_US / 1e6:.1f} 秒ぶん）")
        sim = pansim.simulate(pan, clock, keep_states=True, max_us=(limit_tick + 1) * TICK_US)
        exp_list = [s for t, s in expected if t <= limit_tick]
    else:
        print("pansim の画面を予定の重ね合わせと比べます")
        sim = pansim.simulate(pan, clock, keep_states=True)
        exp_list = [s for _, s in expected]
    pal_words = np.array(pal.colors + [0] * (256 - len(pal.colors)), np.uint16)
    pal_words[1] |= 1
    tpal_words = np.array(tpal.colors + [0] * (256 - len(tpal.colors)), np.uint16)[:16]
    tpal_words[0] = 0
    tpal_words[1] |= 1
    exp_imgs = pansim.dedup([compose(layers, s, pal_words, tpal_words, s_layers, layer_order, g1_front, b_layers)
                             for s in exp_list])
    got = pansim.dedup(sim.states)
    if forever:  # 打ち切りの境目のずれは許す
        n = max(1, min(len(got), len(exp_imgs)) - 1)  # 静止画なら 1 通り
        ok = min(len(got), len(exp_imgs)) >= 1 and all((g == e).all() for g, e in zip(got[:n], exp_imgs[:n]))
    else:
        ok = len(got) == len(exp_imgs) and all((g == e).all() for g, e in zip(got, exp_imgs))
    if not ok:
        bad = next((i for i, (g, e) in enumerate(zip(got, exp_imgs)) if (g != e).any()), min(len(got), len(exp_imgs)))
        raise SystemExit(f"検証エラー：pansim の画面が予定と違います（{bad} 番目。pansim {len(got)} 通り、予定 {len(exp_imgs)} 通り）")
    print(f"検証 OK：pansim の画面（{len(got)} 通り{'、ループ 2 周まで' if forever else ''}）が予定どおりの重ね合わせ")
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
    pos = cli.check_args(args, ["--stop-at-s", "--sim"], 1)
    if pos is None:
        print(__doc__, file=sys.stderr)
        return 1
    cfg_path = cli.need_file(pos[0], "設定ファイル")
    a = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
    if out:
        a["out"] = out
    return build(a, cfg_path.resolve().parent, "--stop-at-s" in argv, str(cfg_path.resolve()),
                 sim=True if "--sim" in argv else None)


if __name__ == "__main__":
    sys.exit(cli.run(main))

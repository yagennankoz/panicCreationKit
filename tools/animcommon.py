"""animcommon.py : mkanim.py と mkscene.py が共通で使うもの（減色、ディザ、時間方向の安定化、動画の切り出し、時刻の記録）"""
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

import adpcm

VSYNC_HZ = 1 / 0.01803  # TMWA 1 カウント = 18.03ms（XM6 で実測）
BUDGET_RATIO = 0.95  # 描画時間の見積もりを待ち時間の何割までに収めるか（見積もりの誤差は 0.5ms 程度、PCM 割り込みなどの余裕。
#   0.85 だと 10MHz の全面描き直し（約 67ms）が 4 カウント（72ms）に入らず飛ばされた。XM6 では 72ms で間に合っている）
PIXEL_ASPECT = 1.5  # 256x256 モードの 1 ドットの「横÷縦」（縦 2：横 3 の横長）。aspect 補正で使う
TIME_WEIGHTS = [0, 0.05, 0.2, 1, 5, 100]  # a_enc.encode の time_weight を小さい順に試す


def to5(a):
    """0〜255 → X68000 の 5 ビットに丸めて 0〜255 に戻す"""
    return ((a.astype(np.uint16) * 31 + 127) // 255 * 255 // 31).astype(np.uint8)


BAYER8 = np.array([[0, 32, 8, 40, 2, 34, 10, 42], [48, 16, 56, 24, 50, 18, 58, 26],
                   [12, 44, 4, 36, 14, 46, 6, 38], [60, 28, 52, 20, 62, 30, 54, 22],
                   [3, 35, 11, 43, 1, 33, 9, 41], [51, 19, 59, 27, 49, 17, 57, 25],
                   [15, 47, 7, 39, 13, 45, 5, 37], [63, 31, 55, 23, 61, 29, 53, 21]]) / 64.0


def frame_words(frame, pal_img, dither, strength=24.0):
    """1 コマを共通パレットの色にして、X68000 の色（GRB ワード）の配列にする
    dither: "none"／"fs"（Floyd-Steinberg。滑らかだが動きのある所以外の模様も毎コマ変わり、差分が効きにくい）／
            "ordered"（8x8 の決まった模様。止まっている所は毎コマ同じになるので差分が効く）"""
    a = np.asarray(frame).astype(np.float64)
    if dither == "ordered":
        th = np.tile(BAYER8, (32, 32))[..., None]
        a = np.clip(a + (th - 0.5) * strength, 0, 255)
    q = Image.fromarray(to5(a.astype(np.uint8))).quantize(
        palette=pal_img, dither=Image.Dither.FLOYDSTEINBERG if dither == "fs" else Image.Dither.NONE)
    rgb = np.asarray(q.convert("RGB")).astype(np.uint16)
    r, g, b = ((rgb[..., k] * 31 + 127) // 255 for k in range(3))
    return (g << 11) | (r << 6) | (b << 1)


def stabilize(idx, ref_idx, frame, pal, threshold):
    """時間方向の安定化：元の色が、前のコマの同じドットの色（パレット色）と threshold 以内なら、前のコマの番号を使う。
    実写などの細かいゆらぎで、止まっている所まで毎コマ書き換わるのを防ぐ（差分が効くようになる）"""
    words = np.array(pal.colors + [0] * (256 - len(pal.colors)), np.uint16)
    w = words[ref_idx]
    ref_rgb = np.stack([(w >> 6) & 31, (w >> 11) & 31, (w >> 1) & 31], -1).astype(np.int16) * 255 // 31
    diff = np.abs(np.asarray(frame).astype(np.int16) - ref_rgb).max(-1)
    keep = (diff <= threshold) & (ref_idx != 0)  # 透明（番号0）は引き継がない
    out = idx.copy()
    out[keep] = ref_idx[keep]
    return out


def pixel_aspect(on, ratio=None):
    """aspect の設定（true／false）と pixel_aspect（横÷縦）から、横を縮める比を返す（補正しないなら None）"""
    if not on:
        return None
    r = float(ratio if ratio is not None else PIXEL_ASPECT)
    if r <= 0:
        raise SystemExit(f"pixel_aspect は正の数（{ratio}）")
    return None if r == 1 else r


FITS = ("crop", "pad")


def fit_mode(fit, aspect):
    """fit の設定（crop／pad）。省略時は aspect 補正ありなら pad、なしなら crop（今までと同じ）"""
    fit = fit or ("pad" if aspect else "crop")
    if fit not in FITS:
        raise SystemExit(f"fit は crop／pad（{fit}）")
    return fit


def parse_key_colors(spec):
    """透明色の指定を [(r, g, b) または "corner"] にする。
    "#FF00FF"／"FF00FF"／"0xFF00FF"＝その色、"corner"（または "0,0"）＝各画像の左上 (0,0) の色（当時の方法）、
    "none"／false／空＝指定なし。";" 区切りかリストで複数指定できる（"0,0" にカンマがあるため）。"""
    if spec is None or spec is False or spec == "":
        return []
    items = spec if isinstance(spec, (list, tuple)) else [s for s in str(spec).replace(" ", "").split(";")]
    out = []
    for it in items:
        it = str(it).strip().lower()
        if it in ("", "none", "false"):
            continue
        if it in ("corner", "0,0", "(0,0)"):
            out.append("corner")
            continue
        h = it[1:] if it.startswith("#") else it[2:] if it.startswith("0x") else it
        if len(h) != 6 or any(c not in "0123456789abcdef" for c in h):
            raise SystemExit(f"透明色の指定が違います：{it}（\"#RRGGBB\" か \"corner\"）")
        out.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    return out


def key_transparent(im: Image.Image, colors, tolerance=0) -> Image.Image:
    """colors（parse_key_colors の結果）の色のドットを透明（アルファ 0）にする。tolerance は RGB 各 0〜255 の許す差"""
    if not colors:
        return im
    a = np.array(im.convert("RGBA"))
    rgb = a[..., :3].astype(np.int16)
    hit = np.zeros(a.shape[:2], bool)
    for c in colors:
        c = tuple(int(v) for v in a[0, 0, :3]) if c == "corner" else c
        hit |= (np.abs(rgb - np.array(c, np.int16)).max(axis=2) <= tolerance)
    a[hit, 3] = 0
    return Image.fromarray(a, "RGBA")


def fit_256(im: Image.Image, aspect=None, fit=None) -> Image.Image:
    """画像を 256x256 にする。
    aspect（1 ドットの横÷縦）を指定すると、先に横を 1/aspect に縮めて、X68000 の横長のドットで正しい形に見えるようにする。
    fit="crop"：縦横比を保って 256x256 を埋めるように拡大縮小し、はみ出た所を切る。
    fit="pad" ：縦横比を保って 256x256 に収まるように拡大縮小し、余白は透明（色番号 0）にする。"""
    fit = fit_mode(fit, aspect)
    w, h = im.size
    if aspect:
        w = max(1, round(w / aspect))
        im = im.resize((w, h), Image.LANCZOS)
    if fit == "pad":
        s = 256 / max(w, h)
        if s != 1:
            w, h = max(1, min(256, round(w * s))), max(1, min(256, round(h * s)))
            im = im.resize((w, h), Image.LANCZOS)
        canvas = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
        canvas.paste(im, ((256 - w) // 2, (256 - h) // 2))
        return canvas
    s = 256 / min(w, h)
    if s != 1:
        im = im.resize((max(256, round(w * s)), max(256, round(h * s))), Image.LANCZOS)
    w, h = im.size
    left, top = (w - 256) // 2, (h - 256) // 2
    return im.crop((left, top, left + 256, top + 256))


def write_sjis(path: Path, text: str):
    path.write_bytes(text.replace("\n", "\r\n").encode("cp932"))


def timelog_code(tlpath, expect):
    """時刻の記録（BSUB tl_t0／tl_t1）のルーチン：x68/lib/timelog.s を .include し、書くファイルの名前と EXPECT の値をラベルで渡す。
    EXIT の後、素材より前に置く行の列を返す。"""
    return ["", "* ---- 時刻の記録（x68/lib/timelog.s。docs/LIBRARY.md）----",
            f"tl_fn:\t.dc.b\t'{tlpath}',0\t\t* 書くファイル",
            f"tl_exp:\t.dc.b\t'{expect}',13,10\t\t* EXPECT= の後（予想の値。1/100 秒）",
            "tl_exp_end:", "\t.even", "\t.include\ttimelog.s"]


# ---- VWAIT：再生の頭からの「予定の時刻」で待つ（TMWA の代わり）----
# TMWA は前の TMWA を抜けてからの V-Sync を数えて待ち、遅れたときは「次の V-Sync まで待って 0 に戻す」ので、遅れは取り戻されない
# （遅い機械ほど再生が延びる）。VWAIT は panic.x の V-Sync のカウンタ（作業領域 $2C8(A6)、V-Sync の割り込みで +1。
# panic.x V1.38 の逆アセンブルで確認）を 0 に戻さずに積み上げ、予定の時刻（待ちの合計）になるまで待つ。
# すでに過ぎていたら次の V-Sync まで待つだけ（画面の乱れを防ぐ）で、遅れは予定の時刻に対して残るので、後の待ちが短くなって取り戻す。
# 待っている間も ESC の印（$2E0(A6)）を見て、立っていればすぐ戻る（panic.x は命令ごとに ESC を調べる）。
# 先頭の 'PTVI'／'PTVW' は pansim が見分けるための印。
# ルーチンの本体とマクロは x68/lib/vwait.s・vwait.h（panicCreationKitForWin のライブラリ。docs/LIBRARY.md）。
# buildPan.py が x68/lib/ のファイルを作業フォルダに写すので、.s からは .include するだけでよい。
VWAIT_HEAD = "\t.include\tvwait.h\t\t* VWAIT のマクロ（x68/lib/。docs/LIBRARY.md）"
VWAIT_INIT = "\tVWINIT\t\t\t\t* VWAIT の基準の時刻（ここから予定の時刻を数える）"
VWAIT_CODE = "\n* ---- VWAIT のルーチン（x68/lib/vwait.s。EXIT の後、素材より前に置く）----\n\t.include\tvwait.s"


def vwadj_line(every, delta):
    """VWADJ：予定の時刻が every カウント進むごとに delta カウント足す（負＝早める、正＝遅らせる）"""
    how = f"{abs(delta)} カウント{'早める' if delta < 0 else '遅らせる'}"
    return f"\tVWADJ\t{every},{delta}\t\t* 補正：予定の時刻が {every} カウント進むごとに {how}"


def vwait_line(count, comment=""):
    return f"\tVWAIT\t{count}" + (f"\t\t\t* {comment}" if comment else "\t\t\t* 予定の時刻まで待つ（VWAIT）")


def with_vwait_head(lines):
    """.include sch.h の直後に .include vwait.h を入れる"""
    out = []
    for ln in lines:
        out.append(ln)
        if ln.startswith("\t.include\tsch.h"):
            out.append(VWAIT_HEAD)
    assert VWAIT_HEAD in out, ".include sch.h が見つかりません"
    return out


# ---- Z-MUSIC：FM 音源の曲・効果音（x68/lib/zmusic.h・zmusic.s。docs/LIBRARY.md）----
# マクロ ZMPL（曲を頭から）・ZMST（止める）・ZMFO（フェードアウト）・ZSEP／ZSES（効果音を鳴らす／止める）・ZMVS（音色の登録）。
# Z-MUSIC ver2（ZMSC.X など）が常駐していなければ、どれも何もしない。
ZMUSIC_HEAD = "\t.include\tzmusic.h\t\t* Z-MUSIC のマクロ（x68/lib/。docs/LIBRARY.md）"
ZMUSIC_CODE = "\n* ---- Z-MUSIC のルーチン（x68/lib/zmusic.s。EXIT の後、素材より前に置く）----\n\t.include\tzmusic.s"


def with_zmusic_head(lines):
    """.include sch.h の直後に .include zmusic.h を入れる"""
    out = []
    for ln in lines:
        out.append(ln)
        if ln.startswith("\t.include\tsch.h"):
            out.append(ZMUSIC_HEAD)
    assert ZMUSIC_HEAD in out, ".include sch.h が見つかりません"
    return out


def extract_video(video: Path, dst: Path, fps, start=None, duration=None, aspect=None, fit=None):
    """ffmpeg で動画から 256x256 の PNG 連番を切り出す（縦横比を保って縮小し中央を切り出す）。
    aspect（1 ドットの横÷縦）を指定すると、横 256*aspect の範囲を切り出して 256 に縮める。
    fit="pad" なら切らずに全体を 256x256 に収め、余白は黒にする（fit_256 と同じ）。"""
    fit = fit_mode(fit, aspect)
    if dst.exists():
        for f in dst.glob("*.png"):
            f.unlink()
    dst.mkdir(parents=True, exist_ok=True)
    vw = round(256 * aspect / 2) * 2 if aspect else 256  # 縮める前の幅（ffmpeg のため偶数に）
    cmd = [adpcm.FFMPEG, "-v", "error"]
    if start is not None:
        cmd += ["-ss", str(start)]
    if duration is not None:
        cmd += ["-t", str(duration)]
    if fit == "pad":
        vf = (f"fps={fps}," + (f"scale=trunc(iw/{aspect}/2)*2:ih:flags=lanczos,setsar=1," if aspect else "")
              + "scale=256:256:force_original_aspect_ratio=decrease:flags=lanczos,pad=256:256:(ow-iw)/2:(oh-ih)/2:black,setsar=1")
    else:
        vf = (f"fps={fps},scale={vw}:256:force_original_aspect_ratio=increase:flags=lanczos,crop={vw}:256"
              + (",scale=256:256:flags=lanczos,setsar=1" if aspect else ""))
    cmd += ["-i", str(video), "-vf", vf,
            str(dst / "f%04d.png")]
    subprocess.run(cmd, check=True)

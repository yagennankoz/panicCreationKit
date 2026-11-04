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


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tif", ".tiff", ".webp"}  # 画像として読む形式（Pillow）


def is_image(path: Path) -> bool:
    """画像のファイルか（拡張子で見る）"""
    return path.is_file() and path.suffix.lower() in IMAGE_EXT


def list_images(path: Path):
    """フォルダの中の画像（IMAGE_EXT）を名前順に並べる。画像 1 枚なら [その画像]。どちらでもなければ []"""
    if path.is_dir():
        return sorted(f for f in path.iterdir() if f.suffix.lower() in IMAGE_EXT and f.is_file())
    return [path] if is_image(path) else []


def is_animated(path: Path) -> bool:
    """コマが 2 枚以上ある画像（アニメーション GIF・PNG・WebP）か"""
    if not is_image(path):
        return False
    try:
        with Image.open(path) as im:
            return getattr(im, "n_frames", 1) > 1
    except OSError:
        return False


def is_moving(path: Path) -> bool:
    """動画として切り出す素材か（動画のファイル、またはアニメーション画像）"""
    return path.is_file() and (not is_image(path) or is_animated(path))


def extract_frames(src: Path, dst: Path, fps, start=None, duration=None, aspect=None, fit=None, raw=0):
    """動画かアニメーション画像から、fps ごとのコマを PNG 連番で dst に切り出す。
    動画は extract_video（raw の意味も同じ）。アニメーション画像は Pillow で、各コマの表示時間を守って取り出し、
    元の大きさ・透明（アルファ）のまま書く。
    戻り値：書いた PNG が元の縦横比のまま（呼ぶ側で aspect・fit を使って 256x256 にする）なら True、256x256 なら False"""
    if not is_animated(src):
        extract_video(src, dst, fps, start, duration, aspect, fit, raw)
        return bool(raw)
    if dst.exists():
        for f in dst.glob("*.png"):
            f.unlink()
    dst.mkdir(parents=True, exist_ok=True)
    frames, ends, t = [], [], 0.0
    with Image.open(src) as im:
        for i in range(im.n_frames):
            im.seek(i)
            d = im.info.get("duration") or 0
            t += (d if d > 10 else 100) / 1000  # 10ms 以下の表示時間は 100ms とみなす（ブラウザと同じ）
            frames.append(im.convert("RGBA"))
            ends.append(t)
    t0 = float(start or 0)
    t1 = ends[-1] if duration is None else min(ends[-1], t0 + float(duration))
    n, k = 0, 0
    while True:
        tt = t0 + n / float(fps)
        if tt >= t1 - 1e-9:
            break
        while k < len(ends) - 1 and ends[k] <= tt:
            k += 1
        frames[k].save(dst / f"f{n + 1:04d}.png")
        n += 1
    if n == 0:
        raise SystemExit(f"{src.name}：start = {t0} 秒より後にコマがありません（全体 {ends[-1]:.2f} 秒）")
    return True


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
    "auto"＝画像のまわりの色から自動で決める（detect_key。ほかの指定とは一緒に使えない）、
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
        if it == "auto":
            out.append("auto")
            continue
        h = it[1:] if it.startswith("#") else it[2:] if it.startswith("0x") else it
        if len(h) != 6 or any(c not in "0123456789abcdef" for c in h):
            raise SystemExit(f"透明色の指定が違います：{it}（\"#RRGGBB\"、\"corner\"、\"auto\"）")
        out.append((int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)))
    if "auto" in out and len(out) > 1:
        raise SystemExit("透明色の \"auto\" は、ほかの色と一緒には書けません")
    return out


AUTO_BORDER = 0.04      # 自動判定：画像のまわりの何割（幅）を背景の候補として見るか
AUTO_SHARE = 0.25       # 自動判定：まわりのドットのうち、この割合以上を占める色を背景色とみなす
AUTO_NEAR = 48          # 自動判定：同じ背景色とみなす差（RGB 各）
AUTO_MAX_TOL = 64       # 自動判定の許す差の上限
AUTO_FRAMES = 16        # 自動判定に使うコマの数（等間隔に選ぶ）


AUTO_FIRST = 0.45      # 自動判定：いちばん多い背景色が、まわりのこの割合以上を占めること
AUTO_ALL = 0.97        # 自動判定：画像全体のこの割合以上が背景色になるなら、背景ではない（実写の背景など）とみなす


def detect_key(images):
    """画像（RGBA の配列か PNG のパス）のまわりの色から、背景色（透明にする色）と許す差を決める。
    まわり（幅 AUTO_BORDER）のドットを集め、5 ビットに丸めた色でいちばん多い色の近く（AUTO_NEAR 以内）の
    ドットの中央値を背景色にする（背景色は 1 色だけ。残りのうち AUTO_SHARE 以上を占める色がほかにもあれば止める）。
    許す差は、画像全体の背景色に近い（AUTO_NEAR 以内）ドットの「背景色との差」の 99.9% 点＋4（ゆれが無ければ 0、上限 AUTO_MAX_TOL）。
    戻り値：([(r, g, b), ...], 許す差, 説明)。まわりがもともと透明（PNG のアルファ）なら ([], 0, 説明)。
    背景らしい色が無い（目立つ色が 2 つ以上、いちばん多い色でも AUTO_FIRST 未満、画像のほとんどが背景色）なら SystemExit"""
    if len(images) > AUTO_FRAMES:
        step = len(images) / AUTO_FRAMES
        images = [images[int(i * step)] for i in range(AUTO_FRAMES)]
    arrays = [np.asarray(Image.open(im).convert("RGBA")) if not isinstance(im, np.ndarray) else im for im in images]
    px, n_border = [], 0
    for a in arrays:
        H, W = a.shape[:2]
        b = max(1, int(round(min(H, W) * AUTO_BORDER)))
        m = np.zeros((H, W), bool)
        m[:b], m[-b:], m[:, :b], m[:, -b:] = True, True, True, True
        n_border += int(m.sum())
        px.append(a[m & (a[..., 3] >= 128)][:, :3].astype(np.int16))
    px = np.concatenate(px)
    total = len(px)
    if total < n_border * 0.5:
        return [], 0, "画像のまわりがもともと透明（アルファ）なので、透明色は使いません"
    fail = "透明色を自動で決められません：{}（transparent = \"#RRGGBB\" で色を書いてください）"
    keys, shares = [], []
    rest = px
    while len(rest) and len(keys) < 3:
        q = (rest >> 3).astype(np.int32)
        code = (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
        top = np.bincount(code).argmax()
        center = np.array([(top >> 10) & 31, (top >> 5) & 31, top & 31]) * 8 + 4
        near = np.abs(rest - center).max(-1) <= AUTO_NEAR
        if near.sum() < total * AUTO_SHARE:
            break
        key = np.median(rest[near], axis=0).round().astype(int)
        mine = np.abs(rest - key).max(-1) <= AUTO_NEAR
        keys.append(tuple(int(v) for v in key))
        shares.append(mine.sum() / total)
        rest = rest[~mine]
    if not keys or shares[0] < AUTO_FIRST:
        raise SystemExit(fail.format("画像のまわりに、背景らしい同じ色がありません"))
    if len(keys) > 1:  # グリーンバックなどの背景は 1 色。まわりに目立つ色が 2 つ以上あるのは、背景の絵や実写
        raise SystemExit(fail.format("画像のまわりの色が " + "、".join(f"{key_text([k])}（{s:.0%}）" for k, s in
                                                                   zip(keys, shares)) + " に分かれています"))
    allpx = np.concatenate([a[a[..., 3] >= 128][:, :3].astype(np.int16) for a in arrays])
    d = np.min([np.abs(allpx - np.array(k, np.int16)).max(-1) for k in keys], axis=0)
    bg = d <= AUTO_NEAR
    if bg.mean() >= AUTO_ALL:
        raise SystemExit(fail.format(f"画像のほとんど（{bg.mean():.0%}）が背景の色の近くで、絵と見分けられません"))
    p = float(np.percentile(d[bg], 99.9))
    tol = 0 if p == 0 else int(min(AUTO_MAX_TOL, np.ceil(p) + 4))
    how = "、".join(f"{key_text([k])}（まわりの {s:.0%}）" for k, s in zip(keys, shares))
    return keys, tol, f"背景色 {how}、許す差 {tol}"


def key_text(keys):
    """透明色の一覧を設定ファイルに書ける形（"#RRGGBB;#RRGGBB"）にする"""
    return ";".join(f"#{r:02X}{g:02X}{b:02X}" for r, g, b in keys)


DESPECKLE_DEFAULT = 24  # despeckle = true のときの色の差（RGB 各）


def _shift(a, dy, dx, fill):
    """a を (dy, dx) だけずらす（はみ出た所は fill）。out[y, x] = a[y - dy, x - dx]"""
    out = np.full_like(a, fill)
    H, W = a.shape[:2]
    ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
    xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
    out[yd, xd] = a[ys, xs]
    return out


N4 = ((-1, 0), (1, 0), (0, -1), (0, 1))
N8 = tuple((dy, dx) for dy in (-1, 0, 1) for dx in (-1, 0, 1) if dy or dx)


def _slices(dy, dx, H, W):
    """(dy, dx) だけずらすときの、元の範囲と行き先の範囲（dst[y, x] ← src[y - dy, x - dx]）"""
    ys, yd = (slice(0, H - dy), slice(dy, H)) if dy >= 0 else (slice(-dy, H), slice(0, H + dy))
    xs, xd = (slice(0, W - dx), slice(dx, W)) if dx >= 0 else (slice(-dx, W), slice(0, W + dx))
    return (ys, xs), (yd, xd)


def _dilate(m, n):
    """上下左右に n ドット広げる"""
    H, W = m.shape
    for _ in range(n):
        out = m.copy()
        for dy, dx in N4:
            s, d = _slices(dy, dx, H, W)
            out[d] |= m[s]
        m = out
    return m


def _nearest_color(rgb, src, steps, need=None):
    """src（True のドット）の色を、まわりへ 1 ドットずつ写していく（上・下・左・右の順で、先に見つかった 1 ドットの色。
    平均しないので新しい色はできない）。steps 回で届かなかったドットは done が False のまま。
    need：色が要るドット（True）。指定すると、そのまわり steps ドットの範囲だけで計算する（速い。結果は同じ）"""
    if need is not None:
        col = np.zeros_like(rgb)
        done = np.zeros(src.shape, bool)
        ys, xs = np.nonzero(need)
        if len(ys) == 0:
            return col, done
        H, W = src.shape
        y0, y1 = max(0, ys.min() - steps - 1), min(H, ys.max() + steps + 2)
        x0, x1 = max(0, xs.min() - steps - 1), min(W, xs.max() + steps + 2)
        c, d = _nearest_color(rgb[y0:y1, x0:x1], src[y0:y1, x0:x1], steps)
        col[y0:y1, x0:x1], done[y0:y1, x0:x1] = c, d
        return col, done
    col = np.where(src[..., None], rgb, 0)
    done = src.copy()
    H, W = done.shape
    for _ in range(steps):
        new_any = False
        for dy, dx in N4:
            s, d = _slices(dy, dx, H, W)
            new = done[s] & ~done[d]
            if new.any():
                dst = col[d]
                dst[new] = col[s][new]  # 右辺は先に写しを作るので、重なっていても正しい
                done[d] |= new
                new_any = True
        if not new_any:
            break
    return col, done


FRINGE_MIN = 0.1       # 透明色がこれより少なく混ざった色は、ふちでも直さない
FRINGE_RESIDUAL = 24   # 「内側の色と透明色を混ぜた色」からの離れ（RGB 各）の許す量：
FRINGE_RESIDUAL_REL = 0.5  # FRINGE_RESIDUAL か、透明色の方へ動いた量（RGB 各の最大）× これ、の大きい方。
#   これより離れた色（黒い輪郭線、ドット絵の影など）は、ふちでも直さない


DESPILL_DEFAULT = 4     # transparent_despill = true のときの幅（ドット）
PRESCALE_DEFAULT = 2    # 動画の層で透明色を指定したときの transparent_prescale の既定（縦 512 で抜いてから縮める）
SPECK_LOOSE = 1.5       # despeckle のとき、透明に囲まれた点は、透明色の許す差をこの倍まで緩める
SPECK_SIZE = 2          # 「透明に囲まれた点」：まわり 3x3 で透明でないドットが自分を含めてこれ以下


def speck_tolerance(tolerance, despeckle):
    """despeckle のとき、透明に囲まれた点に使う緩めた許す差（key_transparent の speck。しないなら 0）"""
    return int(round(tolerance * SPECK_LOOSE)) if despeckle and tolerance else 0
DESPILL_MIN = 0.03      # 透明色の混ざり具合がこれより少ない色は変えない（細かいゆれを増やさないため）
DESPILL_MAX = 0.6       # 混ざり具合はここまでとみなす（大きいほど、割り戻すときにゆれが大きくなる）


def despill(rgb, mask, keys, ref=None, cap=DESPILL_MAX, with_alpha=False):
    """かぶり取り：mask のドットの色 P を「元の色 O と透明色 K を混ぜた色」(1−α)O + αK とみなし、O を推測して戻す。
    色み（色から灰色を引いたもの）を透明色の色みの向き k で測った量 a(色) = (色み・k) / |k|² を使う。
    元の色の a は、ref（近くの奥のドットの色。mask と同じ形。None や NaN の所は 0＝透明色の色みが無い）と同じとみなして、
    α = (a(P) − a(ref)) / (1 − a(ref))、O = (P − αK) / (1 − α) にする（色みだけでなく明るさも戻る）。
    透明色が複数なら α の大きい方を使う。
    奥まで透明色に似た色の物（ピンクの服など）は、ref も同じ色なので変わらない。奥の無い小さな物
    （緑の背景の黄緑の葉など）は、元の色が違う色だったものとして変わる。
    with_alpha：(色, α) を返す（α は cap で切る前の 0〜1。透明色がどれだけ混ざっているかの見積もり）"""
    P = rgb.astype(np.float64)
    pc = P - P.mean(-1, keepdims=True)
    if ref is not None:
        R = np.nan_to_num(ref.astype(np.float64), nan=0.0)
        rc = R - R.mean(-1, keepdims=True)
        has_ref = ~np.isnan(ref.astype(np.float64)).any(-1)
    best = np.zeros(P.shape[:2])
    raw = np.zeros(P.shape[:2])
    bestK = np.zeros_like(P)
    for c in keys:
        K = np.array(c, np.float64)
        k = K - K.mean()
        den = (k ** 2).sum()
        if den < 1:  # 灰色の透明色には色みが無いので、かぶり取りはできない
            continue
        ap = (pc * k).sum(-1) / den
        if ref is not None:
            ar = np.where(has_ref, np.clip((rc * k).sum(-1) / den, 0, 0.95), 0.0)
            ap = (ap - ar) / (1 - ar)
        raw = np.maximum(raw, np.clip(ap, 0, 1))
        al = np.clip(ap, 0, cap)
        better = al > best
        best = np.where(better, al, best)
        bestK[better] = K
    m = mask & (best >= DESPILL_MIN)
    al = best[m][:, None]
    out = rgb.copy()
    out[m] = np.clip(np.rint((P[m] - al * bestK[m]) / (1 - al)), 0, 255).astype(rgb.dtype)
    return (out, raw) if with_alpha else out


def key_transparent(im: Image.Image, colors, tolerance=0, fringe=0, cut=0.5, spill=0, speck=0) -> Image.Image:
    """colors（parse_key_colors の結果）の色のドットを透明（アルファ 0）にする。tolerance は RGB 各 0〜255 の許す差。
    fringe：透明にしたドットから fringe ドット以内（ふち）の、透明色が混ざった色（アンチエイリアスや JPEG のにじみ）を直す。
      ふちのドット P ごとに、近くの内側（ふちより奥）のドットの色 C を写してきて、P を「C と透明色 K を混ぜた色」
      C + α(K−C) で表す（α = ((P−C)·(K−C)) / |K−C|²）。P がその混ぜた色に近く（FRINGE_RESIDUAL の所の説明）、
      α が FRINGE_MIN 以上のときだけ直す：α ≥ cut なら透明、そうでなければ色を C にする。
      混ぜた色から離れた色（黒い輪郭線など）や、近くに内側のドットが無い所（ふちの幅より細い線など）は、そのまま残す。
    spill：透明にしたドットから spill ドット以内の色のかぶり取り（despill）。fringe の後にする。
      ふちの処理で直せなかった色（細い線、動きのブレで奥まで混ざった所、内側の色にも混ざっている所）の元の色を推測して戻す。
      透明色の混ざり具合が cut 以上のドット（背景が見えている細い隙間など）は透明にする。
    speck：透明に囲まれた小さな点（背景の中に残った点）だけ、透明色の許す差を speck まで緩める（tolerance 以下なら何もしない）。"""
    if not colors:
        return im
    a = np.array(im.convert("RGBA"))
    if list(colors) == ["auto"]:  # この画像のまわりの色から決める（たくさんのコマは呼ぶ側で detect_key をまとめて使う）
        colors, tol, _ = detect_key([a])
        if not colors:
            return Image.fromarray(a, "RGBA")
        tolerance = tol if tolerance is None else tolerance
    tolerance = int(tolerance or 0)
    rgb = a[..., :3].astype(np.int16)
    # "corner"：左上 (0,0) の色。左上がもともと透明（pad の余白など）なら、その画像では使わない
    keys = [tuple(int(v) for v in a[0, 0, :3]) if c == "corner" else tuple(c) for c in colors
            if c != "corner" or a[0, 0, 3] >= 128]
    if not keys:
        return Image.fromarray(a, "RGBA")
    hit = np.zeros(a.shape[:2], bool)
    diff = np.full(a.shape[:2], 999, np.int16)  # いちばん近い透明色との差（RGB 各の最大）
    for c in keys:
        diff = np.minimum(diff, np.abs(rgb - np.array(c, np.int16)).max(axis=2))
    hit = diff <= tolerance
    if speck > tolerance and hit.any():
        # 透明に囲まれた小さな点（まわり 3x3 で透明でないのが自分を含めて SPECK_SIZE 以下）は、透明色との差が speck 以内なら透明に
        # （背景の色のゆれが許す差を少し超えた所。2 回くり返して 2 ドットのかたまりも消す）
        H, W = hit.shape
        for _ in range(2):
            op = (a[..., 3] >= 128) & ~hit
            cnt = op.astype(np.int8).copy()
            for dy, dx in N8:
                s, d = _slices(dy, dx, H, W)
                cnt[d] += op[s]
            rm = op & (cnt <= SPECK_SIZE) & (diff <= speck)
            if not rm.any():
                break
            hit |= rm
    if (fringe > 0 or spill > 0) and hit.any():
        # ふち・かぶり取りは、絵（透明でないドット）のまわりだけで計算する（速い。結果は全体でするのと同じ）
        obj = (a[..., 3] >= 128) & ~hit
        ys, xs = np.nonzero(obj)
        if len(ys):
            m = 2 * max(int(fringe), int(spill)) + 4
            H, W = hit.shape
            y0, y1 = max(0, ys.min() - m), min(H, ys.max() + m + 1)
            x0, x1 = max(0, xs.min() - m), min(W, xs.max() + m + 1)
            _clean_edges(a[y0:y1, x0:x1], rgb[y0:y1, x0:x1], hit[y0:y1, x0:x1], keys, fringe, cut, spill)
    a[hit, 3] = 0
    return Image.fromarray(a, "RGBA")


def _clean_edges(a, rgb, hit, keys, fringe, cut, spill):
    """key_transparent のふち（fringe）とかぶり取り（spill）。a（RGBA）と hit（透明にするドット）をその場で書き換える"""
    if fringe > 0 and hit.any():
        opaque = (a[..., 3] >= 128) & ~hit
        near = _dilate(hit, int(fringe)) & opaque
        interior = opaque & ~near
        C, found = _nearest_color(rgb, interior, 2 * int(fringe) + 2, need=near)
        P, C = rgb.astype(np.float64), C.astype(np.float64)
        alpha = np.zeros(a.shape[:2])
        mixed = np.zeros(a.shape[:2], bool)
        for c in keys:  # 透明色が複数なら、どれかと混ざった色なら直す（α は大きい方）
            KC = np.array(c, np.float64) - C
            den = (KC ** 2).sum(-1) + 1e-6
            al = np.clip(((P - C) * KC).sum(-1) / den, 0, 1)
            room = np.maximum(FRINGE_RESIDUAL, FRINGE_RESIDUAL_REL * al * np.abs(KC).max(-1))
            ok = (np.abs(P - (C + al[..., None] * KC)).max(-1) <= room) & (al >= FRINGE_MIN)
            alpha = np.where(ok, np.maximum(alpha, al), alpha)
            mixed |= ok
        fix = near & found & mixed
        to_clear = fix & (alpha >= cut)
        to_fill = fix & ~to_clear
        a[to_fill, :3] = C[to_fill].astype(np.uint8)
        hit |= to_clear
    if spill > 0 and hit.any():
        opaque = (a[..., 3] >= 128) & ~hit
        band = _dilate(hit, int(spill)) & opaque
        # 元の色の手がかり：かぶり取りの幅より奥のドットの色を写してくる（届かない所は手がかり無し）
        C, found = _nearest_color(a[..., :3].astype(np.int16), opaque & ~band, int(spill) + 2, need=band)
        ref = np.where(found[..., None], C.astype(np.float64), np.nan)
        a[..., :3], al = despill(a[..., :3], band, keys, ref, with_alpha=True)
        hit |= band & (al >= cut)  # ほとんど透明色だったドット（脚の間の細い隙間など）は透明に


def flatten(rgba, th, radius=2, rounds=2):
    """単色のむらを均す（シグマフィルタ）：不透明なドットごとに、まわり (2*radius+1)² の不透明なドットのうち
    自分との差が th 以内（RGB 各）のものだけで平均する。rounds 回くり返す。
    差の小さいむらは消え、差の大きい輪郭は混ざらない。なだらかなグラデーションは左右対称に平均するので保たれる。"""
    if not th:
        return rgba
    op = rgba[..., 3] >= 128
    a = rgba[..., :3].astype(np.float32)
    H, W = op.shape
    r = radius
    opp = np.pad(op, r)
    for _ in range(rounds):
        ap = np.pad(a, ((r, r), (r, r), (0, 0)))
        acc = np.zeros_like(a)
        cnt = np.zeros(op.shape, np.float32)
        for dy in range(2 * r + 1):
            for dx in range(2 * r + 1):
                b = ap[dy:dy + H, dx:dx + W]
                w = (np.abs(b - a).max(-1) <= th) & opp[dy:dy + H, dx:dx + W]
                acc += b * w[..., None]
                cnt += w
        a = np.where(op[..., None], acc / np.maximum(cnt, 1)[..., None], a)
    out = rgba.copy()
    out[..., :3] = np.clip(np.rint(a), 0, 255).astype(np.uint8)
    return out


def word_rgb(words):
    """X68000 の色（GRB ワード）の配列 → RGB（0〜255）"""
    w = np.asarray(words, np.uint16)
    return np.stack([(w >> 6) & 31, (w >> 11) & 31, (w >> 1) & 31], -1).astype(np.int16) * 255 // 31


REDUCED_DIR = "reduced"  # 減色した後の画像を PNG で置くサブフォルダ（出力先の中）


def save_indexed_png(path: Path, idx, pal_words):
    """色番号の画像（idx）を、パレット（X68000 の色のワード）付きの PNG にする。番号 0 は透明"""
    rgb = word_rgb(list(pal_words) + [0] * (256 - len(pal_words))).astype(np.uint8)
    im = Image.fromarray(np.asarray(idx, np.uint8), "P")
    im.putpalette(rgb.reshape(-1).tolist())
    im.info["transparency"] = 0
    im.save(path, transparency=0)


def save_reduced(out: Path, items):
    """減色した後の画像を out/reduced/<名前>/<番号 4 桁>.png に書く（前の中身は消す）。
    items：[(名前, [(番号, 色番号の画像), ...], パレットのワード), ...]。書いた枚数を返す"""
    import shutil
    top = out / REDUCED_DIR
    if top.is_dir():
        shutil.rmtree(top)
    n = 0
    for name, images, pal_words in items:
        d = top / name
        d.mkdir(parents=True, exist_ok=True)
        for no, idx in images:
            save_indexed_png(d / f"{int(no):04d}.png", idx, pal_words)
            n += 1
    return n


def despeckle(idx, pal_words, th=DESPECKLE_DEFAULT, need=5):
    """孤立したドットを消す（色番号の画像で）：上下左右に同じ番号が 1 つも無く、まわり 8 ドットのうち need 以上が
    同じ番号 m で、その色との差が RGB 各 th 以内なら、m にする。透明（0）のドットは変えず、0 にもしない。"""
    if not th:
        return idx
    rgb = word_rgb(list(pal_words) + [0] * (256 - len(pal_words)))
    nb = np.stack([_shift(idx, dy, dx, 0) for dy, dx in N8])  # 0 ＝透明か画面の外
    alone = (idx != 0)
    for k, (dy, dx) in enumerate(N8):
        if abs(dy) + abs(dx) == 1:
            alone &= nb[k] != idx
    if not alone.any():
        return idx
    ys, xs = np.nonzero(alone)
    v = nb[:, ys, xs]                                   # (8, n)
    cnt = ((v[:, None, :] == v[None, :, :]) & (v[None, :, :] != 0)).sum(1)  # 各近傍と同じ番号の数
    cnt[v == 0] = 0
    best = cnt.argmax(0)
    m = v[best, np.arange(len(ys))]
    ok = (cnt.max(0) >= need) & (np.abs(rgb[m] - rgb[idx[ys, xs]]).max(-1) <= th)
    out = idx.copy()
    out[ys[ok], xs[ok]] = m[ok]
    return out


def clean_options(d, base=None):
    """設定（dict）から減色の前処理の値を取り出す（base は全体の値。d に無いものは base のまま）"""
    o = dict(base or {"transparent_fringe": 0, "transparent_cut": 0.5, "transparent_despill": 0,
                      "transparent_prescale": None, "flatten": 0, "despeckle": 0})
    for k in o:
        if d.get(k) is not None:
            o[k] = d[k]
    if o["transparent_despill"] is True:
        o["transparent_despill"] = DESPILL_DEFAULT
    elif o["transparent_despill"] is False:
        o["transparent_despill"] = 0
    if o["despeckle"] is True:
        o["despeckle"] = DESPECKLE_DEFAULT
    elif o["despeckle"] is False:
        o["despeckle"] = 0
    return o


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
# ルーチンの本体とマクロは x68/lib/vwait.s・vwait.h（panicCreationKit のライブラリ。docs/LIBRARY.md）。
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


# ---- ADPCM をサンプリングレートを選んで鳴らす（x68/lib/adpcm.h・adpcm.s。docs/LIBRARY.md）----
# マクロ PCMR 頭,長さ,レート（0＝3.9kHz〜4＝15.6kHz）。15.6kHz なら panic.x の PCMP で足りるので使わない。
ADPCM_HEAD = "\t.include\tadpcm.h\t\t* ADPCM のレートを選んで鳴らすマクロ（x68/lib/。docs/LIBRARY.md）"
ADPCM_CODE = "\n* ---- ADPCM のルーチン（x68/lib/adpcm.s。EXIT の後、素材より前に置く）----\n\t.include\tadpcm.s"


def pcm_play_line(label, rate_code, comment="音"):
    """ADPCM の音（label〜label_end）を鳴らす行。15.6kHz なら PCMP、ほかは PCMR（adpcm.h）"""
    if rate_code == 4:
        return f"\tPCMP\t{label},{label}_end-{label}\t\t* {comment}"
    return f"\tPCMR\t{label},{label}_end-{label},{rate_code}\t* {comment}（{adpcm.RATE_NAMES[rate_code]}）"


def with_adpcm_head(lines):
    """.include sch.h の直後に .include adpcm.h を入れる"""
    out = []
    for ln in lines:
        out.append(ln)
        if ln.startswith("\t.include\tsch.h"):
            out.append(ADPCM_HEAD)
    assert ADPCM_HEAD in out, ".include sch.h が見つかりません"
    return out


def extract_video(video: Path, dst: Path, fps, start=None, duration=None, aspect=None, fit=None, raw=0):
    """ffmpeg で動画から 256x256 の PNG 連番を切り出す（縦横比を保って縮小し中央を切り出す）。
    aspect（1 ドットの横÷縦）を指定すると、横 256*aspect の範囲を切り出して 256 に縮める。
    fit="pad" なら切らずに全体を 256x256 に収め、余白は透明（アルファ 0）にする（fit_256 と同じ）。
    raw：256x256 にせず、縦横比を保ったまま切り出す（1＝元の大きさ、N≥2＝縦 256×N まで縮める）。
      透明色を縮める前に抜くとき（transparent_prescale）に使う。256x256 にするのは呼んだ側（fit_256）。"""
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
    if raw:
        vf = f"fps={fps}" + (f",scale=-2:'min(ih,{256 * int(raw)})':flags=lanczos" if int(raw) > 1 else "")
    elif fit == "pad":
        vf = (f"fps={fps}," + (f"scale=trunc(iw/{aspect}/2)*2:ih:flags=lanczos,setsar=1," if aspect else "")
              # 余白を透明にするため RGBA にする。先に rgb24 にすると、色は余白の無いときと同じになる
              + "scale=256:256:force_original_aspect_ratio=decrease:flags=lanczos,format=rgb24,format=rgba,"
              "pad=256:256:(ow-iw)/2:(oh-ih)/2:color=black@0,setsar=1")
    else:
        vf = (f"fps={fps},scale={vw}:256:force_original_aspect_ratio=increase:flags=lanczos,crop={vw}:256"
              + (",scale=256:256:flags=lanczos,setsar=1" if aspect else ""))
    cmd += ["-i", str(video), "-vf", vf,
            str(dst / "f%04d.png")]
    subprocess.run(cmd, check=True)

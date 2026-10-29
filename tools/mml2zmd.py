r"""mml2zmd.py : Z-MUSIC ver2 の MML（.zms／.opm）を、panic で鳴らす FM 音源のデータ（.zmd／.zse／.zmv）にする

使い方:  pt mml2zmd <MML ファイル…> [--se] [--out フォルダ]
  例：pt mml2zmd bgm.zms                    → bgm.zmd（曲。ZMPL で鳴らす）
      pt mml2zmd shot.zms bomb.zms --se     → shot.zse、bomb.zse（効果音。ZSEP で鳴らす）と、音色があれば shot.zmv など

  MML の書き方は Z-MUSIC ver2 のマニュアル（setup で docs/zmusic/ に置く。MML は ZM5.MAN、ZMS コマンドは ZM4.MAN）。
  MML のファイルは Shift-JIS でも UTF-8 でもよい（Shift-JIS・CRLF にしてからコンパイルする）。頭に (i)（初期化）を足してコンパイルする
  （(i) が無いと音量がすべて 0 になるため。(i) のある曲は同じデータになる）。.zmd を渡すと、コンパイルせずに使う。
  コンパイルは Z-MUSIC の ZMUSIC.X（zmusic -c）を run68 で動かして行う（setup で x68/zmusic/ に置く）。

出力（--out、省略すると MML と同じフォルダ）。名前は英数字 8 文字まで：
  <名前>.zmd   曲（ZMD そのまま。奇数の長さなら 1 バイト詰める）。スケジュールでは ZMPL <ラベル> で鳴らす
  --se のとき：
  <名前>.zse   効果音（ZMD の頭と共通コマンドを外した、トラックの数から後ろ）。ZSEP <ラベル>,トラック で鳴らす
  <名前>.zmv   効果音の MML に音色の定義（(v…)、(@…)）があるとき、その音色の表。ZMVS <ラベル> で先に登録する

効果音の決まり（Z-MUSIC のマニュアル ZM14.MAN）：
  - 共通コマンドは、音色の定義とコメントのほかは使えない（テンポは MML の T で書く）。
  - 効果音のチャンネルは MML の (a チャンネル,トラック) で決まる。曲の同じチャンネルのトラックに割り込ませる（ZSEP のトラック）。
  - トラックは 8 本まで。音量・音色などの初期値は無いので、MML の頭で必ず書く。
"""
import shutil
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paths  # noqa: E402

MML_EXT = {".zms", ".opm"}
ZMD_ID = b"\x10ZmuSiC"
SE_MAX_TRACKS = 8  # x68/lib/zmusic.s の効果音を止めるルーチンが扱える数

# 共通コマンドの長さ（コードを含むバイト数。None＝長さが中身で決まる）。ZM12.MAN の 12.3
VOICE_CODES = {0x04: "(V) 音色", 0x1B: "(@) 音色"}
COMMON_NAMES = {0x04: "音色 (V)", 0x05: "テンポ (O)", 0x15: "ベースチャンネル (B)", 0x18: "MIDI データ (X)",
                0x1B: "音色 (@)", 0x40: "ADPCM の設定", 0x42: "全音符の長さ (Z)", 0x4A: "波形メモリ",
                0x60: ".ADPCM_LIST", 0x61: ".PRINT", 0x62: ".MIDI_DUMP", 0x63: ".ADPCM_BLOCK_DATA",
                0x7E: "なし", 0x7F: ".COMMENT"}


def to_sjis_crlf(data: bytes) -> bytes:
    """MML の中身を Shift-JIS・CRLF にする（UTF-8 なら直す）"""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    try:
        text = data.decode("utf-8")
        data = text.encode("cp932")
    except UnicodeDecodeError:
        pass  # Shift-JIS のまま
    except UnicodeEncodeError as e:
        raise SystemExit(f"MML に Shift-JIS で書けない文字があります（{e.object[e.start:e.end]!r}）")
    data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    if not data.endswith(b"\r\n"):
        data += b"\r\n"
    return data


def compile_mml(src: Path) -> bytes:
    """MML を ZMUSIC.X（zmusic -c）でコンパイルして ZMD を返す"""
    import buildPan  # run68 の作業フォルダ（短いパス）を使う
    zm = Path(paths.zmusic())
    if not zm.is_file():
        raise SystemExit(f"ZMUSIC.X が見つかりません（{zm}）。{paths.SETUP} を実行してください（Z-MUSIC を x68/zmusic/ に置きます）")
    buildPan.need_run68()
    cwd = buildPan.work_dir("zmc")
    cwd.mkdir(parents=True, exist_ok=True)
    for f in cwd.iterdir():
        if f.is_file():
            f.unlink()
    shutil.copyfile(zm, cwd / "zmusic.x")
    # 頭に (i)（初期化）を足す。(i) が無いと ZMUSIC.X -c は音量（v・@v）をすべて 0（$B6,$7F）にしてしまう
    # （効果音の MML には (i) を書かないことが多い）。(i) のある曲は、足しても同じ ZMD になる
    (cwd / "mml.zms").write_bytes(b"(i)\r\n" + to_sjis_crlf(src.read_bytes()))
    rc, out = buildPan.run68([paths.here("zmusic.x"), "-c", "mml.zms", "mml.zmd"], cwd)
    errs = []
    for ln in out.replace("\x1b[", "\x1b").splitlines():  # エラーの行：「mml.zms<TAB>行<TAB>内容」
        ln = "".join(ch for ch in ln if ch >= " " or ch == "\t")
        if ln.startswith("mml.zms\t"):
            f = ln.split("\t")
            line = int(f[1]) - 1 if f[1].strip().isdigit() else f[1]  # 足した (i) の 1 行を引く
            errs.append(f"  {src.name} {line} 行目：{' '.join(f[2:]).strip()}")
    zmd = cwd / "mml.zmd"
    if rc != 0 or not zmd.is_file() or errs:
        msg = f"MML のコンパイルに失敗しました（{src}）"
        if errs:
            msg += "\n" + "\n".join(errs) + "\n  エラーの番号の意味は docs/zmusic/ZM11.MAN"
        elif out.strip():
            msg += "\n" + "\n".join("  " + x for x in strip_esc(out).splitlines() if x.strip())
        raise SystemExit(msg)
    data = zmd.read_bytes()
    check_zmd(data, src)
    return data


def strip_esc(s: str) -> str:
    import re
    return re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", s)


def check_zmd(data: bytes, src) -> None:
    if len(data) < 10 or not data.startswith(ZMD_ID):
        raise SystemExit(f"ZMD ではありません（頭が $10,'ZmuSiC' でない）：{src}")
    if data[7] >> 4 != 2:
        raise SystemExit(f"Z-MUSIC ver2 の ZMD ではありません（版 ${data[7]:02X}）：{src}")


def common_commands(data: bytes, src):
    """共通コマンドを並べる：[(コード, 位置, 長さ)]、トラックの数の位置"""
    p, out = 8, []
    while True:
        if p >= len(data):
            raise SystemExit(f"ZMD の共通コマンドの終わりが見つかりません：{src}")
        c = data[p]
        if c == 0xFF:
            p += 1
            if p % 2:
                p += 1  # 次が奇数番地なら $FF がもう 1 つ
            return out, p
        if c in (0x04, 0x1B):
            n = 57
        elif c == 0x05:
            n = 3
        elif c == 0x15:
            n = 2
        elif c == 0x18:
            n = 3 + struct.unpack_from(">H", data, p + 1)[0]
        elif c == 0x42:
            n = 6
        elif c == 0x7E:
            n = 1
        elif c in (0x60, 0x61, 0x62, 0x63, 0x7F):
            e = data.index(b"\x00", p + 1)
            n = e + 1 - p
        else:  # $40（ADPCM）・$4A（波形メモリ）など：効果音では使えないので、長さは数えずに止める
            return out + [(c, p, None)], None
        out.append((c, p, n))
        p += n


def tracks(data: bytes, tpos: int):
    """トラックの数と、各トラックの絶対チャンネル"""
    n = struct.unpack_from(">H", data, tpos)[0]
    chs = [data[tpos + 2 + 6 * i + 5] for i in range(n)]
    return n, chs


def channel_name(ch: int) -> str:
    if ch < 8:
        return f"FM{ch + 1}"
    if ch == 8:
        return "ADPCM"
    if ch <= 24:
        return f"MIDI{ch - 8}"
    return f"ADPCM{ch - 23}"


def to_bgm(data: bytes) -> bytes:
    """曲：ZMD のまま（偶数の長さに）"""
    return data + (b"\x00" if len(data) % 2 else b"")


def to_se(data: bytes, src):
    """効果音：(.zse のデータ, .zmv のデータ または None, トラックのチャンネルの一覧)"""
    cmds, tpos = common_commands(data, src)
    bad = [c for c, _, _ in cmds if c not in (0x04, 0x1B, 0x7E, 0x7F)]
    if bad:
        names = "、".join(dict.fromkeys(COMMON_NAMES.get(c, f"${c:02X}") for c in bad))
        raise SystemExit(f"効果音の MML に使えない共通コマンドがあります：{names}（{src}）。\n"
                         "  効果音では、共通コマンドは音色の定義のほかは使えません（テンポは MML の T で、トラックの頭に書く。"
                         "docs/zmusic/ZM14.MAN の 14.1.5）")
    n, chs = tracks(data, tpos)
    if n == 0:
        raise SystemExit(f"効果音の MML に鳴らすトラックがありません（{src}）")
    if n > SE_MAX_TRACKS:
        raise SystemExit(f"効果音のトラックは {SE_MAX_TRACKS} 本までにしてください（今は {n} 本。{src}）")
    zse = data[tpos:]
    zse += b"\x00" if len(zse) % 2 else b""
    voices = [(c, p) for c, p, _ in cmds if c in VOICE_CODES]
    zmv = None
    if voices:
        zmv = bytearray(struct.pack(">H", len(voices)))
        for c, p in voices:
            zmv += bytes([c]) + data[p + 1:p + 57] + b"\x00"  # 番号.b、データ 55 バイト、詰め物
        zmv = bytes(zmv)
    return zse, zmv, chs


def load(src: Path) -> bytes:
    """MML ならコンパイル、.zmd ならそのまま読んで ZMD を返す"""
    if src.suffix.lower() == ".zmd":
        data = src.read_bytes()
        check_zmd(data, src)
        return data
    if src.suffix.lower() not in MML_EXT:
        raise SystemExit(f"MML（.zms／.opm）か ZMD（.zmd）を指定してください：{src}")
    return compile_mml(src)


def convert(src: Path, out: Path, name: str, se: bool, quiet=False):
    """1 つ変換して書く。[(ラベル, ファイル名)] を返す（効果音で音色があれば 2 つ）"""
    data = load(src)
    out.mkdir(parents=True, exist_ok=True)
    if not se:
        (out / f"{name}.zmd").write_bytes(to_bgm(data))
        if not quiet:
            cmds, tpos = common_commands(data, src)
            msg = f"{src.name} → {name}.zmd（曲、{len(data)} バイト"
            if tpos is not None:
                n, chs = tracks(data, tpos)
                msg += f"、トラック {n} 本：{' '.join(channel_name(c) for c in chs)}"
            print(msg + "）")
        return [(name, f"{name}.zmd")]
    zse, zmv, chs = to_se(data, src)
    (out / f"{name}.zse").write_bytes(zse)
    res = [(name, f"{name}.zse")]
    if zmv:
        (out / f"{name}v.zmv").write_bytes(zmv)
        res.append((f"{name}v", f"{name}v.zmv"))
    if not quiet:
        print(f"{src.name} → {name}.zse（効果音、{len(zse)} バイト、トラック {len(chs)} 本："
              f"{' '.join(channel_name(c) for c in chs)}）"
              + (f"、{name}v.zmv（音色 {struct.unpack_from('>H', zmv)[0]} 個）" if zmv else ""))
    return res


def short_name(stem: str, used=None) -> str:
    import re
    used = used if used is not None else set()
    base = (re.sub(r"[^A-Za-z0-9]", "", stem).lower() or "zm")[:7]  # 効果音の音色の表は <名前>v なので 7 文字まで
    n, k = base, 1
    while n in used:
        s = str(k)
        n, k = base[:7 - len(s)] + s, k + 1
    used.add(n)
    return n


def main(argv):
    import cli
    args = argv[1:]
    out = None
    if "--out" in args:
        k = args.index("--out")
        if k + 1 >= len(args):
            raise SystemExit("--out の後に出力先のフォルダを書いてください")
        out = Path(args[k + 1])
        args = args[:k] + args[k + 2:]
    se = "--se" in args
    files = [a for a in args if a != "--se"]
    bad = [a for a in files if a.startswith("--")]
    if bad or not files:
        if bad:
            raise SystemExit(f"知らないオプション：{' '.join(bad)}（pt mml2zmd -h で使い方）")
        print(__doc__, file=sys.stderr)
        return 1
    used = set()
    for f in files:
        src = cli.need_file(f, "MML のファイル")
        convert(src, out or src.parent, short_name(src.stem, used), se)
    return 0


if __name__ == "__main__":
    import cli
    sys.exit(cli.run(main))

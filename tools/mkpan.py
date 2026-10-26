"""mkpan.py : Human68k の .x 実行ファイルを panic の .pan に変換する（mkpan.x 互換）

使い方:  pt mkpan <in.x> [out.pan]

.pan の構造（panic.x のローダーを逆アセンブルして確認、mkpan.x の出力と一致）:
  +0   'PANIC',$1A,0,0     sch.h が text 先頭に置く
  +8   .w バージョン         sch.h の VERSION
  +10  .w リロケーション表のワード数（mkpan が埋める。ローダーではループ回数の上限）
  +12  .l リロケーション表の位置（ファイル先頭から。= text+data のサイズ）
  +16  スケジュール本体 …… data 部まで
  末尾 リロケーション表（.x のものをそのまま。.w 差分、$0001 のときは続く .l が差分）
panic.x はファイル全体を読み込み、表に従って各ロングワードに読み込みアドレスを足す。
bss 領域は確保されないので、.pan のソースでは .bss を使わないこと。
"""
import struct
import sys
from pathlib import Path

MAGIC = b"PANIC\x1a\x00\x00"


def count_relocs(table: bytes) -> int:
    n = i = 0
    while i < len(table):
        (v,) = struct.unpack_from(">H", table, i)
        i += 6 if v == 1 else 2
        n += 1
    if i != len(table):
        raise ValueError("リロケーション表の末尾が壊れています")
    return n


def x_to_pan(x: bytes, blob: bytes = b"") -> bytes:
    """blob を渡すと、text+data の直後（リロケーション表の前）につなげる。
    スケジュールのソースの最後に `.data` `.even` `data_top:` と書き、素材は `名前 .equ data_top+位置` で参照する
    （blk.x と HLK を通さずに大きな素材を入れられる。HLK は run68 上で数 MB を超えるとメモリ不足になる）。"""
    if x[:2] != b"HU":
        raise ValueError(".x ファイルではありません（先頭が 'HU' でない）")
    text, data, bss, reloc = struct.unpack_from(">4I", x, 0x0C)
    body = bytearray(x[0x40 : 0x40 + text + data])
    if body[:8] != MAGIC:
        raise ValueError("panic 用の .x ではありません（sch.h を先頭で include しているか確認）")
    if bss:
        print(f"警告: bss が {bss} バイトありますが .pan には含まれません", file=sys.stderr)
    table = x[0x40 + text + data : 0x40 + text + data + reloc]
    count_relocs(table)  # 表の形式チェック
    n = len(table) // 2  # mkpan.x と同じくワード数を書く
    if n > 0xFFFF:
        raise ValueError(f"リロケーション表が大きすぎます（{n} ワード）")
    if blob:
        if len(body) % 2:
            raise ValueError("text+data が奇数サイズです（data_top の前に .even を）")
        body += blob
    struct.pack_into(">HI", body, 10, n, len(body))
    return bytes(body) + table


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__.splitlines()[2], file=sys.stderr)
        return 1
    import cli
    src = cli.need_file(argv[1], ".x ファイル")
    dst = Path(argv[2]) if len(argv) == 3 else src.with_suffix(".pan")
    dst.write_bytes(x_to_pan(src.read_bytes()))
    print(f"{src} -> {dst}")
    return 0


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

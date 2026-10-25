"""lha.py : LZH（LHA）書庫の展開（Python だけで。-lh0- と -lh5-／-lh6-／-lh7-、ヘッダはレベル 0〜2）

使い方:  python lha.py <書庫.lzh> [展開先フォルダ]     （展開先を省略すると中身の一覧を表示）
  setup.py が PAN13801.LZH（panic.x、sch.h など）を展開するのに使う。7-Zip などは要らない。
  展開したファイルは、書庫に記録されている CRC-16 と照らし合わせる。
"""
import struct
import sys
from pathlib import Path


class LhaError(Exception):
    pass


def crc16(data: bytes) -> int:
    """LHA の CRC-16（多項式 0xA001、右回り）"""
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class _Bits:
    """上位ビットから読む"""

    def __init__(self, data: bytes):
        self.data, self.pos, self.buf, self.n = data, 0, 0, 0

    def get(self, k: int) -> int:
        while self.n < k:
            self.buf = (self.buf << 8) | (self.data[self.pos] if self.pos < len(self.data) else 0)
            self.pos += 1
            self.n += 8
        self.n -= k
        v = (self.buf >> self.n) & ((1 << k) - 1)
        self.buf &= (1 << self.n) - 1
        return v

    def peek(self, k: int) -> int:
        v = self.get(k)
        self.buf |= v << self.n
        self.n += k
        return v


class _Huff:
    """符号の長さの並びから作る正準ハフマン符号（LHA の make_table と同じ割り当て）。記号が 1 つだけなら 0 ビット"""

    def __init__(self, lengths, single=None):
        self.single = single
        self.table = {}
        if single is not None:
            return
        code = 0
        for length in range(1, 17):
            for sym, ln in enumerate(lengths):
                if ln == length:
                    self.table[(length, code)] = sym
                    code += 1
            code <<= 1

    def read(self, bits: _Bits) -> int:
        if self.single is not None:
            return self.single
        code = 0
        for length in range(1, 17):
            code = (code << 1) | bits.get(1)
            sym = self.table.get((length, code))
            if sym is not None:
                return sym
        raise LhaError("壊れたハフマン符号")


def _read_pt_len(bits, nn, nbit, special):
    n = bits.get(nbit)
    if n == 0:
        return _Huff(None, single=bits.get(nbit))
    lens = [0] * nn
    i = 0
    while i < n:
        c = bits.get(3)
        if c == 7:
            while bits.get(1):
                c += 1
        lens[i] = c
        i += 1
        if i == special:
            for _ in range(bits.get(2)):
                lens[i] = 0
                i += 1
    return _Huff(lens)


def _read_c_len(bits, pt):
    NC, CBIT = 510, 9
    n = bits.get(CBIT)
    if n == 0:
        return _Huff(None, single=bits.get(CBIT))
    lens = [0] * NC
    i = 0
    while i < n:
        c = pt.read(bits)
        if c <= 2:
            run = 1 if c == 0 else bits.get(4) + 3 if c == 1 else bits.get(CBIT) + 20
            for _ in range(run):
                lens[i] = 0
                i += 1
        else:
            lens[i] = c - 2
            i += 1
    return _Huff(lens)


def decode_lh(data: bytes, size: int, dicbit: int) -> bytes:
    """-lh5-（dicbit 13）／-lh6-（15）／-lh7-（16）を展開する"""
    np_, pbit = dicbit + 1, (4 if dicbit <= 13 else 5)
    bits = _Bits(data)
    out = bytearray()
    remain = 0
    while len(out) < size:
        if remain == 0:
            remain = bits.get(16)
            pt = _read_pt_len(bits, 19, 5, 3)
            c_huff = _read_c_len(bits, pt)
            p_huff = _read_pt_len(bits, np_, pbit, -1)
        remain -= 1
        c = c_huff.read(bits)
        if c < 256:
            out.append(c)
            continue
        length = c - 256 + 3
        j = p_huff.read(bits)
        dist = j if j <= 1 else (1 << (j - 1)) + bits.get(j - 1)
        start = len(out) - dist - 1
        if start < 0:
            raise LhaError("壊れたデータ（距離が範囲外）")
        for k in range(length):
            out.append(out[start + k])
    return bytes(out[:size])


def entries(data: bytes):
    """書庫の各ファイル：(名前, 方式, 圧縮データ, 元の大きさ, CRC-16)"""
    p = 0
    while p < len(data) and data[p] != 0:
        level = data[p + 20]
        method = data[p + 2:p + 7].decode("ascii", "replace")
        packed, orig = struct.unpack_from("<II", data, p + 7)
        if level in (0, 1):
            hs = data[p]
            nl = data[p + 21]
            name = data[p + 22:p + 22 + nl]
            crc = struct.unpack_from("<H", data, p + 22 + nl)[0]
            pos = p + 2 + hs
            ext_total = 0
            if level == 1:  # 拡張ヘッダ（大きさは圧縮データの大きさに含まれる）
                nxt = struct.unpack_from("<H", data, pos - 2)[0]
                while nxt:
                    ext = data[pos:pos + nxt]
                    if ext[0] == 0x01:  # ファイル名
                        name = ext[1:-2]
                    pos += nxt
                    ext_total += nxt
                    nxt = struct.unpack_from("<H", ext, nxt - 2)[0]
            body = data[pos:pos + packed - ext_total]
            p = pos + packed - ext_total
        elif level == 2:
            total = struct.unpack_from("<H", data, p)[0]
            crc = struct.unpack_from("<H", data, p + 21)[0]
            pos, name = p + 24, b""
            nxt = struct.unpack_from("<H", data, pos)[0]
            pos += 2
            while nxt:
                ext = data[pos:pos + nxt]
                if ext[0] == 0x01:
                    name = ext[1:-2]
                pos += nxt
                nxt = struct.unpack_from("<H", ext, nxt - 2)[0]
            body = data[p + total:p + total + packed]
            p = p + total + packed
        else:
            raise LhaError(f"対応していないヘッダのレベル {level}")
        yield name.decode("cp932", "replace").replace("\\", "/"), method, body, orig, crc


def extract(data: bytes, want=None) -> dict:
    """書庫を展開して {名前: 中身} を返す。want（名前の集合、大文字小文字は区別しない）を渡すとそれだけ"""
    out = {}
    for name, method, body, orig, crc in entries(data):
        if want is not None and name.lower() not in {w.lower() for w in want}:
            continue
        if method == "-lh0-":
            content = body[:orig]
        elif method in ("-lh5-", "-lh6-", "-lh7-"):
            content = decode_lh(body, orig, {"-lh5-": 13, "-lh6-": 15, "-lh7-": 16}[method])
        elif method == "-lhd-":
            continue  # フォルダ
        else:
            raise LhaError(f"{name}：対応していない圧縮方式 {method}")
        if crc16(content) != crc:
            raise LhaError(f"{name}：CRC が合いません（展開に失敗）")
        out[name] = content
    return out


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    data = Path(argv[1]).read_bytes()
    if len(argv) == 2:
        for name, method, body, orig, _ in entries(data):
            print(f"{method} {orig:8d} {name}")
        return 0
    dst = Path(argv[2])
    for name, content in extract(data).items():
        (dst / name).parent.mkdir(parents=True, exist_ok=True)
        (dst / name).write_bytes(content)
        print(f"  {name}（{len(content)} バイト）")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

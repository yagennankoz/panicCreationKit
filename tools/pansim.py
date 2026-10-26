r"""pansim.py : .pan を PC 上で実行するシミュレータ（時間と画面の確認用）

使い方:  pt pansim <file.pan> [--clock 10mhz] [--gif out.gif] [--png フォルダ] [--seconds 秒]

  ※ pansim は実機のように画面に再生するものではなく、.pan の命令を PC 上で計算して、時間と画面（画像）を調べる道具。
    キー入力は受け付けず、「キーは押されない」ものとして進める。キーで終わるデータや永久ループのデータは、
    --seconds（既定 60）秒ぶん動かした所で止める。始める前に、そのデータがキーで終わるかどうかを表示する。

  - スケジュールの命令を順に解釈し、時間（V-Sync 単位）とグラフィック画面（G0・G1 の 512x512）を追いかける。
  - GDRW／DRW0／DRW1 は a_enc（code #4）を実際にデコードして GRAM に描く（差分モードは GRAM の今の内容に対して）。
    描画時間は a_enc.estimate_us（XM6 の実測モデル、tools/timing.json）。
  - TMWA は panic.x V1.38 と同じ規則：V-Sync ごとに増えるカウンタが待ち以上になるまで待って 0 に戻す。
    入った時点ですでに待ち以上（遅れ）なら次の V-Sync まで待つ（panic.x V1.38 の逆アセンブルで確認）。
  - 結果：再生時間（最初の TMWA から最後の TMWA まで＝mkanim の --timelog の T1−T0 に相当）、遅れた TMWA の数。
  - --gif／--png：表示が変わるたびの画面（256x256。G0 を G1 の上に重ね、G0 の色0 は透明）を書き出す。
  扱えないもの：BG スケジューラ、キー入力（IKEY／RTOK／BKEY などは「押されない」として進む）、
  BSUB などの 68000 ルーチン（時間 0 として飛ばす）。
"""
import argparse
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import a_enc  # noqa: E402
import spr_enc  # noqa: E402
import clock as clk  # noqa: E402
import txt_enc  # noqa: E402

TICK_US = 18030.0

# 命令コード → (名前, 引数の並び w=ワード l=ロング)。sch.h（V1.38）より
OPS = {
    0x00: ("EXIT", ""), 0x01: ("TMON", ""), 0x02: ("TMOF", ""), 0x03: ("TMWA", "w"),
    0x04: ("SCL0", "ww"), 0x05: ("SCL1", "ww"), 0x06: ("SCLT", "ww"), 0x07: ("GPAL_OLD", "l"),
    0x08: ("TPAL_OLD", "wl"), 0x09: ("GWIP", ""), 0x0A: ("GPWP", "l"), 0x0B: ("TWIP", ""),
    0x0C: ("TPWP", "l"), 0x0D: ("GDRW", "ll"), 0x0E: ("MOVW", "lw"), 0x0F: ("MOVB", "lw"),
    0x10: ("GTOG", "ll"), 0x11: ("GTOT", "ll"), 0x12: ("BSUB", "l"), 0x13: ("BSB1", "ll"),
    0x14: ("BSB2", "lll"), 0x15: ("PCMP", "ll"), 0x16: ("PCMS", ""), 0x17: ("BKEY", "wl"),
    0x18: ("DEND", ""), 0x19: ("GOTO", "l"), 0x1A: ("GSUB", "l"), 0x1B: ("RTSB", ""),
    0x1C: ("IKEY", "wl"), 0x1D: ("SPIN_OLD", ""), 0x1E: ("SPON_OLD", "l"), 0x1F: ("SPOF_OLD", ""),
    0x20: ("SPCG", "wl"), 0x21: ("TDRW", "ll"), 0x22: ("VSWA", ""), 0x23: ("DBOF", ""),
    0x24: ("EINT", "l"), 0x25: ("KGET", "wwl"), 0x26: ("SETR", "l"), 0x27: ("ADDR", "l"),
    0x28: ("SUBR_OLD", "l"), 0x29: ("MULR", "w"), 0x2A: ("DIVR", "w"), 0x2B: ("MODR", "w"),
    0x2C: ("ANDR", "l"), 0x2D: ("OR_R", "l"), 0x2E: ("EORR", "l"), 0x2F: ("NOTR", ""),
    0x30: ("IFEQ", "ll"), 0x31: ("IFNE", "ll"), 0x32: ("LOOP", "l"), 0x33: ("NOPR", ""),
    0x34: ("SETF", "l"), 0x35: ("RELF", ""), 0x36: ("SPOP_OLD", "lww"), 0x37: ("SIGI", ""),
    0x38: ("IFCX", "l"), 0x39: ("TKEY", "lwl"), 0x3A: ("BGSC", "l"), 0x3B: ("SLEP", ""),
    0x3C: ("SYNC", ""), 0x3D: ("KILL", ""), 0x3E: ("GETR", ""), 0x3F: ("SWPR", ""),
    0x40: ("WTRL", "l"), 0x41: ("WTRW", "l"), 0x42: ("WTRB", "l"), 0x43: ("RDRL", "l"),
    0x44: ("RDRW", "l"), 0x45: ("RDRB", "l"), 0x46: ("SUBR", "l"), 0x47: ("RTOK", ""),
    0x48: ("ABRT", ""), 0x49: ("MOVL", "ll"), 0x4A: ("GPAL", "l"), 0x4B: ("TPAL", "wl"),
    0x4C: ("SPIN", ""), 0x4D: ("SPOF", ""), 0x4E: ("SPON", "l"), 0x4F: ("SPOP", "lww"),
}
# 時間のかかる命令（pantime.txt の値。当時の 10MHz 機での値とみなし、24MHz は 1/2.3 にする）
# 命令 1 つの時間 [us]（XM6 10MHz で実測。刻みが粗く ±3us）
MOVE_US = 3.3     # MOVW／MOVB／MOVL
KEY_US = 647.0    # IKEY／RTOK（DOS の _INPOUT を呼ぶので重い）
SPOF_US = 617.0   # SPOF（pantime.txt の 0.2ms より重い）
FIXED_MS_10MHZ = {"GWIP": 138.7, "GPWP": 35.1, "TWIP": 34.7, "TPWP": 2.4, "GTOG": 69.1, "GTOT": 340.0}


class SimError(Exception):
    pass


def load_pan(path):
    d = bytearray(Path(path).read_bytes())  # SPCG がセルを書き換えるので変更できる形で
    if d[:8] != b"PANIC\x1a\x00\x00":
        raise SimError(".pan ではありません")
    return d


def gram_addr(addr):
    """GRAM のアドレス → (面 0/1, x, y)"""
    if not 0xC00000 <= addr < 0xD00000:
        raise SimError(f"GRAM 外のアドレス ${addr:06X}")
    page = (addr - 0xC00000) // 0x80000
    off = (addr - 0xC00000) % 0x80000
    return page, (off % 0x400) // 2, off // 0x400


class Sim:
    def __init__(self, data, clock):
        self.d = data
        self.clock = clock
        self.slow = clk.scale(clock, "cpu")     # 命令の時間の、10MHz に対する倍率（clock.py）
        self.slow_io = clk.scale(clock, "spof")  # スプライトの I/O（SPOF・SPCG・SPON）
        self.gram = [np.zeros((512, 512), np.uint8) for _ in range(2)]
        self.scroll = [[0, 0], [0, 0], [0, 0]]  # G0, G1, テキスト
        self.palette = np.zeros(256, np.uint16)
        self.tram = np.zeros((4, 1024, 128), np.uint8)  # テキスト VRAM：4 プレーン × 1024 行 × 128 バイト
        self.tpal = np.zeros(16, np.uint16)
        self.text_used = False
        # スプライト（panic.x V1.38 の逆アセンブル text+$2A70〜）
        self.pcgmem = bytearray(0x8000)               # PCG／BG のメモリ $EB8000〜$EBFFFF（後ろ半分は BG のマップと共用）
        self.bgctrl = 0                               # $EB0808（bit0 BG0 表示、bit1-2 BG0 のマップ、bit3 BG1、bit4-5 BG1、bit9 表示）
        self.bgscroll = [[0, 0], [0, 0]]              # BG0／BG1 のスクロール（$EB0800〜$EB0806）
        self.prio = 0x06E4                            # $E82500（panic.x の初期値：スプライト＞テキスト＞G0＞G1）
        self.vc_on = 0x7F                             # $E82601（bit6 スプライト／BG、bit5 テキスト、bit0-3 グラフィック）
        self.use_pcg = 0                              # 次に定義する PCG 番号
        self.use_sp = 128                             # 空いているスプライトの数（後ろから使う）
        self.sprites = np.zeros((128, 4), np.int32)   # 各スプライトの X, Y, 属性（パレット<<8｜PCG）, 優先度
        self.spal = np.zeros((16, 16), np.uint16)     # スプライトのパレット（0 はテキストと共用）
        self.t = 0.0           # 現在時刻 [us]（TMON からではなく開始から）
        self.reset_tick = 0    # TMWA のカウンタを 0 にした V-Sync の番号
        self.timer_on = False
        self.d7 = 0
        self.stack = []
        self.tmwa_times = []   # TMWA を抜けた時刻
        self.late = []         # 遅れていた TMWA（命令の位置, 時刻）
        self.frames = []       # (時刻, 画面) 表示が変わった時
        self.changed_at = 0.0   # 表示が変わった時刻（まだ記録していないもの）
        self.keep_states = False
        self.io = {}           # RDR?／WTR? で読み書きしたアドレス（I/O の中身は扱わない）
        self.states = []       # TMWA に入る時点の画面（keep_states のとき）
        self.notes = []
        self.pcm = []          # (時刻, 長さ)

    def note(self, msg):
        if msg not in self.notes:
            self.notes.append(msg)

    def arg(self, pc, fmt):
        vals = []
        for c in fmt:
            if c == "w":
                vals.append(struct.unpack_from(">H", self.d, pc)[0])
                pc += 2
            else:
                vals.append(struct.unpack_from(">I", self.d, pc)[0])
                pc += 4
        return vals, pc

    def changed(self):
        """表示が変わった（スクロール、パレット、見えている所への描画）。時間が進む前に画面を記録する"""
        if self.changed_at is None:
            self.changed_at = self.t

    def flush(self):
        """時間が進む直前に呼ぶ：表示が変わっていれば、変わった時刻の画面として記録する"""
        if self.changed_at is not None:
            img = self.screen()
            if not self.frames or (self.frames[-1][1] != img).any():  # 見た目が同じなら記録しない
                self.frames.append((self.changed_at, img))
            self.changed_at = None

    def advance(self, us):
        self.flush()
        self.t += us

    def tmwa(self, w, pc):
        self.flush()
        if self.keep_states:  # 待ちに入る時点の画面（切り替えの後、次の切り替えまで見えている絵）
            self.states.append(self.screen())
        now_tick = int(self.t // TICK_US)
        if now_tick - self.reset_tick >= w:
            self.late.append((pc, self.t))
            tick = now_tick + 1
        else:
            tick = self.reset_tick + w
        self.t = tick * TICK_US
        self.reset_tick = tick
        self.tmwa_times.append(self.t)

    def vwait(self, w, pc):
        """VWAIT：基準からの予定の時刻（待ちの合計）まで待つ。過ぎていたら次の V-Sync まで（遅れは後で取り戻す）"""
        self.flush()
        if self.keep_states:
            self.states.append(self.screen())
        self.vw_target += w
        every, delta = getattr(self, "vw_adj", (0, 0))
        if every:  # VWADJ：予定の時刻を進めた量が every に達するたびに delta を足す
            self.vw_acc += w
            while self.vw_acc >= every:
                self.vw_acc -= every
                self.vw_target += delta
        now_tick = int(self.t // TICK_US)
        due = self.vw_base + self.vw_target
        if now_tick >= due:
            self.late.append((pc, self.t))
            tick = now_tick + 1
        else:
            tick = due
        self.t = tick * TICK_US
        self.reset_tick = tick
        self.tmwa_times.append(self.t)

    def duration(self):
        """最初の TMWA から最後の TMWA まで [1/100 秒]"""
        return (self.tmwa_times[-1] - self.tmwa_times[0]) / 10000 if len(self.tmwa_times) >= 2 else 0.0

    def bg_layer(self, page, w, m):
        """BG（8x8 タイル、64x64 のマップ＝512x512）を w に重ねる（m は色の付いた所）"""
        on = (self.bgctrl >> (0 if page == 0 else 3)) & 1
        if not on:
            return
        area = (self.bgctrl >> (1 if page == 0 else 4)) & 1  # 0＝$EBC000、1＝$EBE000（XM6 の実装）
        base = 0x4000 + area * 0x2000
        mp = np.frombuffer(bytes(self.pcgmem[base:base + 0x2000]), ">u2").reshape(64, 64)
        tiles = np.frombuffer(bytes(self.pcgmem[:0x2000]), np.uint8).reshape(256, 8, 4)  # 8x8 パターン 256 個（$EB8000〜）
        tiles = np.stack([tiles >> 4, tiles & 15], -1).reshape(256, 8, 8)
        pat = tiles[mp & 0xFF]                         # (64, 64, 8, 8)
        hf = (mp >> 14) & 1
        vf = (mp >> 15) & 1
        pat = np.where(hf[..., None, None] == 1, pat[..., ::-1], pat)
        pat = np.where(vf[..., None, None] == 1, pat[..., ::-1, :], pat)
        pal = np.broadcast_to(((mp >> 8) & 15)[..., None, None], pat.shape)
        img = pat.transpose(0, 2, 1, 3).reshape(512, 512)
        pimg = pal.transpose(0, 2, 1, 3).reshape(512, 512)
        sx, sy = self.bgscroll[page]
        img = np.roll(np.roll(img, -sy % 512, 0), -sx % 512, 1)[:256, :256]
        pimg = np.roll(np.roll(pimg, -sy % 512, 0), -sx % 512, 1)[:256, :256]
        col = self.spal[pimg, img]
        w[:] = np.where(img != 0, col, w)
        m |= img != 0

    def screen(self):
        """今見えている 256x256 を RGB で返す。重なり順は $E82500（既定：スプライト＞テキスト＞G0＞G1）、色0 は透明"""
        out = []
        for p in (0, 1):
            x, y = self.scroll[p]
            g = np.roll(np.roll(self.gram[p], -y % 512, 0), -x % 512, 1)[:256, :256]
            out.append(g)
        front, back = (out[1], out[0]) if (self.prio & 0xFF) == 0x4E else (out[0], out[1])  # $4E なら G1 が手前
        gidx = np.where(front != 0, front, back)
        layers = {}
        layers["gr"] = (self.palette[gidx], gidx != 0)
        if self.text_used:
            sx, sy = self.scroll[2]
            rows = self.tram[:, (sy + np.arange(256)) % 1024, :]  # (4, 256, 128)
            bits = np.unpackbits(rows, axis=2)  # (4, 256, 1024)
            bits = np.roll(bits, -sx % 1024, axis=2)[:, :, :256]
            tidx = bits[0] | (bits[1] << 1) | (bits[2] << 2) | (bits[3] << 3)
            layers["tx"] = (self.tpal[tidx], tidx != 0)
        sw = np.zeros((256, 256), np.uint16)
        sm = np.zeros((256, 256), bool)
        self.bg_layer(1, sw, sm)  # スプライト層の中：BG1 → BG0 → スプライト（PRW=3）の順に手前
        self.bg_layer(0, sw, sm)
        self.sprite_layer(sw, sm)
        layers["sp"] = (sw, sm)
        if not self.vc_on & 0x0F:  # 表示の on／off（$E82601）
            layers.pop("gr", None)
        if not self.vc_on & 0x20:
            layers.pop("tx", None)
        if not self.vc_on & 0x40:
            layers.pop("sp", None)
        hi = self.prio >> 8
        rank = {"gr": hi & 3, "tx": (hi >> 2) & 3, "sp": (hi >> 4) & 3}  # 0 が手前
        w = np.zeros((256, 256), np.uint16)
        for k in sorted(layers, key=lambda k: -rank[k]):  # 奥から重ねる
            lw, lm = layers[k]
            w = np.where(lm, lw, w)
        rgb = np.stack([(w >> 6) & 31, (w >> 11) & 31, (w >> 1) & 31], -1).astype(np.uint16) * 255 // 31
        return rgb.astype(np.uint8)

    def sprite_layer(self, w, m):
        """スプライトを w に重ねる。番号の小さいものほど手前（後に SPON したもの）"""
        if (self.sprites[:, 3] != 0).any():
            for i in range(127, -1, -1):
                x, y, attr, prio = self.sprites[i]
                if prio == 0:
                    continue
                n_ = attr & 0xFF
                t = spr_enc.pcg_tile(self.pcgmem[n_ * 128:(n_ + 1) * 128])
                col = self.spal[(attr >> 8) & 15][t]
                sx, sy = x - 16, y - 16
                x0, y0 = max(sx, 0), max(sy, 0)
                x1, y1 = min(sx + 16, 256), min(sy + 16, 256)
                if x0 >= x1 or y0 >= y1:
                    continue
                tt = t[y0 - sy:y1 - sy, x0 - sx:x1 - sx]
                cc = col[y0 - sy:y1 - sy, x0 - sx:x1 - sx]
                w[y0:y1, x0:x1] = np.where(tt != 0, cc, w[y0:y1, x0:x1])
                m[y0:y1, x0:x1] |= tt != 0

    def poke(self, addr, data, size):
        """MOVW／MOVB／MOVL／WTR? による書き込み。PCG／BG のメモリ、BG のレジスタ、優先順位だけ扱う"""
        raw = int(data).to_bytes(size, "big", signed=False) if data >= 0 else (data & ((1 << (8 * size)) - 1)).to_bytes(size, "big")
        if 0xEB8000 <= addr < 0xEC0000:
            o = addr - 0xEB8000
            self.pcgmem[o:o + size] = raw
            self.advance(MOVE_US * self.slow)
            self.changed()
            return
        if addr == 0xE82601 or (addr == 0xE82600 and size >= 2):  # 表示の on／off
            self.vc_on = raw[-1] if addr == 0xE82600 else raw[0]
            self.advance(MOVE_US * self.slow)
            self.changed()
            return
        if 0xEB0800 <= addr < 0xEB0812 or 0xE82500 <= addr < 0xE82502:
            for k, b in enumerate(raw):  # バイトごとに反映
                a_ = addr + k
                if 0xE82500 <= a_ < 0xE82502:
                    sh = 8 if a_ == 0xE82500 else 0
                    self.prio = (self.prio & ~(0xFF << sh)) | (b << sh)
                elif 0xEB0800 <= a_ < 0xEB0808:
                    reg = (a_ - 0xEB0800) // 2
                    sh = 8 if (a_ % 2 == 0) else 0
                    v = self.bgscroll[reg // 2][reg % 2]
                    self.bgscroll[reg // 2][reg % 2] = ((v & ~(0xFF << sh)) | (b << sh)) & 0x3FF
                elif a_ in (0xEB0808, 0xEB0809):
                    sh = 8 if a_ == 0xEB0808 else 0
                    self.bgctrl = (self.bgctrl & ~(0xFF << sh)) | (b << sh)
            self.advance(MOVE_US * self.slow)
            self.changed()
            return
        self.advance(MOVE_US * self.slow)

    def spof(self):
        self.use_sp = 128
        self.sprites[:] = 0
        self.advance(SPOF_US * self.slow_io)
        self.changed()

    def spcg(self, pal, addr):
        n = struct.unpack_from(">H", self.d, addr)[0]
        if n > 256 or self.use_pcg + n > 256:
            raise SimError(f"SPCG：PCG の定義数が 256 を超えます（今 {self.use_pcg}、追加 {n}）")
        first = self.use_pcg
        self.d[addr + 2] = pal & 0xFF          # SPCG はセルの中を書き換える
        self.d[addr + 3] = first & 0xFF
        self.d[addr + 4:addr + 6] = b"\x00\x03"
        self.pcgmem[first * 128:(first + n) * 128] = self.d[addr + 14:addr + 14 + 128 * n]
        self.use_pcg += n
        self.advance(n * 60 * self.slow_io)  # pantime.txt：キャラ数 × 0.06ms

    def spon(self, addr, dx, dy):
        n, attr, prio, xc, yc, x, y = struct.unpack_from(">7H", self.d, addr)
        if self.use_sp - n < 0:
            raise SimError("SPON：表示できるスプライトの数（128）を超えます")
        self.use_sp -= n
        i = self.use_sp
        k = 0
        for r in range(yc + 1):
            for c in range(xc + 1):
                if i >= 128:
                    break
                self.sprites[i] = (x + dx + 16 * c, y + dy + 16 * r, (attr & 0xFF00) | ((attr + k) & 0xFF), prio)
                i += 1
                k += 1
        self.advance(n * 7 * self.slow_io)  # pantime.txt：キャラ数 × 0.007ms
        self.changed()

    def tdrw(self, addr, cel_off):
        """テキスト面に描く。高速テキスト（code #2）はそのまま、a_enc（code #4）は色番号の下位 4 ビットで描く"""
        off = addr - 0xE00000
        if not 0 <= off < 0x80000:
            raise SimError(f"テキスト VRAM 外のアドレス ${addr:06X}")
        p0, off = off // 0x20000, off % 0x20000  # プレーン 1〜3 に向けたもの（プレーンごとのセル）
        row, cb = off // 128, off % 128
        if cb > 96:
            raise SimError(f"テキストの描画先 ${addr:06X} が右にはみ出します")
        cel = self.d[cel_off:]
        code = struct.unpack_from(">H", cel, 0)[0]
        band = self.tram[:, :, cb:cb + 32].copy()
        if code == 2:
            _, end = txt_enc.decode_planes(cel, band, row, p0)
            try:
                us = txt_enc.estimate_us(cel[:end], self.clock)
            except Exception:
                us = 25.0 * 1024 / self.slow_inv()
                self.note("テキスト面の描画時間はまだ実測していないので仮の値（1 行 25us）")
        elif code == 4:
            img, _, end = a_enc.decode(cel)
            band[:, row:row + 256] = txt_enc.index_to_planes(img & 15)
            us = 249_000 * self.slow  # XM6 10MHz の実測（benchtx の agrad、単純なグラデーション）。絵によって変わる
            self.note("a_enc のセルを TDRW で描く時間は実測 1 例（249ms）の値で数えています")
        else:
            raise SimError(f"TDRW の code #{code} は未対応")
        self.flush()
        self.tram[:, :, cb:cb + 32] = band
        self.text_used = True
        self.t += us
        self.changed()

    def slow_inv(self):
        return 1 / self.slow

    def gdrw(self, addr, cel_off):
        page, x, y = gram_addr(addr)
        cel = self.d[cel_off:]
        code = struct.unpack_from(">H", cel, 0)[0]
        if code != 4:
            raise SimError(f"a_enc（code #4）以外のセル（code #{code}）は未対応")
        g = self.gram[page]
        if x + 256 > 512:
            raise SimError(f"描画先 ({x},{y}) が画面からはみ出します")
        band = g[:, x:x + 256].copy()  # この縦の帯に描く（途中の行から始まるセルも描ける。上の行は行コピーで参照される）
        _, _, end, rows = a_enc.decode_rows(cel, band, y)
        self.flush()
        g[:, x:x + 256] = band
        self.t += a_enc.estimate_us(cel[:end], self.clock)
        # 見えている所（スクロール位置からの 256x256、512 で折り返す）に描いたなら、描き終わった時点で表示が変わる
        sx, sy = self.scroll[page]

        def overlap(a, b):
            return (a - b) % 512 < 256 or (b - a) % 512 < 256

        if overlap(x, sx) and overlap(y, sy):
            self.changed()

    def run(self, max_steps=5_000_000, max_us=None):
        """max_us：この時刻を過ぎたら止める（永久ループのデータ用。止めた所は stopped=True）"""
        pc = 16
        self.stopped = False
        for _ in range(max_steps):
            if max_us is not None and self.t >= max_us:
                self.flush()
                self.stopped = True
                return
            at = pc
            code = struct.unpack_from(">H", self.d, pc)[0]
            pc += 2
            if code not in OPS:
                raise SimError(f"未知の命令 ${code:02X}（+${at:X}）")
            name, fmt = OPS[code]
            a, pc = self.arg(pc, fmt)
            if name in ("EXIT", "ABRT"):
                self.flush()
                return
            elif name == "TMON":
                self.timer_on = True
                self.reset_tick = int(self.t // TICK_US)
            elif name == "TMOF":
                self.timer_on = False
            elif name == "TMWA":
                self.tmwa(a[0], at)
            elif name == "VSWA":
                self.advance((int(self.t // TICK_US) + 1) * TICK_US - self.t)
            elif name in ("SCL0", "SCL1", "SCLT"):
                self.scroll[("SCL0", "SCL1", "SCLT").index(name)] = [a[0], a[1]]
                self.changed()
            elif name == "GPAL":
                p = np.frombuffer(self.d[a[0] + 2:a[0] + 514], ">u2").copy()
                p[0] = 0
                p[1] |= 1
                self.palette = p
                self.changed()
            elif name == "GDRW":
                self.gdrw(a[0], a[1])
            elif name == "TDRW":
                self.tdrw(a[0], a[1])
            elif name == "TPAL":
                # 0 はテキスト用（スプライトのパレット 0 と共用）、1〜15 はスプライト用。V1.38 の $4B：色0=0、色1 に輝度ビット
                p = np.frombuffer(self.d[a[1] + 2:a[1] + 34], ">u2").copy()
                p[0] = 0
                p[1] |= 1
                self.spal[a[0] & 15] = p
                if a[0] == 0:
                    self.tpal = p
                self.changed()
            elif name in ("SPIN", "SPIN_OLD"):
                self.use_pcg = 0
                self.spof()
            elif name in ("SPOF", "SPOF_OLD"):
                self.spof()
            elif name == "SPCG":
                self.spcg(a[0], a[1])
            elif name in ("SPON", "SPON_OLD"):
                self.spon(a[0], 0, 0)
            elif name in ("SPOP", "SPOP_OLD"):
                self.spon(a[0], np.int16(a[1]), np.int16(a[2]))
                if name == "SPOP_OLD":
                    self.d7 = 0x10000  # 旧版はシステム変数を壊す（V1.38 の逆アセンブル）
            elif name == "PCMP":
                self.pcm.append((self.t, a[1]))
            elif name in ("GWIP", "GPWP", "TWIP", "TPWP", "GTOG", "GTOT"):
                self.advance(FIXED_MS_10MHZ[name] * 1000 * self.slow)
                if name == "GWIP":
                    for g in self.gram:
                        g[:] = 0
                    self.changed()
                elif name == "TWIP":
                    self.tram[:] = 0
                    self.changed()
                elif name in ("GTOG", "GPWP"):
                    self.note(f"{name} は時間だけ数えて、画面には反映していません")
            elif name == "GOTO":
                pc = a[0]
            elif name == "GSUB":
                self.stack.append(pc)
                pc = a[0]
            elif name == "RTSB":
                pc = self.stack.pop()
            elif name == "SETR":
                self.d7 = a[0]
            elif name in ("ADDR", "SUBR_OLD"):
                self.d7 = (self.d7 + a[0]) & 0xFFFFFFFF
            elif name == "SUBR":
                self.d7 = (self.d7 - a[0]) & 0xFFFFFFFF
            elif name == "LOOP":  # dbra D7
                w = (self.d7 - 1) & 0xFFFF
                self.d7 = (self.d7 & 0xFFFF0000) | w
                if w != 0xFFFF:
                    pc = a[0]
            elif name == "IFEQ":
                if self.d7 == a[0]:
                    pc = a[1]
            elif name == "IFNE":
                if self.d7 != a[0]:
                    pc = a[1]
            elif name in ("ANDR", "OR_R", "EORR"):
                op = {"ANDR": lambda x, y: x & y, "OR_R": lambda x, y: x | y, "EORR": lambda x, y: x ^ y}[name]
                self.d7 = op(self.d7, a[0])
            elif name == "NOTR":
                self.d7 ^= 0xFFFFFFFF
            elif name in ("BSUB", "BSB1", "BSB2") and self.d[a[0] + 2:a[0] + 6] == b"PTVI":
                self.vw_base, self.vw_target = int(self.t // TICK_US), 0  # VWAIT の基準（x68/lib/vwait.s）
                self.vw_acc = 0
            elif name == "BSB2" and self.d[a[0] + 2:a[0] + 6] == b"PTVA":  # VWADJ every,delta
                d = a[2] & 0xFFFFFFFF
                self.vw_adj = (a[1] & 0xFFFFFFFF, d - (1 << 32) if d & 0x80000000 else d)
                self.vw_acc = 0
            elif name == "BSB1" and self.d[a[0] + 2:a[0] + 6] == b"PTVW":
                self.vwait(a[1], at)
            elif name in ("BSUB", "BSB1", "BSB2"):
                self.note("BSUB など 68000 のルーチンは時間 0 として飛ばしています")
            elif name == "RTOK":
                self.d7 = 0  # キーは押されないものとする
                self.advance(KEY_US * self.slow)
            elif name == "IKEY":
                self.advance(KEY_US * self.slow)
            elif name in ("RDRL", "RDRW", "RDRB"):
                self.d7 = self.vc_on if a[0] == 0xE82601 else self.io.get(a[0], 0)
            elif name in ("WTRL", "WTRW", "WTRB"):
                self.io[a[0]] = self.d7
                self.poke(a[0], self.d7 & {"WTRL": 0xFFFFFFFF, "WTRW": 0xFFFF, "WTRB": 0xFF}[name],
                          {"WTRL": 4, "WTRW": 2, "WTRB": 1}[name])
            elif name == "MOVW":
                self.poke(a[0], a[1], 2)
            elif name == "MOVB":
                self.poke(a[0], a[1] & 0xFF, 1)
            elif name == "MOVL":
                self.poke(a[0], a[1], 4)
            elif name in ("DEND", "DBOF", "NOPR", "SIGI", "PCMS", "EINT", "SETF", "RELF",
                          "IFCX", "KGET", "BKEY", "TKEY"):
                pass  # 画面・時間に（ここでは）影響しない／キーは押されないものとする
            else:
                self.note(f"{name} は未対応（無視しました）")
        raise SimError("命令数が多すぎます（無限ループ？）")


KEY_OPS = {"IKEY": "決まったキー（IKEY）", "RTOK": "どれかのキー（RTOK）", "KGET": "キー入力（KGET）",
           "BKEY": "キー待ち（BKEY）", "TKEY": "キー待ち（TKEY）"}


def inspect(path_or_data):
    """スケジュールを頭から EXIT まで読み、キーを使うか・永久ループ（後ろへの GOTO）があるかを調べる。
    戻り値：{"keys": キーの命令の名前の集合, "loop": 後ろへ戻る GOTO があるか}（実行はしない）"""
    d = load_pan(path_or_data) if not isinstance(path_or_data, (bytes, bytearray)) else path_or_data
    pc, keys, loop = 16, set(), False
    while pc + 2 <= len(d):
        at = pc
        code = struct.unpack_from(">H", d, pc)[0]
        if code not in OPS:
            break
        name, fmt = OPS[code]
        pc += 2
        args = []
        for c in fmt:
            if pc + (2 if c == "w" else 4) > len(d):
                return {"keys": keys, "loop": loop}
            args.append(struct.unpack_from(">H" if c == "w" else ">I", d, pc)[0])
            pc += 2 if c == "w" else 4
        if name in KEY_OPS:
            keys.add(name)
        elif name == "GOTO" and args and args[0] <= at:
            loop = True
        elif name in ("EXIT", "ABRT"):
            break
    return {"keys": keys, "loop": loop}


def start_message(info, clock, stop_sec=None, what="再生"):
    """pansim を動かす前に出すメッセージ"""
    head = f"pansim で{what}を PC 上で計算します（{clock}。実機の画面には出ません）"
    if info["keys"] or info["loop"]:
        kinds = "・".join(sorted({KEY_OPS[k] for k in info["keys"]}))
        kind = f"キー入力で終了します（{kinds}）" if info["keys"] else "ESC で終了する永久ループです"
        head += f"\n  このデータは{kind}。pansim ではキーは押されないものとして進めます"
        if stop_sec is not None:
            head += f"。{stop_sec:.1f} 秒ぶん動かした所で止めます"
    return head


def simulate(path, clock=a_enc.DEFAULT_CLOCK, keep_states=False, max_us=None):
    s = Sim(load_pan(path), clock)
    s.keep_states = keep_states
    s.run(max_us=max_us)
    return s


def dedup(imgs):
    """続けて同じ画面を 1 つにまとめる"""
    out = []
    for im in imgs:
        if not out or (out[-1] != im).any():
            out.append(im)
    return out


def main(argv):
    import cli
    ap = cli.ArgumentParser(description=".pan を PC 上で実行する")
    ap.add_argument("pan", type=Path)
    ap.add_argument("--clock", default=a_enc.DEFAULT_CLOCK)
    ap.add_argument("--gif", type=Path)
    ap.add_argument("--png", type=Path)
    ap.add_argument("--seconds", type=float, default=60.0,
                    help="キーで終わるデータ・永久ループのデータを何秒ぶん動かすか（既定 60）")
    a = ap.parse_args(argv[1:])
    cli.need_file(a.pan, ".pan ファイル")
    a.clock = clk.parse(a.clock, "オプション", "--clock")
    cli.check_number("オプション", "--seconds", a.seconds, above=0)
    info = inspect(a.pan)
    endless = bool(info["keys"] or info["loop"])
    print(start_message(info, a.clock, a.seconds if endless else None))
    s = simulate(a.pan, a.clock, max_us=a.seconds * 1e6 if endless else None)
    if s.stopped:
        print(f"{a.seconds:.1f} 秒ぶん動かして止めました（キーは押されないものとして）")
    if s.stopped and len(s.tmwa_times) >= 2:
        print(f"止めた所までの時間（{a.clock}）：{s.duration() / 100:.2f} 秒（最初の TMWA から最後の TMWA まで）")
    elif len(s.tmwa_times) >= 2:
        dur = s.duration()
        print(f"再生時間（{a.clock}）：{dur / 100:.2f} 秒（{round(dur)}／100 秒。最初の TMWA から最後の TMWA まで＝"
              f"--timelog の T1−T0 に相当）")
    late = [x for x in s.late if x[1] > s.tmwa_times[0]]  # 最初の TMWA（最初のコマを描いた直後）は除く
    print(f"表示の切り替え {len(s.frames)} 回、遅れた TMWA {len(late)} 回（処理落ち）")
    for pc, t in late[:10]:
        print(f"  遅れ：+${pc:X}（{t / 1e6:.2f} 秒）")
    for n in s.notes:
        print(f"  注意：{n}")
    if a.png:
        a.png.mkdir(parents=True, exist_ok=True)
        from PIL import Image
        for k, (t, img) in enumerate(s.frames):
            Image.fromarray(img).save(a.png / f"s{k:04d}.png")
        print(f"-> {a.png}（{len(s.frames)} 枚）")
    if a.gif and s.frames:
        from PIL import Image
        ims = [Image.fromarray(img).resize((512, 512), Image.NEAREST) for _, img in s.frames]
        times = [t for t, _ in s.frames] + [s.t]
        durs = [max(20, round((times[k + 1] - times[k]) / 1000)) for k in range(len(ims))]
        ims[0].save(a.gif, save_all=True, append_images=ims[1:], duration=durs, loop=0)
        print(f"-> {a.gif}")
    return 0


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

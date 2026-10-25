r"""panbuild.py : mkanim.py --stop-at-s で止めた（そして人が .s を編集した）フォルダから .pan を作る

使い方:  python panbuild.py <フォルダ または <名前>.json> [--clock 10mhz] [--sim]

  --sim   できた .pan を pansim（PC 上のシミュレータ）で動かし、再生時間と処理落ちを表示する（既定はしない）

フォルダの中身（mkanim.py が作る）:
  <名前>.s     スケジュール。人が編集してよい。最後の `.include <名前>_d.h` は消さないこと（素材のラベルが入る）
  <名前>_d.h   素材のラベル（data_top からの位置の .equ）。panbuild が毎回作り直すので編集しない
  <名前>.json  素材の一覧 {"name":…, "clock":…, "parts":[[ラベル, ファイル名], …]}。並び順に .pan の後ろへつなげる。
               素材を足すときはここに書き足す（ファイルはフォルダからの相対。奇数サイズなら後ろに 1 バイト詰める）。
               "pcm" で始まるラベル（pcm、pcmse など＝音）の直後には、自動で "<ラベル>_end"（音の終わり）も作る。
処理:  _d.h を作る → run68 で HAS/HLK → 素材をつなげて .pan → 中身の検証（→ --sim なら pansim で再生時間と処理落ちを表示）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buildPan  # noqa: E402
import pansim  # noqa: E402
import clock as clk  # noqa: E402

PAN_SIZE_WARN = 8_000_000  # これより大きい .pan は警告（panic.x は丸ごと読み込む。RAM 10MB の XM6 で 7.9MB は可、9.4MB は不可）


def write_sjis(path: Path, text: str):
    path.write_bytes(text.replace("\n", "\r\n").encode("cp932"))


def data_header(name, labels):
    L = [f"* {name}_d.h : buildPan.py が作る素材のラベル（編集しない。{name}.json を直して buildPan し直す）",
         "\t.data", "\t.even", "data_top:"]
    L += [f"{lab}\t.equ\tdata_top+{off}" for lab, off in labels]
    return "\n".join(L) + "\n"


def build_dir(target, clock=None, quiet=False, sim=False):
    """フォルダ（または .json）から .pan を作り、(pan のパス, pansim の結果) を返す。
    sim=False なら pansim は動かさない（結果は None）"""
    target = Path(target)
    js = target if target.suffix == ".json" else next(iter(sorted(target.glob("*.json"))), None)
    if js is None:
        raise SystemExit(f"{target} に素材の一覧（.json）がありません")
    d = js.parent
    try:
        m = json.loads(js.read_text(encoding="utf-8"))
        name = m["name"]
        parts = list(m["parts"])
    except (json.JSONDecodeError, KeyError, TypeError) as e:
        raise SystemExit(f"{js.name} の中身が正しくありません（{e}）。mkanim／mkscene で作り直してください")
    for lab, fname in parts:
        if not (d / fname).is_file():
            raise SystemExit(f"{js.name} に書かれた素材のファイルがありません：{d / fname}")
    clock = clock or m.get("clock", "10mhz")
    labels, blob = [], bytearray()
    for lab, fname in m["parts"]:
        data = (d / fname).read_bytes()
        labels.append((lab, len(blob)))
        blob += data
        if lab.startswith("pcm"):  # 音（pcm、pcmse など）：終わりのラベル <ラベル>_end も作る
            labels.append((f"{lab}_end", len(blob)))
        if len(data) % 2:  # 次の素材を偶数番地にする詰め物（セルは終端の後ろなので無害）
            blob += b"\x88" if lab.startswith("pcm") else b"\x00"
    write_sjis(d / f"{name}_d.h", data_header(name, labels))
    src = d / f"{name}.s"
    if f"{name}_d.h".lower() not in src.read_bytes().decode("cp932", "replace").lower():
        raise SystemExit(f"{src.name} に `.include {name}_d.h` がありません（ソースの最後に必要）")
    pan = buildPan.build(src, blob=bytes(blob))
    data = pan.read_bytes()
    reloc_at = int.from_bytes(data[12:16], "big")
    if data[reloc_at - len(blob):reloc_at] != blob:
        raise SystemExit("検証エラー：.pan の中の素材データが一致しません（_d.h の .include がソースの最後に無い？）")
    if len(data) > PAN_SIZE_WARN:
        print(f"  警告：.pan が {len(data) / 1e6:.1f}MB あります。panic.x はファイル全体をメモリに読み込むので、"
              f"RAM 10MB でも入らない恐れがあります（10MB で 7.9MB は可、9.4MB は「メモリが不足」）。"
              f"短くするか、mkanim --split で分けてください")
    if not sim:
        return pan, None
    info = pansim.inspect(pan)
    if m.get("forever") or info["keys"] or info["loop"]:  # 永久ループ：1 周の 3 倍の時間で止める
        stop_us = (m.get("cycle", 0) * 3 + 1) * 18030 if m.get("cycle") else 60e6
        if not quiet:
            print(pansim.start_message(info, clock, stop_us / 1e6, "再生時間"))
        sim = pansim.simulate(pan, clock, max_us=stop_us)
    else:
        if not quiet:
            print(pansim.start_message(info, clock, None, "再生時間"))
        sim = pansim.simulate(pan, clock)
    if not quiet:
        report(sim, clock, nominal=m.get("nominal"), forever=m.get("forever"))
    return pan, sim


def report(sim, clock, nominal=None, forever=False):
    dur = sim.duration()
    late = [x for x in sim.late if sim.tmwa_times and x[1] > sim.tmwa_times[0]]
    if forever:
        msg = f"永久ループ（{clock}、pansim）：{dur / 100:.2f} 秒まで動かして止めた"
        if late:
            msg += f"、遅れた TMWA {len(late)} 回（処理落ち）"
        print(msg)
        for n in sim.notes:
            print(f"  注意：{n}")
        return
    msg = f"再生時間（{clock}、pansim）：{dur / 100:.2f} 秒"
    if nominal is not None:
        msg += f"（予定 {nominal / 100:.2f} 秒）"
        if dur > nominal + 2:
            msg += "  ← 処理落ちします"
    print(msg)
    if late:
        print(f"  遅れた TMWA {len(late)} 回（最初：{late[0][1] / 1e6:.2f} 秒）")
    for n in sim.notes:
        print(f"  注意：{n}")


def main(argv):
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 1
    import cli
    sim = "--sim" in argv
    argv = [x for x in argv if x != "--sim"]
    clock = None
    if "--clock" in argv:
        k = argv.index("--clock")
        if k + 1 >= len(argv):
            raise SystemExit("--clock の後に MPU クロック（例 10、16.7、24mhz）を書いてください")
        clock = clk.parse(argv[k + 1], "オプション", "--clock")
        argv = argv[:k] + argv[k + 2:]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 1
    target = Path(argv[1])
    if not target.exists():
        raise SystemExit(f"フォルダ（または .json）が見つかりません：{target}")
    build_dir(target, clock, sim=sim)
    return 0


if __name__ == "__main__":
    import cli  # エラーを分かりやすいメッセージにする（トレースバックは PANTOOL_DEBUG=1 のときだけ）
    sys.exit(cli.run(main))

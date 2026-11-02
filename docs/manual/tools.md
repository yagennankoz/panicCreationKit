# 確かめる（pansim）とそのほかのツール

[← 使い方（MANUAL）へ](../MANUAL.md)

## 1. 確かめる（pansim）

```
pt pansim <file.pan> [--gif out.gif] [--png フォルダ] [--seconds 秒] [--clock 10mhz]
```

- .pan の命令を PC 上で計算して、再生時間・処理落ち（遅れた待ち）・画面を調べます。実機の画面に再生するものではありません。
- キー入力は受け付けず、「キーは押されない」ものとして進めます。キーで終わるデータ・永久ループは `--seconds`（既定 60）秒で止めます。
- `--gif` で、表示が変わるたびの画面を GIF のアニメに書き出します。
- `--png` で、表示が変わるたびの画面を、指定したフォルダに PNG で書き出します。
- mkanim／mkscene／buildPan に `--sim` を付けると、作った直後に pansim で動かし、各切り替えの画面が予定どおりの重ね合わせかを確かめます。

---

## 2. そのほかのツール

| ツール               | 使い方                                                       | 用途                                                                                                                                      |
| -------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `mkbench.py`         | `pt mkbench <設定.toml> [--out] [--stop-at-s]`               | ベンチ動画を作る（[ベンチ動画（mkbench）](mkbench.md)）                                                                                   |
| `mkparts.py`         | `pt mkparts <画像・音声…> --name 名前 [--make …]`            | セル・パレット・ADPCM と .s のひな形を作る（[手で作る（mkparts＋buildPan）](mkparts.md) の 2 章）                                         |
| `buildPan.py`        | `pt buildPan <名前>.s [--sim] [--clock]`                     | .s から .pan を作る。素材の一覧（.json）があれば素材もつなげる（[手で作る（mkparts＋buildPan）](mkparts.md) の 7 章）。panbuild.py も同じ |
| `png2cel.py`         | `pt png2cel [-p] [-a] [-c] [-t 色] <in.png> <out.cel> <pal>` | PNG → a_enc セル（bpica.x 互換）。`-p` でパレットを新しく作る                                                                             |
| `adpcm.py`（enc）    | `pt adpcm enc <音> <out.pcm> [--gain dB]`                    | 音を ADPCM（MSM6258、15.625kHz）に変換する                                                                                                |
| `adpcm.py`（dec）    | `pt adpcm dec <in.pcm> <out.wav>`                            | ADPCM を WAV に戻して確かめる                                                                                                             |
| `mkpan.py`           | `pt mkpan <in.x> [out.pan]`                                  | .x → .pan（mkpan.x 互換）                                                                                                                 |
| `predict_time.py`    | `pt predict_time <名前>`                                     | x68/anim/<名前> の再生時間の大まかな予測（pansim の方が正確）                                                                             |
| `make_test_anim.py`  | —                                                            | テスト用の素材を作る                                                                                                                      |
| `test_a_enc.py`      | `pt test_a_enc`                                              | a_enc エンコーダが bpica.x の出力と一致するかの確認                                                                                       |
| `make_ref_images.py` | `pt make_ref_images`                                         | 正解データ作り用のテスト画像を作る（2.1）                                                                                                 |

### 2.1 セルの正解データ（make_ref_images・gload.x・test_a_enc）

このツールのグラフィックのセル（a_enc）は、当時のエンコーダ bpica.x とバイト単位で同じ出力になるように作ってあります。
その確かめに使う「正解データ」（bpica.x が作ったセル・パレット・ログ）が `samples/reference/` にあります。

**確かめるだけのとき**（ふつうはこれで十分です）

```
pt make_ref_images      # テスト画像を作る（samples/reference/src/*.png と、x68/ref/*.raw）
pt test_a_enc           # 正解データと一致するか（最後に「すべて一致」と出れば OK）
```

**正解データを X68000 の上で作り直すとき**

bpica.x は、画面に表示した絵を読んでセルにします（512x512・65536 色の画面の (0,0)〜(255,255)）。
その画面に絵を出すのが `x68/gload.x` です（ソースは `x68/src/gload.s`）。

- `gload <ファイル>`：画面を 512x512・65536 色にして、256x256 の生データ（1 ドット 1 ワード、GRB 5:5:5:1、131072 バイト）を (0,0) に表示する。
  生データは `pt make_ref_images` が `x68/ref/` に作ります。
- `gload`（ファイルを書かない）：画面を元に戻す。

手順（エミュレータで `x68/` を H: に共有しているとして、X68000 の上で）：

```
H:\>gload ref\r1.raw
H:\>bpica -p ref\r1.cel ref\r1.pal > ref\r1.log
（r2〜r5 も同じように）
H:\>gload ref\r7.raw
H:\>copy ref\r1.pal ref\r7.pal
H:\>bpica ref\r7.cel ref\r7.pal > ref\r7.log
H:\>gload
```

- `-p` はパレットを新しく作ります。r7 は、r1 のパレットに色を足す場合（`-p` なし）の確かめです。
- できた `x68/ref/` の `.cel`・`.pal`・`.log` を `samples/reference/` に写し、`pt test_a_enc` で確かめます。
- テキスト面・スプライトの正解データ（`samples/reference/text/` の t1〜t4・tn1・s1）は、bpic.x 1.08 の `-t -h`・`-t`・`-s` で作ったものです。
  bpic.x は setup.bat ではダウンロードしないので、作り直すときは自分で用意してください。

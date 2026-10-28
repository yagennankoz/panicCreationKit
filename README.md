# panicCreationKitForWin — X68000 ぱにっく データ制作ツール（Windows 版）

Windows 上の素材（PNG 連番・動画・音声）から、X68000 用アニメーション再生システム
**ぱにっく**（panic.x V1.38.01）のデータ（.pan）を作るツール群です。

- PNG 連番や動画 1 本から 1 コマンドで .pan（`mkanim`）
- グラフィック 0／1・テキスト面・スプライト・BG を重ねたアニメを設定ファイルから（`mkscene`）
- 永久ループ＋キーで終了、ADPCM の音、描画が 10MHz で間に合うように自動調整
- FM 音源の曲と効果音（Z-MUSIC ver2 の MML から。好きな時刻に鳴らす・止める）
- ベンチ動画（`mkbench`）、PC 上での再生の確認（`pansim`）

使い方の詳しい説明は **[docs/MANUAL.md](docs/MANUAL.md)** にあります。

## 動く環境

- Windows 10／11（64 ビット）、PowerShell（Windows に最初から入っています）
- 最初の準備のときだけインターネット接続（必要なツールを自動でダウンロードします。全部で約 130MB）
- 作った .pan の確認には、X68000 の実機か X68000 のエミュレータ。エミュレータと ROM は含みません

## 準備（最初に 1 回）

1. 次のどちらかで、このツールを手に入れて、**短いパスの所**に置く（例 `C:\panicCreationKitForWin`。中で使う run68 が長いパスを扱えないため）
   - **git を使う**：コマンドプロンプトで
     ```
     git clone https://github.com/yagennankoz/panicCreationKitForWin.git C:\panicCreationKitForWin
     ```
   - **git を使わない**：GitHub のページの「Code」→「Download ZIP」でダウンロードする。
     ZIP を右クリック →「プロパティ」で「許可する（ブロックの解除）」にチェックを入れてから展開する
     （しないと、setup.bat を開いたときに Windows の警告が出ることがあります）。
     展開したフォルダの名前は `panicCreationKitForWin-main` になりますが、そのままでかまいません。
2. **`setup.bat` をダブルクリック**する
   - サンプルの素材も用意するなら、コマンドプロンプトで `setup.bat --samples`
3. 「そろいました」と出たら完了

setup.bat は次のものを自動でダウンロードして、このフォルダの中に置きます（Windows には何もインストールしません）。
版は固定してあり、ダウンロードした物は SHA-256 で確かめます（`tools/setup/deps.json`）。

| もの                                      | 用途                                   | 置く場所              | 入手元・ライセンス                                |
| ----------------------------------------- | -------------------------------------- | --------------------- | ------------------------------------------------- |
| Python 3.13（埋め込み版）、Pillow、numpy  | ツール本体                             | `runtime/python/`     | python.org（PSF）、PyPI                           |
| ffmpeg 9.0.2                              | 動画・音声の読み込み                   | `runtime/ffmpeg/`     | gyan.dev のビルド（GPL v3）                       |
| run68x 2.3.2                              | X68000 のプログラムを Windows で動かす | `runtime/run68/`      | github.com/kg68k/run68x（GPL v2）                 |
| HAS060X 2.0.3                             | X68000 のアセンブラ                    | `x68/bin/`            | github.com/kg68k/has060xx（HAS060.X の配布規定）  |
| HLK evolution 3.01+18                     | X68000 のリンカ                        | `x68/bin/`            | github.com/kg68k/hlk-ev（転載可）                 |
| panic.x V1.38.01、sch.h、付属ドキュメント | panic の再生器とマクロ、説明書         | `x68/`、`docs/panic/` | retropc.net（PAN13801.LZH。利用・配布・改造自由） |
| Z-MUSIC ver2.08（ZMUSIC.X、ZMSC.X、ZP.R）、マニュアル | FM 音源のドライバ（MML のコンパイルと再生） | `x68/zmusic/`、`docs/zmusic/` | retropc.net（ZMSC208X.LZH・ZMSC2MAN.LZH。原作者 Z.Nishikawa さん、作者 MZL さん。転載可） |
| Big Buck Bunny 10 秒（360p、約 1MB）※     | 動画のサンプル（`samples/bbb/bbb.toml`） | `samples/bbb/`        | test-videos.co.uk（CC BY 3.0、(c) Blender Foundation / www.bigbuckbunny.org） |

※ `setup.bat --samples` で準備したときだけダウンロードします。`--samples` を付けないときは入りません。
`--samples` で用意するもう 1 つのサンプル（テストアニメの PNG）は、ダウンロードせずにその場で作ります。
Big Buck Bunny から作った .pan を配るときは、CC BY 3.0 に従ってクレジット（上の表の著作者）を表示してください。

もう一度ダウンロードし直すときは `setup.bat --force`、そろっているかだけ調べるときは `setup.bat --check`。

**新しい版に更新するとき**

- git で手に入れた場合：このフォルダで `git pull` のあと、`setup.bat --force`
  （使うツールの版が変わっていることがあるので、ダウンロードし直します。サンプルも使うなら `setup.bat --force --samples`）。
- ZIP で手に入れた場合：新しい ZIP を別のフォルダに展開し、`setup.bat` からやり直します。
  前のフォルダで作ったデータ（`x68\anim\` など）は、必要なら新しいフォルダへ写してください。

**自分の（インストール済みの）Python を使う場合**：ツールは `pt` で動かすと、setup.bat が用意した Python（`runtime\python\`）を使います。
`python tools\〇〇.py` のように直接動かすと、インストールしてある Python が使われるので、先に `pip install -r requirements.txt`（Pillow、numpy）が必要です。
ffmpeg などは `python tools\setup\setup.py` で用意できます。くわしくは docs/MANUAL.md の 2 章。

## 使い方（例）

コマンドプロンプトで、このフォルダに移動してから：

```
pt                                                 ツールの一覧
pt mkanim samples\anim2 test1 --fps 12 --diff      PNG 連番から .pan（--samples で用意した素材）
pt mkscene samples\layer1\scene4.toml              層を重ねたアニメ
pt mkbench samples\bench\bench.toml                ベンチ動画
pt mkparts title.png se.wav --name demo            セル・パレット・ADPCM と .s のひな形だけ作る（手で作るとき）
pt mkscene samples\fm\fm.toml                      FM 音源の曲と効果音を鳴らすアニメ
pt mml2zmd bgm.zms                                 FM 音源の MML（Z-MUSIC ver2）を曲のデータにする
pt buildPan x68\anim\demo\demo.s                   自分で書いた .s から .pan を作る
pt pansim x68\anim\test1\test1.pan                 PC 上で再生時間と画面を確かめる
```

できた .pan は `x68\anim\<名前>\` に入ります（`--out` で変えられます）。
作り方は、ツールにおまかせする「自動」（mkanim・mkscene）と、スケジュールを自分で書く「手作業」（mkparts＋buildPan）の 2 通りです。
詳しくは docs/MANUAL.md の 4・5 章を見てください。
エミュレータでは `x68` フォルダを共有し（ホストのフォルダを X68000 のドライブにする機能。WindrvXM など）、X68000 側で `panic anim\test1\test1.pan` のように再生します。
FM 音源を使うデータは、先に `zmusic\zmsc -n -t0 -w0` で Z-MUSIC を常駐させてから再生します（docs/MANUAL.md の 8 章）。

## フォルダ

```
setup.bat  pt.bat     準備と、ツールの入口
tools/                ツール（Python）。tools/setup/ に準備の仕組み
x68/                  X68000 側のファイル（エミュレータで共有する所）
  anim/                 作った .pan の出力先
  lib/                  .s に .include する 68000 のルーチン（VWAIT、FM 音源など。docs/LIBRARY.md）
  zmusic/               Z-MUSIC ver2（setup.bat が置く）
  bin/                  X68000 のアセンブラとリンカ（setup.bat が置く）
samples/              サンプルの設定ファイルと素材
docs/                 マニュアル（MANUAL.md）。setup が docs/panic/ に panic の付属ドキュメント、docs/zmusic/ に Z-MUSIC のマニュアルを置く
runtime/              setup.bat がダウンロードした物（Python、ffmpeg、run68）
```

## ライセンスと無保証

- このリポジトリのファイル（tools/、x68/lib/、docs/、samples/ など。setup.bat がダウンロードする物は除く）は
  **MIT-0（MIT No Attribution）** です。原文は [LICENSE](LICENSE) にあります。
  - 商用を含めて、自由に使う・改変する・配布する・販売することができます。著作権表示やライセンスの文を付ける必要はありません。
  - 作った .pan に x68/lib/ のルーチン（VWAIT など）が入っても、その .pan に表示は要りません。
- **無保証です。** このツールと、このツールで作ったデータは、何の保証もなく提供されます。
  使ったことで損害が出ても、作者は責任を負いません（LICENSE の後半と同じ内容です。正式な文は LICENSE の英文です）。
- 自動でダウンロードするものは、それぞれの配布元のライセンスに従います（上の表）。
- panic は原作者 永田英哉（pako）さんの宣言により利用・配布・改造が自由です。個々の .pan データの扱いはデータの作者に従います。
- Z-MUSIC は Z.Nishikawa さん（原作者）・MZL さん（作者）の作品です（転載可）。.pan には Z-MUSIC は入りません（再生する側で常駐させます）。

## 作者・入手先

- 作者：yagennankoz
- 最新版：https://github.com/yagennankoz/panicCreationKitForWin

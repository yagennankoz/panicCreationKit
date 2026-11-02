# mkanim.py（重ね合わせの無いアニメーションを 1 コマンドで）

[← 使い方（MANUAL）へ](../MANUAL.md)

```
pt mkanim <画像のフォルダ | 動画 | アニメーション GIF> <名前> [オプション]
pt mkanim --config 設定.toml [オプション]
```

`--config` の設定ファイルには、オプション名（`-` は `_` でもよい）を書きます。例：`samples/bbb/bbb.toml`。
コマンドラインで指定したものが優先です。中身は mkscene（G0 に 1 枚の層）と同じなので、[mkscene](mkscene.md)の説明も参考にしてください。

| オプション                            | 意味                                                                                                                      | 既定                           |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `<名前>`                              | 出力名。英数字 8 文字以内（Human68k の 8.3）                                                                              | —                              |
| `--out フォルダ`                      | 出力先                                                                                                                    | `x68/anim/<名前>/`             |
| `--fps N`                             | 1 秒あたりのコマ数（60 まで）                                                                                             | 12                             |
| `--loop N`                            | N 回くり返して 1 本にする                                                                                                 | 1                              |
| `--forever`                           | 永久ループ（キーで終了）                                                                                                  | —                              |
| `--exit-key any／space／return／none` | 永久ループを終わらせるキー（none は ESC だけ）                                                                            | any                            |
| `--diff`                              | 前フレーム差分を使う（ほとんどの素材で速く・小さくなる）                                                                  | 使わない                       |
| `--dither none／fs／ordered`          | 減色のときのディザ。止まった背景なら ordered が差分と相性がよい                                                           | none                           |
| `--dither-strength N`                 | ordered の強さ                                                                                                            | 24                             |
| `--stabilize N`                       | 前のコマとの色の差が N 以下のドットは前の色のまま（実写のゆらぎ対策。目安 16〜24）                                        | 0                              |
| `--sequence 順番`                     | 表示する順番（[mkscene](mkscene.md) の 4 章）                                                                             | 名前順                         |
| `--hold 指定`                         | 画像ごとの表示時間（[mkscene](mkscene.md) の 4 章）                                                                       | —                              |
| `--transparent 色`                    | 透明にする色（[画像の読み込み方](image.md)）                                                                              | —                              |
| `--transparent-tolerance N`           | 透明色の許す差                                                                                                            | 0                              |
| `--transparent-fringe N`              | 透明色が混ざったふちの色を直す幅（[画像の読み込み方](image.md)）                                                          | 0（しない）                    |
| `--transparent-cut A`                 | ふち・かぶり取りで透明にする、透明色の混ざり具合（0〜1）                                                                  | 0.5                            |
| `--transparent-despill [N]`           | 透明色のかぶり取りの幅（[画像の読み込み方](image.md)）                                                                    | 0（しない。付けると 4）        |
| `--transparent-prescale N`            | 動画を 256x256 に縮める前に、縦 256×N の大きさで透明色を抜く（1＝元の大きさ、0＝縮めた後。[画像の読み込み方](image.md)）  | 2                              |
| `--flatten T`                         | 減色の前に単色のむらを均す（[画像の読み込み方](image.md)）                                                                | 0（しない）                    |
| `--despeckle [T]`                     | 減色の後に孤立した 1 ドットを消す（[画像の読み込み方](image.md)）                                                         | しない（付けると 24）          |
| `--aspect`                            | ドットの縦横比の補正（[画像の読み込み方](image.md)）                                                                      | しない                         |
| `--pixel-aspect R`                    | 1 ドットの横÷縦                                                                                                           | 1.5                            |
| `--fit crop／pad`                     | 256x256 への収め方（[画像の読み込み方](image.md)）                                                                        | aspect なら pad、なしなら crop |
| `--audio ファイル`                    | 音。動画なら指定しなくても動画の音を使う                                                                                  | —                              |
| `--no-audio`                          | 動画の音を使わない                                                                                                        | —                              |
| `--gain dB`                           | 音量の調整                                                                                                                | 0                              |
| `--audio-offset 秒`                   | 音を鳴らし始める時刻（負なら音の頭を削る）                                                                                | 0                              |
| `--audio-every N`                     | 永久ループで N 周ごとに鳴らし直す（0 で最初の 1 回だけ）                                                                  | 音の長さから自動               |
| `--fm ファイル`                       | FM 音源の曲（Z-MUSIC の MML か ZMD。[FM 音源](fm.md) の 4 章）                                                            | なし                           |
| `--fm-offset 秒`                      | 曲を鳴らし始める時刻                                                                                                      | 0                              |
| `--fm-every N`                        | 永久ループで N 周ごとに曲を頭から鳴らし直す（0 で最初の 1 回だけ）                                                        | 0                              |
| `--start 秒`                          | （動画・アニメーション GIF）何秒目から使うか                                                                              | 0                              |
| `--duration 秒`                       | （動画・アニメーション GIF）何秒分使うか                                                                                  | 最後まで                       |
| `--split 秒`                          | 長い素材をこの長さごとの .pan に分ける（名前は 6 文字まで。ワイルドカードで連続再生）                                     | —                              |
| `--clock 10` など                     | 対象機の MPU クロック（描画時間の見積もり。[mkscene](mkscene.md) の 1 章の `clock`）                                      | 10mhz                          |
| `--no-drop`                           | 間に合わないコマを飛ばさず、遅らせる                                                                                      | 飛ばす                         |
| `--no-fixed-cels`                     | 分割描画の区切りをその時の空き時間で決める（[mkscene](mkscene.md) の 7 章の `fixed_cels`）                                | 区切りを決めたセル             |
| `--wait tmwa／vwait`                  | 待ち方（[mkscene](mkscene.md) の 1 章の `wait`）                                                                          | vwait                          |
| `--adjust-every 秒`                   | 一定時間ごとの補正：この秒数ごとに待ちを `--adjust-frames` カウント足す（[mkscene](mkscene.md) の 1 章の `adjust_every`） | なし                           |
| `--adjust-frames N`                   | `--adjust-every` ごとに足すカウント（負＝早める、正＝遅らせる）                                                           | なし                           |
| `--timelog`                           | 再生時間を time.txt に書く（確認用）                                                                                      | —                              |
| `--sim`                               | 最後に pansim で確かめる                                                                                                  | しない                         |
| `--stop-at-s`                         | .s まで作って止める                                                                                                       | —                              |

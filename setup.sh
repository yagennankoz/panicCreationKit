#!/bin/sh
# setup.sh : panicCreationKit の準備（Linux・mac 用。Windows は setup.bat）
#   ./setup.sh [--samples] [--force] [--check]
# アセンブラ HAS v3.09・リンカ HLK v3.01・panic.x・Z-MUSIC をダウンロードして置く（tools/setup/setup.py）。
# Python 3.11 以上と、そのパッケージ（pip install -r requirements.txt）、ffmpeg、run68 は自分で入れる
# （docs/MANUAL.md の 2 章「Linux・mac で使う」）。Python は環境変数 PYTHON で指定できる（既定は python3）。
here=$(cd "$(dirname "$0")" && pwd)
exec "${PYTHON:-python3}" "$here/tools/setup/setup.py" "$@"

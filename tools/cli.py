"""cli.py : コマンドとして動かすツールの共通の入口（エラーを分かりやすいメッセージにする）

各ツールの最後で  sys.exit(cli.run(main))  とする。
- ファイルが無い、設定ファイルの書き方が違う、値が正しくない、外部コマンド（ffmpeg／run68）が失敗した、などは
  「エラー：…」の 1〜数行のメッセージにして、終了コード 1 で終わる（Python の例外の表示＝トレースバックは出さない）。
- 詳しい情報（トレースバック）が要るときは、環境変数 PANTOOL_DEBUG=1 を付けて実行する。
- ツールの中では、使う人への説明は SystemExit("メッセージ") で止める（これも「エラー：」を付けて表示する）。

設定の値を確かめる小さな関数（need_file、need_dir、check_number、check_choice、check_keys）もここに置く。
"""
import difflib
import os
import subprocess
import sys
import tomllib
from pathlib import Path

DEBUG = bool(os.environ.get("PANTOOL_DEBUG"))


def _say(msg: str):
    print(f"エラー：{msg}", file=sys.stderr)


def run(main, argv=None) -> int:
    """main(argv) を実行し、例外を分かりやすいメッセージにする。戻り値は終了コード"""
    argv = sys.argv if argv is None else argv
    try:
        rc = main(argv)
        return 0 if rc is None else rc
    except SystemExit as e:  # ツールが自分で止めたとき（メッセージ付き）、argparse の使い方エラー（コード 2）
        if isinstance(e.code, str):
            _say(e.code)
            return 1
        return e.code if isinstance(e.code, int) else 0
    except KeyboardInterrupt:
        _say("中断しました")
        return 130
    except Exception as e:  # noqa: BLE001  ここで全部受け止めて、使う人に分かる形にする
        _say(describe(e))
        if DEBUG:
            import traceback
            traceback.print_exc()
        else:
            print("  （詳しい情報は、環境変数 PANTOOL_DEBUG=1 を付けて実行すると表示されます）", file=sys.stderr)
        return 1


def describe(e: BaseException) -> str:
    """例外を日本語の説明にする"""
    if isinstance(e, FileNotFoundError):
        return f"ファイルが見つかりません：{e.filename or e}"
    if isinstance(e, IsADirectoryError):
        return f"ファイルの所にフォルダが指定されています：{e.filename}"
    if isinstance(e, NotADirectoryError):
        return f"フォルダの所にファイルが指定されています：{e.filename}"
    if isinstance(e, PermissionError):
        return f"ファイルを読み書きできません（使用中か、権限がありません）：{e.filename}"
    if isinstance(e, tomllib.TOMLDecodeError):
        return f"設定ファイル（TOML）の書き方が違います：{e}"
    if isinstance(e, UnicodeDecodeError):
        return "テキストファイルの文字コードを読めません（設定ファイルは UTF-8 で保存してください）"
    if isinstance(e, subprocess.CalledProcessError):
        cmd = e.cmd[0] if isinstance(e.cmd, (list, tuple)) else e.cmd
        err = e.stderr.decode("cp932", "replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        tail = "\n  ".join(err.strip().splitlines()[-5:])
        return f"外部コマンドが失敗しました（{Path(str(cmd)).name}、終了コード {e.returncode}）" + (f"\n  {tail}" if tail else "")
    try:
        from PIL import UnidentifiedImageError
        if isinstance(e, UnidentifiedImageError):
            return f"画像として読めないファイルです：{e}"
    except ImportError:
        pass
    if isinstance(e, MemoryError):
        return "パソコンのメモリが足りません（素材を小さく／短くしてください）"
    if isinstance(e, (ValueError, TypeError, KeyError, IndexError)):
        return f"入力の値が正しくありません（{type(e).__name__}：{e}）"
    return f"思わぬエラーが起きました（{type(e).__name__}：{e}）"


# ---- 設定の値を確かめる ----

def need_file(path, what="ファイル") -> Path:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"{what}が見つかりません：{p}")
    if not p.is_file():
        raise SystemExit(f"{what}の所にフォルダが指定されています：{p}")
    return p


def need_dir(path, what="フォルダ") -> Path:
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"{what}が見つかりません：{p}")
    if not p.is_dir():
        raise SystemExit(f"{what}の所にファイルが指定されています：{p}")
    return p


def check_number(where, key, value, *, integer=False, minimum=None, above=None, maximum=None, allow_none=True):
    """数の設定を確かめて返す。where は「層 bg」などの場所の説明"""
    if value is None:
        if allow_none:
            return None
        raise SystemExit(f"{where}：{key} を指定してください")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SystemExit(f"{where}：{key} は{'整数' if integer else '数'}で書いてください（今は {value!r}）")
    if integer and value != int(value):
        raise SystemExit(f"{where}：{key} は整数で書いてください（今は {value!r}）")
    if minimum is not None and value < minimum:
        raise SystemExit(f"{where}：{key} は {minimum} 以上にしてください（今は {value!r}）")
    if above is not None and value <= above:
        raise SystemExit(f"{where}：{key} は {above} より大きくしてください（今は {value!r}）")
    if maximum is not None and value > maximum:
        raise SystemExit(f"{where}：{key} は {maximum} 以下にしてください（今は {value!r}）")
    return int(value) if integer else value


def check_bool(where, key, value):
    if value is not None and not isinstance(value, bool):
        raise SystemExit(f"{where}：{key} は true か false で書いてください（今は {value!r}）")
    return value


def check_choice(where, key, value, choices):
    if value is not None and value not in choices:
        raise SystemExit(f"{where}：{key} は {'／'.join(map(str, choices))} のどれかにしてください（今は {value!r}）")
    return value


def check_keys(where, d: dict, known, other=(), other_where=""):
    """知らない項目（書き間違い）を見つけたら、近い名前を添えて止める。
    other は別の場所（例：層）に書く項目。そこに書くべき項目なら、そう教える。"""
    for k in d:
        if k in known:
            continue
        if k in other:
            raise SystemExit(f"{where}：{k!r} は{other_where}に書く項目です")
        near = difflib.get_close_matches(k, list(known) + list(other), n=1)
        hint = ""
        if near:
            hint = f"。{near[0]} の書き間違いではありませんか？" + (f"（{near[0]} は{other_where}に書く項目）"
                                                               if near[0] in other and other_where else "")
        raise SystemExit(f"{where}：知らない項目 {k!r} があります{hint}")


class ArgumentParser:
    """argparse.ArgumentParser の、エラーを日本語にしたもの（使い方の表示はそのまま）"""

    def __new__(cls, *args, **kw):
        import argparse
        import re

        class _P(argparse.ArgumentParser):
            def error(self, message):
                self.print_usage(sys.stderr)
                m = re.match(r"argument (\S+): invalid (\w+) value: '(.*)'", message)
                if m:
                    kind = {"float": "数", "int": "整数"}.get(m.group(2), m.group(2))
                    raise SystemExit(f"{m.group(1)} の値 {m.group(3)!r} が正しくありません（{kind}で書いてください）")
                m = re.match(r"argument (\S+): invalid choice: '(.*)' \(choose from (.*)\)", message)
                if m:
                    raise SystemExit(f"{m.group(1)} は {m.group(3)} のどれかにしてください（今は {m.group(2)!r}）")
                m = re.match(r"argument (\S+): expected one argument", message)
                if m:
                    raise SystemExit(f"{m.group(1)} の後に値を書いてください")
                m = re.match(r"unrecognized arguments: (.*)", message)
                if m:
                    raise SystemExit(f"知らないオプションか、余分な引数があります：{m.group(1)}（-h で使い方を表示）")
                m = re.match(r"the following arguments are required: (.*)", message)
                if m:
                    raise SystemExit(f"{m.group(1)} を指定してください（-h で使い方を表示）")
                raise SystemExit(message)

        return _P(*args, **kw)


def check_args(argv, allowed, n_positional):
    """オプション（-- で始まるもの）と、それ以外の引数の数を確かめる"""
    opts = [a for a in argv if a.startswith("--")]
    pos = [a for a in argv if not a.startswith("--")]
    for o in opts:
        if o not in allowed:
            raise SystemExit(f"知らないオプション {o} があります（使えるのは {'、'.join(allowed) or 'なし'}）")
    if len(pos) != n_positional:
        return None
    return pos

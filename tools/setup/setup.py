"""setup.py : 使うツール（ffmpeg、run68x、HAS060X、HLK evolution、panic.x／sch.h）を自動でダウンロードして置く

使い方:  python tools/setup/setup.py [--samples] [--force] [--check]
  （ふつうは一番上の setup.bat から呼ばれる。Python を自分で用意したときは、このファイルを直接動かしてもよい）

  --samples  サンプルの素材も用意する（テストアニメの PNG を作り、Big Buck Bunny 10 秒をダウンロードする）
  --force    すでに置いてあっても、ダウンロードし直す
  --check    ダウンロードはせず、そろっているかだけ調べる

  何をどこから取るかは tools/setup/deps.json（版と SHA-256 を固定）。ダウンロードした物は runtime/downloads/ に残し、
  2 回目からはそれを使う（SHA-256 が合えば）。プロキシは環境変数 HTTPS_PROXY／HTTP_PROXY に従う。
"""
import hashlib
import io
import json
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))
import lha  # noqa: E402

CACHE = ROOT / "runtime" / "downloads"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def download(dep, force):
    """ダウンロードして中身（bytes）を返す。キャッシュがあり SHA-256 が合えばそれを使う"""
    name = dep["url"].rsplit("/", 1)[-1].replace("%2B", "+")
    cached = CACHE / name
    if cached.exists() and not force:
        data = cached.read_bytes()
        if dep.get("sha256") is None or sha256(data) == dep["sha256"]:
            print(f"  （ダウンロード済み：{cached.relative_to(ROOT)}）")
            return data
    size = dep.get("size")
    print(f"  ダウンロード：{dep['url']}" + (f"（{size / 1e6:.1f}MB）" if size else ""))
    req = urllib.request.Request(dep["url"], headers={"User-Agent": "panicCreationKitForWin-setup"})
    buf = io.BytesIO()
    with urllib.request.urlopen(req, timeout=60) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done, last = 0, -1
        while True:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            buf.write(chunk)
            done += len(chunk)
            if total > 4_000_000:
                pct = done * 100 // total
                if pct // 10 != last:
                    last = pct // 10
                    print(f"    {pct}%", flush=True)
    data = buf.getvalue()
    if dep.get("sha256") and sha256(data) != dep["sha256"]:
        raise SystemExit(f"{dep['name']}：ダウンロードした物の SHA-256 が合いません（壊れているか、配布元で差し替えられた）。\n"
                         f"  期待 {dep['sha256']}\n  実際 {sha256(data)}")
    CACHE.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(data)
    return data


def unpack(dep, data):
    """files の中身を取り出して置く"""
    kind = dep["kind"]
    if kind == "zip":
        z = zipfile.ZipFile(io.BytesIO(data))
        get = z.read
    elif kind == "lzh":  # 「書庫!中のファイル」は、書庫の中の書庫から取り出す
        files = lha.extract(data, {f["from"].split("!")[0] for f in dep["files"]})
        nested = {}

        def get(name):
            if "!" not in name:
                return files[name]
            outer, inner = name.split("!", 1)
            if outer not in nested:
                nested[outer] = lha.extract(files[outer])
            return nested[outer][inner]
    else:
        def get(_):
            return data
    for f in dep["files"]:
        dst = ROOT / f["to"]
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(get(f["from"]))
        print(f"    -> {f['to']}")


def have(dep):
    return all((ROOT / f["to"]).exists() for f in dep["files"])


def install(deps, force, check):
    missing = []
    for dep in deps:
        ok = have(dep)
        print(f"■ {dep['name']}：{dep['what']}" + ("（あり）" if ok and not force else ""))
        if check:
            if not ok:
                missing.append(dep["name"])
            continue
        if ok and not force:
            continue
        unpack(dep, download(dep, force))
    return missing


def make_samples():
    """テストアニメの PNG（git に入れていない）を作る"""
    py = sys.executable
    for args in (["samples/anim2", "32", "--static"], ["samples/anim1", "32"], ["--layers"]):
        print(f"  pt make_test_anim {' '.join(args)}")
        subprocess.run([py, str(ROOT / "tools" / "make_test_anim.py"), *args], cwd=ROOT, check=True)


def main(argv):
    force, check = "--force" in argv, "--check" in argv
    m = json.loads((HERE / "deps.json").read_text(encoding="utf-8"))
    print(f"panicCreationKitForWin のセットアップ（{ROOT}）")
    missing = install(m["deps"], force, check)
    if "--samples" in argv:
        missing += install(m["samples"], force, check)
        if not check:
            print("■ テストアニメの PNG を作る")
            make_samples()
    try:
        import numpy  # noqa: F401
        import PIL  # noqa: F401
    except ImportError as e:
        missing.append(f"Python のパッケージ（{e.name}。pip install -r requirements.txt）")
    if missing:
        print("足りないもの：" + "、".join(missing))
        return 1
    print("そろいました。使い方は docs/MANUAL.md（例：pt mkanim samples\\anim2 test1 --diff）")
    return 0


if __name__ == "__main__":
    import cli
    sys.exit(cli.run(lambda argv: main(argv[1:])))

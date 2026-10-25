# bootstrap.ps1 : panicCreationKitForWin の最初の準備（setup.bat から呼ばれる）
#  1. 持ち運べる Python（埋め込み版）を runtime\python にダウンロードして展開する（Windows に Python が無くてよい）
#  2. pip と、ツールが使う Python のパッケージ（requirements.txt：Pillow、numpy）を入れる
#  3. tools\setup\setup.py で、ffmpeg・run68x・HAS060X・HLK evolution・panic.x などをダウンロードする
# 引数はそのまま setup.py に渡す（--samples、--force、--check）。
# PowerShell のモジュール（Get-FileHash、Expand-Archive など）は環境によって読めないことがあるので、.NET を直接使う。
param([Parameter(ValueFromRemainingArguments = $true)] $Rest)
# 外部のプログラム（python、pip）がエラー出力に書いても止まらないよう、Stop にはしない（終了コードで判断する）
$ErrorActionPreference = "Continue"
trap { Write-Host "エラー：$_"; exit 1 }
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Add-Type -AssemblyName System.IO.Compression.FileSystem

$Root = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$Runtime = Join-Path $Root "runtime"
$PyDir = Join-Path $Runtime "python"
$Py = Join-Path $PyDir "python.exe"
$Downloads = Join-Path $Runtime "downloads"

$PyVersion = "3.13.17"
$PyZipName = "python-$PyVersion-embed-amd64.zip"
$PyUrl = "https://www.python.org/ftp/python/$PyVersion/$PyZipName"
$PySha256 = "9e35319bffedab8b36ad44d8f377cb4f1733bcec257a0b6d04d94f01486ddb38"

function Get-File($Url, $Path) {
    Write-Host "  ダウンロード：$Url"
    $wc = New-Object Net.WebClient
    $wc.Headers.Add("User-Agent", "panicCreationKitForWin-setup")
    $wc.DownloadFile($Url, $Path)
}

function Get-Sha256($Path) {
    $sha = [Security.Cryptography.SHA256]::Create()
    $fs = [IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($sha.ComputeHash($fs)) -replace "-", "").ToLower() }
    finally { $fs.Dispose() }
}

[IO.Directory]::CreateDirectory($Downloads) | Out-Null

if (-not [IO.File]::Exists($Py)) {
    Write-Host "■ Python $PyVersion（埋め込み版）を runtime\python に用意します"
    $Zip = Join-Path $Downloads $PyZipName
    if (-not [IO.File]::Exists($Zip)) { Get-File $PyUrl $Zip }
    $Hash = Get-Sha256 $Zip
    if ($Hash -ne $PySha256) {
        [IO.File]::Delete($Zip)
        throw "Python のダウンロードの SHA-256 が合いません（$Hash）。もう一度 setup.bat を実行してください"
    }
    if ([IO.Directory]::Exists($PyDir)) { [IO.Directory]::Delete($PyDir, $true) }
    [IO.Compression.ZipFile]::ExtractToDirectory($Zip, $PyDir)
}
# 埋め込み版の Python の設定（._pth）：site-packages を読む（import site）、tools フォルダを入れる
# （埋め込み版は、動かすスクリプトのフォルダを sys.path に入れないため。各ツールが互いを import できるように）
foreach ($Pth in [IO.Directory]::GetFiles($PyDir, "python*._pth")) {
    $Lines = @([IO.File]::ReadAllLines($Pth) | ForEach-Object { $_ -replace "^#\s*import site", "import site" })
    $Lines = @($Lines | Where-Object { $_ -notmatch "ools$" })   # 前に書いた tools の行は消して書き直す
    $Lines += "..\..\tools"
    [IO.File]::WriteAllLines($Pth, $Lines)
}

& cmd.exe /c "`"`"$Py`" -m pip --version >nul 2>&1`""   # cmd の決まりで、全体をもう一組の引用符で囲む
if ($LASTEXITCODE -ne 0) {
    Write-Host "■ pip を入れます"
    $GetPip = Join-Path $Downloads "get-pip.py"
    Get-File "https://bootstrap.pypa.io/get-pip.py" $GetPip
    & $Py $GetPip --no-warn-script-location
    if ($LASTEXITCODE -ne 0) { throw "pip を入れられませんでした" }
}

Write-Host "■ Python のパッケージ（requirements.txt）を入れます"
& $Py -m pip install --disable-pip-version-check --no-warn-script-location -q -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "Python のパッケージを入れられませんでした" }

& $Py (Join-Path $Root "tools\setup\setup.py") @Rest
exit $LASTEXITCODE

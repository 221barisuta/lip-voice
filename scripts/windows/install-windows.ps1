# LipVoice installer for Windows 11 (no administrator rights needed except for the optional VC++ runtime).
# 管理者権限は不要です（VC++ ランタイムが無い場合だけ許可を求められます）。システム設定は変えず、C:\LipVoice だけに入れます。
# Usage: install.cmd   (or: powershell -ExecutionPolicy Bypass -File install-windows.ps1 [-Root C:\LipVoice] [-Profile patient])
param(
  [string]$Root = "C:\LipVoice",
  [string]$Profile = "patient"
)
$ErrorActionPreference = "Stop"
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

function Step($msg) { Write-Host ""; Write-Host "== $msg" -ForegroundColor Cyan }

if (-not [Environment]::Is64BitOperatingSystem) { throw "64-bit Windows is required. 64bit の Windows が必要です" }
if ($Profile -in @("default", "test")) { throw "Profile name must not be 'default' or 'test' (those are for developer tests). 開発者のテスト用の名前は使えません" }
if ($Root -match '[^\x20-\x7E]') { throw "Install path must be ASCII only (e.g. C:\LipVoice). 英数字だけのパスにしてください" }

Step "1/7 Checking the package (ハッシュの確認)"
$manifest = Join-Path $Here "MANIFEST.sha256"
if (Test-Path $manifest) {
  $bad = 0
  Get-Content $manifest | ForEach-Object {
    if ($_ -match '^([0-9a-fA-F]{64})\s+(.+)$') {
      $f = Join-Path $Here $Matches[2]
      if (-not (Test-Path $f)) { Write-Host "MISSING: $($Matches[2])" -ForegroundColor Red; $bad++ }
      elseif ((Get-FileHash $f -Algorithm SHA256).Hash -ne $Matches[1].ToUpper()) { Write-Host "BROKEN: $($Matches[2])" -ForegroundColor Red; $bad++ }
    }
  }
  if ($bad -gt 0) { throw "$bad file(s) are missing or broken. Copy the package again. ファイルが欠けているか壊れています。コピーし直してください" }
  Write-Host "OK"
} else { Write-Host "MANIFEST.sha256 not found (skipped)" -ForegroundColor Yellow }

Step "2/7 Folders (フォルダ)"
New-Item -ItemType Directory -Force -Path $Root, "$Root\data\assets", "$Root\data\$Profile" | Out-Null

Step "3/7 VC++ runtime"
if (-not (Test-Path "$env:windir\System32\msvcp140.dll")) {
  $vc = Join-Path $Here "vendor\vc_redist.x64.exe"
  if (-not (Test-Path $vc)) { throw "msvcp140.dll is missing and vendor\vc_redist.x64.exe is not in the package" }
  Write-Host "Installing VC++ runtime (a permission prompt may appear / 許可の確認が出ます)"
  $p = Start-Process $vc -ArgumentList "/install", "/quiet", "/norestart" -Wait -PassThru
  if ($p.ExitCode -eq 3010) { Write-Host "A restart is needed later (再起動が必要です。あとで再起動してください)" -ForegroundColor Yellow }
  elseif ($p.ExitCode -ne 0) { throw "VC++ runtime installer failed (exit code $($p.ExitCode))" }
} else { Write-Host "already installed" }

Step "4/7 Python (専用の Python。他のソフトの環境は変えません)"
$py = "$Root\python\python.exe"
if (-not (Test-Path $py)) {
  $installer = Get-ChildItem (Join-Path $Here "vendor") -Filter "python-3.1*-amd64.exe" | Select-Object -First 1
  if (-not $installer) { throw "Python installer is not in vendor\" }
  $p = Start-Process $installer.FullName -ArgumentList "/quiet", "InstallAllUsers=0", "TargetDir=$Root\python", "PrependPath=0",
       "Include_launcher=0", "Include_test=0", "Include_doc=0", "Include_pip=1", "Shortcuts=0", "AssociateFiles=0" -Wait -PassThru
  if ($p.ExitCode -ne 0 -or -not (Test-Path $py)) { throw "Python installer failed (exit code $($p.ExitCode))" }
}
& $py --version

Step "5/7 LipVoice (オフラインで入れます)"
if (-not (Test-Path "$Root\venv\Scripts\python.exe")) { & $py -m venv "$Root\venv" }
$vpy = "$Root\venv\Scripts\python.exe"
& $vpy -m pip install --no-index --find-links (Join-Path $Here "wheels") --upgrade lipvoice
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Step "6/7 Model and settings (顔検出モデルと設定)"
Copy-Item (Join-Path $Here "vendor\face_landmarker.task") "$Root\data\assets\face_landmarker.task" -Force
$cfg = "$Root\data\$Profile\config.json"
if (-not (Test-Path $cfg)) { Copy-Item (Join-Path $Here "profiles\patient.config.json") $cfg } else { Write-Host "config.json already exists (kept)" }
foreach ($f in "run.cmd", "bench.cmd", "cameras.cmd", "train.cmd") { Copy-Item (Join-Path $Here $f) "$Root\$f" -Force }
New-Item -ItemType Directory -Force -Path "$Root\docs" | Out-Null
Copy-Item (Join-Path $Here "docs\*") "$Root\docs" -Force -ErrorAction SilentlyContinue

Step "7/7 Shortcuts (デスクトップのショートカット)"
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
foreach ($pair in @(@("LipVoice", "run.cmd"), @("LipVoice check (bench)", "bench.cmd"))) {
  $lnk = $ws.CreateShortcut((Join-Path $desktop "$($pair[0]).lnk"))
  $lnk.TargetPath = "$Root\$($pair[1])"; $lnk.WorkingDirectory = $Root; $lnk.Save()
}

Write-Host ""
Write-Host "Installed to $Root. Cameras on this PC / このPCのカメラ:" -ForegroundColor Green
Get-PnpDevice -Class Camera, Image -ErrorAction SilentlyContinue | Select-Object Status, FriendlyName | Format-Table -AutoSize
Write-Host "Next: 1) double-click 'LipVoice check (bench)' with the patient in the usual posture."
Write-Host "      2) see docs\day0-checklist.md   次は、いつもの姿勢で『LipVoice check (bench)』を実行してください。"
Write-Host "To uninstall: delete $Root and the two desktop shortcuts. 消すときは $Root とショートカットを削除するだけです。"

Param(
  [string]$Python = "python",
  [string]$AppName = "lab_system_server"
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

Write-Host "==> Repo root: $RepoRoot"
Write-Host "==> Installing build dependencies..."
& $Python -m pip install --upgrade pip
& $Python -m pip install -r (Join-Path $RepoRoot "requirements.txt")
& $Python -m pip install pyinstaller

# 与 src/core/config.py 一致：静态资源进 _MEIPASS，数据库/上传在 exe 旁
$launcher = @'
import uvicorn
from src.main import app
from src.core.config import settings

if __name__ == "__main__":
    uvicorn.run(app, host=settings.HOST, port=settings.PORT)
'@

$tmpFile = Join-Path $RepoRoot "scripts\_build_launcher_windows.py"
Set-Content -Path $tmpFile -Value $launcher -Encoding UTF8

# PyInstaller --add-data 在 Windows 上为 `源;目标`（目标为解压根目录下的相对路径）
$addData = @(
  "--add-data", "web;web",
  "--add-data", "alembic;alembic",
  "--add-data", "alembic.ini;."
)
if (Test-Path (Join-Path $RepoRoot ".env.example")) {
  $addData += @("--add-data", ".env.example;.")
}

Write-Host "==> Building Windows exe (onefile + bundled web/alembic)..."
& $Python -m PyInstaller `
  --clean `
  --noconfirm `
  --onefile `
  --name $AppName `
  --paths $RepoRoot `
  --collect-submodules src `
  --collect-submodules uvicorn `
  @addData `
  $tmpFile

if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force }

$distExe = Join-Path $RepoRoot "dist\$AppName.exe"
Write-Host "==> Done. Output: $distExe"
Write-Host ""
Write-Host "使用说明:"
Write-Host "  1. 将 $AppName.exe 拷到任意文件夹，双击运行（会打开控制台）。"
Write-Host "  2. 首次运行在同目录生成 data/、uploads/ 及 SQLite 库（默认 sqlite:///./data/lab_system.db）。"
Write-Host "  3. 浏览器访问 http://127.0.0.1:8808/login.html（端口可在同目录 .env 中设置 PORT）。"
Write-Host "  4. 可选：复制 .env.example 为 .env 后修改 SECRET_KEY、DATABASE_URL 等。"

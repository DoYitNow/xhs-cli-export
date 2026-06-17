# xhs-cli-export 安装脚本 (Windows PowerShell)
# 用法: .\install.ps1

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  xhs-cli-export 安装脚本" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# 检查 Python 版本
Write-Host "[1/4] 检查 Python 版本..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "错误: 未找到 Python，请先安装 Python 3.10+" -ForegroundColor Red
    exit 1
}
Write-Host "  $pythonVersion" -ForegroundColor Green

# 检查 xhs-cli-headless
Write-Host ""
Write-Host "[2/4] 检查 xhs-cli-headless..." -ForegroundColor Yellow
$xhsPath = Get-Command xhs -ErrorAction SilentlyContinue
if ($xhsPath) {
    $xhsVersion = xhs --version 2>&1
    Write-Host "  已安装: $xhsVersion" -ForegroundColor Green
} else {
    Write-Host "  未找到 xhs-cli-headless" -ForegroundColor Yellow
    Write-Host ""
    $installXhs = Read-Host "是否安装 xhs-cli-headless? (y/n)"
    if ($installXhs -eq "y") {
        Write-Host "  正在安装 xhs-cli-headless..." -ForegroundColor Yellow
        $hasUv = Get-Command uv -ErrorAction SilentlyContinue
        if ($hasUv) {
            uv tool install xhs-cli-headless
        } else {
            $hasPipx = Get-Command pipx -ErrorAction SilentlyContinue
            if ($hasPipx) {
                pipx install xhs-cli-headless
            } else {
                pip install xhs-cli-headless
            }
        }
        Write-Host "  安装完成" -ForegroundColor Green
    } else {
        Write-Host "  跳过安装。请稍后手动安装: uv tool install xhs-cli-headless" -ForegroundColor Yellow
    }
}

# 安装依赖
Write-Host ""
Write-Host "[3/4] 安装依赖 (requests)..." -ForegroundColor Yellow
pip install requests --quiet
Write-Host "  安装完成" -ForegroundColor Green

# 检查登录状态
Write-Host ""
Write-Host "[4/4] 检查小红书登录状态..." -ForegroundColor Yellow
$xhsExe = Get-Command xhs -ErrorAction SilentlyContinue
if ($xhsExe) {
    $doctorResult = xhs auth doctor --json 2>&1
    if ($doctorResult -match '"authenticated":\s*true') {
        Write-Host "  已登录" -ForegroundColor Green
    } else {
        Write-Host "  未登录" -ForegroundColor Yellow
        Write-Host ""
        $doLogin = Read-Host "是否现在登录? (y/n)"
        if ($doLogin -eq "y") {
            Write-Host "  正在生成二维码..." -ForegroundColor Yellow
            xhs login --qr-output ".\xhs-login-qr.png" --print-link
            Write-Host ""
            Write-Host "  请扫描二维码完成登录" -ForegroundColor Cyan
            Write-Host "  二维码已保存到: xhs-login-qr.png" -ForegroundColor Cyan
        }
    }
} else {
    Write-Host "  跳过（xhs-cli-headless 未安装）" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  安装完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "使用方法:" -ForegroundColor White
Write-Host "  python src/xhs_export.py check                    # 检查状态" -ForegroundColor Gray
Write-Host "  python src/xhs_export.py export --source favorites  # 导出收藏" -ForegroundColor Gray
Write-Host "  python src/xhs_export.py export --source likes      # 导出点赞" -ForegroundColor Gray
Write-Host ""

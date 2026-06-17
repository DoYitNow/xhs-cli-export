# xhs-cli-export 快速导出脚本 (Windows PowerShell)
# 用法:
#   .\export.ps1 favorites              # 导出收藏
#   .\export.ps1 likes                  # 导出点赞
#   .\export.ps1 favorites ./my-notes   # 导出到指定目录

param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("favorites", "likes")]
    [string]$Source,

    [Parameter(Position=1)]
    [string]$OutputDir = ".",

    [switch]$NoImages,
    [switch]$DryRun,
    [int]$Max = 0
)

# 构建命令
$cmd = "python src/xhs_export.py export --source $Source --output-dir `"$OutputDir`""

if ($NoImages) {
    $cmd += " --no-images"
}
if ($DryRun) {
    $cmd += " --dry-run"
}
if ($Max -gt 0) {
    $cmd += " --max $Max"
}

Write-Host "执行命令: $cmd" -ForegroundColor Cyan
Write-Host ""

# 执行
Invoke-Expression $cmd

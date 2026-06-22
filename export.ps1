# xhs-cli-export 快速导出脚本 (Windows PowerShell)
# 用法:
#   .\export.ps1 favorites              # 导出收藏
#   .\export.ps1 likes                  # 导出点赞
#   .\export.ps1 search "React 教程"    # 搜索导出
#   .\export.ps1 favorites ./my-notes   # 导出到指定目录

param(
    [Parameter(Position=0, Mandatory=$true)]
    [ValidateSet("favorites", "likes", "search")]
    [string]$Source,

    [Parameter(Position=1)]
    [string]$KeywordOrOutputDir = ".",

    [string]$Sort = "general",
    [ValidateSet("all", "video", "image")]
    [string]$SearchType = "all",
    [switch]$NoImages,
    [switch]$DryRun,
    [int]$Max = 0
)

# 构建命令
if ($Source -eq "search") {
    # For search, second arg is keyword
    $Keyword = $KeywordOrOutputDir
    if (-not $Keyword -or $Keyword -eq ".") {
        Write-Host "错误: search 来源需要提供关键词" -ForegroundColor Red
        exit 1
    }
    $cmd = "python src/xhs_export.py export --source search --keyword `"$Keyword`" --sort $Sort --search-type $SearchType"
} else {
    # For favorites/likes, second arg is output dir
    $cmd = "python src/xhs_export.py export --source $Source --output-dir `"$KeywordOrOutputDir`""
}

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

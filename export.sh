#!/bin/bash
# xhs-cli-export 快速导出脚本 (Linux/macOS)
# 用法:
#   ./export.sh favorites              # 导出收藏
#   ./export.sh likes                  # 导出点赞
#   ./export.sh search "React 教程"    # 搜索导出
#   ./export.sh favorites ./my-notes   # 导出到指定目录

set -e

# 检查参数
if [ $# -lt 1 ]; then
    echo "用法: $0 <favorites|likes|search> [关键词或输出目录] [选项]"
    echo ""
    echo "示例:"
    echo "  $0 favorites              # 导出收藏到当前目录"
    echo "  $0 likes ./my-notes       # 导出点赞到指定目录"
    echo "  $0 search \"React 教程\"    # 搜索并导出"
    echo "  $0 search \"租房\" . --sort popular  # 按热度排序"
    echo "  $0 favorites . --no-images # 不下载图片"
    echo "  $0 likes . --dry-run       # 预览模式"
    exit 1
fi

SOURCE=$1
shift

# 验证来源
if [ "$SOURCE" != "favorites" ] && [ "$SOURCE" != "likes" ] && [ "$SOURCE" != "search" ]; then
    echo "错误: 来源必须是 favorites、likes 或 search"
    exit 1
fi

if [ "$SOURCE" = "search" ]; then
    # For search, first arg is keyword
    if [ $# -lt 1 ] || [ -z "$1" ]; then
        echo "错误: search 来源需要提供关键词"
        exit 1
    fi
    KEYWORD="$1"
    shift
    CMD="python src/xhs_export.py export --source search --keyword \"$KEYWORD\""
    # Parse remaining options
    while [ $# -gt 0 ]; do
        case "$1" in
            --sort)
                shift
                CMD="$CMD --sort $1"
                ;;
            --search-type)
                shift
                CMD="$CMD --search-type $1"
                ;;
            --no-images)
                CMD="$CMD --no-images"
                ;;
            --dry-run)
                CMD="$CMD --dry-run"
                ;;
            --max)
                shift
                CMD="$CMD --max $1"
                ;;
            --output-dir)
                shift
                CMD="$CMD --output-dir \"$1\""
                ;;
            *)
                echo "未知参数: $1"
                exit 1
                ;;
        esac
        shift
    done
else
    # For favorites/likes
    OUTPUT_DIR=${1:-"."}
    shift
    CMD="python src/xhs_export.py export --source $SOURCE --output-dir \"$OUTPUT_DIR\""
    # 处理额外参数
    while [ $# -gt 0 ]; do
        case "$1" in
            --no-images)
                CMD="$CMD --no-images"
                ;;
            --dry-run)
                CMD="$CMD --dry-run"
                ;;
            --max)
                shift
                CMD="$CMD --max $1"
                ;;
            *)
                echo "未知参数: $1"
                exit 1
                ;;
        esac
        shift
    done
fi

echo "执行命令: $CMD"
echo ""

# 执行
eval $CMD

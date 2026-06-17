#!/bin/bash
# 基础使用示例

# 1. 检查登录状态
echo "=== 检查登录状态 ==="
python src/xhs_export.py check

# 2. 导出收藏到当前目录
echo ""
echo "=== 导出收藏 ==="
python src/xhs_export.py export --source favorites

# 3. 导出点赞到指定目录
echo ""
echo "=== 导出点赞 ==="
python src/xhs_export.py export --source likes --output-dir ./my-likes

# 4. 快速预览（不抓详情）
echo ""
echo "=== 快速预览 ==="
python src/xhs_export.py export --source favorites --max 10 --no-fetch-details --dry-run

# 5. 全量历史导出
echo ""
echo "=== 全量导出 ==="
python src/xhs_export.py export --source likes --all-history

# 6. 不下载图片
echo ""
echo "=== 不下载图片 ==="
python src/xhs_export.py export --source favorites --no-images

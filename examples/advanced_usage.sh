#!/bin/bash
# 高级使用示例

# 1. 指定 xhs 路径
python src/xhs_export.py export --source favorites \
  --xhs-bin ~/.xiaohongshu-cli/headless-venv/Scripts/xhs.exe

# 2. 使用环境变量指定 xhs 路径
export XHS_EXPORT_XHS_BIN=~/.xiaohongshu-cli/headless-venv/Scripts/xhs.exe
python src/xhs_export.py export --source likes

# 3. 从已有 JSON 文件离线转换
python src/xhs_export.py export --source favorites \
  --input-json ./favorites_raw.json

# 4. 重置增量状态后全量导出
python src/xhs_export.py export --source favorites \
  --reset-state --all-history

# 5. 仅重置状态（不导出）
python src/xhs_export.py export --source favorites \
  --reset-state --reset-state-only

# 6. 包含远程图片 URL
python src/xhs_export.py export --source likes \
  --include-media-urls

# 7. 限制每条笔记图片数量
python src/xhs_export.py export --source favorites \
  --max-images-per-note 5

# 8. 覆盖已存在的文件
python src/xhs_export.py export --source likes \
  --overwrite

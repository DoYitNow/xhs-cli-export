---
name: xiaohongshu-export
description: "通过 xhs-cli（逆向工程 API）将小红书收藏或点赞笔记增量导出为 Markdown 文件，支持流式详情获取、图片下载和增量状态管理。适用于任何目录。当用户要求导出、同步、导入小红书收藏夹 / 点赞 / favorites / liked notes 时使用此 Skill。"
---

# 小红书笔记导出

将小红书收藏或点赞记录导出为结构化 Markdown 文件。纯导出工具，不绑定任何知识库体系。

推荐入口：`xhs export favorites ...` 或 `xhs export likes ...`

内部导出引擎：`xhs_export.py`（需要单独安装或复制到项目中）

## 前置要求

1. 安装 [xhs-cli-headless](https://github.com/kyalpha313/xhs-cli-headless)
2. 完成小红书登录

```powershell
# 安装 xhs-cli-headless
uv tool install xhs-cli-headless
# 或
pipx install xhs-cli-headless

# 检查登录状态
xhs auth doctor --json

# 如果未登录，使用二维码登录
xhs login --qr-output ".\xhs-login-qr.png" --print-link
```

## 预检查

```powershell
xhs auth doctor --json
```

当前全局 `xhs` 是基于逆向工程 API 的 CLI（`Xiaohongshu CLI via reverse-engineered API`）。如果 PATH 异常，可临时指定稳定路径：

```text
C:\Users\<username>\.xiaohongshu-cli\headless-venv\Scripts\xhs.exe
```

如果 `auth doctor` 显示 `Session expired`、`invalid`、`missing` 或需要验证，优先让用户在正常浏览器完成小红书登录/验证，然后导入字段：

```powershell
xhs auth import-fields --interactive
```

如果用户明确要二维码登录，使用 CLI 输出 PNG 二维码：

```powershell
xhs login --qr-output ".\xhs-login-qr.png" --print-link
```

如果二维码流程返回 `QR login requires verification`，不要反复重试；改为浏览器验证后执行 `auth import-fields --interactive`。

## 来源选择

除非用户要求同时导出，否则只选一个来源：

| 用户意图 | 来源 |
|---|---|
| 收藏、收藏夹、favorites、collected notes | `favorites` |
| 点赞、赞过、liked notes | `likes` |
| 两者 / 全部 | 先导出 `favorites`，再导出 `likes` |

如果用户未指定来源，导出前先简短询问。

## 导出

默认导出为增量模式，并默认获取笔记详情（正文 + 每篇笔记的全部图片）。`--max 0` 表示不限量，也是默认值。

```powershell
# 导出到当前目录（不限量，完整详情）
xhs export likes

# 指定输出目录
xhs export favorites --output-dir "D:\Desktop\my-notes"

# 快速抽样预览，不抓详情
xhs export likes --max 100 --no-fetch-details --dry-run
```

不要绕过 CLI 直接写临时爬虫。如果 `xhs export` 失败，报告错误并停止。

仅在用户明确要求快速列表或抽样时才使用 `--no-fetch-details`，因为它通常只有封面图且可能缺正文。使用 `--dry-run` 预览路径。仅在用户明确要求全量历史导入时使用 `--all-history`。仅在用户明确要求清除此来源的增量检查点时使用 `--reset-state --reset-state-only`。

**注意**: `xhs export` 会调用导出脚本，脚本再调用 xhs CLI 通过逆向工程 API 获取收藏/点赞数据。完整详情模式（默认）采用流式加载：逐条接收笔记列表，每收到一条立即获取详情并导出 Markdown，实时显示进度。快速模式（`--no-fetch-details`）以 NDJSON 流式输出列表，不抓详情页。脚本会保存 `<source>_stream.jsonl`，若中途会话过期/风控，已写出的 Markdown 会保留，但不会推进增量 checkpoint；修复登录后可以安全重跑。

额外可用选项：
- `--save-images / --no-images`：是否下载笔记图片（默认下载）
- `--max-images-per-note N`：每条笔记最多保存的图片数（默认 20）
- `--include-media-urls`：在 Markdown 中包含远程图片 URL

## 输出结构

```text
<output-dir>/
  <source>-<run-id>/
    0001-<title>--<note_id>.md
    _xhs_export_index.md
    <source>_raw.json
    details/<note_id>.json        # 仅 --fetch-details 时
    images/<note_id>/image-01.jpg
  xhs_state.json
```

## 后续步骤

导出后报告：导出来源和数量、增量窗口、输出目录路径、是否有失败项。

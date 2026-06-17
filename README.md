# xhs-cli-export

> 📕 小红书收藏/点赞笔记导出为 Markdown 的工具

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

基于 [xhs-cli-headless](https://github.com/kyalpha313/xhs-cli-headless) 的逆向工程 API，将小红书收藏和点赞导出为结构化 Markdown 文件。

## ✨ 功能特性

- 📝 **Markdown 导出** — 带 frontmatter 的结构化输出，兼容 Obsidian 等笔记软件
- 🔄 **增量同步** — 智能跳过已导出的笔记，避免重复
- 📸 **图片下载** — 自动下载笔记图片到本地
- 💾 **崩溃恢复** — JSONL 流式保存，中断不丢失进度
- 🔁 **自动重试** — 应对浏览器滚动提前停止的情况
- 📊 **进度显示** — 实时显示导出进度和预估时间

## 🚀 快速开始

### 方式一：一键安装（推荐）

```bash
# 克隆仓库
git clone https://github.com/yuyitian/xhs-cli-export.git
cd xhs-cli-export

# 运行安装脚本（自动安装依赖和检查登录）
# Windows PowerShell
.\install.ps1

# Linux/macOS
chmod +x install.sh
./install.sh
```

### 方式二：手动安装

```bash
# 1. 安装 xhs-cli-headless（提供小红书 API 访问能力）
uv tool install xhs-cli-headless
# 或
pipx install xhs-cli-headless

# 2. 登录小红书
xhs login --qr-output ./xhs-login-qr.png --print-link

# 3. 安装本工具的依赖
pip install requests
```

## 📖 使用方法

### 基础用法

```bash
# 检查登录状态
python src/xhs_export.py check

# 导出收藏到当前目录
python src/xhs_export.py export --source favorites

# 导出点赞到指定目录
python src/xhs_export.py export --source likes --output-dir ./my-notes
```

### 常用场景

```bash
# 快速预览（不抓详情，只看列表）
python src/xhs_export.py export --source favorites --max 50 --no-fetch-details --dry-run

# 导出最近 100 条收藏
python src/xhs_export.py export --source favorites --max 100

# 全量历史导出（忽略增量状态）
python src/xhs_export.py export --source likes --all-history

# 不下载图片（更快）
python src/xhs_export.py export --source favorites --no-images

# 重置增量状态后重新导出
python src/xhs_export.py export --source favorites --reset-state
```

### 完整参数

| 参数 | 说明 | 默认值 |
|---|---|---|
| `--source` | 导出来源：`favorites` / `likes` | 必填 |
| `--max` | 最大加载数量（0=不限） | 0 |
| `--limit` | 只转换前 N 条 | 0 |
| `--output-dir` | 输出目录 | 当前目录 |
| `--state-file` | 增量状态文件路径 | `<output-dir>/xhs_state.json` |
| `--fetch-details` | 获取笔记详情（正文+全部图片） | 默认开启 |
| `--no-fetch-details` | 跳过详情页抓取 | - |
| `--save-images` | 下载笔记图片 | 默认开启 |
| `--no-images` | 不下载图片 | - |
| `--max-images-per-note` | 每条笔记最多保存图片数 | 20 |
| `--include-media-urls` | 在 Markdown 中包含远程图片 URL | false |
| `--all-history` | 忽略增量状态，导出所有记录 | false |
| `--reset-state` | 运行前清除增量状态 | false |
| `--overwrite` | 覆盖已生成的文件 | false |
| `--dry-run` | 预览模式，不写入文件 | false |
| `--xhs-bin` | 指定 xhs.exe 路径 | 自动检测 |

## 📁 输出结构

```
<output-dir>/
  <source>-<run-id>/           # 例如: favorites-20260617T153000
    0001-<title>--<note_id>.md
    0002-<title>--<note_id>.md
    ...
    _xhs_export_index.md       # 本次导出索引
    <source>_raw.json          # 原始 JSON 数据
    details/<note_id>.json     # 笔记详情（如果启用）
    images/<note_id>/          # 下载的图片
      image-01.jpg
      image-02.jpg
      ...
  xhs_state.json               # 增量状态文件
```

## 📝 Markdown 输出格式

每条笔记会生成一个 Markdown 文件，包含：

```markdown
---
type: xhs_capture
status: needs-review
created: 2026-06-17
source: xiaohongshu
xhs_export_source: favorites
xhs_note_id: "abc123"
author: "用户昵称"
tags: [source/xiaohongshu]
---

# 笔记标题

## 捕获摘要
- 导出来源: 收藏 (`favorites`)
- 来源: [小红书笔记](https://www.xiaohongshu.com/explore/abc123)
- 作者: xxx
- 笔记 ID: abc123
- 导入时间: 2026-06-17T15:30:00+08:00
- 增量窗口: 2026-06-16 → 2026-06-17

## 原文
笔记正文内容...

## 互动数据
| 指标 | 数值 |
|---|---:|
| 点赞 | 123 |
| 收藏 | 456 |
| 评论 | 78 |

## 已保存图片
- ![[images/abc123/image-01.jpg]]
- ![[images/abc123/image-02.jpg]]
```

## 🔄 增量同步机制

导出脚本使用 `xhs_state.json` 管理增量状态：

```json
{
  "version": 1,
  "sources": {
    "favorites": {
      "last_success_at": "2026-06-17T15:30:00+08:00",
      "seen_note_ids": ["note1", "note2", ...],
      "runs": [...]
    }
  }
}
```

- **首次运行**：导出所有加载的笔记
- **后续运行**：只导出新增笔记（基于收藏/点赞时间和 note_id）
- **重置状态**：使用 `--reset-state --reset-state-only` 清除增量状态

## 🔐 关于登录状态

本工具依赖 [xhs-cli-headless](https://github.com/kyalpha313/xhs-cli-headless) 进行小红书 API 访问：

1. **登录方式**：通过二维码扫码登录
2. **状态保存**：cookies 保存在 `~/.xiaohongshu-cli/cookies.json`
3. **状态检查**：`xhs auth doctor --json`
4. **状态恢复**：如果过期，重新扫码或使用 `xhs auth import-fields --interactive`

## 🛠️ Claude Code 集成

本工具可以作为 Claude Code 的 Skill 使用，让 AI 帮你执行导出：

```bash
# 复制 skill 到 Claude Code 目录
cp -r claude-skill ~/.claude/skills/xiaohongshu-export
```

然后在 Claude Code 中可以直接说：
- "导出我的小红书收藏"
- "同步小红书点赞到本地"

## 🤝 致谢

- [xhs-cli-headless](https://github.com/kyalpha313/xhs-cli-headless) — 提供小红书 CLI 访问能力

## 📄 许可证

[MIT License](LICENSE)

## ⚠️ 免责声明

本工具仅供个人学习和研究使用。请遵守小红书的使用条款和相关法律法规。使用者需自行承担使用风险。

## 📚 相关文档

- [安装指南](INSTALL.md) — 详细安装步骤和故障排除
- [更新日志](CHANGELOG.md) — 版本更新记录
- [贡献指南](CONTRIBUTING.md) — 如何参与贡献
- [安全政策](SECURITY.md) — 安全注意事项

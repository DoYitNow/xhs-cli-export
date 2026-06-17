# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-06-17

### Added

- 初始版本发布
- 支持导出小红书收藏（favorites）和点赞（likes）
- 流式获取笔记列表（NDJSON）
- 逐条获取笔记详情（正文 + 全部图片）
- 增量同步机制（基于时间戳和 note_id）
- 崩溃恢复（JSONL 临时文件）
- 自动重试机制（最多 5 次）
- 图片下载功能
- Markdown 输出带 frontmatter
- 导出索引文件生成
- 进度条显示
- 支持 `--dry-run` 预览模式
- 支持 `--all-history` 全量导出
- 支持 `--reset-state` 重置增量状态

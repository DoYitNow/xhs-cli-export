# 贡献指南

感谢你对 xhs-cli-export 的关注！

## 如何贡献

### 报告问题

1. 使用 GitHub Issues 报告 bug
2. 提供复现步骤和错误信息
3. 说明你的环境（Python 版本、操作系统等）

### 提交代码

1. Fork 本仓库
2. 创建你的特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交你的修改 (`git commit -m 'Add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

### 开发环境

```bash
# 克隆仓库
git clone https://github.com/yuyitian/xhs-cli-export.git
cd xhs-cli-export

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或 .venv\Scripts\activate  # Windows

# 安装依赖
pip install requests ruff

# 运行 lint
ruff check src/
```

### 代码风格

- 使用 ruff 进行代码格式化和 lint
- 遵循 PEP 8 规范
- 行长度限制：120 字符

### 提交规范

使用语义化的提交信息：

- `feat:` 新功能
- `fix:` 修复 bug
- `docs:` 文档更新
- `style:` 代码格式（不影响功能）
- `refactor:` 重构
- `test:` 测试相关
- `chore:` 构建/工具相关

示例：
```
feat: 支持导出评论数据
fix: 修复图片下载超时问题
docs: 更新 README 使用示例
```

## 许可证

贡献的代码将使用与本项目相同的 [MIT License](LICENSE)。

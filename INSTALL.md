# 安装指南

## 系统要求

- Python 3.10 或更高版本
- [xhs-cli-headless](https://github.com/kyalpha313/xhs-cli-headless) 已安装并登录

## 安装步骤

### 1. 安装 xhs-cli-headless

```bash
# 方式一：使用 uv（推荐）
uv tool install xhs-cli-headless

# 方式二：使用 pipx
pipx install xhs-cli-headless

# 方式三：使用 pip
pip install xhs-cli-headless
```

### 2. 登录小红书

```bash
# 检查登录状态
xhs auth doctor --json

# 如果未登录，使用二维码登录
xhs login --qr-output ./xhs-login-qr.png --print-link
```

扫描二维码后，等待登录完成。

### 3. 安装 xhs-cli-export

#### 方式一：作为独立脚本（推荐）

```bash
# 克隆仓库
git clone https://github.com/yuyitian/xhs-cli-export.git
cd xhs-cli-export

# 安装依赖
pip install requests

# 测试运行
python src/xhs_export.py check
```

#### 方式二：pip 安装

```bash
pip install xhs-cli-export
```

安装后可以直接使用 `xhs-export` 命令：

```bash
xhs-export check
xhs-export export --source favorites
```

### 4. 验证安装

```bash
# 检查 xhs 和导出工具
python src/xhs_export.py check

# 如果看到类似以下输出，说明安装成功：
# xhs 可执行文件: C:\Users\xxx\.xiaohongshu-cli\headless-venv\Scripts\xhs.exe
# xhs, version 0.8.9
# 登录状态: logged_in / authenticated=True
```

## 环境变量

可选的环境变量：

| 变量名 | 说明 |
|---|---|
| `XHS_EXPORT_XHS_BIN` | 指定 xhs.exe 路径 |
| `XHS_BIN` | 同上（兼容旧版本） |

示例：

```bash
# Linux/Mac
export XHS_EXPORT_XHS_BIN=~/.xiaohongshu-cli/headless-venv/Scripts/xhs.exe

# Windows PowerShell
$env:XHS_EXPORT_XHS_BIN="C:\Users\xxx\.xiaohongshu-cli\headless-venv\Scripts\xhs.exe"
```

## 故障排除

### 问题：找不到 xhs 可执行文件

**解决方案**：
```bash
# 方式一：指定完整路径
python src/xhs_export.py export --source favorites \
  --xhs-bin ~/.xiaohongshu-cli/headless-venv/Scripts/xhs.exe

# 方式二：设置环境变量
export XHS_EXPORT_XHS_BIN=~/.xiaohongshu-cli/headless-venv/Scripts/xhs.exe
```

### 问题：登录状态过期

**解决方案**：
```bash
# 重新登录
xhs login --qr-output ./xhs-login-qr.png --print-link
```

### 问题：导出中断后如何恢复

**解决方案**：
- 已导出的 Markdown 文件会保留
- 重新运行相同命令，增量机制会跳过已导出的笔记
- 如果需要重新导出，使用 `--reset-state`

### 问题：图片下载失败

**可能原因**：
- 网络问题
- 图片 CDN 访问受限

**解决方案**：
- 检查网络连接
- 使用 `--no-images` 跳过图片下载
- 减少 `--max-images-per-note` 数量

## 卸载

```bash
# 如果使用 pip 安装
pip uninstall xhs-cli-export

# 如果使用 git 克隆
rm -rf xhs-cli-export/
```

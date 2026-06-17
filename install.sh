#!/bin/bash
# xhs-cli-export 安装脚本 (Linux/macOS)
# 用法: ./install.sh

set -e

echo "========================================"
echo "  xhs-cli-export 安装脚本"
echo "========================================"
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 检查 Python 版本
echo -e "${YELLOW}[1/4] 检查 Python 版本...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON=python3
elif command -v python &> /dev/null; then
    PYTHON=python
else
    echo -e "${RED}错误: 未找到 Python，请先安装 Python 3.10+${NC}"
    exit 1
fi
PYTHON_VERSION=$($PYTHON --version 2>&1)
echo -e "  ${GREEN}$PYTHON_VERSION${NC}"

# 检查 xhs-cli-headless
echo ""
echo -e "${YELLOW}[2/4] 检查 xhs-cli-headless...${NC}"
if command -v xhs &> /dev/null; then
    XHS_VERSION=$(xhs --version 2>&1)
    echo -e "  ${GREEN}已安装: $XHS_VERSION${NC}"
else
    echo -e "  ${YELLOW}未找到 xhs-cli-headless${NC}"
    echo ""
    read -p "是否安装 xhs-cli-headless? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        echo -e "  ${YELLOW}正在安装 xhs-cli-headless...${NC}"
        if command -v uv &> /dev/null; then
            uv tool install xhs-cli-headless
        elif command -v pipx &> /dev/null; then
            pipx install xhs-cli-headless
        else
            pip install xhs-cli-headless
        fi
        echo -e "  ${GREEN}安装完成${NC}"
    else
        echo -e "  ${YELLOW}跳过安装。请稍后手动安装: uv tool install xhs-cli-headless${NC}"
    fi
fi

# 安装依赖
echo ""
echo -e "${YELLOW}[3/4] 安装依赖 (requests)...${NC}"
$PYTHON -m pip install requests --quiet
echo -e "  ${GREEN}安装完成${NC}"

# 检查登录状态
echo ""
echo -e "${YELLOW}[4/4] 检查小红书登录状态...${NC}"
if command -v xhs &> /dev/null; then
    DOCTOR_RESULT=$(xhs auth doctor --json 2>&1)
    if echo "$DOCTOR_RESULT" | grep -q '"authenticated":\s*true'; then
        echo -e "  ${GREEN}已登录${NC}"
    else
        echo -e "  ${YELLOW}未登录${NC}"
        echo ""
        read -p "是否现在登录? (y/n) " -n 1 -r
        echo ""
        if [[ $REPLY =~ ^[Yy]$ ]]; then
            echo -e "  ${YELLOW}正在生成二维码...${NC}"
            xhs login --qr-output "./xhs-login-qr.png" --print-link
            echo ""
            echo -e "  ${CYAN}请扫描二维码完成登录${NC}"
            echo -e "  ${CYAN}二维码已保存到: xhs-login-qr.png${NC}"
        fi
    fi
else
    echo -e "  ${YELLOW}跳过（xhs-cli-headless 未安装）${NC}"
fi

echo ""
echo "========================================"
echo -e "  ${GREEN}安装完成！${NC}"
echo "========================================"
echo ""
echo "使用方法:"
echo "  python src/xhs_export.py check                    # 检查状态"
echo "  python src/xhs_export.py export --source favorites  # 导出收藏"
echo "  python src/xhs_export.py export --source likes      # 导出点赞"
echo ""

#!/usr/bin/env bash
# 快速启动脚本（适用于 macOS/Linux）

set -e

echo "🚀 GitHub Copilot SDK SDTM 转换应用"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "❌ Node.js 未安装"
    echo "   访问 https://nodejs.org 安装 Node.js >= 18"
    exit 1
fi

echo "✓ Node.js $(node --version)"
echo "✓ npm $(npm --version)"
echo ""

# 进入 nextjs 目录
cd nextjs

# 检查 .env
if [ ! -f .env ]; then
    echo "📝 创建 .env 文件..."
    cp .env.example .env
    echo "⚠️  请编辑 .env 文件，添加 COPILOT_GITHUB_TOKEN"
    echo ""
    echo "获取 Token 步骤："
    echo "1. 访问 https://github.com/settings/tokens"
    echo "2. 点击 'Generate new token'"
    echo "3. 赋予 'copilot' 权限"
    echo "4. 复制 Token 到 .env"
    echo ""
    exit 1
fi

# 检查 Token
if ! grep -q "COPILOT_GITHUB_TOKEN=ghp_" .env 2>/dev/null; then
    echo "❌ .env 中未找到有效的 COPILOT_GITHUB_TOKEN"
    echo "   请编辑 .env 文件"
    exit 1
fi

echo "✓ .env 已配置"
echo ""

# 安装依赖
if [ ! -d node_modules ]; then
    echo "📦 安装 npm 依赖..."
    npm install
    echo ""
fi

echo "✓ 依赖已安装"
echo ""

# 启动开发服务器
echo "🚀 启动开发服务器..."
echo "   打开浏览器访问：http://localhost:3000"
echo ""

npm run dev

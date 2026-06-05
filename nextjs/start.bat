@echo off
REM 快速启动脚本（Windows PowerShell）

setlocal enabledelayedexpansion

echo.
echo 🚀 GitHub Copilot SDK SDTM 转换应用
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM 检查 Node.js
where node >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ Node.js 未安装
    echo    访问 https://nodejs.org 安装 Node.js 18 或更高版本
    pause
    exit /b 1
)

for /f "tokens=*" %%i in ('node --version') do set NODE_VERSION=%%i
echo ✓ Node.js %NODE_VERSION%

for /f "tokens=*" %%i in ('npm --version') do set NPM_VERSION=%%i
echo ✓ npm %NPM_VERSION%
echo.

REM 进入 nextjs 目录
cd nextjs

REM 检查 .env
if not exist .env (
    echo 📝 创建 .env 文件...
    copy .env.example .env >nul
    echo ⚠️  请编辑 .env 文件，添加 COPILOT_GITHUB_TOKEN
    echo.
    echo 获取 Token 步骤：
    echo 1. 访问 https://github.com/settings/tokens
    echo 2. 点击 'Generate new token'
    echo 3. 赋予 'copilot' 权限
    echo 4. 复制 Token 到 .env
    echo.
    pause
    exit /b 1
)

echo ✓ .env 已存在
echo.

REM 检查 Token
findstr /M "COPILOT_GITHUB_TOKEN=ghp_" .env >nul 2>nul
if %errorlevel% neq 0 (
    echo ❌ .env 中未找到有效的 COPILOT_GITHUB_TOKEN
    echo    请编辑 .env 文件添加你的 Token
    pause
    exit /b 1
)

echo ✓ Token 已配置
echo.

REM 检查 node_modules
if not exist node_modules (
    echo 📦 安装 npm 依赖...
    call npm install
    echo.
)

echo ✓ 依赖已安装
echo.

REM 启动开发服务器
echo 🚀 启动开发服务器...
echo    打开浏览器访问：http://localhost:3000
echo.  npm run dev

call npm run dev

endlocal
pause

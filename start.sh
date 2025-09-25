#!/bin/bash
set -e  # 遇到错误立即退出

# 日志函数
log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"
}

# Debug: Print initial APP_PORT value from the environment
log "DEBUG: Initial ENV APP_PORT: -->${APP_PORT}<--"

# 设置默认端口，如果APP_PORT环境变量未设置，则使用23333
APP_PORT=${APP_PORT:-23333}

# Debug: Print APP_PORT value after script's default assignment
log "DEBUG: Script APP_PORT after default: -->${APP_PORT}<--"

log "PT-Accelerator 启动脚本开始运行..."

# 创建必要的目录
log "创建必要的目录..."
mkdir -p config logs
if [ ! -d "config" ] || [ ! -d "logs" ]; then
    log "错误: 无法创建必要的目录，请检查权限"
    exit 1
fi

# 检查hosts文件权限
log "检查 /etc/hosts 文件权限..."
if [ ! -w "/etc/hosts" ]; then
    log "警告: 无法写入 /etc/hosts 文件，程序可能无法正常工作"
    log "请使用 sudo 或者 root 权限运行，或者确保当前用户有写入 /etc/hosts 的权限"
fi

# 确保CloudflareST有执行权限
if [ -f "cfst_linux_amd64/cfst" ]; then
    log "设置 cfst 可执行权限..."
    chmod +x cfst_linux_amd64/cfst
    chmod +x cfst_linux_amd64/cfst_hosts.sh
else
    log "警告: 未找到 cfst 文件，IP优选功能可能不可用"
fi

# 创建nowip_hosts.txt文件（如果不存在）
if [ ! -f "nowip_hosts.txt" ]; then
    log "创建 nowip_hosts.txt 文件..."
    echo "104.16.91.215" > nowip_hosts.txt
    
# 检查cfst_linux_amd64目录下是否也需要此文件
if [ -d "cfst_linux_amd64" ] && [ ! -f "cfst_linux_amd64/nowip_hosts.txt" ]; then
    cp nowip_hosts.txt cfst_linux_amd64/nowip_hosts.txt
fi
fi

# 启动应用
log "启动应用..."
log "DEBUG: APP_PORT just before uvicorn: -->${APP_PORT}<--" # Added debug log
python -m uvicorn app.main:app --host 0.0.0.0 --port "${APP_PORT}"

# 注意：此行永远不会执行，因为uvicorn会保持运行状态
log "应用已停止" 
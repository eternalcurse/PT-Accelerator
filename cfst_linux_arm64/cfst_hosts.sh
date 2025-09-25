#!/usr/bin/env bash
PATH=/bin:/sbin:/usr/bin:/usr/sbin:/usr/local/bin:/usr/local/sbin:~/bin
export PATH
# --------------------------------------------------------------
#  项目: CloudflareSpeedTest 自动更新 Hosts (arm64 适配版)
#  版本: 1.0.4
#  作者: XIU2  |  项目: https://github.com/XIU2/CloudflareSpeedTest
#  备注: 与 amd64 版保持等价逻辑，仅二进制路径不同
# --------------------------------------------------------------

# 工作目录与日志
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
cd "$SCRIPT_DIR" || exit 1
log() { echo "$(date '+%Y-%m-%d %H:%M:%S') - $1"; }

_CHECK() {
    while true; do
        if [[ ! -e "nowip_hosts.txt" ]]; then
            echo -e "该脚本的作用为 CFST 测速后获取最快 IP 并替换 Hosts 中的 Cloudflare CDN IP。\n使用前请先阅读：https://github.com/XIU2/CloudflareSpeedTest/issues/42#issuecomment-768273848"
            echo -e "第一次使用，请先将 Hosts 中所有 Cloudflare CDN IP 统一改为一个 IP。"
            read -e -p "输入该 Cloudflare CDN IP 并回车（后续不再需要该步骤）：" NOWIP
            if [[ -n "${NOWIP}" ]]; then
                echo ${NOWIP} > nowip_hosts.txt
                break
            else
                echo "该 IP 不能是空！"
            fi
        else
            break
        fi
    done
}

_UPDATE() {
    echo -e "开始测速..."
    NOWIP=$(head -1 nowip_hosts.txt)
    log "当前的IP是: ${NOWIP}"

    # 查找 cfst 可执行文件（arm64 路径优先）
    CFST_PATH=""
    possible_paths=(
        "./cfst"
        "/usr/local/bin/cfst"
        "/usr/bin/cfst"
        "/app/cfst"
        "/app/cfst_linux_arm64/cfst"
    )
    for path in "${possible_paths[@]}"; do
        if [[ -x "$path" ]]; then
            CFST_PATH="$path"
            log "找到 cfst 可执行文件: $CFST_PATH"
            break
        fi
    done
    if [[ -z "$CFST_PATH" ]]; then
        log "错误: 未找到 cfst 可执行文件"
        exit 1
    fi

    # 准备 IP 文件
    IP_FILE="ip.txt"
    if [[ ! -f "$IP_FILE" ]]; then
        log "未找到IP文件，尝试从其他位置复制"
        find / -name "ip.txt" -type f -print 2>/dev/null | head -1 | xargs -I {} cp {} "$IP_FILE" 2>/dev/null
        if [[ ! -f "$IP_FILE" ]]; then
            log "仍然找不到IP文件，创建一个基本的文件"
            cat > "$IP_FILE" << EOL
# Cloudflare IP Ranges
1.1.1.0/24
1.0.0.0/24
104.16.0.0/12
172.64.0.0/13
173.245.48.0/20
103.21.244.0/22
103.22.200.0/22
103.31.4.0/22
141.101.64.0/18
108.162.192.0/18
190.93.240.0/20
188.114.96.0/20
197.234.240.0/22
198.41.128.0/17
162.158.0.0/15
104.16.0.0/13
104.24.0.0/14
EOL
        fi
    fi
    log "使用IP文件: $IP_FILE"

    # 运行 cfst（延迟优先，静默输出，指定IP文件，结果写入）
    log "执行命令: $CFST_PATH -dd -p 0 -f $IP_FILE -o result_hosts.txt"
    $CFST_PATH -dd -p 0 -f "$IP_FILE" -o "result_hosts.txt"
    CFST_EXIT_CODE=$?
    log "cfst 退出代码: $CFST_EXIT_CODE"

    [[ ! -e "result_hosts.txt" ]] && log "CFST 测速结果 IP 数量为 0，跳过下面步骤..." && exit 0

    BESTIP=$(sed -n "2,1p" result_hosts.txt | awk -F, '{print $1}')
    if [[ -z "${BESTIP}" ]]; then
        log "CFST 测速结果 IP 数量为 0，跳过下面步骤..."
        exit 0
    fi
    log "找到最优IP: ${BESTIP}"
    echo ${BESTIP} > nowip_hosts.txt
    echo -e "\n旧 IP 为 ${NOWIP}\n新 IP 为 ${BESTIP}\n"

    # 备份并替换 /etc/hosts（优先替换 PT-Accelerator 区域）
    if [[ -f "/etc/hosts" ]]; then
        cp -f /etc/hosts /etc/hosts_backup
        cp -f /etc/hosts /etc/hosts.cfst.bak
        if grep -q "PT-Accelerator" /etc/hosts; then
            PT_START=$(grep -n "PT站点加速开始" /etc/hosts | cut -d: -f1)
            PT_END=$(grep -n "PT站点加速结束" /etc/hosts | cut -d: -f1)
            if [[ -n "$PT_START" && -n "$PT_END" ]]; then
                PT_SECTION=$(sed -n "${PT_START},${PT_END}p" /etc/hosts)
                UPDATED_PT_SECTION=$(echo "$PT_SECTION" | sed "s/${NOWIP}/${BESTIP}/g")
                cat /etc/hosts > /tmp/hosts.new
                sed -i "${PT_START},${PT_END}c\\${UPDATED_PT_SECTION}" /tmp/hosts.new
                cat /tmp/hosts.new > /etc/hosts
                rm /tmp/hosts.new
                log "完成 /etc/hosts 中PT区域的IP替换：${NOWIP} -> ${BESTIP}"
            else
                sed -i "s/${NOWIP}/${BESTIP}/g" /etc/hosts
                log "未找到PT分区，已在整个 /etc/hosts 中替换IP"
            fi
        else
            sed -i "s/${NOWIP}/${BESTIP}/g" /etc/hosts
            log "未发现PT标记，已在整个 /etc/hosts 中替换IP"
        fi
    else
        log "找不到 /etc/hosts 文件"
    fi

    # 容器挂载路径处理
    if [[ -f "/mnt/hosts" ]]; then
        log "发现挂载的 /mnt/hosts 文件"
        cp -f /mnt/hosts /mnt/hosts.cfst.bak
        if grep -q "PT-Accelerator" /mnt/hosts; then
            PT_START=$(grep -n "PT站点加速开始" /mnt/hosts | cut -d: -f1)
            PT_END=$(grep -n "PT站点加速结束" /mnt/hosts | cut -d: -f1)
            if [[ -n "$PT_START" && -n "$PT_END" ]]; then
                PT_SECTION=$(sed -n "${PT_START},${PT_END}p" /mnt/hosts)
                UPDATED_PT_SECTION=$(echo "$PT_SECTION" | sed "s/${NOWIP}/${BESTIP}/g")
                cat /mnt/hosts > /tmp/mnt_hosts.new
                sed -i "${PT_START},${PT_END}c\\${UPDATED_PT_SECTION}" /tmp/mnt_hosts.new
                cat /tmp/mnt_hosts.new > /mnt/hosts
                rm /tmp/mnt_hosts.new
                log "完成 /mnt/hosts 中PT区域的IP替换：${NOWIP} -> ${BESTIP}"
            else
                sed -i "s/${NOWIP}/${BESTIP}/g" /mnt/hosts
                log "未找到PT分区，已在整个 /mnt/hosts 中替换IP"
            fi
        else
            sed -i "s/${NOWIP}/${BESTIP}/g" /mnt/hosts
            log "未发现PT标记，已在整个 /mnt/hosts 中替换IP"
        fi
    fi

    echo "${BESTIP}" > nowip_hosts.txt
    log "已更新 nowip_hosts.txt 文件为新IP: ${BESTIP}"
    log "完成所有替换操作"
}

_CHECK
_UPDATE
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request, status, Query, Form
from fastapi.responses import JSONResponse
import yaml
import os
import logging
from typing import List, Dict, Any
from pydantic import BaseModel
import re
from croniter import croniter
from urllib.parse import urlparse
import time
import copy

from app.services.cloudflare_speed_test import CloudflareSpeedTestService
from app.services.hosts_manager import HostsManager
from app.services.scheduler import SchedulerService
from app.services.torrent_clients import TorrentClientManager
from datetime import datetime
from app.models import Tracker, HostsSource, CloudflareConfig, TorrentClientConfig, BatchAddDomainsRequest, User, AuthConfig
from app.utils import notify as notify_module

# 从认证模块导入密码处理函数和依赖项
from app.auth import get_password_hash, verify_password, get_current_user

# 配置相关常量
CONFIG_PATH = "config/config.yaml"
DEFAULT_CLOUDFLARE_IP = "104.16.91.215"  # 全局默认Cloudflare IP

# 获取日志记录器
logger = logging.getLogger(__name__)
# 工具函数：将通知配置展开并按每个启用渠道发送
def _send_task_notify(title: str, content: str):
    try:
        # 1) 根据任务类型美化标题（添加emoji）
        title_map = {
            "IP优选与Hosts更新": "🚀 IP优选与Hosts更新",
            "仅更新Hosts": "🛠️ 仅更新Hosts",
            "清空并更新Hosts": "🧹 清空并更新Hosts",
        }
        pretty_title = title_map.get(title, f"📣 {title}")

        # 2) 根据内容判断成功/失败并加emoji
        text = str(content or "")
        success_markers = ["完成", "success", "已更新", "已完成", "成功"]
        failed_markers = ["失败", "error", "异常"]
        status_emoji = "ℹ️"
        if any(m in text for m in success_markers):
            status_emoji = "✅"
        if any(m in text for m in failed_markers):
            status_emoji = "❌"

        # 3) 统一美化内容：状态 + 原始信息 + 时间
        pretty_content = (
            f"{status_emoji} {text}\n\n"
            f"🕒 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        cfg = get_config() or {}
        notify_cfg = copy.deepcopy(cfg.get("notify", {}))
        channels = notify_cfg.get("channels", {}) or {}

        def flatten_channel(ch_conf: Dict[str, Any]) -> Dict[str, Any]:
            flat: Dict[str, Any] = {}
            for k, v in ch_conf.items():
                if k in ("name", "type", "enable"):
                    continue
                flat[k] = v
            # 一言策略：优先渠道内配置，否则用全局
            if "HITOKOTO" in ch_conf:
                val = ch_conf.get("HITOKOTO")
                if isinstance(val, bool):
                    flat["HITOKOTO"] = "true" if val else "false"
                else:
                    flat["HITOKOTO"] = val
            else:
                global_hitokoto = notify_cfg.get("hitokoto", True)
                flat["HITOKOTO"] = "true" if bool(global_hitokoto) else "false"
            return flat

        # 收集有效渠道
        payloads: list[Dict[str, Any]] = []
        if isinstance(channels, dict):
            for _, ch_conf in channels.items():
                if isinstance(ch_conf, dict) and ch_conf.get("enable"):
                    payloads.append(flatten_channel(ch_conf))

        minimal_keys_sets = [
            ("WEBHOOK_URL", "WEBHOOK_METHOD"),
            ("QYWX_KEY",),
            ("TG_BOT_TOKEN", "TG_USER_ID"),
            ("SMTP_SERVER", "SMTP_EMAIL", "SMTP_PASSWORD"),
            ("BARK_PUSH",),
            ("WXPUSHER_APP_TOKEN",),
            ("GOTIFY_URL", "GOTIFY_TOKEN"),
        ]
        valid = []
        for flat in payloads:
            for keys in minimal_keys_sets:
                if all(flat.get(k) for k in keys):
                    valid.append(flat)
                    break
        for flat in valid:
            notify_module.send(pretty_title, pretty_content, **flat)
    except Exception as e:
        logger.error(f"发送任务结果通知失败: {e}", exc_info=True)


router = APIRouter()

# 获取服务实例的依赖函数
from app.globals import get_hosts_manager, get_cloudflare_service, get_scheduler_service, get_torrent_client_manager




def get_config():
    """从文件获取最新配置"""
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {}
    return {}

# 获取配置（前端拉取用，每次从文件读取）
@router.get("/config")
async def get_config_api():
    """每次都从文件读取最新配置，防止内存与文件不同步导致tracker状态异常"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        return config
    else:
        return {}

# 更新配置（CRON表达式校验）
@router.post("/config")
async def update_config(
    config_data: Dict[str, Any],
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    cloudflare_service: CloudflareSpeedTestService = Depends(get_cloudflare_service),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """更新配置"""
    try:
        # CRON表达式校验
        cron_expr = config_data.get("cloudflare", {}).get("cron", "0 0 * * *")
        if not croniter.is_valid(cron_expr):
            raise HTTPException(status_code=400, detail="CRON表达式无效，请检查格式")
        


        # 保存配置
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config_data, f, default_flow_style=False, allow_unicode=True)
        
        # 更新服务配置
        hosts_manager.update_config(config_data)
        cloudflare_service.update_config(config_data)
        
        # 重启调度器
        scheduler_service.stop()
        scheduler_service.update_config(config_data)
        scheduler_service.start()
        
        return {"message": "配置已更新"}
    except Exception as e:
        logger.error(f"更新配置失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新配置失败: {str(e)}")

# 新增：更新认证配置的 API
@router.post("/auth/config", dependencies=[Depends(get_current_user)])
async def update_auth_config(
    request: Request,
    enable_auth: bool = Form(None),
    username: str = Form(None),
    current_password: str = Form(None),
    new_password: str = Form(None),
    confirm_password: str = Form(None),
    current_user: User = Depends(get_current_user)
):
    """更新认证配置，包括启用/禁用、用户名和密码"""
    current_config = get_config()
    
    if current_config.get("auth", {}).get("enable") and (not current_user or current_user.username == "guest"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权修改认证配置")

    auth_settings = current_config.get("auth", {}).copy()
    config_changed = False

    if enable_auth is not None and enable_auth != auth_settings.get("enable"):
        auth_settings["enable"] = enable_auth
        config_changed = True
        logger.info(f"登录认证已 {'启用' if enable_auth else '禁用'}")

    if username and username != auth_settings.get("username"):
        auth_settings["username"] = username
        config_changed = True
        logger.info(f"登录用户名已修改为: {username}")

    if new_password:
        # 验证新密码长度
        if len(new_password) < 8:
            raise HTTPException(status_code=400, detail="新密码长度至少需要8位字符")
        
        # 检查新密码与确认密码是否匹配
        if new_password != confirm_password:
            raise HTTPException(status_code=400, detail="新密码与确认密码不匹配")
        
        if not current_password:
            # 如果没有提供当前密码，检查是否允许这样做
            if not auth_settings.get("password_hash") or not auth_settings.get("enable"):
                # 首次设置密码或认证被禁用时可以不需要当前密码
                auth_settings["password_hash"] = get_password_hash(new_password)
                config_changed = True
                logger.info("登录密码已设置/更新。")
            else:
                raise HTTPException(status_code=400, detail="修改密码需要提供当前密码。如果您忘记了当前密码，请联系管理员。")
        else:
            # 验证当前密码
            if not auth_settings.get("password_hash"):
                raise HTTPException(status_code=400, detail="当前系统中没有设置密码，请清空当前密码字段后重试")
            elif not verify_password(current_password, auth_settings.get("password_hash", "")):
                raise HTTPException(status_code=400, detail="当前密码错误，请检查并重新输入")
            else:
                # 当前密码正确，更新为新密码
                auth_settings["password_hash"] = get_password_hash(new_password)
                config_changed = True
                logger.info("登录密码已修改") 
                # 密码修改成功，使当前会话失效，强制重新登录
                request.session.pop("user", None) 

    if config_changed:
        current_config["auth"] = auth_settings
        try:
            with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                yaml.dump(current_config, f, default_flow_style=False, allow_unicode=True)
            
            # 重新加载全局配置，确保认证配置变更立即生效
            from app.auth import reload_global_config
            if reload_global_config():
                logger.info("全局配置已重新加载，认证配置变更立即生效")
            else:
                logger.warning("全局配置重新加载失败，部分功能可能需要重启才能生效")
            
            # 重要：如果认证相关配置发生变化，清除当前session，强制重新登录
            # 这确保新的认证配置能够立即生效
            request.session.clear()
            
            message = "认证配置已更新。"
            # 根据具体更改调整消息，并处理会话
            if enable_auth is not None and not auth_settings.get("enable"):
                message += " 登录认证已禁用，您已自动登出。"
            elif new_password:
                 message += " 密码已更改，您已自动登出，请使用新密码重新登录。"
            elif username and username != current_user.username:
                 message += " 用户名已更改，您已自动登出，请重新登录。"
            else:
                message += " 为确保配置立即生效，您已自动登出，请重新登录。"
            
            return {"message": message}
        except Exception as e:
            logger.error(f"更新认证配置失败: {str(e)}")
            raise HTTPException(status_code=500, detail=f"更新认证配置失败: {str(e)}")
    
    return {"message": "未检测到配置更改"}

# 手动运行CloudflareSpeedTest
@router.post("/run-cloudflare-test")
async def run_cloudflare_test(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """手动运行CloudflareSpeedTest和更新hosts源（严格串行）"""
    try:
        # 创建组合任务
        def combined_task():
            logger.info("手动执行组合任务：优选IP + 更新tracker + 更新hosts（严格串行）")
            ok = hosts_manager.run_cfst_and_update_hosts()
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("执行完成" if ok else "执行失败")
            logger.info(f"[任务通知] IP优选与Hosts更新 -> {msg}")
            _send_task_notify("IP优选与Hosts更新", msg)
        # 在后台运行，避免阻塞API响应
        background_tasks.add_task(combined_task)
        return {"message": "IP优选与Hosts更新任务已启动（严格串行）"}
    except Exception as e:
        logger.error(f"启动组合任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动组合任务失败: {str(e)}")

# 获取调度器状态
@router.get("/scheduler-status")
async def get_scheduler_status(
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """获取调度器状态"""
    return {
        "running": scheduler_service.is_running(),
        "jobs": scheduler_service.get_jobs()
    }

# 兼容旧版前端，避免404错误
@router.get("/last-result")
async def get_last_result_compatibility():
    """兼容旧版前端，返回空结果"""
    return {
        "success": False,
        "message": "此API端点已弃用，优选结果不再显示",
        "time": "",
        "results": []
    }

# 任务状态API
@router.get("/task-status")
async def get_task_status(
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    scheduler_service: SchedulerService = Depends(get_scheduler_service)
):
    """获取当前任务状态
    
    前端轮询此接口以获取后台任务的执行状态
    
    Returns:
        任务状态：
        - status: done | running
        - message: 任务状态描述
    """
    try:
        # 首先检查scheduler_service中的任务状态
        scheduler_status = getattr(scheduler_service, 'get_task_status', lambda: {"status": "done", "message": "无任务"})()
        if scheduler_status.get("status") == "running":
            return scheduler_status
            
        # 然后检查hosts_manager中的任务状态
        hosts_status = hosts_manager.get_task_status()
        if hosts_status.get("status") == "running":
            return hosts_status
            
        # 如果都没有运行中的任务，返回默认完成状态
        return {
            "status": "done",
            "message": "无正在运行的任务"
        }
    except Exception as e:
        logger.error(f"获取任务状态时出错: {str(e)}", exc_info=True)
        # 返回安全的默认状态
        return {
            "status": "done",
            "message": "获取任务状态出错，请检查日志"
        }

# 获取日志
@router.get("/logs")
async def get_logs(lines: int = 1000):
    """获取最近的日志，统一按UTF-8读取并返回字符串，避免分块解码导致的乱码。"""
    log_file = "logs/app.log"
    try:
        if not os.path.exists(log_file):
            return {"logs": ""}

        # 使用 UTF-8 严格解码，遇到异常字符以替换符显示，避免抛错
        from collections import deque
        dq = deque(maxlen=max(10, lines))
        with open(log_file, 'r', encoding='utf-8', errors='replace') as f:
            for line in f:
                dq.append(line.rstrip('\n'))
        return {"logs": "\n".join(list(dq)[-lines:])}
    except Exception as e:
        logger.error(f"获取日志失败: {str(e)}")
        return {"logs": "日志读取失败，请检查日志文件权限和编码"}

@router.post("/logs/clear")
async def clear_logs():
    """清空日志文件内容"""
    try:
        log_file = "logs/app.log"
        # 确保目录存在
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        # 以写模式截断文件
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write("")
        logger.info("日志文件已被清空")
        return {"success": True, "message": "日志已清空"}
    except Exception as e:
        logger.error(f"清空日志失败: {str(e)}")
        return {"success": False, "message": f"清空日志失败: {str(e)}"}

# ===== Cloudflare白名单管理API =====

@router.get("/cloudflare-domains")
async def get_cloudflare_domains():
    config = get_config()
    domains = config.get("cloudflare_domains", [])
    return {"cloudflare_domains": domains}

@router.post("/cloudflare-domains")
async def add_cloudflare_domain(background_tasks: BackgroundTasks, domain: str = Query(..., description="要添加的Cloudflare域名")):
    config = get_config()
    domains = set(config.get("cloudflare_domains", []))
    domains.add(domain.strip().lower())
    config["cloudflare_domains"] = list(domains)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    hosts_manager = get_hosts_manager()
    hosts_manager.update_config(config)
    try:
        import app.main
        app.main.config = config
    except Exception:
        pass
    # 新增：白名单变更后自动异步更新hosts
    background_tasks.add_task(hosts_manager.update_hosts)
    return {"message": f"已添加 {domain} 到Cloudflare白名单", "cloudflare_domains": list(domains)}

@router.delete("/cloudflare-domains")
async def delete_cloudflare_domain(background_tasks: BackgroundTasks, domain: str = Query(..., description="要删除的Cloudflare域名")):
    config = get_config()
    domains = set(config.get("cloudflare_domains", []))
    domains.discard(domain.strip().lower())
    config["cloudflare_domains"] = list(domains)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
    hosts_manager = get_hosts_manager()
    hosts_manager.update_config(config)
    try:
        import app.main
        app.main.config = config
    except Exception:
        pass
    # 新增：白名单变更后自动异步更新hosts
    background_tasks.add_task(hosts_manager.update_hosts)
    return {"message": f"已从Cloudflare白名单移除 {domain}", "cloudflare_domains": list(domains)}

# 修改添加tracker接口，支持force_cloudflare参数
@router.post("/trackers")
async def add_tracker(
    tracker: dict,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    force_cloudflare: bool = False
):
    try:
        domain = tracker.get("domain", "")
        if domain:
            domain = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)
            domain = domain.split("/")[0]
            tracker["domain"] = domain
        config = get_config()
        if "trackers" not in config:
            config["trackers"] = []
        for existing in config["trackers"]:
            if existing["domain"] == tracker["domain"]:
                raise HTTPException(status_code=400, detail="Tracker已存在")
        ip_set = set()
        for t in config["trackers"]:
            if t.get("enable") and t.get("ip"):
                ip_set.add(t["ip"])
        if len(ip_set) > 1:
            raise HTTPException(status_code=400, detail="检测到现有Tracker的IP不一致，请先统一所有Tracker的IP后再添加。")
        elif len(ip_set) == 1:
            default_ip = list(ip_set)[0]
        else:
            default_ip = hosts_manager.best_cloudflare_ip or "104.16.91.215"
        tracker["ip"] = default_ip
        config["trackers"].append(tracker)
        # 新增：如force_cloudflare为True，自动写入白名单
        if force_cloudflare:
            domains = set(config.get("cloudflare_domains", []))
            domains.add(domain.strip().lower())
            config["cloudflare_domains"] = list(domains)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        hosts_manager.update_config(config)
        # 统一异步触发hosts更新，避免接口阻塞
        background_tasks.add_task(hosts_manager.update_hosts)
        try:
            import app.main
            app.main.config = config
        except Exception:
            pass
        return {"message": "Tracker已添加，Hosts更新任务已在后台启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加Tracker失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加Tracker失败: {str(e)}")

@router.delete("/trackers/{domain}")
async def delete_tracker(
    domain: str,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """删除Tracker"""
    try:
        # 更新配置
        config = get_config()
        if "trackers" not in config:
            raise HTTPException(status_code=404, detail="Tracker不存在")
        
        found = False
        config["trackers"] = [t for t in config["trackers"] if t["domain"] != domain]
        # 新增：同步清理历史
        hosts_manager.remove_tracker_domain(domain)
        
        # 保存配置
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info(f"删除Tracker API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"删除Tracker API刷新全局config对象失败: {str(e)}")
        
        # 在后台更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        
        return {"message": "Tracker已删除，Hosts更新任务已在后台启动"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除Tracker失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除Tracker失败: {str(e)}")

# 添加hosts源（URL校验）
@router.post("/hosts-sources")
async def add_hosts_source(
    source: Dict[str, Any],
    background_tasks: BackgroundTasks,  # 新增参数
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """添加hosts源"""
    try:
        # URL校验和自动补全
        url = source.get("url", "")
        if url and not re.match(r"^https?://", url, re.IGNORECASE):
            url = "https://" + url
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(status_code=400, detail="Hosts源URL无效，请检查格式")
        source["url"] = url
        config = get_config()
        if "hosts_sources" not in config:
            config["hosts_sources"] = []
        for existing in config["hosts_sources"]:
            if existing["url"] == source["url"]:
                raise HTTPException(status_code=400, detail="hosts源已存在")
        config["hosts_sources"].append(source)
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info("添加hosts源API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"添加hosts源API刷新全局config对象失败: {str(e)}")
            
        # 异步更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"message": "hosts源已添加，正在后台更新hosts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"添加hosts源失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"添加hosts源失败: {str(e)}")

@router.delete("/hosts-sources")
async def delete_hosts_source(
    url: str,
    background_tasks: BackgroundTasks,  # 新增参数
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """删除hosts源"""
    try:
        config = get_config()
        if "hosts_sources" not in config:
            raise HTTPException(status_code=404, detail="hosts源不存在")
        config["hosts_sources"] = [s for s in config["hosts_sources"] if s["url"] != url]
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info("删除hosts源API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"删除hosts源API刷新全局config对象失败: {str(e)}")
            
        # 异步更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"message": "hosts源已删除，正在后台更新hosts"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"删除hosts源失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"删除hosts源失败: {str(e)}")

# 手动更新hosts
@router.post("/update-hosts")
async def update_hosts(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """手动更新hosts"""
    try:
        # 在后台运行，避免阻塞API响应
        def task():
            ok = hosts_manager.update_hosts()
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("更新完成" if ok else "更新失败")
            logger.info(f"[任务通知] 仅更新Hosts -> {msg}")
            _send_task_notify("仅更新Hosts", msg)
        background_tasks.add_task(task)
        return {"message": "hosts更新任务已启动"}
    except Exception as e:
        logger.error(f"更新hosts失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新hosts失败: {str(e)}")

# 获取当前hosts
@router.get("/current-hosts")
async def get_current_hosts(
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """获取当前hosts"""
    try:
        return {"hosts": hosts_manager.read_system_hosts()}
    except Exception as e:
        logger.error(f"获取hosts失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"获取hosts失败: {str(e)}")

# ===== 添加新的模型和API端点 =====

class DomainList(BaseModel):
    domains: List[str]

# 批量添加PT站点域名
@router.post("/batch-add-domains")
async def batch_add_domains(
    request: Request,
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """批量添加域名"""
    try:
        # 获取请求数据
        data = await request.json()
        domains_data = data.get("domains", "")
        
        # 处理不同类型的输入
        if isinstance(domains_data, list):
            domains = domains_data
        else:
            # 假设是字符串，按行分割
            domains = domains_data.strip().split("\n")
        
        # 过滤空行
        domains = [domain.strip() for domain in domains if domain and domain.strip()]
        
        # 新增：自动清洗tracker域名
        cleaned_domains = []
        for domain in domains:
            d = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)
            d = d.split("/")[0]
            cleaned_domains.append(d)
        domains = cleaned_domains
        
        if not domains:
            return {"status": "warning", "message": "没有提供有效的域名"}
        
        # 读取当前配置
        config = get_config()
        if "trackers" not in config:
            config["trackers"] = []
            
        # 检查所有tracker的IP是否一致
        ip_set = set()
        for t in config["trackers"]:
            if t.get("enable") and t.get("ip"):
                ip_set.add(t["ip"])
                
        if len(ip_set) > 1:
            return {"status": "error", "message": "检测到现有Tracker的IP不一致，请先统一所有Tracker的IP后再添加。"}
        
        # 获取默认IP
        if len(ip_set) == 1:
            default_ip = list(ip_set)[0]
        else:
            # 没有tracker时，使用优选IP或默认IP
            default_ip = hosts_manager.best_cloudflare_ip or "104.16.91.215"
            
        # 处理结果统计
        added = []
        skipped = []
        
        # 批量添加域名
        for domain in domains:
            # 检查是否已存在
            if any(t["domain"] == domain for t in config["trackers"]):
                skipped.append(domain)
                continue
                
            # 添加新tracker
            config["trackers"].append({
                "name": domain,
                "domain": domain,
                "ip": default_ip,
                "enable": True
            })
            added.append(domain)
            
        # 保存配置
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
            
        # 更新hosts_manager的配置
        hosts_manager.update_config(config)
        
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = config
            logger.info("批量添加域名API已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"批量添加域名API刷新全局config对象失败: {str(e)}")
            
        # 后台更新hosts
        background_tasks.add_task(hosts_manager.update_hosts)
        
        # 构建响应消息
        message = f"批量添加完成：成功添加 {len(added)} 个域名，跳过 {len(skipped)} 个已存在的域名"
        details = {
            "added": added,
            "skipped": skipped
        }
        
        return {
            "status": "success", 
            "message": message,
            "details": details
        }
    except Exception as e:
        logger.error(f"批量添加域名失败: {str(e)}")
        return {"status": "error", "message": f"批量添加域名失败: {str(e)}"}

# 运行CloudflareSpeedTest优选脚本
@router.post("/run-cfst-script")
async def run_cfst_script(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """运行CloudflareSpeedTest优选脚本和更新hosts源（严格串行）"""
    try:
        def combined_task():
            logger.info("严格串行执行：优选IP+更新tracker+更新hosts")
            ok = hosts_manager.run_cfst_and_update_hosts()
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("执行完成" if ok else "执行失败")
            logger.info(f"[任务通知] IP优选与Hosts更新 -> {msg}")
            _send_task_notify("IP优选与Hosts更新", msg)
        background_tasks.add_task(combined_task)
        return {"message": "IP优选与Hosts更新任务已启动（严格串行）"}
    except Exception as e:
        logger.error(f"启动组合任务失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"启动组合任务失败: {str(e)}")

# 手动更新所有Tracker为最佳IP
@router.post("/update-all-trackers")
async def update_all_trackers(
    ip: str,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """手动更新所有Tracker为指定IP"""
    try:
        hosts_manager._update_all_trackers_ip(ip)
        hosts_manager.update_hosts()
        
        # 确保全局config对象同步更新
        try:
            import app.main
            app.main.config = hosts_manager.config
            logger.info("API端点已同步刷新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"API端点刷新全局config对象失败: {str(e)}")
            
        return {"message": f"已将所有Tracker的IP更新为 {ip}"}
    except Exception as e:
        logger.error(f"更新所有Tracker的IP失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"更新所有Tracker的IP失败: {str(e)}")

# ===== 下载器相关API =====

# 获取下载器客户端列表
@router.get("/torrent-clients")
async def get_torrent_clients(config: Dict[str, Any] = Depends(get_config)):
    """获取所有下载器客户端配置"""
    try:
        clients_config = config.get("torrent_clients", [])
        # 兼容旧配置格式
        if isinstance(clients_config, dict):
            converted_clients = []
            for client_type, client_config in clients_config.items():
                converted_clients.append({
                    "id": f"{client_type}_migrated",
                    "name": f"{client_type.capitalize()} (迁移)",
                    "type": client_type,
                    **client_config
                })
            clients_config = converted_clients
        
        return {"success": True, "clients": clients_config}
    except Exception as e:
        logger.error(f"获取下载器客户端列表失败: {str(e)}")
        return {"success": False, "message": f"获取客户端列表失败: {str(e)}"}

# 保存下载器客户端配置
@router.post("/torrent-clients")
async def save_torrent_clients(
    clients_data: dict,
    config: Dict[str, Any] = Depends(get_config)
):
    """保存下载器客户端配置"""
    try:
        clients_config = clients_data.get("clients", [])
        
        # 验证每个客户端配置
        for client in clients_config:
            # 必填字段验证
            if not client.get("id"):
                return {"success": False, "message": "客户端ID不能为空"}
            if not client.get("name"):
                return {"success": False, "message": "客户端名称不能为空"}
            if not client.get("type") in ["qbittorrent", "transmission"]:
                return {"success": False, "message": "不支持的客户端类型"}
            if not client.get("host"):
                return {"success": False, "message": "主机地址不能为空"}
            
            # 主机地址验证
            host = client.get("host", "")
            if not re.match(r"^(?:[a-zA-Z0-9\-\.]+|\d{1,3}(?:\.\d{1,3}){3})$", host):
                return {"success": False, "message": f"客户端 {client.get('name')} 的主机地址无效"}
            
            # 端口验证
            try:
                port = int(client.get("port", 0))
                if not (1 <= port <= 65535):
                    return {"success": False, "message": f"客户端 {client.get('name')} 的端口范围无效(1-65535)"}
            except (ValueError, TypeError):
                return {"success": False, "message": f"客户端 {client.get('name')} 的端口必须为数字"}
        
        # 检查ID唯一性
        client_ids = [client.get("id") for client in clients_config]
        if len(client_ids) != len(set(client_ids)):
            return {"success": False, "message": "客户端ID不能重复"}
        
        # 更新配置
        config["torrent_clients"] = clients_config
        
        # 保存配置到文件
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        # 更新 TorrentClientManager
        torrent_client_manager = get_torrent_client_manager()
        torrent_client_manager.update_config(config)
        
        logger.info(f"下载器客户端配置已保存，共 {len(clients_config)} 个客户端")
        return {"success": True, "message": f"下载器配置已保存，共 {len(clients_config)} 个客户端"}
        
    except Exception as e:
        logger.error(f"保存下载器客户端配置失败: {str(e)}")
        return {"success": False, "message": f"保存配置失败: {str(e)}"}

# 测试下载器连接 - 支持通过ID或配置测试
@router.post("/test-client-connection")
async def test_client_connection(
    request: Request,
    torrent_client_manager: TorrentClientManager = Depends(get_torrent_client_manager)
):
    """测试下载器连接"""
    try:
        data = await request.json()
        client_id = data.get("client_id")
        client_config = data.get("client_config")
        
        if client_id:
            # 通过客户端ID测试已配置的客户端
            result = torrent_client_manager.test_client_connection(client_id)
        elif client_config:
            # 通过临时配置测试连接
            result = torrent_client_manager.test_client_connection_by_config(client_config)
        else:
            return {"success": False, "message": "请提供 client_id 或 client_config"}
        
        return result
        
    except Exception as e:
        logger.error(f"测试下载器连接失败: {str(e)}")
        return {"success": False, "message": f"测试连接失败: {str(e)}"}

# 兼容旧版API
@router.post("/save-clients-config")
async def save_clients_config_route(
    clients_config: dict,
    config: Dict[str, Any] = Depends(get_config)
):
    """保存下载器配置（兼容旧版API）"""
    logger.info("收到旧版本下载器配置保存请求，正在转换...")
    try:
        # 将旧格式转换为新格式
        converted_clients = []
        
        for client_type, client_config in clients_config.items():
            if client_type in ["qbittorrent", "transmission"]:
                # 生成唯一ID
                client_id = f"{client_type}_{int(time.time())}"
                converted_clients.append({
                    "id": client_id,
                    "name": f"{client_type.capitalize()} 默认",
                    "type": client_type,
                    **client_config
                })
        
        # 调用新版API
        return await save_torrent_clients(
            {"clients": converted_clients},
            config
        )
        
    except Exception as e:
        logger.error(f"保存下载器配置失败: {str(e)}")
        return {"success": False, "message": f"保存配置失败: {str(e)}"}

# 删除下载器客户端
@router.delete("/torrent-clients/{client_id}")
async def delete_torrent_client(
    client_id: str,
    config: Dict[str, Any] = Depends(get_config)
):
    """删除指定的下载器客户端"""
    try:
        clients_config = config.get("torrent_clients", [])
        
        # 查找并删除指定客户端
        updated_clients = [client for client in clients_config if client.get("id") != client_id]
        
        if len(updated_clients) == len(clients_config):
            return {"success": False, "message": f"未找到客户端: {client_id}"}
        
        # 更新配置
        config["torrent_clients"] = updated_clients
        
        # 保存配置到文件
        with open(CONFIG_PATH, 'w') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        
        # 更新 TorrentClientManager
        torrent_client_manager = get_torrent_client_manager()
        torrent_client_manager.update_config(config)
        
        logger.info(f"已删除下载器客户端: {client_id}")
        return {"success": True, "message": "客户端已删除"}
        
    except Exception as e:
        logger.error(f"删除下载器客户端失败: {str(e)}")
        return {"success": False, "message": f"删除客户端失败: {str(e)}"}

# 获取支持的客户端类型
@router.get("/torrent-client-types")
async def get_torrent_client_types():
    """获取支持的下载器客户端类型"""
    return {
        "success": True,
        "types": [
            {
                "type": "qbittorrent",
                "name": "qBittorrent",
                "default_port": 8080,
                "fields": ["host", "port", "username", "password", "use_https"]
            },
            {
                "type": "transmission",
                "name": "Transmission",
                "default_port": 9091,
                "fields": ["host", "port", "username", "password", "use_https", "path"]
            }
        ]
    }

# ===== 通知配置API =====

@router.get("/notify/config")
async def get_notify_config():
    """获取通知配置（从文件读取最新config）"""
    config = get_config()
    notify_cfg = config.get("notify", {})
    return {"success": True, "notify": notify_cfg}


@router.post("/notify/config")
async def save_notify_config(payload: Dict[str, Any]):
    """保存通知配置到config.yaml，并保持其余配置不变"""
    try:
        config = get_config()
        new_notify = payload.get("notify", {})
        if not isinstance(new_notify, dict):
            return {"success": False, "message": "无效的通知配置"}

        # 更新配置
        config["notify"] = new_notify

        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)

        # 尝试同步到全局config，便于前端刷新
        try:
            import app.main
            app.main.config = config
        except Exception:
            pass

        logger.info("通知配置已保存")
        return {"success": True, "message": "通知配置已保存"}
    except Exception as e:
        logger.error(f"保存通知配置失败: {str(e)}")
        return {"success": False, "message": f"保存通知配置失败: {str(e)}"}


@router.post("/notify/test")
async def test_notify(payload: Dict[str, Any]):
    """测试发送通知：可携带title/content与临时覆盖的channels"""
    try:
        title = payload.get("title") or "通知测试"
        content = payload.get("content") or "这是一条测试消息"
        channels_override = payload.get("channels") or {}

        # 读取配置
        config = get_config()
        notify_cfg = copy.deepcopy(config.get("notify", {}))
        enable = notify_cfg.get("enable", True)
        if not enable:
            return {"success": False, "message": "通知功能未启用"}

        # 逐渠道发送：按每个启用渠道构建独立的kwargs，并为其设置独立的HITOKOTO
        channels = notify_cfg.get("channels", {}) or {}
        per_channel_payloads: list[Dict[str, Any]] = []

        def flatten_channel(ch_conf: Dict[str, Any]) -> Dict[str, Any]:
            flat: Dict[str, Any] = {}
            for k, v in ch_conf.items():
                if k in ("name", "type", "enable"):
                    continue
                flat[k] = v
            # 每渠道一言开关映射
            if "HITOKOTO" in ch_conf:
                val = ch_conf.get("HITOKOTO")
                if isinstance(val, bool):
                    flat["HITOKOTO"] = "true" if val else "false"
                else:
                    flat["HITOKOTO"] = val
            else:
                # 如果渠道内未显式设置，则回落到全局 notify.hitokoto（默认为 True）
                global_hitokoto = notify_cfg.get("hitokoto", True)
                flat["HITOKOTO"] = "true" if bool(global_hitokoto) else "false"
            return flat

        # 先收集已保存且启用的渠道（若没有前端嵌套覆盖，则使用；若有嵌套覆盖，仅使用覆盖）
        use_saved_channels = True

        # 应用前端临时覆盖：
        # - 若为嵌套结构（按渠道名），则替换/追加对应渠道
        # - 若为顶层键集合，则作为“单次临时渠道”追加一次发送
        if isinstance(channels_override, dict) and channels_override:
            # 只要前端携带了覆盖对象，就完全忽略已保存的其它渠道
            use_saved_channels = False
            contains_nested = any(isinstance(val, dict) for val in channels_override.values())
            if contains_nested:
                for _, ch_conf in channels_override.items():
                    if isinstance(ch_conf, dict) and ch_conf.get("enable", True):
                        per_channel_payloads.append(flatten_channel(ch_conf))
            else:
                # 顶层键集合 -> 直接作为一次独立发送
                tmp_flat = dict(channels_override)
                if "HITOKOTO" in tmp_flat and isinstance(tmp_flat["HITOKOTO"], bool):
                    tmp_flat["HITOKOTO"] = "true" if tmp_flat["HITOKOTO"] else "false"
                elif "HITOKOTO" not in tmp_flat:
                    tmp_flat["HITOKOTO"] = "true" if bool(notify_cfg.get("hitokoto", True)) else "false"
                per_channel_payloads.append(tmp_flat)

        if use_saved_channels and isinstance(channels, dict):
            for _, ch_conf in channels.items():
                if isinstance(ch_conf, dict) and ch_conf.get("enable"):
                    per_channel_payloads.append(flatten_channel(ch_conf))

        # 过滤无效渠道（最小必需字段校验）
        valid_payloads: list[Dict[str, Any]] = []
        minimal_keys_sets = [
            ("WEBHOOK_URL", "WEBHOOK_METHOD"),           # 自定义Webhook
            ("QYWX_KEY",),                               # 企业微信Bot
            ("QYWX_AM",),                                # 企业微信App
            ("TG_BOT_TOKEN", "TG_USER_ID"),             # Telegram
            ("SMTP_SERVER", "SMTP_EMAIL", "SMTP_PASSWORD"), # 邮件
            ("BARK_PUSH",),                                # Bark
            ("PUSH_KEY",),                               # Server酱
            ("IGOT_PUSH_KEY",),                          # iGot
            ("FSKEY",),                                  # 飞书
            ("DD_BOT_TOKEN", "DD_BOT_SECRET"),          # 钉钉
            ("CHAT_URL", "CHAT_TOKEN"),                 # Synology Chat
        ]
        for flat in per_channel_payloads:
            for keys in minimal_keys_sets:
                if all(flat.get(k) for k in keys):
                    valid_payloads.append(flat)
                    break

        if not valid_payloads:
            return {"success": False, "message": "未检测到可用的通知渠道，请检查渠道是否启用且配置完整"}

        # 跳过标题列表
        skip_titles = notify_cfg.get("skip_titles", []) or []
        if title in skip_titles:
            return {"success": True, "message": "标题在跳过列表中，未发送"}

        # 分渠道依次发送（每次send只带该渠道相关字段，从而按渠道的HITOKOTO生效）
        for flat in valid_payloads:
            # 测试发送时仅使用本渠道配置
            notify_module.send(title, content, ignore_default_config=True, **flat)
        return {"success": True, "message": "测试通知请求已发出，请检查渠道接收情况"}
    except Exception as e:
        logger.error(f"测试通知发送失败: {str(e)}", exc_info=True)
        return {"success": False, "message": f"测试通知失败: {str(e)}"}

# 从下载器导入Tracker
@router.post("/import-trackers-from-clients")
async def import_trackers_from_clients_route(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager),
    config: Dict[str, Any] = Depends(get_config)
):
    """从所有已启用的下载器客户端导入Tracker"""
    logger.info("开始从下载器客户端导入Tracker")
    try:
        torrent_client_manager = get_torrent_client_manager()
        result = torrent_client_manager.import_trackers_from_clients()
        logger.info(f"导入结果: {result}")
        
        if result.get("status") == "success" and result.get("all_domains"):
            existing_domains = {tracker['domain'] for tracker in config.get('trackers', [])}
            new_trackers_added = False
            cf_domains = []
            non_cf_domains = []
            
            # 临时调整日志级别为DEBUG，以便查看详细的Cloudflare检测日志
            hosts_manager_logger = logging.getLogger('app.services.hosts_manager')
            original_level = hosts_manager_logger.level
            hosts_manager_logger.setLevel(logging.DEBUG)
            
            # 域名清洗和Cloudflare检测
            for domain in result["all_domains"]:
                # 清洗tracker域名，移除http前缀和路径
                d = re.sub(r"^https?://", "", domain, flags=re.IGNORECASE)
                d = d.split("/")[0]
                domain = d
                
                # 提取纯域名（移除端口号）用于Cloudflare检测
                clean_domain = domain.split(':')[0] if ':' in domain else domain
                
                logger.info(f"[Cloudflare检测] 正在检测下载器导入的域名: {clean_domain}")
                # 检测Cloudflare
                if hosts_manager.is_cloudflare_domain(clean_domain):
                    cf_domains.append(domain)
                    if domain not in existing_domains:
                        default_ip = DEFAULT_CLOUDFLARE_IP
                        new_tracker = {
                            "name": domain,
                            "domain": domain,
                            "enable": True,
                            "ip": default_ip
                        }
                        config.setdefault('trackers', []).append(new_tracker)
                        existing_domains.add(domain)
                        new_trackers_added = True
                else:
                    logger.info(f"[Cloudflare检测] 域名 {clean_domain} 不是Cloudflare域名，已跳过")
                    non_cf_domains.append(domain)
            
            # 恢复原有日志级别
            hosts_manager_logger.setLevel(original_level)
            
            # 统一输出检测结果
            if cf_domains:
                logger.info("=== Cloudflare站点检测结果 ===")
                logger.info(f"成功检测到 {len(cf_domains)} 个Cloudflare站点:")
                for domain in cf_domains:
                    logger.info(f"- {domain}")
            
            if non_cf_domains:
                logger.info(f"检测到 {len(non_cf_domains)} 个非Cloudflare站点:")
                for domain in non_cf_domains:
                    logger.info(f"- {domain}")
            
            # 只有有新的Cloudflare站点时才更新配置文件
            if new_trackers_added:
                with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
                    yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
                logger.info("已更新配置文件，添加了新的Tracker")
                hosts_manager.update_config(config)
                try:
                    import app.main
                    app.main.config = config
                    logger.info("同步刷新全局config对象，确保前端获取到最新tracker列表")
                except Exception as e:
                    logger.error(f"刷新全局config对象失败: {str(e)}")
                
                # 触发hosts更新
                background_tasks.add_task(hosts_manager.update_hosts)
                
                # 更新结果消息，区分加速和过滤站点
                cf_only_message = f"成功导入 {len(cf_domains)} 个Cloudflare站点"
                if non_cf_domains:
                    cf_only_message += f"，已过滤 {len(non_cf_domains)} 个非Cloudflare站点"
                result["message"] = cf_only_message + "，Hosts更新任务已在后台启动"
            else:
                # 无新Cloudflare站点时的消息
                if cf_domains:
                    result["message"] = f"未发现新的Cloudflare站点，已有站点 {len(cf_domains)} 个，过滤非Cloudflare站点 {len(non_cf_domains)} 个"
                else:
                    result["message"] = f"未找到任何Cloudflare站点，已过滤非Cloudflare站点 {len(non_cf_domains)} 个"
            
            # 添加详细的客户端结果信息
            client_summary = []
            for _, client_result in result.get("client_results", {}).items():
                if client_result.get("success"):
                    client_summary.append(f"{client_result['name']}: {client_result['count']}个")
                else:
                    client_summary.append(f"{client_result['name']}: 失败({client_result.get('error', '未知错误')})")
            
            if client_summary:
                result["client_summary"] = "；".join(client_summary)
        
        return result
        
    except Exception as e:
        logger.error(f"从下载器客户端导入Tracker失败: {str(e)}", exc_info=True)
        return {"status": "error", "message": f"导入过程中发生错误: {str(e)}"}

@router.post("/clear-and-update-hosts")
async def clear_and_update_hosts(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """清理项目分区并重新生成hosts内容（保留原有系统hosts未受影响）"""
    try:
        # 1. 仅移除PT-Accelerator分区，保留原有系统hosts
        hosts_manager.clear_project_sections()
        # 2. 后台更新hosts并通知
        def task():
            ok = hosts_manager.update_hosts()
            status = hosts_manager.get_task_status() if hasattr(hosts_manager, 'get_task_status') else {}
            msg = status.get('message') if isinstance(status, dict) else ("更新完成" if ok else "更新失败")
            logger.info(f"[任务通知] 清空并更新Hosts -> {msg}")
            _send_task_notify("清空并更新Hosts", msg)
        background_tasks.add_task(task)
        return {"message": "已清理项目分区并启动更新任务（原有hosts内容已保留）"}
    except Exception as e:
        logger.error(f"清空并更新hosts失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空并更新hosts失败: {str(e)}")

@router.post("/clear-all-trackers")
async def clear_all_trackers(
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    """清空所有tracker并同步更新hosts"""
    try:
        config = get_config()
        config["trackers"] = []
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True)
        hosts_manager.update_config(config)
        try:
            import app.main
            app.main.config = config
        except Exception:
            pass
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"message": "已清空所有tracker并同步更新hosts"}
    except Exception as e:
        logger.error(f"清空所有tracker失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"清空所有tracker失败: {str(e)}")


# 保存系统hosts内容
@router.post("/save-hosts-content")
async def save_hosts_content(
    payload: Dict[str, Any],
    background_tasks: BackgroundTasks,
    hosts_manager: HostsManager = Depends(get_hosts_manager)
):
    try:
        content = payload.get("content", "")
        if not isinstance(content, str):
            raise HTTPException(status_code=400, detail="无效的内容")
        hosts_path = hosts_manager._get_hosts_path()
        with open(hosts_path, 'w') as f:
            f.write(content)
        # 保存后触发一次后台更新，确保项目分区一致（非阻塞）
        background_tasks.add_task(hosts_manager.update_hosts)
        return {"success": True, "message": "Hosts已保存，已启动后台更新"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"保存hosts失败: {str(e)}")
        raise HTTPException(status_code=500, detail=f"保存hosts失败: {str(e)}")

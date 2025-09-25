import logging
import os
# HostsManager类部分
import platform
import requests
import subprocess
import threading
from typing import Dict, List, Any, Optional, Tuple
from python_hosts import Hosts, HostsEntry
import time
import hashlib
import yaml
import re
import socket
import urllib3
import json


logger = logging.getLogger(__name__)

# 通用域名黑名单，可随时扩展
DOMAIN_BLACKLIST = [
    "docker.com",
    "docker.io",
    "quay.io",
    "gcr.io",
    "k8s.gcr.io",
    "ghcr.io"
]

def is_blacklisted(domain: str) -> bool:
    return any(bad in domain for bad in DOMAIN_BLACKLIST)

class HostsManager:
    """Hosts文件管理器，用于管理系统的hosts文件"""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        # PT-Accelerator添加的hosts标记
        self.start_mark = "# == PT-Accelerator START =="
        self.end_mark = "# == PT-Accelerator END =="
        # PT站点标记
        self.pt_start_mark = "# ===== PT站点加速开始 ===== #"
        self.pt_end_mark = "# ===== PT站点加速结束 (%d 条记录) ===== #"
        # 各订阅源标记模板
        self.source_start_mark = "# ===== %s开始 ===== #"
        self.source_end_mark = "# ===== %s结束 (%d 条记录) ===== #"
        # 最新优选的Cloudflare IP
        self.best_cloudflare_ip = None
        # 域名IP历史记录，用于在网络波动时提供兜底IP
        self.domain_ip_history = {}
        # IP检测失败重试次数
        self.ping_retry_count = 3
        # 连续失败次数阈值，超过此值才真正剔除域名
        self.max_failure_count = 3
        # 域名连续失败计数器
        self.domain_failure_counter = {}
        # 任务状态追踪
        self.task_status = {"status": "done", "message": "无任务"}
        self.task_running = False
        # 新增：变更合并标记
        self.pending_update = False
        self.cf_domains = set()
        # 添加Cloudflare检测结果缓存
        self.cloudflare_cache = {}
        self.cache_expiry = 3600  # 缓存过期时间（秒）
        # 定义HTTP请求头
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'close'
        }
        
    def update_config(self, config: Dict[str, Any]):
        """更新配置，并同步Cloudflare白名单集合"""
        self.config = config
        # 自动同步Cloudflare白名单集合
        cf_domains_from_config = self.config.get('cloudflare_domains', [])
        self.cf_domains = set(cf_domains_from_config) if isinstance(cf_domains_from_config, list) else set([cf_domains_from_config])
        
    def _merge_write_config(self, partial_update: Dict[str, Any]):
        """将局部更新安全合并写回 config/config.yaml，避免覆盖其它未修改配置"""
        config_path = os.path.join("config", "config.yaml")
        try:
            current = {}
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    try:
                        current = yaml.safe_load(f) or {}
                    except Exception:
                        current = {}
            # 合并：以 current 为基础，仅覆盖传入的键
            current.update(partial_update or {})
            with open(config_path, 'w', encoding='utf-8') as f:
                yaml.dump(current, f, default_flow_style=False, allow_unicode=True)
            # 内存中的 self.config 同步为合并后的结果
            self.config = current
            # 同步全局 config 对象（若存在）
            try:
                import app.main
                app.main.config = current
            except Exception:
                pass
        except Exception as e:
            logger.error(f"安全合并写配置失败: {e}")

    def read_system_hosts(self) -> List[str]:
        """读取系统hosts文件内容"""
        try:
            hosts_path = self._get_hosts_path()
            with open(hosts_path, 'r') as f:
                return f.readlines()
        except Exception as e:
            logger.error(f"读取hosts文件失败: {str(e)}")
            return []
    
    def _collect_pt_entries(self) -> List[str]:
        """收集PT站点的条目（已优化：不再检测IP连通性，直接写入，但严格过滤非Cloudflare站点）"""
        entries = []
        # 如果有优选的IP，使用该IP，否则使用配置中的IP
        cloudflare_ip = self.best_cloudflare_ip or "104.16.91.215"  # 默认IP
        # 添加来自配置的Tracker域名，但只添加Cloudflare站点
        if self.config.get("trackers"):
            non_cf_domains = []
            for tracker in self.config["trackers"]:
                if not tracker.get("enable") or not tracker.get("domain"):
                    continue
                    
                domain = tracker['domain']
                # 移除端口号再检测
                clean_domain = domain.split(':')[0] if ':' in domain else domain
                
                # 严格检查是否为Cloudflare站点
                is_cf = self.is_cloudflare_domain(clean_domain)
                
                if is_cf:
                    ip = tracker.get("ip") or cloudflare_ip
                    # 直接写入，不再检测连通性
                    self.domain_ip_history[domain] = ip
                    entries.append(f"{ip}\t{domain}")
                else:
                    non_cf_domains.append(domain)
            
            # 记录被过滤的非Cloudflare站点
            if non_cf_domains:
                logger.info(f"[PT站点过滤] 以下{len(non_cf_domains)}个非Cloudflare站点未添加到hosts: {', '.join(non_cf_domains)}")
                
        return entries
    

    
    def _get_cache_path(self, url: str) -> str:
        """根据url生成本地缓存文件路径"""
        cache_dir = "cache"
        os.makedirs(cache_dir, exist_ok=True)
        url_hash = hashlib.md5(url.encode('utf-8')).hexdigest()
        return os.path.join(cache_dir, url_hash + ".cache")

    def _fetch_hosts_source(self, url: str) -> List[Tuple[str, str]]:
        """智能重试+超时+本地缓存兜底+黑名单过滤"""
        cache_path = self._get_cache_path(url)
        max_retries = 2
        timeout = 20
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                response = requests.get(url, timeout=timeout)
                if response.status_code == 200:
                    entries = []
                    lines = response.text.splitlines()
                    for line in lines:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        parts = line.split()
                        if len(parts) < 2:
                            continue
                        ip, domain = parts[0], parts[1]
                        if is_blacklisted(domain):
                            continue  # 跳过黑名单域名
                        entries.append((ip, domain))
                    # 拉取成功，写入本地缓存
                    try:
                        with open(cache_path, 'w', encoding='utf-8') as f:
                            f.write(response.text)
                    except Exception as e:
                        logger.warning(f"写入缓存失败: {cache_path}, 错误: {e}")
                    return entries
                else:
                    last_exception = Exception(f"HTTP状态码: {response.status_code}")
            except Exception as e:
                last_exception = e
                logger.warning(f"拉取hosts源失败({attempt+1}/{max_retries+1}): {url}, 错误: {e}")
        # 全部重试失败，尝试本地缓存兜底
        if os.path.exists(cache_path):
            logger.warning(f"所有重试失败，使用本地缓存兜底: {cache_path}")
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    lines = f.readlines()
                entries = []
                for line in lines:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = line.split()
                    if len(parts) < 2:
                        continue
                    ip, domain = parts[0], parts[1]
                    if is_blacklisted(domain):
                        continue
                    entries.append((ip, domain))
                return entries
            except Exception as e:
                logger.error(f"读取本地缓存失败: {cache_path}, 错误: {e}")
        logger.error(f"处理hosts源出错: {url}, 错误: {last_exception}")
        return []
    
    def _ping_ip(self, ip: str, timeout: int = 1, cache: Dict[str, float] = None, domain: str = None) -> float:
        """用socket方式检测IP连通性，返回延迟（毫秒），不可达返回None
        
        Args:
            ip: 要测试的IP地址
            timeout: 超时时间（秒）
            cache: IP延迟缓存字典，用于避免重复测试同一IP
            domain: 与IP关联的域名，用于记录历史IP和失败计数
        """
        # 使用缓存避免重复测试
        if cache is not None and ip in cache:
            return cache[ip]
            
        # 增加多方式检测（socket连接+ICMP ping），并增加重试机制，避免因临时网络波动导致误判
        ports = [80, 443]
        last_exception = None
        # 优先尝试socket连接
        for retry in range(self.ping_retry_count):
            for port in ports:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(timeout)
                    start = time.time()
                    s.connect((ip, port))
                    end = time.time()
                    s.close()
                    latency = (end - start) * 1000  # 毫秒
                    if cache is not None:
                        cache[ip] = latency
                    if domain:
                        self.domain_ip_history[domain] = ip
                        self.domain_failure_counter[domain] = 0
                    return latency
                except Exception as e:
                    last_exception = e
                    continue
            # 如果所有端口都连接失败，等待短暂时间后重试
            if retry < self.ping_retry_count - 1:
                time.sleep(0.5)
        # socket全部失败后，尝试ICMP ping
        try:
            # Windows下ping命令参数不同
            ping_cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip] if os.name == "nt" else ["ping", "-c", "1", "-W", str(timeout), ip]
            result = subprocess.run(ping_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if result.returncode == 0:
                if cache is not None:
                    cache[ip] = 999  # ping通但端口不通，延迟设为较高
                if domain:
                    self.domain_ip_history[domain] = ip
                    self.domain_failure_counter[domain] = 0
                return 999
        except Exception as e:
            last_exception = e
        # 所有重试都失败
        if cache is not None:
            cache[ip] = None
        if domain:
            self.domain_failure_counter[domain] = self.domain_failure_counter.get(domain, 0) + 1
        return None
    
    def update_hosts(self):
        """更新hosts文件，合并PT站点、订阅源和自定义规则"""
        self.task_running = True
        self.task_status = {"status": "running", "message": "开始更新hosts文件..."}
        logger.info("开始更新hosts文件...")

        try:
            logger.info("开始更新hosts文件")
            ip_latency_cache = {}
            
            # 1. 清理trackers列表，移除非Cloudflare站点（避免历史残留问题）
            if self.config.get("trackers"):
                original_count = len(self.config["trackers"])
                filtered_trackers = []
                non_cf_domains = []
                
                for tracker in self.config["trackers"]:
                    if not tracker.get("domain"):
                        continue
                        
                    domain = tracker["domain"]
                    # 提取纯域名（移除端口号）用于Cloudflare检测
                    clean_domain = domain.split(':')[0] if ':' in domain else domain
                    
                    if self.is_cloudflare_domain(clean_domain):
                        filtered_trackers.append(tracker)
                    else:
                        non_cf_domains.append(domain)
                
                if len(filtered_trackers) < original_count:
                    # 有非Cloudflare站点被过滤
                    logger.info(f"[历史清理] 从配置中过滤了 {original_count - len(filtered_trackers)} 个非Cloudflare站点: {', '.join(non_cf_domains)}")
                    self.config["trackers"] = filtered_trackers
                    
                    # 保存更新的配置
                    # 仅合并写 trackers，避免覆盖其它配置
                    self._merge_write_config({"trackers": self.config.get("trackers", [])})
                    logger.info("[历史清理] 已更新配置文件(合并写)，移除了所有非Cloudflare站点")
                    
                    # 更新全局配置
                    try:
                        import app.main
                        app.main.config = self.config
                        logger.info("[历史清理] 同步更新全局config对象完成")
                    except Exception as e:
                        logger.error(f"[历史清理] 更新全局config对象失败: {str(e)}")

            # 收集所有条目
            all_entries: Dict[str, List[str]] = {}
            
            # 2. PT站点条目
            pt_entries = self._collect_pt_entries()
            if pt_entries:
                all_entries["pt_sites"] = pt_entries
            logger.info(f"收集到 {len(pt_entries)} 条PT站点条目")



            # 3. 订阅源条目
            source_entries_map: Dict[str, List[str]] = {}
            tracker_domains = set()
            disabled_domains = self._get_disabled_tracker_domains()  # 新增：获取所有禁用tracker域名
            if self.config.get("trackers"):
                for tracker in self.config["trackers"]:
                    if tracker.get("enable") and tracker.get("domain"):
                        tracker_domains.add(tracker["domain"])
            merged_hosts_backup = self._load_merged_hosts_backup()
            backup_domains = set(merged_hosts_backup.keys())
            current_domains = set()
            abnormal_sources = set()
            if self.config.get("hosts_sources"):
                total_sources = len([s for s in self.config["hosts_sources"] if s.get("enable") and s.get("url") and s.get("name")])
                logger.info(f"开始处理 {total_sources} 个外部hosts源")
                for i, source in enumerate(self.config["hosts_sources"]):
                    if source.get("enable") and source.get("url") and source.get("name"):
                        source_name = source.get("name", "未命名源")
                        self.task_status = {"status": "running", "message": f"正在处理hosts源 ({i+1}/{total_sources}): {source_name}"}
                        source_start_time = time.time()
                        logger.info(f"正在处理hosts源 ({i+1}/{total_sources}): {source_name}")
                        source_entries = self._fetch_hosts_source(source["url"])
                        logger.info(f"获取hosts源 {source_name} 完成，返回 {len(source_entries)} 条记录，耗时 {time.time() - source_start_time:.2f} 秒")
                        if len(source_entries) < 5:
                            abnormal_sources.add(source_name)
                        entry_process_start = time.time()
                        entry_count = 0
                        for ip, domain in source_entries:
                            # 新增：跳过禁用tracker域名
                            if domain in tracker_domains or domain.strip().lower() in disabled_domains:
                                continue
                            source_entries_map.setdefault(source_name, []).append(f"{ip}\t{domain}")
                            current_domains.add(domain)
                            entry_count += 1
                        logger.info(f"处理hosts源 {source_name} 的 {entry_count} 条记录完成，耗时 {time.time() - entry_process_start:.2f} 秒")
            # 4. 处理历史IP记录作为兜底（只收集，不检测）
            for domain, ip in self.domain_ip_history.items():
                # 新增：跳过禁用tracker域名
                if domain in tracker_domains or domain.strip().lower() in disabled_domains:
                    continue
                source_entries_map.setdefault("HistoryIPs", []).append(f"{ip}\t{domain}")
                current_domains.add(domain)
            # 4.5 智能兜底：对比备份，找出本次丢失的域名
            lost_domains = backup_domains - current_domains
            # 获取已禁用的tracker域名
            disabled_domains = self._get_disabled_tracker_domains()
            
            for lost_domain in lost_domains:
                # 跳过已禁用的域名
                if lost_domain.strip().lower() in disabled_domains:
                    logger.info(f"[兜底跳过] 域名 {lost_domain} 已被用户禁用，不参与兜底保留")
                    continue


                
                lost_ip = merged_hosts_backup[lost_domain]
                if self._dns_check(lost_domain, lost_ip):
                    source_entries_map.setdefault("LostHosts", []).append(f"{lost_ip}\t{lost_domain}")
                    logger.warning(f"[兜底保留] 域名 {lost_domain} 本次未被任何源收录，但DNS检测有效，保留上次IP: {lost_ip}")
                else:
                    logger.warning(f"[兜底丢弃] 域名 {lost_domain} 本次未被任何源收录，且DNS检测无效，丢弃上次IP: {lost_ip}")
            # 5. 按域名分组并选择最佳IP
            self.task_status = {"status": "running", "message": "正在进行域名IP优选"}
            domain_ips = {}
            for source_name, entries in source_entries_map.items():
                if is_blacklisted(source_name):
                    continue
                for entry in entries:
                    ip, domain = entry.split('\t', 1)
                    if is_blacklisted(domain):
                        continue
                    if domain not in domain_ips:
                        domain_ips[domain] = []
                    domain_ips[domain].append((ip, source_name))
            
            # 为每个域名选择最佳IP
            merged_dict = {}
            log_lines = []
            
            for domain, ip_sources in domain_ips.items():
                best_ip = None
                best_latency = None
                ip_set = set()
                for ip, source in ip_sources:
                    ip_set.add(ip)
                
                for ip in ip_set:
                    latency = self._ping_ip(ip, cache=ip_latency_cache, domain=domain)
                    if latency is not None and (best_latency is None or latency < best_latency):
                        best_ip = ip
                        best_latency = latency
                
                if best_ip:
                    merged_dict[domain] = best_ip
                    log_lines.append(f"域名 {domain} 选用IP: {best_ip}，延迟: {best_latency:.2f} ms")
                else:
                    # 兜底选择第一个IP
                    fallback_ip = next(iter(ip_set))
                    merged_dict[domain] = fallback_ip
                    log_lines.append(f"域名 {domain} 所有IP不可达，兜底选用: {fallback_ip}")
            
            # 6. 生成最终hosts条目
            self.task_status = {"status": "running", "message": "正在生成最终hosts条目"}
            logger.info("生成合并后的最终hosts条目")
            sections = []
            
            # 添加PT站点
            if "pt_sites" in all_entries:
                sections.append((self.pt_start_mark, all_entries["pt_sites"], self.pt_end_mark % len(all_entries["pt_sites"])))
            
            # 生成合并后的hosts源条目（所有源合并为一个section）
            merged_entries = []
            for domain, best_ip in merged_dict.items():
                if not is_blacklisted(domain):
                    merged_entries.append(f"{best_ip}\t{domain}")
            
            # 按域名排序，保持输出稳定
            merged_entries.sort(key=lambda x: x.split('\t')[1])
            
            # 添加合并后的hosts源section（保持与1.1.0版本兼容的名称）
            if merged_entries:
                sections.append((
                    self.source_start_mark % "MergedHosts",
                    merged_entries,
                    self.source_end_mark % ("MergedHosts", len(merged_entries))
                ))
            
            # 7. 更新系统hosts文件
            self.task_status = {"status": "running", "message": "正在更新系统hosts文件"}
            logger.info("开始更新系统hosts文件")
            update_start = time.time()
            self._update_system_hosts_with_sections(sections)
            logger.info(f"更新系统hosts文件完成，耗时 {time.time() - update_start:.2f} 秒")
            total_entries = sum(len(entries) for _, entries, _ in sections)
            logger.info(f"成功更新hosts文件，添加了{total_entries}条记录，共{len(sections)}个分区")
            # 8. 输出最终检测结果日志
            logger.info("=== 域名优选IP结果汇总 ===")
            for line in log_lines:
                logger.info(line)
            # 9. 合并完成后更新备份
            self._save_merged_hosts_backup(merged_dict)
            self.task_status = {"status": "done", "message": f"已完成hosts更新，添加了{total_entries}条记录"}
            self.task_running = False
            if self.pending_update:
                logger.info("检测到pending_update标记，自动补偿执行一次update_hosts")
                self.pending_update = False
                self.update_hosts()
            return True
        except Exception as e:
            error_msg = f"更新hosts文件失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.task_status = {"status": "done", "message": error_msg}
            self.task_running = False
            if self.pending_update:
                logger.info("检测到pending_update标记（异常分支），自动补偿执行一次update_hosts")
                self.pending_update = False
                self.update_hosts()
            return False
    
    def _get_hosts_path(self) -> str:
        """获取hosts文件路径，优先读取配置中的自定义路径 hosts_path"""
        try:
            if isinstance(self.config, dict):
                custom_path = self.config.get("hosts_path")
                if isinstance(custom_path, str) and custom_path.strip():
                    return custom_path
        except Exception:
            pass
        system = platform.system()
        if system == "Windows":
            return r"c:\\windows\\system32\\drivers\\etc\\hosts"
        else:  # Linux or macOS
            return "/etc/hosts"
    
    def _update_system_hosts_with_sections(self, sections: List[Tuple[str, List[str], str]]):
        """更新系统hosts文件，保持分段格式，彻底移除所有PT-Accelerator分区，防止分区重复"""
        hosts_path = self._get_hosts_path()
        # 读取当前hosts文件
        with open(hosts_path, 'r') as f:
            content = f.read()
        # 循环移除所有PT-Accelerator分区，防止历史残留
        while self.start_mark in content and self.end_mark in content:
            start_pos = content.find(self.start_mark)
            end_pos = content.find(self.end_mark) + len(self.end_mark)
            content = content[:start_pos] + content[end_pos:]
        # 添加新的条目，保持分段格式
        new_content = content.rstrip() + "\n\n" + self.start_mark + "\n"
        for start_mark, entries, end_mark in sections:
            new_content += start_mark + "\n"
            for entry in entries:
                new_content += entry + "\n"
            new_content += end_mark + "\n"
        new_content += self.end_mark + "\n"
        # 写入hosts文件
        with open(hosts_path, 'w') as f:
            f.write(new_content)

    def clear_project_sections(self) -> None:
        """仅移除本项目写入的分区，保留系统原有hosts内容不变"""
        hosts_path = self._get_hosts_path()
        try:
            with open(hosts_path, 'r') as f:
                content = f.read()
            changed = False
            while self.start_mark in content and self.end_mark in content:
                start_pos = content.find(self.start_mark)
                end_pos = content.find(self.end_mark) + len(self.end_mark)
                content = content[:start_pos] + content[end_pos:]
                changed = True
            if changed:
                with open(hosts_path, 'w') as f:
                    f.write(content.rstrip() + "\n")
                logger.info("已清理PT-Accelerator分区，保留系统原有hosts内容")
            else:
                logger.info("未发现需要清理的PT-Accelerator分区")
        except Exception as e:
            logger.error(f"清理PT-Accelerator分区失败: {str(e)}")
    
    def add_cloudflare_ip(self, domain: str, ip: str):
        """添加Cloudflare优选IP到配置"""
        logger.info(f"为域名 {domain} 设置Cloudflare优选IP: {ip}")
        
        # 设置最佳IP
        self.best_cloudflare_ip = ip
        logger.info(f"设置最佳Cloudflare IP: {ip}")
        
        # 更新配置中的IP
        if not self.config.get("trackers"):
            self.config["trackers"] = []
        
        # 查找是否已存在该域名
        for tracker in self.config["trackers"]:
            if tracker["domain"] == domain:
                tracker["ip"] = ip
                break
        else:
            # 不存在则添加
            self.config["trackers"].append({
                "name": domain,
                "domain": domain,
                "ip": ip,
                "enable": True
            })
        
        # 保存配置（仅写入 trackers 变更）
        self._merge_write_config({"trackers": self.config.get("trackers", [])})
            
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = self.config
            logger.info("已同步更新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"更新全局config对象失败: {str(e)}")
        
        # 更新所有tracker的IP
        self._update_all_trackers_ip(ip)
        
        # 更新hosts
        self.update_hosts()
    
    def _update_all_trackers_ip(self, ip: str):
        """更新所有tracker的IP为最优IP"""
        if not self.config.get("trackers"):
            return
        
        for tracker in self.config["trackers"]:
            if tracker.get("enable"):
                tracker["ip"] = ip
                logger.info(f"更新tracker {tracker.get('domain')} 的IP为 {ip}")
        
        # 保存配置
        with open("config/config.yaml", 'w', encoding='utf-8') as f:
            yaml.dump(self.config, f, default_flow_style=False, allow_unicode=True)
            
        # 同步更新全局config对象，确保前端API获取到最新数据
        try:
            import app.main
            app.main.config = self.config
            logger.info("已同步更新全局config对象，确保前端获取到最新数据")
        except Exception as e:
            logger.error(f"更新全局config对象失败: {str(e)}")
    
    def run_cfst_and_update_hosts(self, script_path: str = None):
        if self.task_running:
            logger.warning("已有hosts更新任务在运行，阻止Cloudflare优选任务执行，避免冲突")
            return False
        self.task_running = True
        self.task_status = {"status": "running", "message": "正在执行Cloudflare优选IP任务"}
        try:
            # 架构自适应：未显式传入时按平台自动选择脚本
            if not script_path:
                machine = platform.machine().lower()
                if machine in ("aarch64", "arm64"):
                    script_path = "cfst_linux_arm64/cfst_hosts.sh"
                else:
                    script_path = "cfst_linux_amd64/cfst_hosts.sh"
            logger.info("开始执行严格串行的优选IP+更新tracker+更新hosts流程")
            best_ip = None
            if os.path.exists(script_path):
                self.task_status = {"status": "running", "message": "正在运行Cloudflare优选脚本"}
                result = subprocess.run(["bash", script_path], capture_output=True, text=True)
                if result.returncode == 0:
                    logger.info(f"脚本执行成功: {result.stdout}")
                    for line in result.stdout.splitlines():
                        if "找到最优IP" in line or "新 IP 为" in line:
                            if "新 IP 为" in line:
                                parts = line.split("新 IP 为")
                                if len(parts) > 1:
                                    best_ip = parts[1].strip()
                                    break
                            else:
                                parts = line.split()
                                for i, part in enumerate(parts):
                                    if part == "最优IP:" or part == "IP:":
                                        best_ip = parts[i+1].strip().rstrip(',')
                                        break
            else:
                logger.error(f"脚本文件不存在: {script_path}")
                self.task_status = {"status": "done", "message": f"优选失败: 脚本文件不存在: {script_path}"}
                self.task_running = False
                return False
            if not best_ip:
                logger.error("未能从脚本输出中提取到最优IP，流程中止")
                self.task_status = {"status": "done", "message": "优选失败: 未能提取到最优IP"}
                self.task_running = False
                return False
            self.best_cloudflare_ip = best_ip
            logger.info(f"串行流程提取到最优IP: {best_ip}")
            filtered_trackers = []  # 确保后续统计时变量已定义
            if self.config.get("trackers"):
                original_count = len(self.config["trackers"])
                non_cf_domains = []
                for tracker in self.config["trackers"]:
                    if not tracker.get("domain"):
                        continue
                    domain = tracker["domain"]
                    clean_domain = domain.split(':')[0] if ':' in domain else domain
                    if self.is_cloudflare_domain(clean_domain):
                        tracker["ip"] = best_ip
                        filtered_trackers.append(tracker)
                    else:
                        non_cf_domains.append(domain)
                if len(filtered_trackers) < original_count:
                    self.config["trackers"] = filtered_trackers
                    logger.info(f"[IP优选] 过滤了 {original_count - len(filtered_trackers)} 个非Cloudflare站点: {', '.join(non_cf_domains)}")
                logger.info(f"已将 {len(filtered_trackers)} 个Cloudflare站点Tracker的IP更新为 {best_ip}")
            config_path = "config/config.yaml"
            # 仅合并写 trackers（以及可能的 cloudflare_domains 后续有需要可一并传入）
            self._merge_write_config({"trackers": self.config.get("trackers", [])})
            self.update_config(self.config)
            try:
                import app.main
                app.main.config = self.config
                logger.info("已同步更新全局config对象，确保前端获取到最新数据")
            except Exception as e:
                logger.error(f"更新全局config对象失败: {str(e)}")
            # 严格串行流程下的合并与兜底
            ip_latency_cache = {}
            start_time = time.time()
            logger.info("开始处理PT站点条目")
            self.task_status = {"status": "running", "message": "正在处理PT站点条目"}
            pt_entries = self._collect_pt_entries()
            logger.info(f"处理PT站点条目完成，共 {len(pt_entries)} 条，耗时 {time.time() - start_time:.2f} 秒")
            sections = []
            if pt_entries:
                sections.append((self.pt_start_mark, pt_entries, self.pt_end_mark % len(pt_entries)))
            domain_ip_candidates = {}
            tracker_domains = set()
            disabled_domains = self._get_disabled_tracker_domains()  # 新增：获取所有禁用tracker域名
            if self.config.get("trackers"):
                for tracker in self.config["trackers"]:
                    if tracker.get("enable") and tracker.get("domain"):
                        tracker_domains.add(tracker["domain"])
            merged_hosts_backup = self._load_merged_hosts_backup()
            backup_domains = set(merged_hosts_backup.keys())
            current_domains = set()
            abnormal_sources = set()
            if self.config.get("hosts_sources"):
                total_sources = len([s for s in self.config["hosts_sources"] if s.get("enable") and s.get("url") and s.get("name")])
                logger.info(f"开始处理 {total_sources} 个外部hosts源")
                for i, source in enumerate(self.config["hosts_sources"]):
                    if source.get("enable") and source.get("url") and source.get("name"):
                        source_name = source.get("name", "未命名源")
                        self.task_status = {"status": "running", "message": f"正在处理hosts源 ({i+1}/{total_sources}): {source_name}"}
                        source_start_time = time.time()
                        logger.info(f"正在处理hosts源 ({i+1}/{total_sources}): {source_name}")
                        source_entries = self._fetch_hosts_source(source["url"])
                        logger.info(f"获取hosts源 {source_name} 完成，返回 {len(source_entries)} 条记录，耗时 {time.time() - source_start_time:.2f} 秒")
                        if len(source_entries) < 5:
                            abnormal_sources.add(source_name)
                        entry_process_start = time.time()
                        entry_count = 0
                        for ip, domain in source_entries:
                            # 新增：跳过禁用tracker域名
                            if domain in tracker_domains or domain.strip().lower() in disabled_domains:
                                continue
                            domain_ip_candidates.setdefault(domain, set()).add(ip)
                            current_domains.add(domain)
                            entry_count += 1
                        logger.info(f"处理hosts源 {source_name} 的 {entry_count} 条记录完成，耗时 {time.time() - entry_process_start:.2f} 秒")
                for domain, ip in self.domain_ip_history.items():
                    # 新增：跳过禁用tracker域名
                    if domain in tracker_domains or domain.strip().lower() in disabled_domains:
                        continue
                    domain_ip_candidates.setdefault(domain, set()).add(ip)
                    current_domains.add(domain)
            lost_domains = backup_domains - current_domains
            for lost_domain in lost_domains:
                lost_ip = merged_hosts_backup[lost_domain]
                if self._dns_check(lost_domain, lost_ip):
                    domain_ip_candidates.setdefault(lost_domain, set()).add(lost_ip)
                    logger.warning(f"[兜底保留] 域名 {lost_domain} 本次未被任何源收录，但DNS检测有效，保留上次IP: {lost_ip}")
                else:
                    logger.warning(f"[兜底丢弃] 域名 {lost_domain} 本次未被任何源收录，且DNS检测无效，丢弃上次IP: {lost_ip}")
            domain_ip_latency = {}
            log_lines = []
            merged_dict = {}
            for domain, ip_set in domain_ip_candidates.items():
                if is_blacklisted(domain):
                    continue
                best_ip = None
                best_latency = None
                ip_results = []
                for ip in ip_set:
                    latency = self._ping_ip(ip, cache=ip_latency_cache, domain=domain)
                    ip_results.append((ip, latency))
                    if latency is not None and (best_latency is None or latency < best_latency):
                        best_ip = ip
                        best_latency = latency
                if best_ip:
                    domain_ip_latency[domain] = (best_ip, best_latency)
                    merged_dict[domain] = best_ip
                    log_lines.append(f"域名 {domain} 选用IP: {best_ip}，延迟: {best_latency:.2f} ms")
                else:
                    ip = next(iter(ip_set))
                    domain_ip_latency[domain] = (ip, 999.0)
                    merged_dict[domain] = ip
                    log_lines.append(f"域名 {domain} 所有IP不可达，兜底选用: {ip}")
                
            # 批量处理完所有域名后，一次性生成最终hosts条目
            self.task_status = {"status": "running", "message": "正在生成最终hosts条目"}
            logger.info("生成合并后的最终hosts条目")
            merged_entries = [f"{ip}\t{domain}" for domain, (ip, _) in domain_ip_latency.items()]
            if merged_entries:
                sections.append((self.source_start_mark % "MergedHosts", merged_entries, self.source_end_mark % ("MergedHosts", len(merged_entries))))
                
            self.task_status = {"status": "running", "message": "正在更新系统hosts文件"}
            logger.info("开始更新系统hosts文件")
            update_start = time.time()
            self._update_system_hosts_with_sections(sections)
            logger.info(f"更新系统hosts文件完成，耗时 {time.time() - update_start:.2f} 秒")
            total_entries = sum(len(entries) for _, entries, _ in sections)
            logger.info(f"成功更新hosts文件，添加了{total_entries}条记录，共{len(sections)}个分区")
            logger.info("=== 域名优选IP结果汇总 ===")
            for line in log_lines:
                logger.info(line)
            self._save_merged_hosts_backup(merged_dict)
            self.task_status = {"status": "done", "message": f"Cloudflare优选完成！IP: {best_ip}，已更新 {len(filtered_trackers) if isinstance(filtered_trackers, list) else 0} 个Tracker和 {total_entries} 条hosts记录"}
            self.task_running = False
            logger.info("已完成hosts文件更新")
            if self.pending_update:
                logger.info("检测到pending_update标记，自动补偿执行一次update_hosts")
                self.pending_update = False
                self.update_hosts()
            return True
        except Exception as e:
            error_msg = f"严格串行流程执行失败: {str(e)}"
            logger.error(error_msg, exc_info=True)
            self.task_status = {"status": "done", "message": error_msg}
            self.task_running = False
            return False

    def get_task_status(self):
        """获取当前任务状态"""
        return self.task_status

    def is_cloudflare_domain(self, domain: str) -> bool:
        """判断域名是否使用了Cloudflare"""
        if not domain:
            logger.debug(f"[Cloudflare检测] 域名为空，返回False")
            return False
        
        # 规范化域名，移除协议前缀、路径后缀和端口号
        domain = domain.lower()
        domain = re.sub(r'^https?://', '', domain)
        domain = re.sub(r'/.*$', '', domain)  # 移除路径
        domain = re.sub(r':\d+$', '', domain)  # 移除端口号
        
        # 检查缓存中是否已有结果
        current_time = time.time()
        if domain in self.cloudflare_cache:
            cache_time, is_cf = self.cloudflare_cache[domain]
            # 检查缓存是否过期
            if current_time - cache_time < self.cache_expiry:
                logger.debug(f"[Cloudflare检测] 域名 {domain} 使用缓存结果: {is_cf}")
                return is_cf
        
        logger.info(f"[Cloudflare检测] 开始检测域名: {domain}")
        
        # 获取配置中的Cloudflare域名
        cf_domains_from_config = self.config.get('cloudflare_domains', [])
        if isinstance(cf_domains_from_config, list):
            self.cf_domains.update(cf_domains_from_config)
        elif isinstance(cf_domains_from_config, str):
            self.cf_domains.add(cf_domains_from_config)
        
        # 1. 检查域名是否在白名单中
        if domain in self.cf_domains:
            logger.info(f"[Cloudflare检测] 域名 {domain} 在配置的Cloudflare域名白名单中")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 2. 检查主域名
        main_domain = self._get_main_domain(domain)
        if main_domain in self.cf_domains:
            logger.info(f"[Cloudflare检测] 域名 {domain} 的主域名 {main_domain} 在Cloudflare域名白名单中")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 3. 检查IP范围
        try:
            ip = socket.gethostbyname(domain)
            logger.debug(f"[Cloudflare检测] 域名 {domain} 解析到IP: {ip}")
            if self._is_cloudflare_ip(ip):
                logger.info(f"[Cloudflare检测] 域名 {domain} 解析到Cloudflare IP范围: {ip}")
                self._cache_cloudflare_result(domain, True)
                return True
            else:
                logger.debug(f"[Cloudflare检测] 域名 {domain} 解析到非Cloudflare IP: {ip}")
        except socket.error as e:
            logger.debug(f"[Cloudflare检测] 域名 {domain} 解析IP失败: {str(e)}")
        
        # 4. 检查DNS CNAME记录
        logger.debug(f"[Cloudflare检测] 开始CNAME记录检查: {domain}")
        is_cf_by_cname = self._check_cloudflare_by_cname(domain)
        if is_cf_by_cname:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过CNAME记录确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 5. 检查HTTP头部
        logger.debug(f"[Cloudflare检测] 开始HTTP头部检查: {domain}")
        is_cf_by_headers = self._check_cloudflare_by_headers(domain)
        if is_cf_by_headers:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过HTTP头部确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 6. 使用HTTP请求方法检测
        logger.debug(f"[Cloudflare检测] 开始HTTP请求方法检查: {domain}")
        is_cf_by_http = self._check_cloudflare_by_http(domain)
        if is_cf_by_http:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过HTTP请求内容确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 7. 使用多个DNS服务器进行验证
        logger.debug(f"[Cloudflare检测] 开始多DNS服务器验证: {domain}")
        is_cf_by_multi_dns = self._check_cloudflare_by_multi_dns(domain)
        if is_cf_by_multi_dns:
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过多DNS服务器确认使用Cloudflare")
            self._cache_cloudflare_result(domain, True)
            return True
        
        # 8. 最后尝试直接解析
        logger.debug(f"[Cloudflare检测] 开始最后IP解析尝试: {domain}")
        try:
            for attempt in range(2):  # 尝试两次，增加可靠性
                ip = socket.gethostbyname(domain)
                logger.debug(f"[Cloudflare检测] 域名 {domain} 最终解析尝试 #{attempt+1}, IP: {ip}")
                if self._is_cloudflare_ip(ip):
                    logger.info(f"[Cloudflare检测] 域名 {domain} 最终解析确认使用Cloudflare IP: {ip}")
                    self._cache_cloudflare_result(domain, True)
                    return True
                time.sleep(0.5)  # 短暂延迟后再次尝试
        except socket.error as e:
            logger.debug(f"[Cloudflare检测] 域名 {domain} 最终解析失败: {str(e)}")
        
        logger.info(f"[Cloudflare检测] 域名 {domain} 通过所有检测方法均未确认使用Cloudflare")
        self._cache_cloudflare_result(domain, False)
        return False
    
    def _cache_cloudflare_result(self, domain, is_cloudflare):
        """缓存Cloudflare检测结果"""
        self.cloudflare_cache[domain] = (time.time(), is_cloudflare)
        # 清理过期缓存
        if len(self.cloudflare_cache) > 1000:  # 防止缓存过大
            self._clean_expired_cache()
    
    def _clean_expired_cache(self):
        """清理过期的缓存项"""
        current_time = time.time()
        expired_keys = [
            k for k, (timestamp, _) in self.cloudflare_cache.items() 
            if current_time - timestamp > self.cache_expiry
        ]
        for key in expired_keys:
            del self.cloudflare_cache[key]
    
    def _get_main_domain(self, domain: str) -> str:
        """获取域名的主域名部分"""
        parts = domain.split('.')
        if len(parts) <= 2:
            return domain
        
        # 检查是否为国家/地区代码域名（如 .co.uk, .com.cn）
        country_tlds = {'uk', 'au', 'jp', 'cn', 'br', 'mx', 'ru', 'eu', 'de', 'fr', 'it', 'nl', 'sg', 'kr'}
        if len(parts) >= 3 and parts[-2] in country_tlds:
            return '.'.join(parts[-3:])
        
        return '.'.join(parts[-2:])
    
    def _check_cloudflare_by_cname(self, domain: str) -> bool:
        """通过CNAME记录检查是否使用Cloudflare"""
        try:
            import dns.resolver
            try:
                # 配置解析器
                resolver = dns.resolver.Resolver(configure=True)
                resolver.timeout = 2.0
                resolver.lifetime = 2.0
                
                # 查询CNAME记录
                answers = resolver.resolve(domain, 'CNAME')
                for rdata in answers:
                    cname = str(rdata.target).lower()
                    # 检查CNAME是否指向Cloudflare
                    cf_indicators = ['cloudflare', 'cdn', 'cdnproviders', 'ssl', 'workers.dev', 'pages.dev']
                    if any(indicator in cname for indicator in cf_indicators):
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 的CNAME指向Cloudflare: {cname}")
                        return True
            except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.Timeout, dns.exception.DNSException) as e:
                logger.debug(f"[Cloudflare检测] CNAME解析失败: {domain}, 错误: {str(e)}")
        except ImportError:
            logger.debug("[Cloudflare检测] dns.resolver模块不可用")
        
        return False
    
    def _check_cloudflare_by_headers(self, domain: str) -> bool:
        """通过HTTP响应头检查是否使用Cloudflare"""
        try:
            import requests
            
            # 禁用SSL不安全请求的警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                # 尝试HTTPS和HTTP
                for protocol in ['https', 'http']:
                    try:
                        url = f"{protocol}://{domain}"
                        resp = requests.head(url, headers=headers, timeout=3, allow_redirects=True, verify=False)
                        
                        # 检查Cloudflare特有的HTTP头
                        cf_headers = [
                            'cf-ray', 'cf-cache-status', 'cf-request-id', 'cf-worker', 
                            'cf-connecting-ip', 'cf-visitor', 'cf-bgj', 'cf-ipcountry'
                        ]
                        
                        for cf_header in cf_headers:
                            if cf_header in resp.headers:
                                logger.debug(f"[Cloudflare检测] 域名 {domain} 的HTTP响应头包含Cloudflare标识: {cf_header}")
                                return True
                        
                        # 检查Server头
                        server = resp.headers.get('Server', '').lower()
                        if 'cloudflare' in server:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的Server头指示Cloudflare: {server}")
                            return True
                        
                        # 检查Set-Cookie头
                        cookies = resp.headers.get('Set-Cookie', '').lower()
                        if any(cookie in cookies for cookie in ['__cfduid', 'cf_clearance', 'cf_use_ob']):
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的Cookie包含Cloudflare标识")
                            return True
                    except Exception as e:
                        logger.debug(f"[Cloudflare检测] {protocol}请求失败: {domain}, 错误: {str(e)}")
                        continue
            except Exception as e:
                logger.debug(f"[Cloudflare检测] HTTP请求异常: {str(e)}")
        except ImportError:
            logger.debug("[Cloudflare检测] requests模块不可用")
        
        return False
    
    def _check_cloudflare_by_multi_dns(self, domain: str) -> bool:
        """使用多个DNS服务器验证是否使用Cloudflare"""
        try:
            # 使用常见的公共DNS服务器
            dns_servers = ['8.8.8.8', '1.1.1.1', '9.9.9.9', '208.67.222.222']
            
            try:
                import dns.resolver
                import concurrent.futures
                
                def resolve_with_dns(dns_server):
                    try:
                        resolver = dns.resolver.Resolver(configure=False)
                        resolver.nameservers = [dns_server]
                        resolver.timeout = 1.5
                        resolver.lifetime = 1.5
                        answers = resolver.resolve(domain, 'A')
                        return [str(rdata) for rdata in answers]
                    except Exception as e:
                        logger.debug(f"[Cloudflare检测] DNS {dns_server} 解析失败: {str(e)}")
                        return []
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    future_to_dns = {executor.submit(resolve_with_dns, dns): dns for dns in dns_servers}
                    for future in concurrent.futures.as_completed(future_to_dns):
                        dns = future_to_dns[future]
                        try:
                            ips = future.result()
                            for ip in ips:
                                if self._is_cloudflare_ip(ip):
                                    logger.debug(f"[Cloudflare检测] 通过DNS {dns} 解析到Cloudflare IP: {ip}")
                                    return True
                        except Exception as e:
                            logger.debug(f"[Cloudflare检测] 处理DNS {dns} 结果时出错: {str(e)}")
            except ImportError:
                logger.debug("[Cloudflare检测] dns.resolver或concurrent.futures模块不可用")
                
                # 备用方案：使用socket直接解析
                try:
                    ip = socket.gethostbyname(domain)
                    if self._is_cloudflare_ip(ip):
                        logger.debug(f"[Cloudflare检测] 使用socket直接解析到Cloudflare IP: {ip}")
                        return True
                except socket.error:
                    pass
        except Exception as e:
            logger.debug(f"[Cloudflare检测] 多DNS检测异常: {str(e)}")
        
        return False
    
    def _is_cloudflare_ip(self, ip: str) -> bool:
        """判断IP是否属于Cloudflare"""
        if not ip:
            logger.debug("[Cloudflare检测] IP为空")
            return False
            
        try:
            # 检查常见的Cloudflare IP范围
            cf_ip_ranges = [
                # IPv4范围 (部分)
                '103.21.244.0/22', '103.22.200.0/22', '103.31.4.0/22', '104.16.0.0/13', 
                '104.24.0.0/14', '108.162.192.0/18', '131.0.72.0/22', '141.101.64.0/18', 
                '162.158.0.0/15', '172.64.0.0/13', '173.245.48.0/20', '188.114.96.0/20', 
                '190.93.240.0/20', '197.234.240.0/22', '198.41.128.0/17',
                
                # IPv6范围 (部分)
                '2400:cb00::/32', '2405:8100::/32', '2405:b500::/32', '2606:4700::/32', 
                '2803:f800::/32', '2c0f:f248::/32', '2a06:98c0::/29'
            ]
            
            # 获取版本信息
            family = socket.AF_INET if '.' in ip else socket.AF_INET6
            
            # 转换IP为网络字节序
            ip_packed = socket.inet_pton(family, ip)
            
            try:
                import ipaddress
                ip_obj = ipaddress.ip_address(ip)
                
                for ip_range in cf_ip_ranges:
                    try:
                        if ip_obj in ipaddress.ip_network(ip_range):
                            logger.debug(f"[Cloudflare检测] IP {ip} 属于Cloudflare IP范围 {ip_range}")
                            return True
                    except ValueError as e:
                        logger.debug(f"[Cloudflare检测] 检查IP范围出错: {ip_range}, 错误: {str(e)}")
                        continue
                
                # 未匹配到任何范围
                logger.debug(f"[Cloudflare检测] IP {ip} 不在任何已知的Cloudflare IP范围内")
                
            except ImportError:
                logger.debug("[Cloudflare检测] ipaddress模块不可用，使用基本检查")
                
                # 如果ipaddress模块不可用，至少检查一些常见的范围
                cf_prefixes = [
                    '104.16.', '104.17.', '104.18.', '104.19.', '104.20.', '104.21.', '104.22.', '104.23.',
                    '172.64.', '172.65.', '172.66.', '172.67.', '172.68.', '172.69.', '172.70.',
                    '162.158.', '198.41.', '103.21.244.', '103.22.200.'
                ]
                
                for prefix in cf_prefixes:
                    if ip.startswith(prefix):
                        logger.debug(f"[Cloudflare检测] IP {ip} 匹配Cloudflare前缀 {prefix}")
                        return True
                
                logger.debug(f"[Cloudflare检测] IP {ip} 不匹配任何已知的Cloudflare前缀")
                
        except Exception as e:
            logger.debug(f"[Cloudflare检测] IP检查异常: {str(e)}")
        
        return False

    def remove_tracker_domain(self, domain: str):
        """删除tracker时同步清理历史IP和失败计数，防止兜底机制误兜底"""
        if domain in self.domain_ip_history:
            del self.domain_ip_history[domain]
        if domain in self.domain_failure_counter:
            del self.domain_failure_counter[domain]
        # 日志
        logger = logging.getLogger(__name__)
        logger.info(f"[Tracker删除] 已清理历史记录和失败计数: {domain}")

    def _check_cloudflare_by_cf_ray(self, domain: str) -> bool:
        """通过检查响应头中的CF-Ray字段判断域名是否使用Cloudflare"""
        try:
            logger.debug(f"[Cloudflare检测] 使用CF-Ray标头检查域名 {domain}")
            
            # 禁用SSL不安全请求的警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            urls = [
                f"https://{domain}",
                f"http://{domain}"
            ]
            
            for url in urls:
                try:
                    response = requests.get(
                        url, 
                        headers=self.headers, 
                        timeout=5,
                        verify=False
                    )
                    
                    # 检查CF-Ray头部
                    if 'CF-Ray' in response.headers:
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 响应包含CF-Ray头: {response.headers.get('CF-Ray')}")
                        return True
                        
                    # 检查其他Cloudflare特有的头部
                    cf_headers = ['cf-cache-status', 'cf-apo-via', 'cf-edge-cache', 'cf-bgj']
                    for header in cf_headers:
                        if header in response.headers:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 响应包含Cloudflare特有头: {header}")
                            return True
                            
                    # 检查服务器信息
                    server = response.headers.get('Server', '').lower()
                    if 'cloudflare' in server:
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 服务器信息包含Cloudflare: {server}")
                        return True
                        
                except requests.RequestException as e:
                    logger.debug(f"[Cloudflare检测] 请求 {url} 失败: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.debug(f"[Cloudflare检测] CF-Ray检查异常: {str(e)}")
            
        return False

    def is_cloudflare_enabled(self, domain: str) -> bool:
        """
        检查域名是否启用了Cloudflare
        综合使用多种方法进行检测，任一方法返回True则认为域名使用了Cloudflare
        """
        if not domain:
            return False
            
        logger.debug(f"[Cloudflare检测] 开始检查域名 {domain}")
        
        # 首先尝试DNS检测方法
        if self._check_cloudflare_by_dns(domain):
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过DNS检测确认使用Cloudflare")
            return True
            
        # 然后尝试通过Cloudflare IP范围检测
        resolved_ips = self._resolve_domain(domain)
        if resolved_ips:
            for ip in resolved_ips:
                if self._is_cloudflare_ip(ip):
                    logger.info(f"[Cloudflare检测] 域名 {domain} 解析到Cloudflare IP: {ip}")
                    return True
                    
        # 最后尝试HTTP头部检测方法
        if self._check_cloudflare_by_cf_ray(domain):
            logger.info(f"[Cloudflare检测] 域名 {domain} 通过HTTP头部检测确认使用Cloudflare")
            return True
            
        logger.debug(f"[Cloudflare检测] 域名 {domain} 未检测到使用Cloudflare")
        return False

    def _resolve_domain(self, domain: str) -> List[str]:
        """解析域名获取IP地址列表"""
        ips = []
        try:
            # 首先尝试使用socket库解析
            try:
                ip = socket.gethostbyname(domain)
                ips.append(ip)
            except socket.error:
                pass
            
            # 如果有dns.resolver模块，尝试使用它获取更完整的结果
            try:
                import dns.resolver
                resolver = dns.resolver.Resolver(configure=True)
                resolver.timeout = 2.0
                resolver.lifetime = 2.0
                answers = resolver.resolve(domain, 'A')
                for rdata in answers:
                    ip = str(rdata)
                    if ip not in ips:
                        ips.append(ip)
            except (ImportError, dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.exception.DNSException):
                pass
                
            # 如果上述方法都失败，使用系统nslookup命令尝试解析
            if not ips:
                try:
                    import subprocess
                    cmd = ['nslookup', domain]
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
                    for line in result.stdout.splitlines():
                        line = line.strip()
                        # 查找Address行，提取IP地址
                        if line.startswith('Address:') or 'Address:' in line:
                            ip = line.split('Address:')[-1].strip()
                            if ip and ip not in ips and not ip.startswith('127.0.') and not ip.startswith('::1'):
                                ips.append(ip)
                except (subprocess.SubprocessError, FileNotFoundError, Exception):
                    pass
                    
        except Exception as e:
            logger.debug(f"[域名解析] 解析域名 {domain} 出错: {str(e)}")
            
        return ips
        
    def _check_cloudflare_by_dns(self, domain: str) -> bool:
        """通过DNS记录检查域名是否使用Cloudflare"""
        try:
            # 检查域名NS记录是否指向Cloudflare
            try:
                import dns.resolver
                resolver = dns.resolver.Resolver(configure=True)
                resolver.timeout = 2.0
                resolver.lifetime = 2.0
                
                # 先检查顶级域名的NS记录
                try:
                    parts = domain.split('.')
                    if len(parts) > 2:
                        root_domain = '.'.join(parts[-2:])
                    else:
                        root_domain = domain
                    
                    answers = resolver.resolve(root_domain, 'NS')
                    for rdata in answers:
                        ns = str(rdata).lower()
                        if 'cloudflare' in ns or 'ns.cloudflare.com' in ns:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的NS记录指向Cloudflare: {ns}")
                            return True
                except Exception:
                    pass
                
                # 检查CNAME记录
                try:
                    answers = resolver.resolve(domain, 'CNAME')
                    for rdata in answers:
                        cname = str(rdata.target).lower()
                        # Cloudflare CNAME特征
                        cf_indicators = ['cloudflare', 'cdn', 'workers.dev', 'pages.dev']
                        if any(indicator in cname for indicator in cf_indicators):
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的CNAME指向Cloudflare: {cname}")
                            return True
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    pass
                
                # 检查MX记录
                try:
                    answers = resolver.resolve(domain, 'MX')
                    for rdata in answers:
                        mx = str(rdata.exchange).lower()
                        if 'cloudflare' in mx:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的MX记录指向Cloudflare: {mx}")
                            return True
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    pass
                
                # 检查TXT记录中的特征
                try:
                    answers = resolver.resolve(domain, 'TXT')
                    for rdata in answers:
                        txt = str(rdata).lower()
                        if 'cloudflare' in txt:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的TXT记录包含Cloudflare特征: {txt}")
                            return True
                except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
                    pass
                    
            except ImportError:
                logger.debug("[Cloudflare检测] dns.resolver模块不可用")
                
        except Exception as e:
            logger.debug(f"[Cloudflare检测] DNS检测异常: {str(e)}")
            
        return False

    def _check_cloudflare_by_http(self, domain: str) -> bool:
        """通过HTTP请求和响应头检查域名是否使用Cloudflare"""
        try:
            # 禁用SSL不安全请求的警告
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            
            # 尝试HTTPS和HTTP
            for protocol in ['https', 'http']:
                logger.debug(f"[Cloudflare检测] 尝试 {protocol} 请求: {domain}")
                url = f"{protocol}://{domain}"
                
                # 尝试发送HTTP请求
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Connection': 'close'
                }
                
                # 设置较短的超时时间，避免长时间等待
                timeout = 5
                
                try:
                    response = requests.get(url, headers=headers, timeout=timeout, verify=False)
                    
                    # 检查HTTP头部是否有Cloudflare特征
                    response_headers = response.headers
                    
                    # Cloudflare特征头部
                    cf_headers = [
                        'cf-ray',
                        'cf-cache-status',
                        'cf-request-id',
                        'cf-worker',
                        'cf-connecting-ip',
                        'cf-ipcountry',
                        'cf-visitor',
                        'cf-bgj'
                    ]
                    
                    for header in cf_headers:
                        if header.lower() in response_headers:
                            logger.debug(f"[Cloudflare检测] 域名 {domain} 的HTTP响应头包含Cloudflare特征: {header}")
                            return True
                    
                    # 检查服务器头部
                    server = response_headers.get('server', '').lower()
                    if 'cloudflare' in server:
                        logger.debug(f"[Cloudflare检测] 域名 {domain} 的Server头显示使用Cloudflare: {server}")
                        return True
                    
                    # 检查响应内容中的Cloudflare特征
                    try:
                        content = response.text.lower()
                        cf_content_markers = [
                            'cloudflare',
                            'cdn-cgi',
                            'cloudflare-nginx',
                            '__cf_email__',
                            'cf-error-code',
                            'cf_chl_'
                        ]
                        
                        for marker in cf_content_markers:
                            if marker in content:
                                logger.debug(f"[Cloudflare检测] 域名 {domain} 的响应内容包含Cloudflare特征: {marker}")
                                return True
                    except Exception as e:
                        logger.debug(f"[Cloudflare检测] 解析响应内容时出错: {str(e)}")
                        
                except requests.RequestException as e:
                    logger.debug(f"[Cloudflare检测] {protocol}请求异常: {str(e)}")
                    
                    # 如果连接被重置，可能是Cloudflare防火墙拦截
                    if "connection" in str(e).lower() and ("reset" in str(e).lower() or "aborted" in str(e).lower()):
                        logger.debug(f"[Cloudflare检测] 连接被重置，可能是Cloudflare防火墙: {domain}")
                        return True
                    continue  # 尝试下一个协议
                    
        except Exception as e:
            logger.debug(f"[Cloudflare检测] HTTP检测异常: {str(e)}")
            
        return False

    def _load_merged_hosts_backup(self):
        backup_path = os.path.join("config", "merged_hosts_backup.json")
        if os.path.exists(backup_path):
            try:
                with open(backup_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"读取MergedHosts备份失败: {e}")
        return {}

    def _save_merged_hosts_backup(self, merged_dict):
        backup_path = os.path.join("config", "merged_hosts_backup.json")
        try:
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(merged_dict, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"写入MergedHosts备份失败: {e}")

    def _dns_check(self, domain, ip):
        try:
            result = socket.gethostbyname(domain)
            return result == ip
        except Exception:
            return False

    def _get_disabled_tracker_domains(self):
        """获取所有已禁用的tracker域名"""
        disabled_domains = set()
        trackers = self.config.get('trackers', [])
        for t in trackers:
            if not t.get('enable', True) and t.get('domain'):
                disabled_domains.add(t['domain'].strip().lower())
        return disabled_domains


 
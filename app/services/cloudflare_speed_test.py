import logging
import os
import subprocess
import time
import shutil
import platform
from typing import Dict, Any

from app.services.hosts_manager import HostsManager

logger = logging.getLogger(__name__)

class CloudflareSpeedTestService:
    """CloudflareSpeedTest服务，用于测试优选Cloudflare IP"""
    
    def __init__(self, config: Dict[str, Any], hosts_manager: HostsManager):
        self.config = config
        self.hosts_manager = hosts_manager
        
        # 工作目录
        self.base_dir = os.getcwd()
        logger.info(f"当前工作目录: {self.base_dir}")
        
        # 查找CloudflareSpeedTest可执行文件
        self.cft_path = self._find_cloudflare_st()
        self.bin_dir = os.path.dirname(self.cft_path)
        
        # 结果和IP文件路径
        self.result_file = os.path.join(self.base_dir, "result.csv")
        self.ip_file = os.path.join(self.base_dir, "ip.txt")
        self.ipv6_file = os.path.join(self.base_dir, "ipv6.txt")
        
        # 记录当前状态
        self.running = False
        
        # 输出初始化信息
        logger.info(f"CloudflareSpeedTest可执行文件: {self.cft_path}")
        logger.info(f"CloudflareSpeedTest目录: {self.bin_dir}")
        logger.info(f"IP文件路径: {self.ip_file}")
        logger.info(f"IPv6文件路径: {self.ipv6_file}")
        logger.info(f"结果文件路径: {self.result_file}")
        
        # 确保IP文件存在
        self._ensure_ip_files()
        
    def _find_cloudflare_st(self) -> str:
        """查找CloudflareSpeedTest可执行文件，支持架构自适应"""
        # 获取架构目录
        arch_dir = self._get_arch_dir()
        machine = platform.machine().lower()
        logger.info(f"检测到架构: {machine}, 使用目录: {arch_dir}")
        
        # 可能的路径，按架构自适应
        possible_paths = [
            # 在当前目录查找
            os.path.join(self.base_dir, "cfst"),
            os.path.join(self.base_dir, arch_dir, "cfst"),
            
            # 在系统目录查找
            "/usr/local/bin/cfst",
            "/usr/bin/cfst",
            
            # 在Docker环境中的路径
            "/app/cfst",
            f"/app/{arch_dir}/cfst"
        ]
        
        # 输出所有可能的路径方便调试
        logger.info("正在查找CloudflareSpeedTest可执行文件...")
        for path in possible_paths:
            logger.info(f"检查路径: {path} - {'存在' if os.path.exists(path) else '不存在'}")
        
        # 查找可执行文件
        for path in possible_paths:
            if os.path.exists(path) and os.access(path, os.X_OK):
                logger.info(f"找到可执行的CloudflareSpeedTest: {path}")
                return path
                
        # 如果没有找到可执行文件，使用架构自适应的默认路径并发出警告
        default_path = f"./{arch_dir}/cfst"
        logger.warning(f"未找到CloudflareSpeedTest可执行文件，将使用默认路径 {default_path}")
        return default_path
        
    def update_config(self, config: Dict[str, Any]):
        """更新配置"""
        self.config = config
    
    def _get_arch_dir(self) -> str:
        """获取当前架构对应的目录名"""
        machine = platform.machine().lower()
        if machine in ("aarch64", "arm64"):
            return "cfst_linux_arm64"
        else:
            return "cfst_linux_amd64"
    
    def _ensure_ip_files(self):
        """确保IP文件存在"""
        logger.info(f"确保IP文件存在: {self.ip_file}")
        
        # 检查当前目录下是否已存在ip.txt
        if os.path.exists(self.ip_file):
            logger.info(f"IP文件已存在: {self.ip_file}")
            self._verify_ip_file(self.ip_file)
            return
        
        # 未找到ip.txt，尝试在可执行文件同目录下查找
        bin_dir_ip_file = os.path.join(self.bin_dir, "ip.txt")
        if os.path.exists(bin_dir_ip_file):
            logger.info(f"在可执行文件目录下找到IP文件: {bin_dir_ip_file}")
            try:
                # 复制到当前目录
                shutil.copy(bin_dir_ip_file, self.ip_file)
                logger.info(f"已复制IP文件: {bin_dir_ip_file} -> {self.ip_file}")
                self._verify_ip_file(self.ip_file)
                return
            except Exception as e:
                logger.error(f"复制IP文件失败: {str(e)}")
        
        # 在其他可能位置查找，支持架构自适应
        logger.info("在其他位置查找IP文件...")
        # 获取架构目录
        arch_dir = self._get_arch_dir()
        
        possible_paths = [
            os.path.join(self.base_dir, arch_dir, "ip.txt"),
            "/usr/local/bin/ip.txt",
            "/usr/local/share/CloudflareST/ip.txt",
            "/app/ip.txt"
        ]
        
        for path in possible_paths:
            logger.info(f"检查路径: {path} - {'存在' if os.path.exists(path) else '不存在'}")
            if os.path.exists(path):
                try:
                    shutil.copy(path, self.ip_file)
                    logger.info(f"已复制IP文件: {path} -> {self.ip_file}")
                    self._verify_ip_file(self.ip_file)
                    return
                except Exception as e:
                    logger.error(f"复制IP文件失败: {str(e)}")
        
        # 还是找不到，创建一个基本的
        logger.warning(f"未找到现有IP文件，创建一个基本的Cloudflare IP列表在 {self.ip_file}")
        self._create_default_ip_file()
        
        # 同样处理IPv6文件
        if self.config.get("cloudflare", {}).get("ipv6", False):
            self._ensure_ipv6_file()
    
    def _verify_ip_file(self, file_path: str):
        """验证IP文件是否有效"""
        try:
            with open(file_path, 'r') as f:
                content = f.read()
                line_count = len(content.splitlines())
                logger.info(f"IP文件内容长度: {len(content)} 字节, {line_count} 行")
                if len(content) < 10 or line_count < 2:
                    logger.warning(f"IP文件内容可能无效，将创建默认IP文件")
                    self._create_default_ip_file()
        except Exception as e:
            logger.error(f"读取IP文件失败: {str(e)}")
            self._create_default_ip_file()
    
    def _create_default_ip_file(self):
        """创建默认的IP文件"""
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(self.ip_file), exist_ok=True)
            
            with open(self.ip_file, "w") as f:
                f.write("# Cloudflare IP Ranges\n")
                f.write("# From: https://www.cloudflare.com/ips/\n")
                f.write("1.1.1.0/24\n")  # Cloudflare DNS
                f.write("1.0.0.0/24\n")  # Cloudflare DNS
                f.write("104.16.0.0/12\n")  # Cloudflare CDN
                f.write("172.64.0.0/13\n")  # Cloudflare CDN
                f.write("173.245.48.0/20\n")  # Cloudflare
                f.write("103.21.244.0/22\n")  # Cloudflare
                f.write("103.22.200.0/22\n")  # Cloudflare
                f.write("103.31.4.0/22\n")  # Cloudflare
                f.write("141.101.64.0/18\n")  # Cloudflare
                f.write("108.162.192.0/18\n")  # Cloudflare
                f.write("190.93.240.0/20\n")  # Cloudflare
                f.write("188.114.96.0/20\n")  # Cloudflare
                f.write("197.234.240.0/22\n")  # Cloudflare
                f.write("198.41.128.0/17\n")  # Cloudflare
                f.write("162.158.0.0/15\n")  # Cloudflare
                f.write("104.16.0.0/13\n")  # Cloudflare
                f.write("104.24.0.0/14\n")  # Cloudflare
            
            # 输出文件信息
            if os.path.exists(self.ip_file):
                file_size = os.path.getsize(self.ip_file)
                logger.info(f"成功创建IP文件: {self.ip_file}, 大小: {file_size} 字节")
                with open(self.ip_file, 'r') as f:
                    lines = f.readlines()
                    logger.info(f"IP文件包含 {len(lines)} 行")
            else:
                logger.error(f"IP文件创建失败: {self.ip_file}")
        except Exception as e:
            logger.error(f"创建IP文件失败: {str(e)}")
    
    def _ensure_ipv6_file(self):
        """确保IPv6文件存在"""
        logger.info(f"确保IPv6文件存在: {self.ipv6_file}")
        
        if os.path.exists(self.ipv6_file):
            logger.info(f"IPv6文件已存在: {self.ipv6_file}")
            return
        
        # 在可执行文件目录下查找
        bin_dir_ipv6_file = os.path.join(self.bin_dir, "ipv6.txt")
        if os.path.exists(bin_dir_ipv6_file):
            try:
                shutil.copy(bin_dir_ipv6_file, self.ipv6_file)
                logger.info(f"已复制IPv6文件: {bin_dir_ipv6_file} -> {self.ipv6_file}")
                return
            except Exception as e:
                logger.error(f"复制IPv6文件失败: {str(e)}")
        
        # 在其他位置查找，支持架构自适应
        # 获取架构目录
        arch_dir = self._get_arch_dir()
        
        possible_paths = [
            os.path.join(self.base_dir, arch_dir, "ipv6.txt"),
            "/usr/local/bin/ipv6.txt",
            "/usr/local/share/CloudflareST/ipv6.txt",
            "/app/ipv6.txt"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                try:
                    shutil.copy(path, self.ipv6_file)
                    logger.info(f"已复制IPv6文件: {path} -> {self.ipv6_file}")
                    return
                except Exception as e:
                    logger.error(f"复制IPv6文件失败: {str(e)}")
        
        # 创建一个基本的IPv6文件
        try:
            with open(self.ipv6_file, "w") as f:
                f.write("# Cloudflare IPv6 Ranges\n")
                f.write("# From: https://www.cloudflare.com/ips/\n")
                f.write("2400:cb00::/32\n")
                f.write("2405:8100::/32\n")
                f.write("2606:4700::/32\n")
                f.write("2803:f800::/32\n")
                f.write("2a06:98c0::/29\n")
                f.write("2c0f:f248::/32\n")
            
            logger.info(f"成功创建IPv6文件: {self.ipv6_file}")
        except Exception as e:
            logger.error(f"创建IPv6文件失败: {str(e)}")
    
    def run(self):
        """运行CloudflareSpeedTest"""
        if self.running:
            logger.warning("CloudflareSpeedTest已在运行中，跳过本次执行")
            return False
        
        try:
            self.running = True
            logger.info("开始运行CloudflareSpeedTest...")
            
            # 确保IP文件存在
            self._ensure_ip_files()
            
            # 验证文件和可执行文件是否存在
            if not os.path.exists(self.cft_path):
                logger.error(f"CloudflareSpeedTest可执行文件不存在: {self.cft_path}")
                return {
                    "success": False,
                    "logs": [f"错误: CloudflareSpeedTest可执行文件不存在: {self.cft_path}"]
                }
            
            if not os.path.exists(self.ip_file):
                logger.error(f"IP文件不存在: {self.ip_file}")
                return {
                    "success": False,
                    "logs": [f"错误: IP文件不存在: {self.ip_file}"]
                }
            
            # 列出目录内容，便于调试
            logger.info(f"当前目录文件列表: {', '.join(os.listdir(self.base_dir))}")
            
            # 构建命令行参数
            cmd = [self.cft_path]
            
            # 添加配置中的参数
            cloudflare_config = self.config.get("cloudflare", {})
            
            # 注意：不要使用ipv4参数，CloudflareSpeedTest默认就是测试IPv4
            # 只有需要IPv6时才添加-ipv6参数
            if cloudflare_config.get("ipv6", False):
                cmd.append("-ipv6")
            
            # 输出文件 - 使用绝对路径
            cmd.extend(["-o", self.result_file])
            
            # 显式指定IP文件 - 使用绝对路径
            cmd.extend(["-f", self.ip_file])
            
            # 其他参数
            additional_args = cloudflare_config.get("additional_args", "")
            if additional_args:
                # 确保额外参数中不包含-ipv4
                args_list = []
                for arg in additional_args.split():
                    if arg.strip() != "-ipv4":
                        args_list.append(arg.strip())
                if args_list:
                    cmd.extend(args_list)
            
            # 设置工作目录
            working_dir = self.base_dir
            
            # 运行命令
            cmd_str = ' '.join(cmd)
            logger.info(f"执行命令: {cmd_str}")
            logger.info(f"工作目录: {working_dir}")
            
            # 将命令写入临时脚本文件，便于调试
            script_path = os.path.join(self.base_dir, "cloudflare_test.sh")
            with open(script_path, "w") as f:
                f.write("#!/bin/bash\n")
                f.write(f"cd {working_dir}\n")
                f.write(f"{cmd_str}\n")
            os.chmod(script_path, 0o755)
            logger.info(f"已创建调试脚本: {script_path}")
            
            # 执行命令
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=working_dir  # 设置工作目录
            )
            
            # 实时获取输出
            logs = []
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    log_line = output.strip()
                    logger.info(log_line)
                    logs.append(log_line)
            
            # 获取错误信息
            stderr = process.stderr.read()
            if stderr:
                logger.error(f"CloudflareSpeedTest执行错误: {stderr}")
                logs.append(f"错误: {stderr}")
            
            # 检查结果
            if os.path.exists(self.result_file):
                # 处理结果
                self._process_results()
                logger.info("CloudflareSpeedTest执行完成")
            else:
                logger.error("CloudflareSpeedTest执行失败，未生成结果文件")
            
            return {
                "success": process.returncode == 0,
                "logs": logs
            }
        except Exception as e:
            logger.error(f"运行CloudflareSpeedTest出错: {str(e)}")
            return {
                "success": False,
                "logs": [f"错误: {str(e)}"]
            }
        finally:
            self.running = False
    
    def _process_results(self):
        """处理测试结果"""
        try:
            if not os.path.exists(self.result_file):
                logger.error("结果文件不存在")
                return
            
            # 读取结果文件
            with open(self.result_file, 'r') as f:
                lines = f.readlines()
            
            if len(lines) <= 1:  # 只有标题行
                logger.warning("结果文件中没有有效数据")
                return
            
            # 解析标题行
            headers = lines[0].strip().split(',')
            
            # 获取IP和速度列的索引
            ip_index = headers.index("IP")
            speed_index = headers.index("下载速度 (MB/s)")
            
            # 获取最快的IP
            best_ip = None
            best_speed = 0
            
            for i in range(1, len(lines)):
                data = lines[i].strip().split(',')
                if len(data) > max(ip_index, speed_index):
                    ip = data[ip_index]
                    try:
                        speed = float(data[speed_index])
                        if speed > best_speed:
                            best_speed = speed
                            best_ip = ip
                    except ValueError:
                        continue
            
            if best_ip:
                logger.info(f"找到最优IP: {best_ip}，速度: {best_speed} MB/s")
                
                # 更新所有启用的Tracker
                for tracker in self.config.get("trackers", []):
                    if tracker.get("enable", False):
                        domain = tracker.get("domain")
                        if domain:
                            logger.info(f"为 {domain} 设置新的IP: {best_ip}")
                            self.hosts_manager.add_cloudflare_ip(domain, best_ip)
            else:
                logger.warning("未找到合适的IP")
                
        except Exception as e:
            logger.error(f"处理结果出错: {str(e)}")
    
    def get_last_result(self) -> Dict[str, Any]:
        """获取最后一次测试结果"""
        try:
            if not os.path.exists(self.result_file):
                return {"success": False, "message": "尚未执行测试或结果文件不存在"}
            
            # 获取文件修改时间
            modified_time = os.path.getmtime(self.result_file)
            modified_time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(modified_time))
            
            # 读取结果文件
            with open(self.result_file, 'r') as f:
                lines = f.readlines()
            
            if len(lines) <= 1:
                return {"success": False, "message": "结果文件中没有有效数据", "time": modified_time_str}
            
            # 解析结果
            headers = lines[0].strip().split(',')
            results = []
            
            for i in range(1, min(11, len(lines))):  # 最多返回前10条
                data = lines[i].strip().split(',')
                if len(data) >= len(headers):
                    result = {}
                    for j, header in enumerate(headers):
                        result[header] = data[j]
                    results.append(result)
            
            return {
                "success": True,
                "time": modified_time_str,
                "results": results
            }
        except Exception as e:
            logger.error(f"获取测试结果出错: {str(e)}")
            return {"success": False, "message": f"获取测试结果出错: {str(e)}"}
    
    def is_running(self) -> bool:
        """检查是否正在运行测试"""
        return self.running 
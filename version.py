"""
PT-Accelerator 版本信息
"""

__version__ = "2.0.0"
__version_info__ = (2, 0, 0)
__author__ = "PT-Accelerator Team"
__description__ = "一个面向PT站点用户的全自动加速与管理平台"

# 版本历史
VERSION_HISTORY = {
    "2.0.0": "2024-01-15 - 架构自适应支持、多通知渠道、移动端适配、Hosts结构保护",
    "1.0.0": "2024-01-01 - 初始版本发布"
}

def get_version():
    """获取当前版本号"""
    return __version__

def get_version_info():
    """获取版本信息元组"""
    return __version_info__

def get_version_history():
    """获取版本历史"""
    return VERSION_HISTORY

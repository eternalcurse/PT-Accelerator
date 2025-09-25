from fastapi import Request, HTTPException, status
from passlib.context import CryptContext
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadTimeSignature
import os
import yaml
import logging
from typing import Optional
from app.models import User

# 配置日志
logger = logging.getLogger(__name__)

# 密码处理上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Session 签名器
session_serializer = None

# 配置路径
CONFIG_PATH = "config/config.yaml"

def init_session_serializer(secret_key: str):
    """初始化session签名器"""
    global session_serializer
    session_serializer = URLSafeTimedSerializer(secret_key)

def verify_password(plain_password, hashed_password):
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    """生成密码哈希"""
    return pwd_context.hash(password)

async def get_current_user(request: Request) -> Optional[User]:
    """获取当前登录用户"""
    # 加载当前配置以检查认证是否启用
    config = load_current_config()
    
    # 如果未启用认证，返回游客用户
    if not config.get("auth", {}).get("enable", False):
        return User(username="guest", is_authenticated=False)
    
    # 检查session中的用户信息
    user_data = request.session.get("user")
    if not user_data:
        return None
    
    try:
        # 验证session token  
        if session_serializer and user_data.get("token"):
            username = session_serializer.loads(user_data.get("token", ""), max_age=3600*24*7)  # 7天有效期
            if username == user_data.get("username"):
                return User(username=username, is_authenticated=True)
        elif user_data.get("username"):
            # 向后兼容没有token的旧session格式
            return User(username=user_data.get("username"), is_authenticated=True)
    except (SignatureExpired, BadTimeSignature):
        # Token过期或无效，清除session
        request.session.pop("user", None)
        return None
    
    return None

def load_current_config():
    """加载当前配置文件"""
    if os.path.exists(CONFIG_PATH):
        try:
            # 优先UTF-8，失败回退GBK/GB18030
            try:
                with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f) or {}
            except UnicodeDecodeError:
                try:
                    with open(CONFIG_PATH, 'r', encoding='gbk') as f:
                        config = yaml.safe_load(f) or {}
                except UnicodeDecodeError:
                    with open(CONFIG_PATH, 'r', encoding='gb18030') as f:
                        config = yaml.safe_load(f) or {}
                # 确保配置中有auth部分
                if "auth" not in config:
                    config["auth"] = {}
                return config
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            return {"auth": {}}
    return {"auth": {}}

def create_user_session(username: str) -> dict:
    """创建用户session数据"""
    if session_serializer:
        token = session_serializer.dumps(username)
        return {
            "username": username,
            "token": token
        }
    return {"username": username}

def reload_global_config():
    """重新加载全局配置，确保认证配置更改能立即生效"""
    try:
        # 动态导入以避免循环导入
        import importlib
        import app.main
        
        # 重新加载当前配置
        new_config = load_current_config()
        
        # 更新全局配置
        app.main.config.clear()
        app.main.config.update(new_config)
        
        # 如果secret_key发生变化，重新初始化session序列化器
        if new_config.get("auth", {}).get("secret_key"):
            init_session_serializer(new_config["auth"]["secret_key"])
            
        logger.info("全局配置已重新加载，认证配置变更立即生效")
        return True
    except Exception as e:
        logger.error(f"重新加载全局配置失败: {e}")
        return False 
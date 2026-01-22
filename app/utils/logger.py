import os
import sys
import logging
from app.config import CURRENT_VERSION

def get_logger(name):
    """获取指定名称的 Logger 实例"""
    return logging.getLogger(name)

def setup_logging():
    """初始化全局日志配置"""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)

    log_path = os.path.join(log_dir, "emuman.log")
    old_log_path = os.path.join(log_dir, "emuman_old.log")

    try:
        if os.path.exists(log_path):
            if os.path.exists(old_log_path):
                os.remove(old_log_path)
            os.rename(log_path, old_log_path)
    except Exception as e:
        print(f"Failed to rotate log files: {e}")

    # 统一日志格式：时间 - 模块名 - 级别 - 消息
    log_format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        handlers=[
            logging.FileHandler(log_path, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    
    logger = get_logger("APP")
    logger.info(f"=== EmuMan Started | Version: {CURRENT_VERSION} | OS: {sys.platform} ===")

def handle_exception(exc_type, exc_value, exc_traceback):
    """捕获全局未处理的异常"""
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return
    
    logger = get_logger("EXCEPTION")
    logger.critical("Uncaught Exception detected:", exc_info=(exc_type, exc_value, exc_traceback))

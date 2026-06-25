import logging
import os
import datetime
from core.config import Config

def get_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG) # 接收所有级别
    
    if not logger.handlers:
        # 确保日志目录存在
        log_dir = "logs"
        os.makedirs(log_dir, exist_ok=True)
            
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        
        # 1. INFO Handler: 记录 INFO 及以上级别
        info_handler = logging.FileHandler(os.path.join(log_dir, f"info_{datetime.date.today()}.log"), encoding='utf-8')
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(formatter)
        logger.addHandler(info_handler)
        
        # 2. DEBUG Handler: 记录 DEBUG 及以上级别
        debug_handler = logging.FileHandler(os.path.join(log_dir, f"debug_{datetime.date.today()}.log"), encoding='utf-8')
        debug_handler.setLevel(logging.DEBUG)
        debug_handler.setFormatter(formatter)
        logger.addHandler(debug_handler)
    return logger

pipeline_logger = get_logger("MemoryPipeline")

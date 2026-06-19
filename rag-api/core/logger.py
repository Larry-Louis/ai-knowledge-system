import logging
import os
import datetime
from core.config import Config

# 测试模式开关，可以通过环境变量开启
TEST_MODE = os.getenv("TEST_MODE", "true").lower() == "true"

def get_logger(name: str):
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG if TEST_MODE else logging.INFO)
        
        # 确保日志目录存在
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        file_handler = logging.FileHandler(os.path.join(log_dir, f"memory_pipeline_{datetime.date.today()}.log"), encoding='utf-8')
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # 同时输出到控制台
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
    return logger

pipeline_logger = get_logger("MemoryPipeline")

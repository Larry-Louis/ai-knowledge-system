import logging
import logging.handlers
import os
import datetime

def get_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if not logger.handlers:
        # 基于 logger.py 文件位置确定日志目录，确保无论工作目录在哪都写对位置
        base_dir = os.path.dirname(os.path.abspath(__file__))  # rag-api/core/
        log_dir = os.path.normpath(os.path.join(base_dir, "..", "logs"))
        os.makedirs(log_dir, exist_ok=True)

        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

        today = datetime.date.today().isoformat()

        # 1. INFO 及以上 → 文件
        info_path = os.path.join(log_dir, f"info_{today}.log")
        fh_info = logging.handlers.WatchedFileHandler(info_path, encoding='utf-8')
        fh_info.setLevel(logging.INFO)
        fh_info.setFormatter(formatter)
        logger.addHandler(fh_info)

        # 2. DEBUG 及以上 → 文件
        debug_path = os.path.join(log_dir, f"debug_{today}.log")
        fh_debug = logging.handlers.WatchedFileHandler(debug_path, encoding='utf-8')
        fh_debug.setLevel(logging.DEBUG)
        fh_debug.setFormatter(formatter)
        logger.addHandler(fh_debug)

        # 3. 控制台输出（Docker 下通过 docker logs 可见）
        ch = logging.StreamHandler()
        ch.setLevel(logging.DEBUG)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger

pipeline_logger = get_logger("MemoryPipeline")

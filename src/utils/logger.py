import logging
import sys
from typing import Optional


def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """获取一个配置好的logger实例。

    Args:
        name: logger名称，通常使用__name__
        level: 日志级别，默认为INFO

    Returns:
        配置好的logger实例
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = logging.Formatter(
        fmt='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger

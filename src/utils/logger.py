import logging
import sys
import json
from typing import Optional, List, Dict, Any

# ANSI 颜色代码
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


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


def log_section(logger: logging.Logger, title: str, level: int = logging.INFO) -> None:
    """打印醒目的分节标题。

    Args:
        logger: logger 实例
        title: 标题内容
        level: 日志级别
    """
    border = "=" * 80
    colored_title = f"{Colors.BOLD}{Colors.HEADER}{title}{Colors.ENDC}"
    logger.log(level, f"\n{border}")
    logger.log(level, f"{colored_title}")
    logger.log(level, f"{border}\n")


def log_success(logger: logging.Logger, message: str) -> None:
    """打印成功消息（绿色）。

    Args:
        logger: logger 实例
        message: 消息内容
    """
    colored_msg = f"{Colors.BOLD}{Colors.OKGREEN}✓ {message}{Colors.ENDC}"
    logger.info(colored_msg)


def log_error(logger: logging.Logger, message: str) -> None:
    """打印错误消息（红色）。

    Args:
        logger: logger 实例
        message: 消息内容
    """
    colored_msg = f"{Colors.BOLD}{Colors.FAIL}✗ {message}{Colors.ENDC}"
    logger.error(colored_msg)


def log_warning(logger: logging.Logger, message: str) -> None:
    """打印警告消息（黄色）。

    Args:
        logger: logger 实例
        message: 消息内容
    """
    colored_msg = f"{Colors.BOLD}{Colors.WARNING}⚠ {message}{Colors.ENDC}"
    logger.warning(colored_msg)


def log_info(logger: logging.Logger, message: str) -> None:
    """打印信息消息（蓝色）。

    Args:
        logger: logger 实例
        message: 消息内容
    """
    colored_msg = f"{Colors.BOLD}{Colors.OKBLUE}ℹ {message}{Colors.ENDC}"
    logger.info(colored_msg)


def log_step(logger: logging.Logger, step_num: int, total: int, message: str) -> None:
    """打印步骤信息（青色）。

    Args:
        logger: logger 实例
        step_num: 当前步骤号
        total: 总步骤数
        message: 消息内容
    """
    colored_msg = f"{Colors.BOLD}{Colors.OKCYAN}[{step_num}/{total}] {message}{Colors.ENDC}"
    logger.info(colored_msg)


def log_tool_call(logger: logging.Logger, tool_name: str, args: Dict[str, Any]) -> None:
    """打印工具调用信息（醒目）。

    Args:
        logger: logger 实例
        tool_name: 工具名称
        args: 参数字典
    """
    colored_name = f"{Colors.BOLD}{Colors.OKCYAN}🔧 Tool: {tool_name}{Colors.ENDC}"
    logger.info(colored_name)
    if args:
        logger.info(f"   Args: {json.dumps(args, ensure_ascii=False)}")


def log_tool_result(logger: logging.Logger, tool_name: str, returncode: int, stdout: str = "", stderr: str = "") -> None:
    """打印工具执行结果（醒目）。

    Args:
        logger: logger 实例
        tool_name: 工具名称
        returncode: 返回码
        stdout: 标准输出
        stderr: 标准错误
    """
    if returncode == 0:
        colored_msg = f"{Colors.BOLD}{Colors.OKGREEN}✓ Tool '{tool_name}' completed successfully (returncode: {returncode}){Colors.ENDC}"
        logger.info(colored_msg)
    else:
        colored_msg = f"{Colors.BOLD}{Colors.WARNING}⚠ Tool '{tool_name}' failed (returncode: {returncode}){Colors.ENDC}"
        logger.warning(colored_msg)
    
    if stdout:
        logger.info(f"{Colors.OKCYAN}   stdout:{Colors.ENDC}")
        for line in stdout.split('\n')[:10]:  # 只显示前10行
            logger.info(f"      {line}")
        if len(stdout.split('\n')) > 10:
            logger.info(f"      ... ({len(stdout.split('\n')) - 10} more lines)")
    
    if stderr:
        logger.warning(f"{Colors.OKCYAN}   stderr:{Colors.ENDC}")
        for line in stderr.split('\n')[:10]:  # 只显示前10行
            logger.warning(f"      {line}")
        if len(stderr.split('\n')) > 10:
            logger.warning(f"      ... ({len(stderr.split('\n')) - 10} more lines)")


import logging
import sys
import json
from typing import Optional, List, Dict, Any

# 跟踪每个logger已经打印过的消息数量
_printed_message_counts: Dict[str, int] = {}


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


def log_llm_request(logger: logging.Logger, messages: List[Dict[str, Any]], round: int = 1) -> None:
    """记录 LLM 请求信息。

    Args:
        logger: logger 实例
        messages: 消息列表
        round: 当前轮次
    """
    logger.info("=" * 80)
    logger.info(f"LLM Request (Round {round}):")
    logger.info("-" * 80)
    
    logger_name = logger.name
    printed_count = _printed_message_counts.get(logger_name, 0)
    
    # 第一次调用时，打印 system prompt
    if printed_count == 0 and messages:
        system_msg = messages[0]
        if system_msg.get("role") == "system":
            content = system_msg.get("content", "")
            logger.info(f"[System Prompt]")
            if isinstance(content, str) and content:
                logger.info(f"\nContent: {content}")
            elif content:
                logger.info(f"\nContent: {str(content)}")
            logger.info("")
            printed_count = 1
    
    # 只打印新增的 messages
    new_messages = messages[printed_count:]
    if new_messages:
        logger.info(f"New messages: {len(new_messages)}")
        for i, msg in enumerate(new_messages):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            logger.info(f"[Message {i + 1}] Role: {role}")
            
            if role == "tool":
                tool_call_id = msg.get("tool_call_id", "")
                logger.info(f"\nTool Call ID: {tool_call_id}")

            if isinstance(content, str) and content:
                logger.info(f"\nContent: {content}")
            elif content:
                logger.info(f"\nContent: {str(content)}")
            
            logger.info("")
    
    # 更新已打印的消息数量
    _printed_message_counts[logger_name] = len(messages)
    
    logger.info("-" * 80)


def log_llm_response(logger: logging.Logger, response: Dict[str, Any], round: int = 1) -> None:
    """记录 LLM 响应信息。

    Args:
        logger: logger 实例
        response: 响应字典
        round: 当前轮次
    """
    logger.info("=" * 80)
    logger.info(f"LLM Response (Round {round}):")
    logger.info("-" * 80)
    
    content = response.get("content", "")
    if content:
        logger.info(f"\nContent: {content}{'...' if len(content) > 1000 else ''}")
    
    tool_calls = response.get("tool_calls")
    if tool_calls and isinstance(tool_calls, list):
        logger.info(f"Tool Calls: {len(tool_calls)}")
        for i, call in enumerate(tool_calls):
            if isinstance(call, dict):
                fn = call.get("function", {})
                name = fn.get("name", "unknown")
                args = fn.get("arguments", "{}")
                logger.info(f"  [{i+1}] {name}")
                try:
                    parsed_args = json.loads(args) if isinstance(args, str) else args
                    logger.info(f"\nArgs: {json.dumps(parsed_args, ensure_ascii=False)}")
                except:
                    logger.info(f"\nArgs: {str(args)}")
    
    logger.info("-" * 80)

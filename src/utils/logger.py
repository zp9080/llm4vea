import logging
import sys
import json
from typing import Optional, List, Dict, Any


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


def log_llm_request(logger: logging.Logger, messages: List[Dict[str, Any]], tools: Optional[List[Dict[str, Any]]] = None) -> None:
    """记录 LLM 请求信息。

    Args:
        logger: logger 实例
        messages: 消息列表
        tools: 工具列表（可选）
    """
    logger.info("=" * 80)
    logger.info("LLM Request:")
    logger.info("-" * 80)
    
    for i, msg in enumerate(messages):
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        logger.info(f"[Message {i+1}] Role: {role}")
        
        if role == "tool":
            tool_call_id = msg.get("tool_call_id", "")
            logger.info(f"  Tool Call ID: {tool_call_id}")
        
        if isinstance(content, str) and content:
            logger.info(f"  Content: {content[:500]}{'...' if len(content) > 500 else ''}")
        elif content:
            logger.info(f"  Content: {str(content)[:500]}{'...' if len(str(content)) > 500 else ''}")
        
        logger.info("")
    
    if tools:
        logger.info(f"Available tools: {len(tools)}")
        for tool in tools:
            tool_name = tool.get("name", "unknown")
            logger.info(f"  - {tool_name}")
    
    logger.info("-" * 80)


def log_llm_response(logger: logging.Logger, response: Dict[str, Any]) -> None:
    """记录 LLM 响应信息。

    Args:
        logger: logger 实例
        response: 响应字典
    """
    logger.info("=" * 80)
    logger.info("LLM Response:")
    logger.info("-" * 80)
    
    content = response.get("content", "")
    if content:
        logger.info(f"Content: {content[:1000]}{'...' if len(content) > 1000 else ''}")
    
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
                    logger.info(f"      Args: {json.dumps(parsed_args, ensure_ascii=False)[:500]}")
                except:
                    logger.info(f"      Args: {str(args)[:500]}")
    
    logger.info("-" * 80)

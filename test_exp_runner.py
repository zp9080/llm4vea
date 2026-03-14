#!/usr/bin/env python3

import sys
sys.path.insert(0, '/home/zp9080/llm4vea')

from src.tools.tool_registry import exp_runner
from pathlib import Path

exp_path = Path("/home/zp9080/llm4vea/runs/26-03-14-16-56-17/exp.py")

print(f"运行 exp.py...")
print(f"脚本路径: {exp_path}")
print(f"超时设置: 15s")
print("="*60)

result = exp_runner(script_path=exp_path, timeout=30.0)

print(f"\n返回码: {result.returncode}")
print(f"stdout 长度: {len(result.stdout)} 字符")
print(f"stderr 长度: {len(result.stderr)} 字符")
print(f"metadata: {result.metadata}")

print("\n" + "="*60)
print("过滤后的 stdout:")
print("="*60)
print(result.stdout)

if result.stderr:
    print("\n" + "="*60)
    print("stderr:")
    print("="*60)
    print(result.stderr)

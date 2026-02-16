---
name: "pwn-edge-skill"
description: "Edge-case Pwn skill for rare but critical failures. Used when standard exploitation still fails or crashes mysteriously, to apply specialized fixes."
---

# 使用场景
- 常规 Pwn 分析流程已经走完，但程序仍然出现异常崩溃或行为与预期不符时。
- 遇到难以通过常见利用模板解释的“诡异问题”，怀疑是栈对齐要求或其他实现细节导致时。

# 内容说明
- `stack-alignment.md`: 解释 x86-64 System ABI 下函数调用前 16 字节栈对齐的要求，说明 ROP 链如何打破对齐，并给出通过额外插入 `ret` gadget 修复对齐、避免在 `movaps` 等 SSE 指令处崩溃的标准做法。

# 索引
- [stack-alignment.md](./stack-alignment.md)

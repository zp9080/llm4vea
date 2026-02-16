---
name: stack_overflow
description: "提供针对栈溢出漏洞的核心利用技术与 EXP 模板。涵盖在 NX 保护下的返回导向编程（ROP）基础，包括 ret2libc 和 ret2csu 两种主流攻击路径；同时提供栈迁移（Stack Pivoting）技术，用于解决利用空间不足的问题。此技能包旨在帮助使用者在发现栈溢出后，根据环境约束选择并实施最有效的控制流劫持方案。"
---

# 使用场景
- 发现栈溢出漏洞，能够覆盖返回地址，但由于 NX 保护开启，需要构造 ROP 链来执行代码。
- 需要通过 `ret2libc` 方式，分两阶段攻击：先利用输出函数泄露 libc 基址，再调用 `system('/bin/sh')` 获取 Shell。
- 在 64 位程序中，找不到 `pop rdi; ret` 等方便的传参 gadget，需要利用 `__libc_csu_init` 中的通用 gadget (`ret2csu`) 来控制函数调用的前三个参数。
- 溢出点可写的栈空间非常有限，无法容纳完整的 ROP 链，需要将栈指针 (`rsp`) 迁移到 BSS 段或堆上等更大空间再进行攻击。
- 调试 ROP 链时，需要参考标准 EXP 骨架来组织 payload，或排查因栈对齐、地址计算错误导致的问题。
- 希望系统性地学习和掌握从简单 `ret2libc` 到 `ret2csu` 再到栈迁移的进阶栈溢出利用技巧。


# 索引

## knowledge
- [ROP基础知识](./knowledge/rop-basics.md)
- [栈迁移基础知识](./knowledge/stack-migration.md)

## templates

- [ret2csu漏洞利用EXP模板](./templates/ret2csu-exp.md)
- [ret2libc漏洞利用EXP模板](./templates/ret2libc-exp.md)
- [栈迁移漏洞利用EXP模板](./templates/stack-migration-exp.md)

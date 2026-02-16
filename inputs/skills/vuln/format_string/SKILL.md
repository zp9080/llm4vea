---
name: format-string
description: 提供针对格式化字符串漏洞的利用技术与EXP模板。涵盖格式化字符串漏洞的成因、利用 `%p/%s` 进行信息泄露（如泄露 Canary、代码基址、libc 地址）和任意地址读的方法，以及利用 `%n` 进行任意地址写（特别是 GOT 覆写）的核心原理与实战。此技能包旨在帮助使用者在发现格式化字符串漏洞后，能够系统性地进行漏洞验证、信息泄露和控制流劫持。
---

# 使用场景
- 发现程序将用户输入直接作为 `printf` 等函数的格式化字符串，需要验证漏洞并确定利用路径时。
- 需要利用格式化字符串漏洞进行信息泄露，以绕过 Canary、PIE、ASLR 等安全保护。
- 计划通过 `%s` 说明符读取内存中任意地址（如 GOT 表项）的内容。
- 在 Partial RELRO 环境下，希望通过 `%n` 说明符覆盖 GOT 表项，将函数指针劫持到 `system` 或其他地址。
- 需要 `pwntools` 的 `fmtstr_payload` 自动生成复杂的任意地址写 payload，以避免手动计算。
- 调试格式化字符串 EXP 时，需要参考标准的两阶段（泄露 -> 写入）攻击模板。


# 索引
## knowledge
- [格式化字符串基础知识](./knowledge/format-string-basics.md)

## templates
- [格式化字符串漏洞利用EXP模板](./templates/fmtstr-leak-write-exp.md)

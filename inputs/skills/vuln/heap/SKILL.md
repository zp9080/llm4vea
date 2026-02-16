---
name: heap
description: "提供针对 glibc 堆漏洞的核心利用技术与 EXP 模板。涵盖 ptmalloc2 堆管理基础、tcache 投毒（Tcache Poisoning）、`__free_hook` 劫持等主流攻击方法，并深入到基于文件流的利用（FSOP），详解 `house of apple2` 等高级技巧。此技能包旨在帮助使用者在面对堆溢出、UAF 等漏洞时，能根据 glibc 版本和保护机制，选择并实施从获取任意写到实现 RCE 的完整攻击链。"
---

# 使用场景
- 分析堆相关的 Pwn 题，需要理解 `chunk` 结构、`tcache`/`bins` 的工作原理以及 `malloc`/`free` 的内部行为时。
- 发现 UAF 或堆溢出漏洞，计划使用 `tcache poisoning` 来获得任意地址写原语时。
- 在 glibc 2.33 及以下版本中，已获得任意地址写能力，希望通过覆盖 `__free_hook` 为 `system` 来稳定获取 Shell 时。
- 面对高版本 glibc（`__free_hook` 被移除），需要采用 FSOP（文件流导向编程）作为 RCE 终点，特别是实施 `house of apple2` 攻击时。
- 调试堆利用 EXP 时，需要参考标准模板（如 tcache 投毒）来组织 payload，或排查因 `safe-linking`、结构体偏移错误导致的问题。
- 希望系统性地学习 glibc 堆从入门（tcache）到进阶（FSOP）的漏洞利用技术。

# 索引
## knowledge

- [free-hook攻击参考知识](./knowledge/free-hook-usage.md)
- [heap基础知识](./knowledge/heap-basics.md)
- [house-of-apple2攻击参考知识](./knowledge/house-of-apple2.md)
- [堆攻击IO_FILE参考知识](./knowledge/io-file-basics.md)
- [tcache-poison攻击参考知识](./knowledge/tcache-poisoning.md)

## templates

- [house-of-apple2漏洞利用EXP模板](./templates/house-of-apple2-exp.md)
- [tcache-poisoni漏洞利用EXP模板](./templates/tcache-poisoning-exp.md)

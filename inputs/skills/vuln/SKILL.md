---
name: "pwn-vuln-skill"
description: "Pwn vulnerability-skill collection. Used after identifying the vulnerability type to enter the corresponding exploitation flow and templates."
---

# 适用场景
- 已定位到具体漏洞类型，需要直接进入该漏洞的利用方法与模板时。
- 需要在格式化字符串/栈溢出/堆漏洞之间快速切换知识路径时。
- 希望按漏洞类别组织知识与模板，建立可复用的解题流程时。

# 内容说明
- 本目录聚合各类漏洞的专项技能包，每个子目录对应一种漏洞类型，包含原理、利用技巧与 EXP 模板。
- 使用时先确定漏洞类型，再进入对应子技能包进行深挖与实现。

# 索引
- [format_string类型漏洞](./format_string/SKILL.md)
- [stack_overflow类型漏洞](./stack_overflow/SKILL.md)
- [heap类型漏洞](./heap/SKILL.md)

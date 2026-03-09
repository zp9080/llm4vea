---
name: "pwn-core-skill"
description: "Core pwn skill covering binary protections, ROP gadgets, and pwn basic tool use. Used at the start of any binary exploitation task to define the attack path and debugging flow."
---

# 使用场景
- 需要用 `checksec` 分析二进制保护机制并规划宏观利用路径
- 需要依赖 ROP gadgets 进行代码重用攻击
- 使用用 `pwntools` 生成 EXP 脚本d
- 动态调试栈溢出、堆漏洞或格式化字符串漏洞，需借助 `pwndbg` 可视化内存、栈、堆和 bins 状态

# 内容说明
- `checksec.md`: 解释 Canary、NX、PIE、RELRO 等常见保护机制的含义，并给出在不同保护组合下选择 shellcode、ret2libc、ROP、GOT 覆写等利用思路的决策路径。
- `pwntools.md`: 总结 pwntools 在进程/网络交互、ELF 静态分析、格式化字符串自动构造 (`fmtstr_payload`)、偏移计算 (`cyclic`) 与 GDB 集成调试 (`gdb.attach`) 中的高频 API 与推荐写法。
- `pwndbg.md`: 说明在 GDB 中使用 pwndbg 进行内存映射 (`vmmap`)、内存探查 (`telescope`)、堆与各类 bins 状态观察 (`heap`, `tcache`, `bins`)，以及配合 pwntools 脚本进行半自动化调试的典型流程。

# 索引
- [checksec.md](./checksec.md)
- [pwntools.md](./pwntools.md)
- [pwndbg.md](./pwndbg.md)


# 适用场景与前置条件

`__free_hook` 是 glibc 提供的一个弱符号函数指针，它为堆漏洞利用提供了一个经典、可靠的 RCE (Remote Code Execution) 终点。当攻击者通过堆漏洞（如 tcache poisoning、fastbin attack 等）获得任意地址写能力后，可以将 `__free_hook` 的值覆盖为恶意函数（如 `system`）的地址。之后，任何可控的 `free(ptr)` 调用都会被劫持，从而执行任意代码。

本知识适用于以下场景：
- 目标环境为 **glibc 2.33 及以下**，`nm` 或 GDB 调试显示 `__free_hook` 符号存在。
- 已经通过堆漏洞获得**任意地址写**或**任意地址分配**的原语。
- 程序逻辑中存在可以触发的 `free(ptr)` 调用，并且 `ptr` 的内容是可控的，适合用来构造 `free("/bin/sh")`。
- 需要在不同 glibc 版本间选择最合适的利用终点，评估 `__free_hook` 是否可用。

# 原理要点与利用路径

- **核心机制**:
  - `__free_hook` 是一个函数指针，默认值为 NULL。
  - 当其值非 NULL 时，`free(ptr)` 的行为会从标准释放流程变为 `__free_hook(ptr, caller_address)` 的调用。
  - 攻击者利用这一点，将 `__free_hook` 指向 `system`，然后调用 `free` 并使其第一个参数 `ptr` 指向字符串 `"/bin/sh"`。

- **标准利用路径**:
  1.  **信息泄露**: 通过 unsorted bin attack 或其他漏洞泄露 libc 的基地址。
  2.  **计算地址**: 根据基址计算 `__free_hook` 和 `system` 的绝对地址。
      - `free_hook_addr = libc.address + libc.symbols['__free_hook']`
      - `system_addr = libc.address + libc.symbols['system']`
  3.  **获取任意写**: 使用 `tcache poisoning` 等技术获得向任意地址写入的能力。
  4.  **覆盖 Hook**: 将 `__free_hook` 的地址覆盖为 `system` 的地址。
  5.  **触发 Hook**:
      - 申请一个 chunk，并向其中写入 `"/bin/sh\x00"`。
      - 调用 `free()` 释放这个 chunk。
      - 这将触发 `__free_hook("/bin/sh"...)`，即 `system("/bin/sh")`，成功获取 Shell。

- **Glibc 版本演进与影响**:
  - **< 2.34**: `__free_hook` 普遍存在且可用，是堆利用的首选 RCE 终点。
    - **2.26 - 2.31**: Tcache 机制的引入使得获取任意写变得异常简单，`tcache poisoning -> __free_hook` 是此阶段的黄金组合。
    - **2.32 - 2.33**: Safe-Linking 的引入增加了 tcache 投毒的难度，需要先泄露堆地址绕过检查，但 `__free_hook` 本身依然是可用的目标。
  - **>= 2.34**: `__free_hook` **被移除**。从此版本开始，这条经典的利用路径被彻底堵死。攻击者必须转向 **FSOP (File Stream Oriented Programming)**、`__exit_funcs` 链、`setcontext` ROP 等更复杂的替代方案。

# 调试线索与判定方法

- **GDB/pwndbg 调试**:
  - **`watch __free_hook`**: 对 `__free_hook` 设置硬件观察点，是验证其何时被覆盖、被谁覆盖的最直接方法。
  - **`p __free_hook`**: 在 EXP 的关键步骤后，打印 `__free_hook` 的当前值，确认其是否已成功变为 `system` 的地址。
  - **`b free`**: 在最后触发 hook 的 `free` 调用处下断点。
    - 检查 `rdi` (在 x64 下) 是否指向包含 `"/bin/sh"` 字符串的地址。
    - 单步进入 (`si`)，观察 `rip` 是否跳转到 `system` 函数。

- **判定成功**:
  - GDB 显示 `__free_hook` 的值已从 `0x0` 变为 `system` 的地址。
  - 最后一次 `free` 调用成功打开了一个 shell，`interactive()` 模式下可以执行 `ls`, `whoami` 等命令。

# 常见陷阱与收敛建议

- **版本不匹配**: 在 glibc >= 2.34 的环境上尝试利用 `__free_hook` 是最常见的错误。务必先确认 libc 版本。
- **忘记 `/bin/sh`**: 覆盖了 `__free_hook` 为 `system`，但 `free` 的指针指向的内容不是一个有效的命令，导致 `system` 执行失败。
- **One-Gadget 的约束**: 有时为了缩短 payload，会将 `__free_hook` 直接覆盖为 one-gadget 的地址。这通常是不可行的，因为 `free` 调用时寄存器的状态（如 `rdi` 指向堆块）很难满足 one-gadget 对寄存器的苛刻约束条件。`system` 几乎总是更可靠的选择。
- **替代方案的抉择**:
  - 当 `__free_hook` 不可用时，应立即考虑 **FSOP**。这是高版本 glibc 下最主流的 RCE 手段，通过伪造 `_IO_FILE` 结构并劫持 `_IO_list_all` 来实现。
  - 其他可考虑的方案包括：
    - **`__malloc_hook`**: 在 glibc < 2.34 中可用，但通常不如 `__free_hook` 方便触发。
    - **`__exit_funcs`**: 进程退出时调用的函数链表，如果能任意写，可以伪造一个来劫持控制流。
    - **`setcontext` Gadget**: 利用 ROP 链跳转到一个可以控制所有寄存器的通用 gadget，然后构造 `execve` 系统调用。
    - **栈变量覆盖**: 如果能通过任意写泄露栈地址，并覆盖栈上的返回地址，也是一条可行的路径，但这需要额外的栈泄露原语。

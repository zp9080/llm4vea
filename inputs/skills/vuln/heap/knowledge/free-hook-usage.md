# 适用场景与前置条件
`__free_hook` 是 glibc 提供的一个弱符号函数指针，它为堆漏洞利用提供了一个经典、可靠的 RCE (Remote Code Execution) 终点。当攻击者通过堆漏洞（如 tcache poison、fastbin attack 等）获得任意地址写能力后，可以将 `__free_hook` 的值覆盖为恶意函数（如 `system`）的地址。之后，任何可控的 `free(ptr)` 调用都会被劫持，从而执行任意代码。

本知识适用于以下场景：
- 目标环境为 **glibc 2.33 及以下**。
- 已经通过堆漏洞获得**任意地址写**或**任意地址分配**的原语。
- 程序逻辑中存在可以触发的 `free(ptr)` 调用，并且 `ptr` 的内容是可控的，适合用来构造 `free("/bin/sh")`。

# 原理要点与利用路径
- **核心机制**:
  - `__free_hook` 是一个函数指针，默认值为 NULL。
  - 当其值非 NULL 时，`free(ptr)` 的行为会从标准释放流程变为 `__free_hook(ptr, caller_address)` 的调用。
  - 攻击者利用这一点，将 `__free_hook` 指向 `system`，然后调用 `free` 并使其第一个参数 `ptr` 指向字符串 `"/bin/sh"`。

- **标准利用路径**:
  1.  **信息泄露**: 通过 unsorted bin attack 或其他漏洞泄露 libc 的基地址。
      - 执行 unsorted bin attack 后，目标堆块会被写入 unsorted bin 的地址（main_arena 相关指针）。
      - 调用程序提供的 `show` 类功能，打印该堆块的内容，即可泄露存储在其中的 libc 相关地址。
      - 泄露的地址通常指向 `main_arena` 中的某个位置，位于 libc 基地址附近。
      - **【必须】使用 `\x7f` 方式接收泄露数据**：`leaked = u64(p.recvuntil(b'\x7f')[-6:].ljust(8, b'\x00'))`
        - libc 地址的高字节总是 `0x7f`，通过 `recvuntil(b'\x7f')` 可以精确定位泄露的 libc 地址。
        - 其他接收方式（如固定长度接收）容易受到输出格式变化的影响，导致地址解析错误。
      - **【必须】在调试阶段，通过 `dbg_exec('vmmap')` 命令查看当前运行的 libc 基地址**。
        - 这是计算泄露地址偏移的唯一可靠方法，直接硬编码偏移值会导致 exp 在不同 libc 版本下失败。
      - 由于 ASLR 只随机化基地址，相对偏移在每次运行中保持不变，因此可通过 `libc_base = leaked_addr - offset` 计算出任意运行时的 libc 基地址。
  2.  **计算地址**: 根据基址计算 `__free_hook` 和 `system` 的绝对地址。
      - `free_hook_addr = libc.address + libc.symbols['__free_hook']`
      - `system_addr = libc.address + libc.symbols['system']`
  3.  **获取任意写**: 使用 `tcache poison` 等技术获得向任意地址写入的能力。
      - **【必须】执行 tcache poison 后，立即调用 `dbg_exec('bins')` 查看 tcache 状态**。
        - 这是验证 tcache poison 是否成功的唯一方法，如果不执行此步骤，无法确认 `fd` 指针是否被正确修改。
      - 如果看到目标 chunk 的 fd 指针被成功修改为 `__free_hook` 的地址，说明 tcache poison 攻击成功。
  4.  **覆盖 Hook**: 将 `__free_hook` 的地址覆盖为 `system` 的地址。
  5.  **触发 Hook**:
      - 申请一个 chunk，并向其中写入 `"/bin/sh\x00"`。
      - 调用 `free()` 释放这个 chunk。
      - 这将触发 `__free_hook("/bin/sh"...)`，即 `system("/bin/sh")`，成功获取 Shell。

- **Glibc 版本演进与影响**:
  - **< 2.34**: `__free_hook` 普遍存在且可用，是堆利用的首选 RCE 终点。
    - **2.26 - 2.31**: Tcache 机制的引入使得获取任意写变得异常简单，`tcache poison -> __free_hook` 是此阶段的黄金组合。
    - **2.32 - 2.33**: Safe-Linking 的引入增加了 tcache 投毒的难度，需要先泄露堆地址绕过检查，但 `__free_hook` 本身依然是可用的目标。
  - **>= 2.34**: `__free_hook` **被移除**。从此版本开始，这条经典的利用路径被彻底堵死。攻击者必须转向 **FSOP (File Stream Oriented Programming)**、`__exit_funcs` 链、`setcontext` ROP 等更复杂的替代方案。

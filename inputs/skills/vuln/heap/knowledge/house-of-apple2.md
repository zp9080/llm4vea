
# 适用场景与前置条件

`house of apple2` 是一种基于 `_IO_FILE` 结构进行攻击的高级堆利用技术，属于 FSOP (File Stream Oriented Programming) 的一种。它通常在攻击者已经获得**稳定任意地址写**和 **libc 地址泄露**两大原语后，作为实现 RCE (Remote Code Execution) 的临门一脚。特别是在高版本 glibc 中，当 `__free_hook` 等传统利用路径被移除时，FSOP 成为主流选择。

本知识适用于以下场景：
- 已通过 tcache poisoning 等手段获得任意地址写能力。
- 已泄露 libc 基址，能够定位 `_IO_list_all`, `_IO_wfile_jumps` (或类似的 vtable) 和 `system` 等符号的地址。
- 程序执行流最终会正常退出（调用 `exit()` 或从 `main` 返回），从而触发 `_IO_flush_all_lockp` 函数。
- 调试 `house of apple2` payload 时遇到崩溃，需要根据 glibc 版本核对 `_IO_FILE`, `_IO_wide_data`, vtable 等结构体的偏移和检查条件。

# 原理要点与利用路径

- **核心原理**:
  - glibc 内部通过一个名为 `_IO_list_all` 的全局指针，维护一个连接了所有 `FILE` 结构（如 `stdin`, `stdout`, `stderr`）的链表。
  - 当程序退出时，会调用 `_IO_flush_all_lockp` 函数，该函数会遍历 `_IO_list_all` 链表，并对每个 `FILE` 结构执行 flush 操作。
  - 这个 flush 操作最终会通过一个虚函数表 (vtable) 调用 `_IO_overflow` 函数指针。
  - `house of apple2` 的思想就是：
    1.  在可控内存（如堆上）伪造一个 `_IO_FILE_plus` 结构体和一个虚假的 vtable。
    2.  利用任意地址写，将 `_IO_list_all` 的头指针指向我们伪造的 `FILE` 结构。
    3.  在伪造的 vtable 中，将 `_IO_overflow` 函数指针替换为 `system` 的地址。
    4.  在伪造的 `FILE` 结构的开头放置 `"/bin/sh"` 字符串。
    5.  等待程序退出，自动触发 `_IO_flush_all_lockp` -> `_IO_overflow(fake_file, ...)` -> `system("/bin/sh")`。

- **关键结构与偏移 (以 glibc 2.27 为例)**:
  - **`_IO_FILE_plus`**: 伪造的核心。
    - `flags`: `0xfbad0000` 左右，以绕过检查。
    - `_IO_write_ptr > _IO_write_base`: 满足 `_IO_OVERFLOW` 的触发条件。
    - `_lock`: 指向一个可写的地址，以通过 `_IO_flockfile` 的检查。
    - `_wide_data`: 指向一个伪造的 `_IO_wide_data` 结构。
    - `vtable`: 指向伪造的 vtable。
  - **`_IO_wide_data`**: 用于宽字符流，其内部包含指向 `_wide_vtable` 的指针。在 glibc 2.27 中，这个指针位于 `_IO_wide_data` 偏移 `+0x130` 处。
  - **vtable (`_IO_wfile_jumps`)**: glibc 提供的可供利用的 vtable 之一。我们将伪造一个类似的 vtable，并将 `_IO_wfile_overflow` 对应的函数指针改为 `system`。

- **版本差异**:
  - `_IO_FILE` 和 `_IO_wide_data` 的结构体布局在不同 glibc 版本中会发生变化。例如，glibc 2.35 中 `_wide_vtable` 的偏移是 `+0xe0`。构造 payload 时必须精确匹配目标版本。

# 调试线索与判定方法

- **GDB/pwndbg 调试**:
  - **`watch _IO_list_all`**: 观察 `_IO_list_all` 何时被成功篡改。
  - **`p/x *(struct _IO_FILE_plus *) <fake_file_addr>`**: 在 GDB 中以结构体格式打印伪造的 `FILE`，检查所有字段是否按预期填充。
  - **`b exit` / `b _IO_flush_all_lockp`**: 从 `exit` 函数或直接在 `_IO_flush_all_lockp` 处下断点，开始跟踪攻击链。
  - **单步跟踪 vtable 调用**: 在 `_IO_flush_all_lockp` 内部，仔细跟踪到 `call [rax+offset]` 这样的虚函数调用指令。检查 `rax` 是否是我们伪造的 vtable 地址，以及调用的函数是否是 `system`。
  - **检查参数 `rdi`**: 在 `call system` 时，检查 `rdi` 是否指向我们伪造的 `FILE` 结构（即指向 `"/bin/sh"` 字符串）。

# 常见陷阱与收敛建议

- **vtable/结构体偏移错误**: 这是 `house of apple2` 失败的最常见原因。必须使用与目标环境完全一致的 libc 版本来确定 `_IO_FILE`, `_IO_wide_data` 等结构体的字段偏移。
- **检查条件不满足**: `_IO_flush_all_lockp` 在调用 `_IO_OVERFLOW` 之前，会对 `_mode`, `_flags`, `_IO_write_ptr` 等字段进行检查。伪造的 `FILE` 必须精确地设置这些值以通过检查。
- **锁 (`_lock`) 问题**: `_lock` 字段必须指向一个可写的地址，否则在 `_IO_flockfile` 尝试对锁进行操作时会因写入只读内存而崩溃。通常可以将其指向伪造的 `FILE` 结构自身或其他可写区域。
- **参数问题**: `system` 函数的参数是 `rdi`。在 `house of apple2` 中，`_IO_overflow` 被调用时，第一个参数（`rdi`）恰好是 `FILE` 结构体自身的指针。因此，必须将 `"/bin/sh"` 字符串放置在伪造的 `FILE` 结构的开头。
- **触发时机**: 确保你的利用路径能够让程序正常退出。如果程序以 `_exit` 或其他非正常方式终止，`_IO_flush_all_lockp` 可能不会被调用。


# 适用场景与前置条件

本知识旨在梳理 glibc 中与文件流 (`FILE` stream) 相关的核心数据结构，如 `_IO_FILE`, `_IO_FILE_plus`, `_IO_jump_t` (vtable), `_IO_wide_data`，以及它们如何通过 `_IO_list_all` 链表进行管理。这些是理解所有高级 IO_FILE 利用（也称 FSOP, File Stream Oriented Programming）的基础，例如 `house of apple2`, `house of kiwi` 等。

本知识适用于以下场景：
- 计划实施 FSOP 攻击，需要伪造 `_IO_FILE` 结构并劫持 `_IO_list_all`，但对内部结构、字段偏移不熟悉。
- 分析 `house of` 系列堆利用时，需要根据目标 glibc 版本，确认 `_IO_FILE`、vtable 等关键字段的布局和 `_IO_flush_all_lockp` 等函数的检查条件。
- 在 GDB 中调试 FSOP 利用，需要跟踪 vtable 跳转、检查伪造的 `FILE` 结构是否正确，以及理解为何程序在 `exit()` 或 `fflush()` 时崩溃。
- 评估高版本 glibc（`__free_hook` 被移除后）的 RCE 路径，需要选择合适的 vtable（如 `_IO_wfile_jumps`）和触发点。

# 原理要点与利用路径

- **`_IO_FILE` 结构**:
  - 这是 C 语言中 `FILE` 类型的底层实现，包含了文件描述符、缓冲区指针 (`_IO_read_ptr`, `_IO_write_ptr` 等)、标志位 (`_flags`)、模式 (`_mode`) 等。
  - `_chain` 字段: 一个指向下一个 `_IO_FILE` 结构的指针，用于将所有打开的文件流链接成一个单向链表。
  - `_lock` 字段: 指向一个锁对象，用于多线程环境下的同步。在 FSOP 中，该指针必须指向一个可写地址。
  - `_vtable_offset` 和 `vtable`: `_IO_FILE_plus` 结构在 `_IO_FILE` 的基础上增加了一个 `vtable` 指针，指向一个包含各种 IO 操作函数指针的 `_IO_jump_t` 结构。攻击的核心就是劫持这个 `vtable` 指针或其内容。

- **`_IO_list_all` 全局链表**:
  - 是一个全局变量，指向 `_IO_FILE` 链表的头部。`stdin`, `stdout`, `stderr` 通常位于这个链表中。
  - FSOP 的第一步就是利用任意地址写，将 `_IO_list_all` 的值修改为我们伪造的 `_IO_FILE` 结构的地址，从而将我们的假 `FILE` 插入到链表头部。

- **`_IO_jump_t` (vtable)**:
  - 一个包含多个函数指针的结构体，如 `__overflow`, `__underflow`, `__xsputn`, `__sync` 等。
  - 当对一个 `FILE` 对象执行 `fflush`, `fwrite`, `fclose` 等操作时，实际上会调用其 vtable 中的相应函数。
  - 攻击者通过伪造一个 vtable，并将其中某个会被调用的函数指针（如 `__overflow` 或 `__sync`）替换为 `system` 的地址，来实现控制流劫持。

- **FSOP 触发机制 (`_IO_flush_all_lockp`)**:
  - 当程序正常退出（`exit()` 或从 `main` 返回）时，`_IO_flush_all_lockp` 函数会被调用。
  - 该函数会遍历 `_IO_list_all` 链表，并对每个 `FILE` 执行刷新操作。
  - 在特定条件下（如 `fp->_mode <= 0 && fp->_IO_write_ptr > fp->_IO_write_base`），刷新操作会触发 `_IO_OVERFLOW` 宏，最终调用 vtable 中的 `__overflow` 函数指针。
  - 这为攻击者提供了一个在程序退出时稳定触发 payload 的机会。

- **`__malloc_assert` 触发**:
  - 在某些堆利用场景（如 `house of kiwi`）中，攻击者通过破坏堆的完整性（如修改 top chunk 的 size）来故意触发 `malloc` 内部的 `assert` 失败。
  - `__malloc_assert` 会调用 `__fxprintf(NULL, ...)`，最终会操作 `stderr` 这个 `FILE` 对象。如果攻击者能提前伪造 `stderr` 的 `FILE` 结构及其 vtable，同样可以劫持控制流。

# 调试线索与判定方法

- **检查 `_IO_list_all`**:
  - `p &_IO_list_all`: 获取 `_IO_list_all` 的地址。
  - `x/gx <addr_of_IO_list_all>`: 查看其值，确认是否已被覆盖为伪造 `FILE` 的地址。
  - `p *(struct _IO_FILE_plus *)_IO_list_all`: 以结构体形式递归打印整个 `FILE` 链表。

- **检查伪造的 `FILE` 结构**:
  - `p/x *(struct _IO_FILE_plus *) <fake_file_addr>`: 详细检查伪造 `FILE` 的每个字段，特别是 `_flags`, `_mode`, `_IO_write_ptr`, `_IO_write_base`, `_lock`, `vtable` 等。

- **跟踪 vtable 调用**:
  - 在 `_IO_flush_all_lockp` 内部循环的 `_IO_OVERFLOW` 宏调用处或 `__malloc_assert` 的 `__fxprintf` 调用处下断点。
  - 单步执行 (`si`)，观察程序如何通过 `_IO_JUMPS_FUNC` 宏找到 vtable 地址，以及最终 `call` 的目标是否是 `system`。


# 常见陷阱与收敛建议

- **版本依赖性**: `_IO_FILE`、`_IO_wide_data` 等结构体的布局在不同 glibc 版本中差异很大。进行 FSOP 攻击时，**必须**使用与目标环境完全相同的 libc 版本来确定所有字段的偏移。这是 FSOP 成功与否最关键的一点。
- **检查条件繁多**: `_IO_flush_all_lockp` 等触发函数内部有大量检查，伪造的 `FILE` 必须满足所有条件才能走到最终的 vtable 调用。调试时需要耐心比对 glibc 源码，逐一满足这些条件。
- **vtable 验证**: 在较新版本的 glibc 中，`IO_validate_vtable` 函数会对 vtable 指针进行合法性检查，要求它必须指向 `__libc_IO_vtables` 段内。这使得直接将 vtable 伪造在堆或 BSS 段上的方法失效。攻击者需要找到绕过方法，例如将 `_IO_FILE` 中的 `_vtable_offset` 字段与一个合法的 vtable 地址进行巧妙组合，使其最终计算出的函数指针指向我们的目标。
- **`_lock` 字段**: `_lock` 必须指向一个可写地址，否则在加锁操作时会崩溃。最简单的方法是将其指向伪造的 `FILE` 结构本身或其他可控的可写内存区域。
- **Wide Data**: 某些利用路径会涉及到 `_wide_data` 结构和宽字符的 vtable (`_IO_wfile_jumps`)。伪造时需要同时构造 `_IO_FILE` 和 `_IO_wide_data` 两个结构。

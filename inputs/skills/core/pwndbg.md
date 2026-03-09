# 适用场景
`pwndbg` 是 GDB 的一个强大插件，旨在极大提升二进制漏洞利用的调试效率。当你在 Linux 环境下分析 ELF 文件的 Pwn 问题时，`pwndbg` 都是首选工具。无论是栈溢出、堆漏洞还是格式化字符串，它提供的上下文显示、内存分析和专用命令都能让你快速理解程序状态。

`pwndbg` 适用于以下场景：
- 需要快速理解程序崩溃时的上下文（寄存器、反汇编、栈回溯）。
- 动态调试 ROP 链、各类堆利用（tcache poisoning、UAF 等）时，需要可视化观察栈、堆、bins 的状态。
- 使用 `pwntools` 编写 EXP，并希望通过 `gdb.attach` 实现脚本与 GDB 的无缝联动调试。
- **AI 自动化调试**: 通过 `pwntools` 的 GDB Python API，让 AI 能够程序化地控制 GDB，执行调试命令、读取内存状态、验证漏洞利用逻辑，无需人工交互。

# 使用方法
- **内存与状态分析**
  - **内存映射**: `vmmap` 命令显示进程的内存布局，是定位程序基址、libc 基址、堆和栈地址的第一步。
  - **内存探查**: `telescope <addr/reg>` 可以智能地解引用并显示连续内存，对于检查 ROP 链、结构体和字符串极为方便。
  - **堆分析**: 
    - `heap` / `heap chunks`: 可视化整个堆的布局，显示所有 chunk 的大小和状态。
    - `tcache`: 实时查看 tcache bins 的状态，是调试 tcache 相关漏洞的核心。
    - `bins`: 查看 fastbins, unsorted bin, smallbins, largebins 的状态。
  - **ROP 调试**: `retaddr` 显示当前栈帧返回地址，`stack` 命令可详细展示栈内容。

- **断点与观察点**:
  - `b *<address>`: 在关键地址（如函数返回、gadget）下断点。
  - `x/10gx <address>`: 以 8 字节为单位连续查看 10 个内存单元，常用于检查返回地址、堆块指针等关键数据。

- **与 `pwntools` 联动**
  - 在 `pwntools` 脚本中使用 `gdb.attach(proc, gdbscript='...')` 是标准工作流程。
  - `gdbscript` 参数可以让你在 GDB 附加后自动执行一系列 `pwndbg` 命令，如设置断点、查看内存等，实现调试自动化。

- **AI 自动化调试（GDB Python API）**
  - 使用 `gdb.attach(proc, gdbscript='...', api=True)` 启用 GDB Python API 访问。
  - 返回的 `Gdb` 对象可以通过 RPyC 库远程调用 GDB 的 Python API，实现程序化控制。
  - 可以执行 GDB 命令、设置断点、读取寄存器和内存、控制程序执行流程。
  - 使用 `gdb.continue_and_wait()` 同步执行 continue，或 `gdb.continue_nowait()` 异步执行。

# 使用示例

## 示例 1: 传统人工调试方式
使用pwntools中的gdb.debug，然后定义dbg函数，在需要调试的地方调用dbg函数，即可在完成pwndbg的调试。

**注意**: 这种方式会启动一个新的 GDB UI 进程，只能通过人工交互进行调试，AI 无法使用此方式进行程序化调试。

```python
p = process("/path/to/binary")

def dbg():
    gdb.attach(p, 'b *0x401895')
    pause()

payload = b'b'.ljust(0x50, b'a')
dbg()

p.send(payload)
p.interactive()
```

## 示例 2: AI 自动化调试方式（推荐）
使用 `api=True` 启用 GDB Python API，AI 可以程序化地控制调试流程，无需人工交互。

```python
from pwn import *

context(os='linux', arch='amd64', log_level='debug')
p = process("/path/to/binary")

gdb_instance = None

def dbg_init(breakpoint_cmd):
    """
    初始化 GDB 并启用 Python API
    返回 Gdb 对象，可用于程序化控制
    """
    global gdb_instance
    gdb_instance = gdb.attach(p, gdbscript=breakpoint_cmd, api=True)
    return gdb_instance

def dbg_exec(cmd):
    """
    在 GDB 中执行命令并返回输出
    所有 GDB/pwndbg 命令都可以通过此函数执行
    """
    if gdb_instance is None:
        raise Exception("GDB not initialized. Call dbg_init() first.")
    return gdb_instance.execute(cmd, to_string=True)

def dbg_continue():
    """
    继续执行程序（同步方式）
    """
    if gdb_instance is None:
        raise Exception("GDB not initialized. Call dbg_init() first.")
    gdb_instance.continue_and_wait()

# ... 程序交互函数定义 ...

def add(idx, size, cont):
    p.sendlineafter(b"choice:", str(1))
    p.sendlineafter(b"idx:", str(idx))
    p.sendlineafter(b"size:", str(size))
    p.sendafter(b"content:", cont)

def delete(idx):
    p.sendlineafter(b"choice:", str(2))
    p.sendlineafter(b"idx:", str(idx))

# 执行一些程序操作
add(0, 0x100, b'aaaa')
add(1, 0x100, b'bbbb')
delete(0)

# 在关键位置初始化 GDB 并设置断点
# 
# 重要说明：
# 1. 前面的 add/delete 操作已经发送了数据到程序，程序正在等待下一次输入
# 2. 此时调用 dbg_init() 会附加 GDB 并设置断点
# 3. 断点地址 'b *0x401839' 是程序后续会执行到的关键位置（如某个函数入口、漏洞触发点等）
# 4. 当程序继续执行并运行到该地址时，会自动停在断点处
# 5. 此时 AI 可以执行各种调试命令查看程序状态
#
# 选择这个位置的原因：
# - 程序已经执行了一些操作（如堆分配、释放），状态已经改变
# - 程序还未执行到关键代码路径，可以在那里设置断点
# - 断点位置是后续必然会执行到的代码地址
dbg_init('b *0x401839')

# AI 执行调试命令
heap_info = dbg_exec('heap')
print("Heap status:", heap_info)

mem_data = dbg_exec('telescope 0x404140')
print("Memory at target:", mem_data)

# 继续执行程序
dbg_continue()

# ... 后续漏洞利用逻辑 ...
```

# 注意事项
1. **同步与异步**: 使用 `continue_and_wait()` 进行同步执行（等待程序停下），使用 `continue_nowait()` 进行异步执行。
2. **本地进程限制**: GDB Python API 目前仅支持本地进程调试。
3. **断点时机**: `gdb.attach()` 附加后程序会暂停，需要在合适的时机调用 `continue_and_wait()` 让程序继续运行。

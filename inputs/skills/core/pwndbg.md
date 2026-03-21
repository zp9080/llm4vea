# 适用场景
`pwndbg` 是 GDB 的一个强大插件，旨在极大提升二进制漏洞利用的调试效率。当你在 Linux 环境下分析 ELF 文件的 Pwn 问题时，`pwndbg` 都是首选工具。无论是栈溢出、堆漏洞还是格式化字符串，它提供的上下文显示、内存分析和专用命令都能让你快速理解程序状态。

`pwndbg` 适用于以下场景：
- 需要快速理解程序崩溃时的上下文（寄存器、反汇编、栈回溯）。
- 动态调试 ROP 链、各类堆利用（tcache poisoning、UAF 等）时，需要可视化观察栈、堆、bins 的状态。
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
  - `break *<address>`: 设置断点，程序执行到该地址时会暂停。
  - **PIE 程序断点**: 若 checksec 显示 `PIE: PIE enabled`，断点地址需用 `*$rebase(offset)` 形式。例如 `break *$rebase(0x1839)`，其中 offset 是 IDA 中看到的地址。
  - `x/10gx <address>`: 以 8 字节为单位连续查看 10 个内存单元，常用于检查返回地址、堆块指针等关键数据。

- **AI 自动化调试（GDB Python API）**
  - 使用 `gdb.attach(proc, gdbscript='...', api=True)` 启用 GDB Python API 访问。
  - 返回的 `gdb_instance` 对象可以通过 RPyC 库远程调用 GDB 的 Python API，实现程序化控制。
  - 可以执行 GDB 命令、设置断点、读取寄存器和内存、控制程序执行流程。
  - 使用 `dbg_continue()` 删除断点并异步继续执行程序，确保后续可以正常交互。

# 使用示例

## AI 自动化调试方式
使用 `api=True` 启用 GDB Python API，AI 可以程序化地控制调试流程，无需人工交互。

```python
from pwn import *

context(os='linux', arch='amd64', log_level='debug')
p = process("/path/to/binary")

gdb_instance = None

def dbg_init(breakpoint_cmd):
    """
    初始化 GDB 并启用 Python API（单例模式）
    
    首次调用：附加 GDB 到进程并设置断点
    后续调用：在已附加的 GDB 中设置新断点
    
    返回 Gdb 对象，可用于程序化控制
    注意: gdb.attach() 当 api=True 时返回 (PID, Gdb) 元组
    """
    global gdb_instance
    if gdb_instance is None:
        pid, gdb_obj = gdb.attach(p, gdbscript=breakpoint_cmd, api=True)
        gdb_instance = gdb_obj
    else:
        gdb_instance.execute(breakpoint_cmd)
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
    删除断点并继续执行程序
    
    此函数会：
    1. 删除当前所有断点（避免后续执行时再次停止）
    2. 继续执行程序
    
    如果需要在其他程序状态打断点，应再次调用 dbg_init()
    """
    if gdb_instance is None:
        raise Exception("GDB not initialized. Call dbg_init() first.")
    gdb_instance.execute('delete breakpoints')    
    try:
        gdb_instance.execute('c')
    except:
        pass

# ... 程序交互函数定义 ...
# 注意：下面的 "xxx" 应该替换为 ida-pro-mcp 中 view_func 对应函数的实际字符串
def add(idx, size, cont):
    p.sendlineafter(b"xxx", str(1))
    p.sendlineafter(b"xxx", str(idx))
    p.sendlineafter(b"xxx", str(size))
    p.sendafter(b"xxx", cont)

def delete(idx):
    p.sendlineafter(b"xxx", str(2))
    p.sendlineafter(b"xxx", str(idx))

# 执行一些程序操作
add(0, 0x100, b'aaaa')
add(1, 0x100, b'bbbb')
delete(0)

# 初始化 GDB 并设置断点
#
# 重要说明：
# 1. 前面的 add/delete 操作已经发送了数据到程序，程序正在等待下一次输入
# 2. 此时调用 dbg_init() 会附加 GDB 并设置断点
# 3. 当程序继续执行并运行到断点地址时，会自动停在断点处
# 4. 此时 AI 可以执行各种调试命令查看程序状态
#
# 断点设置原则：
# 1. 使用 break 设置断点
# 2. PIE 程序用 $rebase(offset)，offset 为 IDA 中的地址偏移
# 3. 断在 menu 函数入口，可有序观察每次操作后的状态
#
# 示例：menu 函数在 IDA 中地址为 0x1839（PIE 程序）
dbg_init('break *$rebase(0x1839)')

# AI 执行调试命令（可连续执行多个 dbg_exec，但 dbg_continue 必须在程序操作之前执行）
heap_info = dbg_exec('heap')
print("Heap status:", heap_info)

mem_data = dbg_exec('telescope 0x404140')
print("Memory at target:", mem_data)

# ... 继续调试或进行其他操作 ...
dbg_continue()

# 程序继续运行，等待断点或执行 add、delete 等操作
# 后续可再次设置断点进行调试
```

# 注意事项
1. **断点设置**: 使用 `break` 设置断点，PIE 程序使用 `$rebase(offset)` 格式，offset 为 IDA 中看到的地址偏移。
2. **dbg_continue 行为**: 该函数删除断点后继续执行程序，确保后续 pwntools 可以正常与程序交互。
3. **多次调试**: 需要在不同程序状态打断点时，再次调用 `dbg_init()` 设置新的断点。
4. **本地进程限制**: GDB Python API 目前仅支持本地进程调试。
5. **【必须】打印 dbg_exec 结果**: 每次 `dbg_exec()` 后必须打印输出
6. **【必须】调试函数调用顺序**：`dbg_init()` → `dbg_exec()` → `dbg_continue()`
   - **`dbg_exec()` 必须在 `dbg_init()` 之后调用**，否则 GDB 未初始化会报错
   - **任何程序交互前必须先调用 `dbg_continue()`**

# pwndbg命令详解

## vmmap
显示进程内存布局，定位程序基址、libc 基址、堆和栈地址。通过 `dbg_exec('vmmap')` 调用。

**注意：** `dbg_exec()` 输出包含 ANSI 颜色代码，解析前需过滤：
```python
clean_output = re.sub(r'\x1b\[[0-9;]*m', '', dbg_exec('vmmap'))
```

**输出格式示例：**
```
LEGEND: STACK | HEAP | CODE | DATA | RWX | RODATA 
             Start                End Perm     Size Offset File 
          0x3fe000           0x400000 rw-p     2000      0 /path/to/pwn 
        0x35dd1000         0x35df2000 rw-p    21000      0 [heap] 
    0x7f7536849000     0x7f753686b000 r--p    22000      0 /path/to/libc.so.6 
    0x7f753686b000     0x7f75369e3000 r-xp   178000  22000 /path/to/libc.so.6 
    0x7f75369e3000     0x7f7536a31000 r--p    4e000 19a000 /path/to/libc.so.6 
    0x7f7536a31000     0x7f7536a35000 r--p     4000 1e7000 /path/to/libc.so.6 
    0x7f7536a35000     0x7f7536a37000 rw-p     2000 1eb000 /path/to/libc.so.6 
    0x7fff9764a000     0x7fff9766b000 rw-p    21000      0 [stack] 
```

**地址定位：**
- libc 基址：查找第一个包含 `libc` 的行，Start 列即为基址（**禁止**添加 `r-xp` 等过滤条件！第一个 libc 行是 `r--p` 只读数据段，这才是真正的基址；`r-xp` 是代码段映射，不是基址）
- 堆地址：查找 `[heap]` 行，Start 列即为堆起始地址
- 栈地址：查找 `[stack]` 行，Start 列即为栈起始地址

**信息泄露配合：**
```python
# 【必须】使用 \x7f 方式接收泄露数据，libc 地址的高字节总是 0x7f，通过 recvuntil(b'\x7f') 可以精确定位
# 其他接收方式（如固定长度接收）容易受到输出格式变化的影响，导致地址解析错误
# 正确：recvuntil(b'\x7f')[-6:] 精确定位 libc 地址，禁止：data[:8]、recv(8)、固定长度接收等方式
leaked_addr = u64(p.recvuntil(b'\x7f')[-6:].ljust(8, b'\x00'))
offset = leaked_addr - libc_base_from_vmmap
# 后续运行时: libc_base = leaked_addr - offset
```

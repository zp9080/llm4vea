# 适用场景
`pwndbg` 是 GDB 的一个强大插件，旨在极大提升二进制漏洞利用的调试效率。当你在 Linux 环境下分析 ELF 文件的 Pwn 问题时，`pwndbg` 都是首选工具。无论是栈溢出、堆漏洞还是格式化字符串，它提供的上下文显示、内存分析和专用命令都能让你快速理解程序状态。

`pwndbg` 适用于以下场景：
- 需要快速理解程序崩溃时的上下文（寄存器、反汇编、栈回溯）。
- 动态调试 ROP 链、各类堆利用（tcache poisoning、UAF 等）时，需要可视化观察栈、堆、bins 的状态。
- 使用 `pwntools` 编写 EXP，并希望通过 `gdb.attach` 实现脚本与 GDB 的无缝联动调试。

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

# 使用示例
使用pwntools中的gdb.debug，然后定义dbg函数，在需要调试的地方调用dbg函数，即可在完成pwndbg的调试。
```python
p=gdb.debug("/home/zp9080/PWN/pwn")

#b *$rebase(0x14F5)
def dbg():
    gdb.attach(p,'b *0x401895')
    pause()

payload=b'b'
payload=payload.ljust(0x50,b'a')
dbg()

p.send(payload)
p.interactive()
```
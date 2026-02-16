
# 适用场景与前置条件

当程序存在栈溢出漏洞，且 `checksec` 显示已开启 NX (No-eXecute) 保护时，攻击者无法在栈上直接执行 Shellcode。此时，必须采用返回导向编程 (Return-Oriented Programming, ROP) 技术，利用程序自身或其链接库中已存在的代码片段 (gadgets) 来构造攻击链。本知识系统性地介绍 ROP 的基础原理，以及两种最核心的利用方式：`ret2libc` 和 `ret2csu`。

本知识适用于以下场景：
- 初步确认存在栈溢出，需要绕过 NX 保护执行任意代码。
- 需要通过 ROP 链泄露 libc 地址以绕过 ASLR，然后构造第二段 ROP 链调用 `system("/bin/sh")`。
- 目标为 64 位程序，但找不到 `pop rdi; ret` 等理想的传参 gadget，希望利用 `__libc_csu_init` 中的通用 gadget (ret2csu) 来控制函数参数。
- 调试 ROP 链时频繁出错，需要系统性地梳理寄存器传参、栈布局与 gadget 执行顺序。

# 原理要点与利用路径

- **ROP 核心原理**: 通过溢出覆盖栈上的返回地址，将其指向一个 gadget 的地址。该 gadget 执行完毕后，其末尾的 `ret` 指令会从新的栈顶弹出一个地址，跳转到下一个 gadget。通过精心排列栈上的 gadget 地址和参数，可以像调用函数一样执行一系列操作。

- **`ret2libc`**:
  - **原理**: 复用 C 标准库 (libc) 中的函数，特别是 `system`。由于 ASLR 的存在，libc 的基地址是随机的，因此 `ret2libc` 通常分两步：
    1.  **泄露地址**: 构造第一段 ROP 链，调用一个输出函数（如 `puts` 或 `write`）打印某个已解析的 libc 函数在 GOT 表中的地址（如 `puts@got`）。
    2.  **计算基址与 Get Shell**: 根据泄露的函数地址和其在对应 libc 版本中的偏移，计算出 libc 的基地址。然后构造第二段 ROP 链，调用 `system` 函数，并将 `"/bin/sh"` 字符串的地址作为参数传递。
  - **x86-64 传参**: 需要找到 `pop rdi; ret` 等 gadget，将参数放入 `rdi`, `rsi`, `rdx` 等寄存器。

- **`ret2csu` (x86-64)**:
  - **原理**: `__libc_csu_init` 函数（通常在静态链接或动态链接的可执行文件中都存在）包含两段非常有用的通用 gadgets，可以用来在缺少特定传参 gadget 的情况下，控制 `rdi`, `rsi`, `rdx` 三个寄存器，并调用一个函数指针。
  - **利用路径**:
    1.  构造一段特殊的 ROP chain，依次设置 `rbx`, `rbp`, `r12` (函数地址), `r13` (rdi), `r14` (rsi), `r15` (rdx)。
    2.  通过 `csu_front_gadget` 中的 `mov` 指令将 `r13`, `r14`, `r15` 的值赋给 `rdi`, `rsi`, `rdx`。
    3.  最后通过 `call qword ptr [r12+rbx*8]` 执行目标函数。
  - **应用**: 常用于在缺少 `pop rdi; ret` 等 gadget 时，调用 `write(1, read_got, 8)` 来泄露地址，或直接构造 `execve("/bin/sh", 0, 0)` 的系统调用。

# 调试线索与判定方法

- **GDB/pwndbg 调试**:
  - **验证溢出**: 在溢出函数的 `ret` 指令处下断点，检查 `rsp` 指向的地址是否已被 ROP 链的第一个 gadget 地址覆盖。
  - **跟踪 ROP 链**: 在每个 gadget 的地址处下断点，单步执行 (`si`/`ni`) 并检查：
    - `rip` 是否按预期跳转。
    - 相应的寄存器是否被正确赋值（如 `pop rdi; ret` 后 `rdi` 的值）。
    - `rsp` 是否正确地在每个 `ret` 后增加。
  - **libc 基址验证**: 泄露地址后，用 `vmmap` 查看 GDB 中 libc 的实际基址，与计算出的基址进行比对。
  - **`ret2csu` 调试**: 在 `csu_end_gadget` (`pop` 序列) 和 `csu_front_gadget` (`call`) 处下断点，仔细检查 `rbx` 到 `r15` 寄存器是否被 payload 控制，以及 `rdi`, `rsi`, `rdx` 是否被正确赋值。

# 常见陷阱与收敛建议

- **栈对齐 (Stack Alignment)**: x86-64 架构要求在 `call` libc 函数前，`rsp` 必须是 16 字节对齐的。否则可能导致 `movaps` 指令崩溃。**解决方法**：在调用 `system` 等函数前，额外添加一个 `ret` gadget 来调整栈。
- **地址错误**:
  - **PIE/ASLR**: 忘记为 payload 中的地址（gadgets, PLT/GOT entries）加上程序基址或 libc 基址。
  - **libc 版本不匹配**: 本地与远程的 libc 版本不同，导致函数偏移计算错误。务必使用目标环境的 libc 文件进行分析。
- **坏字符 (Bad Characters)**: `strcpy`, `scanf` 等函数可能会截断 `\x00`, `\x0a` 等字符。payload 中使用的地址或数据如果包含坏字符，会导致 ROP 链不完整。
- **`ret2csu` 的细节**:
  - `call` 指令是 `call qword ptr [r12+rbx*8]`。为简化利用，通常将 `rbx` 设置为 0，`r12` 直接设置为目标函数在 GOT 表中的地址。
  - `rbp` 必须设置为 `rbx+1`，以通过 `cmp rbp, rbx` 的检查。
- **找不到 Gadget**: 如果程序本身很小，找不到足够的 gadgets，别忘了在 `libc.so.6` 中搜索。`pwntools` 的 `ROP(libc)` 会自动完成这一步。

# 适用场景
`pwntools` 是为 Pwn 竞赛和漏洞利用开发而设计的 Python 框架。当你需要将手工的 GDB 调试过程转化为自动化的 EXP (Exploit) 脚本时，`pwntools` 是不二之选。它适用于任何需要与本地或远程二进制程序进行复杂交互的场景。

使用本知识的典型场景包括：
- 编写 EXP 脚本，需要方便地在本地调试 (`process`) 和远程攻击 (`remote`) 之间切换。
- 需要快速解析 ELF 文件信息（如符号地址、GOT/PLT 地址）。
- 构造和调试 ROP 链或格式化字符串漏洞，希望利用高级 API (`ROP`, `fmtstr_payload`) 自动生成 payload。
- 希望在 Python 脚本中无缝集成 GDB (`gdb.attach`)，实现自动化与手动调试的结合。

# 使用方法
`pwntools` 的核心思想是提供一套高级、简洁的 API，将 Pwn 中的常见模式和繁琐任务进行封装，让研究者能专注于漏洞逻辑本身。
- **连接与交互 (`tube`)**
  - 提供统一的 `process` 和 `remote` 接口，返回一个 `tube` 对象，该对象具有相同的 `send`/`recv` 方法，使得本地和远程代码几乎无需修改。
  - `sendlineafter(delim, data)` 是处理菜单式交互程序的最佳实践，它能确保在收到程序提示（`delim`）后才发送数据，避免了因时序问题导致的交互混乱。
  - `interactive()` 是脚本的终点，它将控制权交还给用户，方便在拿到 shell 后进行手动操作。

- **ELF 静态分析 (`ELF`)**
  - `ELF` 类可以像操作 Python 对象一样访问二进制文件的内部信息，如 `elf.symbols['main']`、`elf.got['puts']`、`elf.bss()` 等，免去了手动使用 `readelf` 或 `objdump` 的麻烦。

- **格式化字符串 (`fmtstr_payload`)**
  - 这是一个黑魔法函数，只需提供格式化字符串的偏移和要写入的地址-值对 ` {addr: value}`，它就能自动计算并生成最短、最高效的 `%n` 写入 payload。

- **偏移计算 (`cyclic`)**:
  - **现象**: 栈溢出时，不确定需要多少填充字节才能覆盖返回地址。
  - **方法**: 使用 `p.sendline(cyclic(200))` 发送随机的字符串。程序崩溃后，在 pwndbg 中查看崩溃时的内存状态找到准确偏移量。

- **调试集成 (`gdb.attach`)**
  - 允许在脚本的任意位置暂停，并启动 GDB 附加到正在运行的进程上。
  - `gdbscript` 参数可以传递一系列 GDB/`pwndbg` 命令，实现调试的自动化设置。


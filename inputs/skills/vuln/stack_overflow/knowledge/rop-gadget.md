# 适用场景
当栈溢出漏洞存在但 NX 保护开启时，必须使用代码重用攻击，而返回导向编程 (ROP) 是最主流的技术。本知识旨在指导如何利用工具高效地查找和筛选 ROP gadgets，为构造 ROP 链打下基础。

此知识适用于以下场景：
- 已确定需要构造 ROP 链，但手动在反汇编中寻找 `pop rdi; ret` 等 gadget 效率低下。
- 需要寻找满足特定语义的 gadget，如控制多个寄存器（`pop rsi; pop r15; ret`）、执行系统调用（`syscall; ret`）等。

# 使用方法
Gadget 是程序中以 `ret` 或其他间接跳转指令结尾的一小段指令序列。ROP 的核心思想就是通过精心布置栈上的返回地址，将这些 gadgets "串"起来，形成一个完整的、具有攻击者所需逻辑的执行流。

- **`ROPgadget`**: 一个强大的独立 Python 工具，可以对二进制文件及其依赖的库进行深度搜索。
  - `ROPgadget --binary <file> --only "pop|ret"`: 查找只包含 `pop` 或 `ret` 的 gadgets。
  - `ROPgadget --binary <file> --string "/bin/sh"`: 在二进制文件中查找字符串。

- **Gadget 的种类**:
  - **传参 Gadgets**: `pop <reg>; ret` 是最常见的，用于将栈上的值加载到寄存器中，以满足函数调用的参数要求（如 x64 下的 `rdi`, `rsi`, `rdx`）。
  - **运算 Gadgets**: `add rax, rbx; ret`, `xor eax, eax; ret` 等，用于执行简单的算术或逻辑运算。
  - **内存读写 Gadgets**: `mov [rax], rdx; ret` (写), `mov rax, [rbx]; ret` (读)，用于与内存交互。
  - **系统调用 Gadgets**: `syscall; ret` 或 `int 0x80; ret`，用于直接触发系统调用。
  - **栈迁移 (Stack Pivot) Gadgets**: `leave; ret` 或 `mov rsp, rbp; ret`，用于将栈指针迁移到其他可控内存区域。

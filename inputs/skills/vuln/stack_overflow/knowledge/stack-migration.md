
# 适用场景与前置条件

当存在栈溢出漏洞，但可供利用的溢出空间非常有限，无法在当前栈帧上构造一个完整的 ROP 链时，就需要使用**栈迁移 (Stack Pivoting)** 技术。其核心思想是将栈指针 (`rsp`) 劫持到一个我们能够完全控制的、空间更大的内存区域（如 BSS 段或堆块），并在该新栈上展开后续的 ROP 攻击。

本知识适用于以下场景：
- 已确认存在栈溢出，但可溢出空间不足以放下完整的 `ret2libc` 或其他 ROP 链。
- 程序中有地址已知且可写的内存区域（如 `.bss` 段），或已通过信息泄露获得某个可控堆块的地址。
- 在 GDB 中调试发现，短的 ROP 链可以工作，但加长后就因覆盖到其他关键栈上数据而失败。
- 需要利用 `leave; ret` 这个经典 gadget 来实现对 `rsp` 的控制。

# 原理要点与利用路径

- **核心 Gadget: `leave; ret`**
  - `leave` 指令等价于两条指令：`mov rsp, rbp` 和 `pop rbp`。
  - **`mov rsp, rbp`**: 这是栈迁移的关键。它将当前的栈指针 `rsp` 直接设置为 `rbp` 的值。
  - **`pop rbp`**: 从新的 `rsp` 指向的位置弹出一个值到 `rbp`，为下一次函数调用做准备（虽然在 ROP 链中我们更关心它对 `rsp` 的影响：`rsp` 会增加 8 字节）。
  - 通过在溢出时精心构造栈，我们可以控制 `leave` 执行前的 `rbp` 值。如果我们能将 `rbp` 设置为我们伪造的新栈的地址，那么 `mov rsp, rbp` 就会将 `rsp` 指向我们的新栈。

- **利用路径**: 栈迁移通常是一个两阶段的过程。
  1.  **第一阶段：布置新栈并触发迁移**
      - **布置新栈**: 利用程序中的 `read`、`gets` 或其他写入函数，向一个已知地址（如 `.bss` 段）写入一个完整的、将在第二阶段使用的 ROP 链。
      - **触发迁移**: 再次触发栈溢出，构造一个短的 payload，其目标不是直接 get shell，而是劫持控制流去执行 `leave; ret`。
        - **Payload 结构**: `[padding] + [new_stack_addr] + [leave_ret_gadget]`
        - `padding`: 填充物，直到覆盖到 `saved rbp`。
        - `new_stack_addr`: 伪造的新栈的起始地址。这个地址将被 `pop rbp` 恢复到 `rbp` 寄存器。
        - `leave_ret_gadget`: `leave; ret` gadget 的地址，将被放在返回地址的位置。

  2.  **第二阶段：执行新栈上的 ROP 链**
      - 当溢出函数执行到函数尾声的 `leave; ret` 时：
        1. 首先执行函数自己的 `leave`，这会从栈上恢复我们伪造的 `new_stack_addr` 到 `rbp`。
        2. 然后执行 `ret`，这会跳转到我们布置的 `leave_ret_gadget`。
        3. 执行 `leave_ret_gadget` 中的 `leave`：`mov rsp, rbp`，此时 `rsp` 就指向了 `new_stack_addr`，栈迁移完成！
        4. 紧接着的 `pop rbp` 和 `ret` 会开始执行新栈上的 ROP 链。

# 调试线索与判定方法

- **GDB/pwndbg 调试**:
  - **断点设置**:
    1.  在溢出函数的 `leave; ret` 指令处下断点。
    2.  在 `leave; ret` gadget 的地址处下断点。
    3.  在新 ROP 链的第一个 gadget 地址处下断点。
  - **状态观察**:
    - 在第一个断点处，检查 `rbp` 寄存器的值是否即将被覆盖为 `new_stack_addr`。
    - 在第二个断点处，单步执行 `leave` 指令 (`ni`)，并观察 `rsp` 是否成功变为 `new_stack_addr`。
    - 在第三个断点处，如果程序能命中，说明整个栈迁移和 ROP 链的启动都已成功。
  - **内存检查**: 在触发迁移之前，使用 `x/20gx <new_stack_addr>` 检查伪造栈的内容是否已按预期写入。

# 常见陷阱与收敛建议

- **地址精确计算**: `rbp` 应该被设置为新 ROP 链的起始地址。`leave` 指令执行 `mov rsp, rbp` 后，`rsp` 指向新链，然后 `pop rbp` 会消耗掉链的第一个 8 字节，`ret` 会消耗第二个 8 字节。因此，新 ROP 链的布局通常是 `[fake_rbp] + [first_gadget] + ...`，而 `rbp` 应该被设置为 `new_stack_addr`，即 `fake_rbp` 的地址。
- **时序问题**: 必须保证在执行栈迁移的 `leave; ret` **之前**，新栈区的内容已经被完全写入。如果程序逻辑是先溢出再 `read`，这个顺序就不对。
- **内存区域权限**: 用于伪造新栈的内存区域必须是可读可写的。BSS 段是最佳选择（如果 PIE 关闭）。如果 PIE 开启，则需要先泄露 `.bss` 或堆的地址。
- **Gadget 可用性**: `leave; ret` 非常常见，几乎所有程序都有。如果没有，可以使用 `mov rsp, <reg>; ret` 等其他可以控制 `rsp` 的 gadget 组合，但这会更复杂。
- **Payload 长度**: 虽然栈迁移解决了 ROP 链过长的问题，但第一阶段触发迁移的 payload 本身也需要空间。你需要确保溢出空间至少能放下 `new_stack_addr` 和 `leave_ret_gadget` 的地址。

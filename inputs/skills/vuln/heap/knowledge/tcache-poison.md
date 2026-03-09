
# 适用场景与前置条件

`Tcache Poison` 是针对 glibc 堆中 tcache 机制的一种核心利用技术。当存在漏洞（通常是 Use-After-Free 或堆溢出）可以修改一个已被释放到 tcache 中的 chunk 内容时，攻击者可以篡改其 `fd` (next) 指针，使其指向一个任意的目标地址（如 `__free_hook`）。当程序下一次从该 tcache bin 中申请内存时，就会错误地返回这个被“投毒”的目标地址，从而让攻击者获得一次向任意地址写入任意内容的能力。

本知识适用于以下场景：
- 目标程序使用 glibc 2.26 及以上版本，`pwndbg` 的 `tcache` 命令可以显示 tcache 链表。
- 已发现 Use-After-Free (UAF) 或堆溢出漏洞，能够修改已 `free` 到 tcache 中的 chunk 的内容。
- 需要一个强大的原语来获得任意地址写，以劫持控制流，例如覆盖 `__free_hook`、`__malloc_hook` 或其他函数指针。
- 调试 tcache 相关利用时，需要通过 `tcache`、`x/gx` 等命令确认投毒是否成功，或排查失败原因。

# 原理要点与利用路径

- **Tcache 机制**:
  - Tcache 是每个线程私有的、用于缓存小尺寸空闲 chunk 的单向链表数组。
  - `free` 一个 tcache-size 的 chunk 时，它会被直接放到对应 tcache bin 的头部。
  - `malloc` 时，会优先从 tcache 中取 chunk。
  - 在 glibc 2.26 - 2.31 版本中，tcache 对 `fd` 指针和 double free 的检查非常薄弱，使其成为攻击的重灾区。

- **利用路径 (无 Safe-Linking, glibc < 2.32)**:
  1.  **布置与释放**: 申请至少两个 chunk (`a` 和 `b`)，然后 `free(a)`。`a` 进入 tcache。`b` 的作用是防止 `a` 与 top chunk 合并。
  2.  **投毒**: 利用 UAF 或堆溢出漏洞，将 `a` 的 `fd` 指针覆盖为目标地址 `target_addr` (如 `__free_hook` 的地址)。此时 tcache 链表被污染，变成了 `tcache_bin -> a -> target_addr`。
  3.  **获取目标地址**: `malloc` 两次相同大小的 chunk。
      -   第一次 `malloc` 会分配出原始的 chunk `a`。
      -   第二次 `malloc` 会沿着被污染的 `fd` 指针，返回 `target_addr`。
  4.  **任意地址写**: 程序以为它得到了一个合法的堆块，并向其写入数据。实际上，它正向 `target_addr` 写入数据。通过控制写入的数据（如 `system` 函数的地址），即可完成任意地址写。

- **Safe-Linking (glibc >= 2.32)**:
  - **原理**: `fd` 指针被 `(L >> 12) ^ P` 加密，其中 `P` 是 chunk 地址，`L` 是 `fd` 的明文值。直接覆盖 `fd` 会导致 `malloc` 时解密检查失败。
  - **绕过**: 攻击者需要先泄露堆地址（以获得 `P`），然后计算出一个合法的加密 `fd` 值 `(target_addr >> 12) ^ P`，再将其写入。这要求漏洞利用链中必须包含信息泄露环节。

# 调试线索与判定方法

- **GDB/pwndbg 调试**:
  - **`tcache` 命令**: 用于检查 tcache 链表状态。通常在攻击链完成、准备进行任意地址写时检查一次即可，确认链表指针指向目标地址。
  - **`x/gx <chunk_addr>`**: 精确检查被 `free` 的 chunk 的 `fd` 指针是否被成功覆盖。
  - **`malloc` 返回值**: 在 `malloc` 调用后，检查其返回值。第二次 `malloc` 的返回值应等于 `target_addr`。
  - **`watch <target_addr>`**: 对目标地址（如 `__free_hook`）设置观察点，当其被写入时 GDB 会暂停，可以确认写入时机和内容。

- **判定成功**:
  - `x/gx <chunk_addr>` 显示的 `fd` 指针是我们伪造的目标地址。
  - 第二次 `malloc` 返回的指针指向了 `target_addr`。
  - `x/gx <target_addr>` 显示其内容已被我们写入的数据覆盖。

# 常见陷阱与收敛建议

- **Chunk Size 不匹配**: `malloc` 的大小必须与被污染的 tcache bin **严格对应**，否则 `malloc` 不会从该 bin 中分配。注意 `malloc(0x20)` 对应的是 `0x30` 大小的 tcache bin。
- **Tcache Bin 已满**: 每个 tcache bin 默认最多存放 7 个 chunks。如果 bin 已满，`free` 会将 chunk 放入 unsorted bin，导致投毒失败。
- **错误的 Target Address**: 如果目标地址是只读的，写入会失败。如果地址无效，程序会崩溃。
- **Safe-Linking 计算错误**: 在 glibc >= 2.32 中，如果泄露的堆地址不准，或加密 `fd` 的计算有误，`malloc` 在解密时会发现 `(decrypted_fd >> 12) != P`，导致 `abort`。

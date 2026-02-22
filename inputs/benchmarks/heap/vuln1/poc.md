# 漏洞描述
libc2.31
tcache poison然后打free_hook

# Source Code
```c
#include <stdio.h>
#include <stdlib.h>
#include <sys/mman.h>
#include <unistd.h>

char *notes[0x10];
size_t len[0x10];

void init() {
  setbuf(stdin, 0);
  setbuf(stdout, 0);
  setbuf(stderr, 0);
}

int add_note() {

  char buf[32];
  unsigned int idx=0;
  unsigned int size=0;
  printf("Idx:\n");
  read(0,buf,32);
  idx=atoi(buf);
  memset(buf,0,32);
  if(idx<0 || idx >=0x10){
    printf("Invalid Idx\n");
    exit(0);
  }

  printf("Size:\n");
  read(0,buf,32);
  size=atoi(buf);
  memset(buf,0,32);
  if(size<0x410 || size >=0x1000){
    printf("Invalid Size\n");
    exit(0);
  }

  notes[idx]=malloc(size);
  len[idx]=size;
  printf("note added successfully\n");
  printf("input the note: ");
  read(0, notes[idx], len[idx]);
  return 0;

}

int delete_note() {
  char buf[32];
  unsigned int idx=0;
  printf("Idx:\n");
  read(0,buf,32);
  idx=atoi(buf);
  memset(buf,0,32);
  if(idx<0 || idx >=0x10){
    printf("Invalid Idx\n");
    exit(0);
  }

  if (notes[idx] != NULL) {
    free(notes[idx]);
  } else {
    printf("note don't exist\n");
    return 1;
  }
  return 0;
}

int edit_note() {
  char buf[32];
  unsigned int idx=0;
  printf("Idx:\n");
  read(0,buf,32);
  idx=atoi(buf);
  memset(buf,0,32);
  if(idx<0 || idx >=0x10){
    printf("Invalid Idx\n");
    exit(0);
  }

  if (notes[idx] != NULL) {
    printf("input the note: ");
    read(0, notes[idx], len[idx]);
  } else {
    printf("note don't exist\n");
    return 1;
  }
  return 0;

}

int view_note() {
  char buf[32];
  unsigned int idx=0;
  printf("Idx:\n");
  read(0,buf,32);
  idx=atoi(buf);
  memset(buf,0,32);
  if(idx<0 || idx >=0x10){
    printf("Invalid Idx\n");
    exit(0);
  }

  if (notes[idx] != NULL) {
    write(1, notes[idx], len[idx]);
  } else {
    printf("note don't exist\n");
    return 1;
  }
  return 0;
}

int read_num() {
  char s[8];
  read(0,s,8);
  return atoi(s);
}

void print_menu() {
  puts("1.add note");
  puts("2.delete note");
  puts("3.view note");
  puts("4.edit note");
  puts("5.exit");
}
int main() {
  init();
  printf("JuicyMio和ZER0出完Pwn方向的题信心满满,觉得这次Pwn覆盖面挺广,类型挺全.\n");
  printf("在聊天水群的时候想起来还有23级也会参加比赛,突然感到焦虑怕Pwn方向被AK了\n");
  printf("于是决定和notebook那道题梦幻联动出一个堆题,真有出题人新生赛出堆啊),轻点喷\n");
  while (1) {
    print_menu();
    int option = read_num();
    int idx;
    if (option == 1) {
      add_note();
    } else if (option == 2) {
      delete_note();
    } else if (option == 3) {
      view_note();
    } else if (option == 4) {
      edit_note();
    } else if (option == 5) {
      exit(0);
    } else
      puts("invalid option");
  }
}
```
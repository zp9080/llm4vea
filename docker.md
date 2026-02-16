# 构建镜像
```bash
docker build --platform linux/amd64 -t pwn-u22 .
docker images | grep pwn-u22
```


# 启动容器
--rm：容器退出后自动删除，不留垃圾
```bash
docker run -it --rm pwn-u22 /bin/bash
```


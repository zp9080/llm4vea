# Docker
## 构建镜像
```bash
docker build --platform linux/amd64 -t pwn-u22 .
docker images | grep pwn-u22
```

## 启动容器
```bash
# --rm：容器退出后自动删除，不留垃圾
docker run -it --rm pwn-u22 /bin/bash
# 不删除容器,允许容器访问宿主服务，添加端口映射
docker run -it --add-host host.docker.internal:host-gateway -p 8080:8080 -p 8501:8501 pwn-u22 /bin/bash

docker exec -it container_id /bin/bash

```

# Streamlit
streamlit run src/web_ui.py --server.headless true  --server.port 8502


# Patchelf
patchelf --replace-needed libc.so.6 /root/llm4vea/inputs/benchmarks/heap/vuln1/libc.so.6 /root/llm4vea/inputs/benchmarks/heap/vuln1/pwn
patchelf --set-interpreter /root/llm4vea/inputs/benchmarks/heap/vuln1/ld-linux-x86-64.so.2 /root/llm4vea/inputs/benchmarks/heap/vuln1/pwn
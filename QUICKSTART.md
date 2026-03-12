# Docker
## 构建镜像
```bash
docker build --platform linux/amd64 -t pwn-final-u22 .
docker images | grep pwn-final-u22
```

## 启动容器
```bash
# 允许容器访问宿主服务，允许宿主访问容器8080,8501端口的服务，允许macos的docker进行ptrace调试
docker run -it --add-host host.docker.internal:host-gateway -p 8080:8080 -p 8501:8501 --cap-add=SYS_PTRACE --security-opt seccomp=unconfined pwn-final-u22 /bin/bash

docker exec -it container_id /bin/bash

```

# Streamlit
streamlit run src/web_ui.py --server.headless true  --server.port 8501


# Patchelf
patchelf --replace-needed libc.so.6 /root/llm4vea/inputs/benchmarks/heap/vuln1/libc.so.6 /root/llm4vea/inputs/benchmarks/heap/vuln1/pwn
patchelf --set-interpreter /root/llm4vea/inputs/benchmarks/heap/vuln1/ld-linux-x86-64.so.2 /root/llm4vea/inputs/benchmarks/heap/vuln1/pwn
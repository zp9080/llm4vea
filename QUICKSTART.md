# Docker
## 构建镜像
```bash
docker build --platform linux/amd64 -t pwn-u22 .
docker images | grep pwn-u22
```

## 启动容器
```bash
# 允许容器访问宿主服务，允许宿主访问容器8080,8501端口的服务，允许macos的docker进行ptrace调试
docker run -it --network host --add-host host.docker.internal:host-gateway -p 8080:8080 -p 8501:8501 --cap-add=SYS_PTRACE --security-opt seccomp=unconfined pwn-u22 /bin/bash

docker exec -it container_id /bin/bash

```

# 推荐运行环境

本项目推荐在 Windows WSL 环境中运行，原因如下：

- 测试用例均为 amd64 架构
- macOS 主流为 ARM 架构，Docker 运行 amd64 镜像时 pwndbg 无法正常启动 gdb 进程
- WSL 原生支持 amd64，调试体验更佳

ida-mcp 可直接在 Windows 宿主机启动，只需修改 mcps.json 中的 url 配置即可。

# LLM 配置

项目依赖 LLM API，需要配置 `.env` 文件。请参考 `.env_example` 创建自己的配置文件：

```bash
cp .env_example .env
```

然后修改 `.env` 中的以下配置项：

- `OPENAI_API_KEY`: LLM API 密钥
- `OPENAI_API_BASE`: API 地址
- `OPENAI_MODEL`: 模型名称


# Streamlit
streamlit run src/web_ui.py --server.headless true  --server.port 8501


# Patchelf
patchelf --replace-needed libc.so.6 ~/llm4vea/inputs/benchmarks/heap/vuln1/libc.so.6 ~/llm4vea/inputs/benchmarks/heap/vuln1/pwn
patchelf --set-interpreter ~/llm4vea/inputs/benchmarks/heap/vuln1/ld-linux-x86-64.so.2 ~/llm4vea/inputs/benchmarks/heap/vuln1/pwn
chmod +x ~/llm4vea/inputs/benchmarks/heap/vuln1/pwn
chmod +x ~/llm4vea/inputs/benchmarks/heap/vuln1/ld-linux-x86-64.so.2

# Dockerfile for Pwn Environment (Clean Version)
# Based on Ubuntu 22.04

FROM ubuntu:22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
# Set locale to avoid issues with some tools
ENV LANG=C.UTF-8

# Update and install essential tools
RUN apt-get update && apt-get install -y \
    # 基础工具
    curl wget net-tools iputils-ping iproute2 dnsutils \
    # 编辑器
    vim nano \
    # 终端复用
    tmux screen \
    # 压缩工具
    zip unzip tar gzip bzip2 xz-utils \
    # 进程/系统工具
    procps htop lsof psmisc tree \
    # 网络调试
    telnet netcat-traditional traceroute mtr \
    # 开发编译工具
    git \
    python3 \
    python3-pip \
    ruby \
    gdb \
    build-essential \
    patchelf \
    # 其他常用工具
    less file man-db sudo apt-utils \
    # 清理缓存
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 1. Install one_gadget (Blog: "sudo apt update ... gem install one_gadget")
RUN gem install one_gadget

# 2. Install pwntools (Blog: "直接pip install pwntools")
# 3. Install ROPgadget (Blog: Referenced link usually uses pip)
RUN pip3 install pwntools ROPgadget

# 4. Install pwndbg (Blog: "sudo ./setup.sh")
WORKDIR /root
RUN git clone https://github.com/pwndbg/pwndbg && \
    cd pwndbg && \
    ./setup.sh
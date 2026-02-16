# Dockerfile for Pwn Environment (Clean Version)
# Based on Ubuntu 22.04

FROM ubuntu:22.04

# Avoid interactive prompts
ENV DEBIAN_FRONTEND=noninteractive
# Set locale to avoid issues with some tools
ENV LANG=C.UTF-8

# Update and install minimal dependencies required for the tools
# git: for cloning pwndbg
# python3, python3-pip: for pwntools and ROPgadget
# ruby: for one_gadget
# sudo: required by pwndbg's setup.sh script
# gdb: base debugger
RUN apt-get update && apt-get install -y \
    git \
    python3 \
    python3-pip \
    ruby \
    gdb \
    build-essential

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

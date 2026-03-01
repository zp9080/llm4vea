# LLM 驱动 GDB 的自动化 Pwn 调试与 EXP 演化

本项目探索用 LLM 驱动 GDB，从已触发漏洞的 PoC 自动演化到可用 EXP。重点在漏洞触发后的动态调试、路径判断与利用迭代，目标是形成可验证的利用方案与报告。

## 目标与定位
- 场景：已有稳定触发漏洞的 PoC
- 目标：自动调试 → 判断利用路径 → 迭代 EXP → 验证可利用性
- 方式：多智能体协作 + GDB 动态反馈 + 知识/模板注入

## Skill 设计（Core / Vuln / Edge）
- **Core**：任何二进制利用任务的起始阶段必读，覆盖保护机制、ROP gadget、工具链与通用流程
- **Vuln**：确认漏洞类型后读取，提供该漏洞的系统化方法与 EXP 模板
- **Edge**：常规流程仍失败或出现异常崩溃时读取，处理少见但关键的边界问题

## 代码与数据设计

### skills 目录
```
inputs/skills/
  core/      # 核心通用知识（每次必读）
  vuln/      # 漏洞类型知识（按类型读取）
    format_string/
    stack_overflow/
    heap/
  edge/      # 边界问题知识（异常时读取）
```
vuln 类型的 skill 由 **knowledge** 与 **templates** 两部分组成：knowledge 负责原理与判断，templates 负责可直接改造的 EXP 骨架。

### inputs/benchmarks
用于评测与回归测试的 Pwn 题目集合，按类型组织。每个题目包含：
- `pwn`：可执行文件
- `poc.md`：漏洞触发点与 PoC 说明
- `exp.md`：参考 EXP

### inputs/tools.json
系统可用工具清单，例如 `checksec`、`ROPgadget`、`exp-runner` 等，用于工具调用编排。

## src 设计

### agents
- `BaseAgent`：统一的 Agent 基类与执行框架
- `PlanAgent`：
  - 输入：Binary + `poc.md`（或直接给出源码，作为 IDA-MCP 的替代信息源）
  - 调用：`checksec`、`ropgadget` 等工具进行静态分析
  - 读取：Core skill（必读）与候选 Vuln skill（辅助判断）
  - 输出：`plan.md`，包含漏洞类型判断、工具输出、建议PwnAgent读取的 Vuln skill、初步利用思路
- `PwnAgent`：
  - 输入：`plan.md`
  - 读取：Core skill + plan 指定的 Vuln skill（含 templates）
  - 生成：基于模板编写 `exp.py`
  - 运行：调用 `exp-runner` 执行 `exp.py`，并利用超时机制避免卡死
  - 调试：根据 `exp-runner` 反馈，在 `exp.py` 中联动 `pwndbg`（结合 pwntools 的 `gdb.attach`）
  - 输出：`report.md`
- `EvaluateAgent`：
  - 独立脚本运行，不参与主流程
  - 输入：`plan.md`、`report.md` 与 benchmarks 的 `exp.md`
  - 输出：对 PlanAgent和PwnAgent 执行质量的评估与打分

### 执行开关
- PlanAgent 与 PwnAgent 支持独立开关，便于只运行单个阶段
- EvaluateAgent 独立执行，与主流程解耦

## 运行时产物
运行产物保存在 `runs/{timestamp}/`（timestamp用YY-MM-DD-HH-MM-SS格式），包括：
- plan.md: 任务计划与中间决策
- report.md: PwnAgent 生成的报告与 EXP

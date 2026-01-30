<h4 align="center">
    <p>
        <b>简体中文</b> |
        <a href="README.md">English</a>
    </p>
</h4>

<div align="center">


# ASTRA：Automated Synthesis of agentic Trajectories and Reinforcement Arenas

[![Blog](https://img.shields.io/badge/Blog-Project%20Page-orange?logo=github)](https://lianjiatech.github.io/astra.blog/)
[![HuggingFace](https://img.shields.io/badge/🤗%20HuggingFace-Datasets-yellow)](https://huggingface.co/collections/Emperorizzis/astra-dataset)
[![HuggingFace](https://img.shields.io/badge/🤗%20HuggingFace-Models-yellow)](https://huggingface.co/collections/Emperorizzis/astra-models)
[![Paper](https://img.shields.io/badge/📄%20Arxiv-Paper-blue)](https://arxiv.org/pdf/2601.21558)
[![License](https://img.shields.io/badge/License-Apache%202.0-green.svg)](assets/LICENSE.txt)

</div>

## 🆕 更新日志

| 日期 | 更新内容 |
|------|----------|
| 2026/01/30 | 📄 [论文发布](https://arxiv.org/pdf/2601.21558) |
| 2026/01/22 | 🎉 发布代码、模型和数据集 |

---

## 📖 简介

本代码库提供一套端到端的 **全自动**、**可验证** 的高质量数据与环境合成流水线，原生支持 **过程级奖励（Process-level Rewards）**。该方案专为训练具备多步推理和工具使用能力的模型设计，并且易于 **扩展** 到新的任务和工具。以下是两个核心模块：

- **Trajectory 合成**：自动生成高质量、多步骤的交互式 **轨迹**，并通过 **奖励系统** 进行验证。

- **环境合成**：全自动合成交互式 **环境**，**无需人工标注**，提供 **过程奖励** 以支持 **RLVR** 训练。



| 模块 | 功能 | 目录 |
|------|------|------|
| **Trajectory 合成** | 工具图构建 → 任务生成 → 轨迹采集 → Reward 评估 | [`trajectory_synthesis/`](trajectory_synthesis/) |
| **环境合成** | 问题分解 → 工具环境自动生成 → RLVR 训练数据 | [`env_synthesis/`](env_synthesis/) |

## 🏆 模型性能

我们发布了两个模型：**ASTRA-32B-Thinking-v1** 和 **ASTRA-14B-Thinking-v1**，是基于合成的数据进行 SFT 和 RL 训练后得到的模型。以下是在 **BFCL-V3-MT** 上的评分结果：

| Model | Base | Long Context | Miss Func | Miss Param | Average ↓ |
|-------|------|--------------|-----------|------------|---------|
| Claude-Opus-4-5-20251101 | 81.5 | 70.5 | 64.0 | 58.0 | 68.5 |
| GLM-4.6 | 74.5 | 66.5 | 68.0 | 63.0 | 68.0 |
| **ASTRA-32B-Thinking-v1** | **76.5** | **66.5** | **65.5** | **48.5** | **64.3** |
| Gemini-3-Pro-Preview | 69.0 | 64.0 | 63.0 | 56.5 | 63.1 |
| o3-2025-04-16 | 68.0 | 63.0 | 63.5 | 54.5 | 62.3 |
| Claude-Sonnet-4-5-20250929 | 69.0 | 59.0 | 65.0 | 52.5 | 61.4 |
| Grok-4-1-fast-reasoning | 70.5 | 62.5 | 59.5 | 43.0 | 58.9 |
| **ASTRA-14B-Thinking-v1** | **67.0** | **61.0** | **56.0** | **48.5** | **58.1** |
| LoopTool-32B (Report From Paper)  | - | - | - | - | 57.8 |
| Claude-Haiku-4-5-20251001 | 63.5 | 56.0 | 42.5 | 52.5 | 53.6 |
| Kimi-K2-Instruct| 62.0 | 55.0 | 41.0 | 44.5 | 50.6 |
| Qwen3-32B | 59.0 | 51.5 | 47.5 | 40.5 | 49.6 |
| Qwen3-30B-A3B-Thinking-2507 | 66.0 | 58.0 | 31.5 | 35.5 | 47.8 |
| TouCan-32B (Report From Paper) | - | - | - | - | 46.5 |
| Qwen3-14B | 50.5 | 48.0 | 39.5 | 40.0 | 44.5 |
| Qwen3-30B-A3B-Instruct-2507| 43.5 | 41.0 | 10.5 | 25.0 | 30.0 |

---

## 🔄 Pipelines

### Part 1: 轨迹数据合成

<div align="center">
<img src="assets/sft-pipeline.png" alt="SFT Pipeline" width="80%"/>
</div>

从 MCP Server 工具文档出发，构建工具依赖图，生成高质量 SFT 训练数据。

```
mcp_servers.jsonl → 图构建 → 任务生成 → LLM交互 → Reward评估 → SFT数据
```

👉 **详细使用说明请参考 [`trajectory_synthesis/README_zh.md`](trajectory_synthesis/README_zh.md)**

---

### Part 2: 环境合成

<div align="center">
<img src="assets/env.png" alt="Environment Synthesis Pipeline" width="100%"/>
</div>

从问答对自动生成可执行的工具环境，支持 RLVR 训练。

```
QA数据 → 问题分解 → 工具必要性检查 → 验证 → 环境合成 → 工具合并
```

👉 **详细使用说明请参考 [`env_synthesis/README_zh.md`](env_synthesis/README_zh.md)**

---

## 📜 License

本项目采用 [Apache 2.0 License](assets/LICENSE.txt)。

---

## 📎 Citation

```bibtex
@misc{astra2026,
  title={ASTRA：Automated Synthesis of agentic Trajectories and Reinforcement Arenas},
  author={Beike Language and Intelligence (BLI)},
  year={2026},
}
```

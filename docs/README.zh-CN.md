# AgentKit

[English README](../README.md)

一个基于 LLM 的通用 Agent 框架，支持 workspace 隔离、统一 LLM 抽象、工具调用循环、CLI 与 Python SDK。

## 当前能力

- workspace 强隔离：所有读写通过 `WorkspaceFS`
- 统一 LLM 抽象：`ConversationItem` / `ConversationState` / `UnifiedLLMRequest` / `UnifiedLLMResponse`
- Provider 支持（同步、非流式、文本）
  - OpenAI (`responses` / `chat_completions`)
  - Anthropic (`messages`)
  - Gemini (`generateContent`)
  - Qwen（OpenAI-compatible `chat_completions`）
  - vLLM（OpenAI-compatible `chat_completions`）
- 工具系统：注册式工具机制，工具模块放在 `src/agentkit/tools/library/`
- Agent loop：模型推理与工具执行闭环，受 step/time budget 约束
- runlog：每次任务写入 `workspace/logs/run_<run_id>.jsonl`

## 状态

- 当前仓库包含针对 Agent loop、CLI、工具系统、runlog 以及 OpenAI / Anthropic / Gemini / Qwen / vLLM provider 适配层的单元测试
- 尚未提供针对真实上游 API 的集成 smoke test，因此正式发布前仍建议用目标模型做一次端到端验证

## 文档

详细使用说明和完整文档见 `docs/agentkit/`。

## 从源码安装

```bash
uv sync
uv run agentkit --help
```

## 从 PyPI 安装

```bash
pip install base-agentkit
agentkit --help
```

安装后的导入路径和 CLI 名称保持不变：

```python
from agentkit import create_agent
```

## 配置示例

### vLLM

```yaml
workspace:
  root: "./vllm_workspace"

provider:
  kind: "vllm"
  model: "glm-5"
  openai_api_variant: "chat_completions"
  conversation_mode: "auto"
  base_url: "http://localhost:8000/v1"
  api_key: "empty"
  temperature: 0.8
  timeout_s: 600
  retries: 2
  enable_thinking: true

agent:
  system_prompt: "You are a helpful agent. Use tools when needed."
  budget:
    max_steps: 200
    time_budget_s: 1800
    max_input_chars: 180000

tools:
  allowed:
    - "view"
    - "create_file"
    - "str_replace"
    - "word_count"

runlog:
  enabled: true
  redact: true
  max_text_chars: 20000
```

## CLI 运行

```bash
export OPENAI_API_KEY="your-key"
uv run agentkit --config path/to/config.yaml run --task "列出当前 workspace 的文件"
```

## Python SDK

```python
from agentkit import create_agent

agent = create_agent("path/to/config.yaml")
report = agent.run("在 workspace 里新建 notes/todo.txt 并写入今天计划")
print(report.final_output)
```

## 项目结构

核心实现位于 `src/agentkit/`：

- `config/`: 配置结构与加载
- `workspace/`: 强隔离文件系统和目录布局
- `llm/`: 统一抽象、provider base/factory 与四平台 adapter
- `tools/`: 工具抽象、注册表与自动加载
- `agent/`: budget、report、runtime、Agent loop
- `runlog/`: 结构化事件、event sink 与 JSONL runlog
- `cli/`: 命令行入口

# Decision Memory MCP Server

> **“决策的本质，就是用过去的经验去预测未来，用未来的结果去修正经验。”**
> 
> **“记忆的本质，不是文件的堆砌，而是为未来的上下文窗口（Context Window）制造索引。LLM 只能激活它眼前的上下文，而双链和标签，就是在这个注意力的探照灯扫过来时，能为它连带拉出整张认知关系网络的那根绳索。查询本身就是在建立路径——每一次检索和融汇，都是在为认知突触连线；一次任务里没有被当前 link/tag 通路激活的内容，就是本次推理中的‘遗忘’。”**

---

## 🚀 极速安装与部署

### 1. 安装模块
在你的项目虚拟环境激活后，运行命令直接安装：
```bash
pip install git+https://github.com/crossagent/decision-memory.git
```

### 2. 配置启动规则
打开你的项目配置文件（如 `agents.md`），注册此 MCP 记忆服务：
```markdown
## MCP Servers

- **memory_mcp**:
  - command: python
  - args: ["-m", "mcp_server.server"]
  - env:
    - PYTHONPATH: "."
    - MEMORY_VAULT_PATH: "path/to/your/obsidian/vault" # 指向你的 Obsidian 记忆库根目录
```

---

## ⚠️ CRITICAL STEP / 核心必读步骤

> [!IMPORTANT]
> **安装完成后，请务必将本仓库根目录下的 `agents.md` 文件复制到你正在开发项目的根目录下（与你项目的 `.git` 或 `pyproject.toml` 同级）！**
> 
> 这一步至关重要，因为 `agents.md` 是向 AI Agent 声明外部记忆规则的**核心指令卡**。大模型启动时会自动扫描该文件，从而领会：
> 1.  如何使用 5 大子目录（Model, Simulation, Control, Perception, Learning）进行知识归纳。
> 2.  如何强制检索并把外部的长期记忆真正运转起来。

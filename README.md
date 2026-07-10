# Decision Memory MCP Server

> **“决策的本质，就是用过去的经验去预测未来，用未来的结果去修正经验。”**
> 
> **“记忆的本质，不是文件的堆砌，而是为未来的上下文窗口（Context Window）制造索引。LLM 只能激活它眼前的上下文，而双链和标签，就是在这个注意力的探照灯扫过来时，能为它连带拉出整张认知关系网络的那根绳索。主动阅读本身就是在建立路径——每一次 Read 和融汇，都是在为认知突触连线；一次任务里没有被当前关联通路激活的内容，就是本次推理中的‘遗忘’。”**

## 🧠 偏好记忆闭环

本服务把长期知识与注意力偏好严格分开：Markdown/Obsidian 保存知识节点，SQLite 保存实际发生的 Read 事件与可重建的关联权重。

```text
Write  = 创建记忆节点
Recall = 根据 Query、Note 激活值与当前已读节点形成快速直觉
Search = 绕过历史偏好进行完整、可复现的严谨研究
Read   = 记录真实兴趣，并影响未来 Recall
```

标准流程是：

1. `begin_episode`：记录当前 Query；Episode ID 只负责给同一条思考链的 Read 排序和分组。
2. `recall_notes`：只读取现成索引和偏好边，低成本获取少量直觉候选；或使用支持 `limit/offset` 分页的 `search_notes` 同步并严谨检索全库。
3. `read_note`：只有主动阅读全文才写入注意力事件。

Read 事务会同时追加原始事件，并物化每个 Note 的可衰减激活值与 `Note <-> Note` 共同激活关联。Recall 只计算当前 Query 的文本相关度、Note 的历史激活值，以及当前 Episode 已读节点与候选节点的历史共同激活；Episode 和 Query 都不会被伪装成长期语义实体。Search 从不读取或修改这些偏好。默认数据库位于 Vault 的 `.memory-mcp/memory.sqlite3`，可通过 `MEMORY_INDEX_PATH` 修改。

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

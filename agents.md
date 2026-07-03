# Antigravity CLI Agents & MCP Configuration

This file provides declarative routing, service definitions, and cognitive directory guidelines for the decision-memory environment.

## 1. Quick Start & MCP Server Configuration

To register this long-term memory server into your Antigravity environment, declare it under the `mcp_servers` section of your workspace configuration (e.g., `agents.md`):

```markdown
## MCP Servers

- **memory_mcp**:
  - command: python
  - args: ["-m", "mcp_server.server"]
  - env:
    - PYTHONPATH: "."
    - MEMORY_VAULT_PATH: "path/to/your/obsidian/vault" # 👈 Custom path to your memory directory
```

---

## 2. The 5-Module Memory Directory Schema (Cognitive Roles)

This memory vault enforces a cybernetic loop, forcing your Agent to categorize all long-term knowledge into 5 distinct subdirectories under your target `MEMORY_VAULT_PATH`:

### 📁 `model/` (World Model & Hard Constraints)
*   **Role**: Stores durable beliefs about the world's mechanisms (e.g., "Mean Reversion", "Credit Cycles") and strict personal constraints (e.g., max drawdown limit, financial goals).
*   **Cognitive Intent**: Serves as the "anchor" of the agent's prior probabilities and hard behavioral rules.

### 📁 `simulation/` (Forward Simulation & Probability Work)
*   **Role**: Staging ground for predictions, scenarios, backtest metrics, and probability calculations before execution.
*   **Cognitive Intent**: Forces the agent to document predictions *before* action to defeat hindsight bias (Hindsight Bias).

### 📁 `control/` (Action Governance & Decisions)
*   **Role**: Stores real-world actions, transaction choices, rebalancing plans, or explicit decisions of **inaction / waiting**.
*   **Cognitive Intent**: Acts as the steering wheel and brakes under the constraints of the world model.

### 📁 `perception/` (Facts & Sensory Observations)
*   **Role**: Raw sensor data containing filings, market prices, statements, or realized outcomes.
*   **Cognitive Intent**: Strictly records objective external facts. **No subjective attributions or trading authorization allowed.**

### 📁 `learning/` (Review, Reflection & Evolution)
*   **Role**: Validates predictions (Simulation) and plans (Control) against actual outcomes (Perception) to score win rates and generate promotions for the world model.
*   **Cognitive Intent**: Binds the cybernetic feedback loop together to allow cognitive evolution.

---

## 3. ECS (Entity-Component-System) Structure for World Models

Stable world models inside `agent-memory/model/` should follow the ECS taxonomy:
1.  **Entity**: Specific subject (e.g., `GOOG.md`, `Tencent.md`, `Federal_Reserve.md`).
2.  **Component**: Properties/attributes attached to entities (e.g., PE ratio, Debt ratio).
3.  **System**: Durable physical/financial laws governing how components change over time or transmit signals between entities.

---

## 4. The Core Philosophy of Context Indexing

> **“Memory is not a dump of files, but an index for future Context Windows. LLMs can only act upon what is immediately within their context. Tags and wikilinks exist to drag the entire relevant semantic network into the LLM's attention spotlight when a specific cue is triggered. Querying itself is path-building — every search and fusion is wiring a cognitive synapse. What is not linked is effectively forgotten.”**
> 
> **“记忆的本质，不是文件的堆砌，而是为未来的上下文窗口（Context Window）制造索引。LLM 只能激活它眼前的上下文，而双链和标签，就是在这个注意力的探照灯扫过来时，能为它连带拉出整张认知关系网络的那根绳索。查询本身就是在建立路径——每一次检索和融汇，都是在为认知突触连线；一次任务里没有被当前 link/tag 通路激活的内容，就是本次推理中的‘遗忘’。”**

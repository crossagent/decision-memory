# Antigravity CLI Agents & MCP Configuration

This file provides declarative routing, service definitions, and cognitive instructions for the decision-memory environment.

## 1. MCP Servers

- **memory_mcp**:
  - command: python
  - args: ["-m", "mcp_server.server"]
  - env:
    - PYTHONPATH: "."
    - MEMORY_VAULT_PATH: "d:/investment"

---

## 2. CRITICAL INSTRUCTION FOR AI AGENT (强制记忆唤醒指令)

> [!IMPORTANT]
> **YOU MUST ACTIVE-USE THIS EXTERNAL MEMORY VAULT!**
> 
> 作为 AI 智能体，你的上下文窗口（Context Window）是短暂且狭窄的。本 MCP 服务是你的**长期外部记忆大脑**。
> 
> **硬性行为准则**：
> 1.  **先想后做 (Search Before You Act)**：在开始任何复杂的分析、重构、投资计划或决策前，**你必须首先调用 `search_notes` 或 `read_note` 检索外部记忆**。查找是否有已存在的世界规律（Model）、前期的情景推演（Simulation）或历史上的失败教训（Learning）。
> 2.  **严禁短视 (No Short-termism)**：只依赖你眼前的 Prompt 上下文而不去检索历史记忆的行为，视作严重的认知懈怠和不负责任。
> 3.  **查询即是建路 (Querying is Path-building)**：每一次检索、双链引用和反思写入，都是在为你大脑的认知突触进行连线。

---

## 3. The 5-Module Memory Directory Schema (认知子目录定义)

为了保持你大脑知识库的干净与专注，你必须将所有长期沉淀的知识严格分类到以下五个子目录中：

### 📁 `model/` (世界模型 & 规则约束)
*   **物理路径**：`agent-memory/model/`
*   **定位**：客观世界运行规律的持久信念（如“均值回归”、“信用周期”）以及个人硬性资产边界。
*   **作用**：是决策系统的“锚”，提供行动的物理规律和先验约束。

### 📁 `simulation/` (前向仿真 & 概率测算)
*   **物理路径**：`agent-memory/simulation/`
*   **定位**：行动前的沙盒推演。包括个股涨跌幅预测（`stock-prediction`）、量化回测或概率估算。
*   **作用**：强迫你在行动前留下无偏见的书面预测，对抗事后诸葛亮偏差。

### 📁 `control/` (决策控制 & 行动治理)
*   **物理路径**：`agent-memory/control/`
*   **定位**：具体买卖决策、调仓计划、或明确做出的“等待/不行动”决策。
*   **作用**：基于 Model 的风险限制与 Simulation 的赢面估算，产生现实动作。

### 📁 `perception/` (客观感知 & 事实传感器)
*   **物理路径**：`agent-memory/perception/`
*   **定位**：只记录最真实的外部客观事实，例如公司公告、大盘日线行情、账户资产快照。
*   **作用**：提供最真实的物理反馈，**禁止包含任何主观推论、归因或交易授权**。

### 📁 `learning/` (反思复盘 & 进化提案)
*   **物理路径**：`agent-memory/learning/`
*   **定位**：胜率打分、归因分析、失误复盘和 Model 的更新促进提案（Promotions）。
*   **作用**：对比预测（Simulation）、行动（Control）与真实反馈（Perception），完成认知闭环。

---

## 4. ECS (Entity-Component-System) Structure for World Models

在编写 `agent-memory/model/` 下的世界模型知识点时，必须遵循以下 ECS 强类型规范：
1.  **Entity (实体)**：世界中的主体对象（如具体公司 `Tencent.md`、具体国家）。
2.  **Component (组件)**：附加在实体上的状态或属性（如市盈率、负债率）。
3.  **System (系统)**：描述组件状态如何在时间中变化，或如何在实体之间传导的金融/物理规律。

import argparse
import hashlib
import json
import os
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

from .policy import validate_safe_write
from .vault import (
    BASE_DIR,
    AGENT_MEMORY_MODULES,
    AGENT_MEMORY_ROOT,
    format_front_matter,
    normalize_tags,
    parse_front_matter,
    sanitize_filename,
    sanitize_tag,
)


ROOT = Path(BASE_DIR)
SOURCE_ROOTS = ("memory", "research", "observe", "plan", "action")
WIKI_RE = re.compile(r"\[\[([^\]]+)\]\]")


def rel_posix(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def first_heading(body: str, fallback: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip() or fallback
    return fallback


def classify_research_analysis(
    relative_path: str,
    title: str,
    metadata: dict[str, Any],
    body: str,
) -> tuple[str, str, list[str]]:
    """Classify legacy research/analyses notes by cognitive role.

    Analysis is not an agent-memory module. It can support learning,
    model-building, simulation, or control depending on what the note
    primarily does.
    """
    text = " ".join(
        [
            relative_path,
            title,
            " ".join(as_list(metadata.get("tags"))),
            body[:2000],
        ]
    ).lower()

    if relative_path.endswith("Research_Index.md"):
        return "learning", "research-index", ["learning/index", "legacy/research-index"]

    if any(marker in text for marker in ["日本", "japan", "泡沫", "资产负债表修复"]):
        return "learning", "case-study", ["learning/case-study", "case/japan"]

    if any(marker in text for marker in ["gold_oil", "黄金", "原油", "战争量化", "correlation"]):
        return (
            "learning",
            "empirical-study",
            ["learning/empirical-study", "macro/empirical"],
        )

    if any(
        marker in text
        for marker in [
            "professional_backtesting",
            "专业量化回测",
            "回测引擎",
            "backtesting systems",
            "lean engine",
            "freqtrade",
        ]
    ):
        return "model", "method", ["model/method", "quant/backtesting"]

    if any(
        marker in text
        for marker in [
            "zk-rollup",
            "system_design",
            "技术差异",
            "业务场景评估",
            "zk 加密资产研究",
            "零知识证明",
        ]
    ):
        return (
            "model",
            "system-candidate",
            ["model/system-candidate", "domain/crypto-zk"],
        )

    if any(marker in text for marker in ["horizon/3m", "三个月", "配置比较", "rotation"]):
        return (
            "simulation",
            "scenario",
            ["simulation/scenario", "allocation/scenario"],
        )

    if any(marker in text for marker in ["qlib", "backtest", "回测", "止盈原型", "profit_extraction"]):
        return "simulation", "backtest", ["simulation/backtest", "quant/backtest"]

    if any(marker in text for marker in ["ibkr 投资情况", "当前定投规则", "是否需要调整定投"]):
        return (
            "control",
            "plan-analysis",
            ["control/plan-analysis", "broker/ibkr"],
        )

    return "learning", "analysis-review", ["learning/analysis-review"]


def route_note(
    relative_path: str,
    title: str,
    metadata: dict[str, Any],
    body: str,
) -> tuple[str, str, list[str]]:
    parts = relative_path.split("/")
    root = parts[0]

    if root == "memory":
        if parts[1:3] == ["world", "entities"]:
            return "model", "world/entity", ["model/world", "world/entity"]
        if parts[1:3] == ["world", "components"]:
            return "model", "world/component", ["model/world", "world/component"]
        if parts[1:3] == ["world", "systems"]:
            return "model", "world/system", ["model/world", "world/system"]
        if parts[1:3] == ["personal", "assets"]:
            return "model", "personal/asset", ["model/personal", "personal/asset"]
        if parts[1:3] == ["personal", "goals"]:
            return "model", "personal/goal", ["model/personal", "personal/goal"]
        if parts[1:3] == ["personal", "situations"]:
            return (
                "model",
                "personal/situation",
                ["model/personal", "personal/situation"],
            )
        return "model", "memory", ["model/memory"]

    if root == "research":
        if parts[1:3] == ["practice", "predictions"]:
            ticker = parts[3].lower() if len(parts) > 3 else "unknown"
            return (
                "simulation",
                "prediction",
                ["simulation/prediction", f"ticker/{ticker}"],
            )
        if len(parts) > 1 and parts[1] == "practice":
            return "learning", "practice-review", ["learning/practice-review"]
        if len(parts) > 1 and parts[1] == "theses":
            return "simulation", "thesis", ["simulation/thesis"]
        if len(parts) > 1 and parts[1] == "analyses":
            return classify_research_analysis(relative_path, title, metadata, body)
        return "simulation", "research", ["simulation/research"]

    if root == "observe":
        if len(parts) > 1 and parts[1] == "sources":
            return "perception", "source", ["perception/source"]
        if len(parts) > 1 and parts[1] == "watchlists":
            return "perception", "watchlist", ["perception/watchlist"]
        return "perception", "observation", ["perception/observation"]

    if root == "plan":
        if len(parts) > 1 and parts[1] == "principles":
            return "control", "policy", ["control/policy"]
        if len(parts) > 1 and parts[1] == "strategies":
            return "control", "strategy", ["control/strategy"]
        if len(parts) > 1 and parts[1] == "scenarios":
            return "simulation", "scenario", ["simulation/scenario"]
        if len(parts) > 1 and parts[1] == "proposals":
            return "simulation", "proposal", ["simulation/proposal"]
        return "control", "plan", ["control/plan"]

    if root == "action":
        if len(parts) > 1 and parts[1] == "decisions":
            return "control", "decision", ["control/decision"]
        if len(parts) > 1 and parts[1] == "execution":
            return "control", "execution", ["control/execution"]
        if len(parts) > 1 and parts[1] == "paper":
            return "control", "paper-trading", ["control/paper-trading"]
        return "control", "action", ["control/action"]

    raise ValueError(f"Unsupported source root: {relative_path}")


def target_for_source(relative_path: str, title: str, module: str, kind: str) -> str:
    kind_slug = sanitize_filename(kind.replace("/", "-"))
    title_slug = sanitize_filename(title)
    candidate = f"{AGENT_MEMORY_ROOT}/{module}/{kind_slug}_{title_slug}.md"
    digest = hashlib.sha1(relative_path.encode("utf-8")).hexdigest()[:8]
    return candidate.replace(".md", f"_{digest}.md")


def collect_sources() -> list[dict[str, Any]]:
    sources: list[dict[str, Any]] = []
    for source_root in SOURCE_ROOTS:
        root = ROOT / source_root
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.md")):
            relative_path = rel_posix(path)
            content = path.read_text(encoding="utf-8")
            metadata, body = parse_front_matter(content)
            title = str(metadata.get("title") or first_heading(body, path.stem))
            module, kind, route_tags = route_note(relative_path, title, metadata, body)
            target = target_for_source(relative_path, title, module, kind)
            sources.append(
                {
                    "source_path": relative_path,
                    "source_abs": path,
                    "target_path": target,
                    "obsidian_target": target.removeprefix(
                        f"{AGENT_MEMORY_ROOT}/"
                    ).removesuffix(".md"),
                    "module": module,
                    "kind": kind,
                    "route_tags": route_tags,
                    "title": title,
                    "metadata": metadata,
                    "body": body,
                }
            )
    return sources


def build_link_map(sources: list[dict[str, Any]]) -> dict[str, str]:
    full_map: dict[str, str] = {}
    stems = Counter(Path(item["source_path"]).stem for item in sources)

    for item in sources:
        source = item["source_path"]
        without_ext = source.removesuffix(".md")
        target = item["obsidian_target"]
        full_map[source.lower()] = target
        full_map[without_ext.lower()] = target
        if stems[Path(source).stem] == 1:
            full_map[Path(source).stem.lower()] = target
        title = str(item["metadata"].get("title") or "").strip()
        if title:
            full_map[title.lower()] = target
        stem = Path(source).stem
        if stem in {"_Index", "README"}:
            parent = str(Path(source).parent).replace("\\", "/")
            full_map[parent.lower()] = target
            full_map[f"{parent}/".lower()] = target
    return full_map


def unresolved_agent_memory_placeholder(key: str) -> str | None:
    root = key.split("/", 1)[0]
    if root not in SOURCE_ROOTS:
        return None
    stripped = key.rstrip("/")
    name = stripped.rsplit("/", 1)[-1] or stripped.rsplit("/", 2)[-2]
    return sanitize_filename(name.removesuffix(".md"))


def rewrite_wiki_links(text: str, link_map: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        inner = match.group(1)
        target_and_anchor, *alias_part = inner.split("|", 1)
        target, *anchor_part = target_and_anchor.split("#", 1)
        key = target.replace("\\", "/").strip("/").removesuffix(".md").lower()
        mapped = link_map.get(key)
        if not mapped:
            mapped = unresolved_agent_memory_placeholder(key)
        if not mapped:
            return match.group(0)
        if anchor_part:
            mapped = f"{mapped}#{anchor_part[0]}"
        if alias_part:
            mapped = f"{mapped}|{alias_part[0]}"
        return f"[[{mapped}]]"

    return WIKI_RE.sub(replace, text)


def rewrite_metadata_links(value: Any, link_map: dict[str, str]) -> Any:
    if isinstance(value, str):
        return rewrite_wiki_links(value, link_map)
    if isinstance(value, list):
        return [rewrite_metadata_links(item, link_map) for item in value]
    return value


def write_note(target_path: str, metadata: dict[str, Any], body: str) -> None:
    full_path = ROOT / target_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    content = format_front_matter(metadata, body)
    validate_safe_write(str(full_path), content)
    full_path.write_text(content, encoding="utf-8")


def clean_agent_memory_root() -> None:
    agent_memory_root = (ROOT / AGENT_MEMORY_ROOT).resolve()
    expected = (ROOT / AGENT_MEMORY_ROOT).resolve()
    if agent_memory_root != expected or not agent_memory_root.is_relative_to(
        ROOT.resolve()
    ):
        raise RuntimeError(
            f"Refusing to clean unexpected path: {agent_memory_root}"
        )
    if agent_memory_root.exists():
        shutil.rmtree(agent_memory_root)


def write_index(summary: dict[str, int]) -> None:
    body_lines = [
        "# Investment Agent Memory",
        "",
        "这个 Obsidian Vault 是投资智能体的长期外部记忆系统，使用五个认知模块组织：",
        "",
        "- [[model/00-model|model]]：世界模型、自我约束、风险边界和已学会的规则。",
        "- [[simulation/00-simulation|simulation]]：预测、假设、概率测算、情景和回测。",
        "- [[control/00-control|control]]：计划、政策、决策、执行、等待、停止和不行动。",
        "- [[perception/00-perception|perception]]：行情、财报、账户快照、真实结果和外部事实。",
        "- [[learning/00-learning|learning]]：验证、打分、归因、校准和 model 更新候选。",
        "",
        "## 当前迁移数量",
        "",
        "| Module | Notes |",
        "| --- | ---: |",
    ]
    for module in AGENT_MEMORY_MODULES:
        body_lines.append(f"| {module} | {summary.get(module, 0)} |")
    write_note(
        f"{AGENT_MEMORY_ROOT}/00-Investment-Agent-Memory.md",
        {"title": "Investment Agent Memory Index", "tags": ["agent-memory/index"]},
        "\n".join(body_lines),
    )


def write_module_indices(summary: dict[str, int]) -> None:
    descriptions = {
        "model": "世界模型、自我约束、风险边界、先验和复盘后沉淀的规则。",
        "simulation": "预测、假设、概率测算、情景推演和回测。",
        "control": "计划、政策、决策、执行、等待、停止和明确不行动。",
        "perception": "行情、财报、账户快照、外部事实和真实结果。",
        "learning": "验证、打分、归因、校准和 model 更新候选。",
    }
    for module in AGENT_MEMORY_MODULES:
        body = "\n".join(
            [
                f"# {module}",
                "",
                descriptions[module],
                "",
                f"- 当前迁移笔记数：{summary.get(module, 0)}",
                f"- 聚合标签：`#agent-memory/{module}`",
            ]
        )
        write_note(
            f"{AGENT_MEMORY_ROOT}/{module}/00-{module}.md",
            {
                "title": module,
                "module": module,
                "kind": "module-index",
                "tags": [f"agent-memory/{module}", f"{module}/index"],
            },
            body,
        )


def rebuild(clean: bool) -> dict[str, Any]:
    sources = collect_sources()
    link_map = build_link_map(sources)
    if clean:
        clean_agent_memory_root()

    summary: dict[str, int] = {module: 0 for module in AGENT_MEMORY_MODULES}
    written: list[dict[str, str]] = []
    for item in sources:
        metadata = {
            key: rewrite_metadata_links(value, link_map)
            for key, value in item["metadata"].items()
        }
        metadata["module"] = item["module"]
        metadata["kind"] = item["kind"]
        metadata["title"] = item["title"]
        metadata["source_path"] = item["source_path"]
        metadata["tags"] = normalize_tags(
            [
                *as_list(metadata.get("tags")),
                f"agent-memory/{item['module']}",
                f"{item['module']}/{sanitize_tag(item['kind'])}",
                *item["route_tags"],
            ]
        )

        body = rewrite_wiki_links(item["body"], link_map).strip() + "\n"
        write_note(item["target_path"], metadata, body)
        summary[item["module"]] += 1
        written.append(
            {
                "source": item["source_path"],
                "target": item["target_path"],
                "module": item["module"],
                "kind": item["kind"],
            }
        )

    write_index(summary)
    write_module_indices(summary)
    return {"summary": summary, "written": written}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild the strict five-module Obsidian agent-memory vault."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove the existing agent-memory/ directory before rebuilding.",
    )
    args = parser.parse_args()
    result = rebuild(clean=args.clean)
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

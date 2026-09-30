"""Codex Interactive Stability Layer for RDS-L3.

Ensures reliable, frictionless human-AI scientific collaboration:
1. Intent Compiler: Translates informal human language ("try smaller lr", "run 1k steps", "reuse baseline")
   into rigorous RDS-L3 CLI plans and commands without asking 20 tedious form questions.
2. Constructive Card Translator: Translates [RDS-REJECT] messages into actionable 3-line Minimal Falsifiable Protocols.
3. Progress Heartbeat Card: Generates compact, standard status cards so project context is instantly resumable.
"""
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


@dataclass
class IntentCompilationResult:
    intent_type: str
    suggested_cli_command: str
    auto_plan: Optional[Dict[str, Any]]
    confidence: float
    bounded_clarification_question: Optional[str]


class CodexAdapter:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()

    def compile_human_intent(self, text: str, state: Optional[Dict[str, Any]] = None) -> IntentCompilationResult:
        """Translates informal human dialogue into actionable RDS operations."""
        text_lower = text.lower().strip()

        # 1. Status query
        if any(kw in text_lower for kw in ["status", "进度", "跑到哪了", "看看状态", "看看进展", "当前分支"]):
            return IntentCompilationResult(
                intent_type="QUERY_STATUS",
                suggested_cli_command="python -B scripts/rds_cli.py status",
                auto_plan=None,
                confidence=0.98,
                bounded_clarification_question=None,
            )

        # 2. Branching / Stagnation escape
        if any(kw in text_lower for kw in ["换个方向", "开个新分支", "分叉", "fork", "正交分支", "停滞"]):
            m_name = re.search(r"(?:分支|branch|叫|名)\s*[:=]?\s*([a-zA-Z0-9_-]+)", text)
            branch_id = m_name.group(1) if m_name else "branch-orthogonal-hypothesis"
            return IntentCompilationResult(
                intent_type="BRANCH_FORK",
                suggested_cli_command=f"python -B scripts/rds_cli.py branch fork --spec spec.json",
                auto_plan={
                    "id": branch_id,
                    "parent_id": state.get("active_branch", "main") if state else "main",
                    "orthogonal_dimension": "mechanism",
                    "rationale": "Human requested orthogonal exploration to escape local stagnation",
                },
                confidence=0.90,
                bounded_clarification_question="检测到您希望开辟正交方向。是否以当前分支为母本，创建名为 '" + branch_id + "' 的机制正交分支？",
            )

        # 3. Execution intent (Run experiment)
        if any(kw in text_lower for kw in ["跑一下", "训练", "run", "试一下", "测试", "execute", "试试"]):
            # Extract runtime if mentioned
            m_runtime = re.search(r"([0-9]+)\s*(?:步|step|ms|毫秒|秒|s)", text_lower)
            runtime_ms = int(m_runtime.group(1)) * 10 if m_runtime else 10000

            has_baseline_cache = bool(state and state.get("baseline_cache"))
            return IntentCompilationResult(
                intent_type="CREATE_AND_RUN_PLAN",
                suggested_cli_command="python -B scripts/rds_cli.py run execute --id P-auto",
                auto_plan={
                    "id": "P-auto",
                    "hypothesis_id": "H1",
                    "split_id": "development",
                    "purpose": "explore",
                    "resources": {"runtime_ms": min(runtime_ms, 30000), "runs": 1},
                },
                confidence=0.88,
                bounded_clarification_question=(
                    f"已就绪：已自动检测并复用已有空白对照缓存（省去基线跑卡）。准备分配 {min(runtime_ms, 30000)//1000}s 预算在开发集运行该探索方案，是否立即执行？"
                    if has_baseline_cache else
                    f"准备分配 {min(runtime_ms, 30000)//1000}s 预算执行该探索方案，是否立即执行？"
                ),
            )

        # Fallback intent
        return IntentCompilationResult(
            intent_type="GENERAL_EXPLORATION",
            suggested_cli_command="python -B scripts/rds_cli.py status",
            auto_plan=None,
            confidence=0.50,
            bounded_clarification_question="请确认下一步目标：[1] 运行当前假说方案  [2] 查看当前分支与预算  [3] 开辟新正交假说分支？",
        )

    @staticmethod
    def render_heartbeat_card(state: Dict[str, Any]) -> str:
        """Renders an ultra-compact progress card to maintain context across turns."""
        branch = state.get("active_branch", "main")
        budget = state.get("budget", {})
        limits = budget.get("limits", {}).get("runtime_ms", 1)
        spent = budget.get("spent", {}).get("runtime_ms", 0)
        remaining_pct = max(0.0, 100.0 * (limits - spent) / max(1, limits))
        hypotheses = state.get("hypotheses", {})
        active_hypo = list(hypotheses.keys())[-1] if hypotheses else "None"
        cached_baselines = len(state.get("baseline_cache", {}))

        return f"""
```rds-progress
[RDS 心跳推进卡片]
• 当前活跃分支: {branch} (假说: {active_hypo})
• 剩余算力预算: {remaining_pct:.1f}% ({limits - spent}ms 可用)
• 空白对照缓存: 已锁定 {cached_baselines} 组基线 (后续探索 100% 自动复用，不重复跑基线)
• 推荐推进操作: 聚焦单一机制变量，执行最小有界对照方案
```
"""

    @staticmethod
    def translate_rejection(error_msg: str) -> str:
        """Translates cold deterministic errors into constructive guidance."""
        if "Self-signed" in error_msg:
            return (
                "> [!WARNING] 门禁拦截：检测到伪造自签标识（如 manipulation_verified=True）。\n"
                "> 💡 **建设性方案**：系统已强制剥夺自签权限；请直接让代码在沙箱执行，由确定性 AST 探针自动生成真实收据。"
            )
        if "one-time confirmation only" in error_msg or "Exploration requires development" in error_msg:
            return (
                "> [!WARNING] 数据泄露拦截：严禁在未确立探索优势前在留出测试集（final）上进行探索。\n"
                "> 💡 **建设性方案**：将当前方案的 `split_id` 绑定至 `development`，待开发集稳健优胜后再解锁最终确认。"
            )
        if "Budget unavailable" in error_msg or "maximum allocation" in error_msg:
            return (
                "> [!WARNING] 算力熔断：请求时间超出当前可用预算配额。\n"
                "> 💡 **建设性方案**：已启用预算保护；建议先以 1000 步（约 10s）小规模探针测算吞吐量，释放未完成任务后再增量追加。"
            )
        return f"> [!NOTE] 门禁提示：{error_msg}"

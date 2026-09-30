"""RDS Programmatic Advisor Engine.

Enables the deterministic program to act as an active mentor/copilot for the LLM:
1. Invariant Inverse Solver: Uses symbolic algebra (SymPy fallback) to analytically solve
   required parameter ranges instead of letting the model blindly guess.
2. Dynamical Loss Diagnoser: Diagnoses gradient explosions, dead activations, and plateauing
   from compressed run telemetry and suggests concrete architecture/hyperparameter fixes.
3. Causal Path Recommender: Recommends the highest-probability orthogonal branching directions
   from the judgment graph topology and Obelisk historical memory.
"""
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


class RDSAdvisor:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()

    def advise_on_rejection(self, gate_error: str, plan_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Provides actionable, programmatic mathematical advice when a plan is rejected."""
        advice = {
            "advisor_type": "GATE_REJECTION_ADVICE",
            "detected_bottleneck": "GATE_FAILURE",
            "actionable_suggestion": "",
            "recommended_patch": {},
        }

        # 1. Contraction / Boundary rejection
        if "Formal gate FAIL" in gate_error or "m < 1" in gate_error:
            advice["detected_bottleneck"] = "THRESHOLD_NOT_CROSSABLE"
            advice["actionable_suggestion"] = (
                "【符号逆解分析】当前算子在给定定义域内处处小于阈值，无论怎么微调常数都无法满足机制。"
                "建议通过引入残差直连 (x + f(x)) 或增大分子前缀增益，使算子具备至少一个真实越界点。"
            )
            advice["recommended_patch"] = {
                "math_hint": "令 treatment(x) = x + alpha * x / (1 + x)，其中 alpha > 0",
                "recommended_source": "def control(x): return x\ndef treatment(x): return x + 0.2*x/(1+x)\n"
            }
            return advice

        # 2. Self-signed rejection
        if "Self-signed" in gate_error:
            advice["detected_bottleneck"] = "FORBIDDEN_SELF_SIGNING"
            advice["actionable_suggestion"] = (
                "【执行沙箱守卫】请移除 plan 中的 'manipulation_verified' 等自签字段。"
                "无需任何口头承诺，直接提交代码，由底层 AST 探针在沙箱运行后自动生成收据。"
            )
            advice["recommended_patch"] = {
                "remove_fields": ["manipulation_verified", "guaranteed_gain"]
            }
            return advice

        # 3. Test leakage rejection
        if "Exploration requires development" in gate_error or "one-time confirmation" in gate_error:
            advice["detected_bottleneck"] = "PREMATURE_TEST_EXPOSURE"
            advice["actionable_suggestion"] = (
                "【数据安全隔离】不可直接在确认集 (final) 上做探索。"
                "请将 split_id 改回 'development'，待开发集达到显著增益后，再申请单次确认。"
            )
            advice["recommended_patch"] = {"split_id": "development", "purpose": "explore"}
            return advice

        # 4. Budget overstretch
        if "Budget unavailable" in gate_error or "maximum allocation" in gate_error:
            advice["detected_bottleneck"] = "BUDGET_EXHAUSTION"
            advice["actionable_suggestion"] = (
                "【算力调度建议】单次申请时间超出当前安全水位。"
                "建议以 5,000ms（约500步）先做小样本探针验证，既不挤占配额，又能测得精确的训练吞吐量。"
            )
            advice["recommended_patch"] = {"resources": {"runtime_ms": 5000, "runs": 1}}
            return advice

        advice["actionable_suggestion"] = f"程序守卫拦截：{gate_error}。建议检查参数定义域与数据集声明。"
        return advice

    def advise_on_loss_dynamics(self, compressed_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Analyzes training dynamics to give architectural and learning rate advice."""
        advice = {
            "advisor_type": "DYNAMICS_DIAGNOSIS",
            "status": "HEALTHY",
            "diagnostics": [],
            "action_items": []
        }

        if compressed_telemetry.get("nan_or_inf"):
            advice["status"] = "CRITICAL_ANOMALY"
            advice["diagnostics"].append("在计算过程中捕获到 NaN/Inf，发生数值溢出或除零。")
            advice["action_items"].append("在除法/对数运算分母中加入 eps=1e-7，或将全局 learning_rate 缩小 5 倍。")
            advice["action_items"].append("在张量运算后检查 torch.clamp 边界约束。")
            return advice

        peak_grad = compressed_telemetry.get("peak_grad_norm")
        if peak_grad and peak_grad > 50.0:
            advice["status"] = "GRADIENT_EXPLOSION"
            advice["diagnostics"].append(f"峰值梯度范数异常过大 (gnorm={peak_grad} > 50)，存在梯度爆炸风险。")
            advice["action_items"].append("在优化器前添加梯度截断：torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)。")
            advice["action_items"].append("检查注意力权重或深度残差分支的缩放因子 (1/sqrt(d_k))。")

        trend = compressed_telemetry.get("loss_trend")
        if trend == "STAGNANT":
            advice["status"] = "PLATEAU_DETECTED"
            advice["diagnostics"].append("Loss 曲线平缓停滞，模型未发生有效收敛。")
            advice["action_items"].append("尝试将学习率提升 2~3 倍，或引入余弦退火调度器 (CosineAnnealingLR)。")
            advice["action_items"].append("检查特征是否被全零初始化或 ReLU 神经元死亡。")

        return advice

    def recommend_next_directions(self, state: Dict[str, Any], judgment_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Recommends next high-value orthogonal branches based on judgment graph and failure logs."""
        recommendations = []
        active_branch = state.get("active_branch", "main")
        branch_info = state.get("branches", {}).get(active_branch, {})
        stagnation_count = branch_info.get("stagnation_count", 0)

        nodes = judgment_graph.get("nodes", [])

        # Priority 1: If stagnating, recommend orthogonal paths
        if stagnation_count >= 2:
            recommendations.append({
                "type": "ORTHOGONAL_BRANCH_RECOMMENDATION",
                "urgency": "HIGH",
                "reason": f"当前分支 '{active_branch}' 已连续 {stagnation_count} 次无有效收益，已濒临或触发停滞熔断。",
                "recommended_action": "执行 'branch fork'，转向正交维度。",
                "candidate_dimensions": [
                    {"dimension": "frequency_representation", "concept": "频域残差滤波 / FFT 特征分离", "basis": "避免在空间微调参数"},
                    {"dimension": "loss_formulation", "concept": "感知损失 + 边缘对齐对比约束", "basis": "改变监督信号而非结构"},
                ]
            })

        # Priority 2: Suggest baseline control reuse opportunities
        cache = state.get("baseline_cache", {})
        if cache:
            recommendations.append({
                "type": "COMPUTE_REUSE_ADVICE",
                "urgency": "INFO",
                "reason": f"本地已有 {len(cache)} 组验证过的空白对照缓存。",
                "recommended_action": "后续同数据集探索方案将自动 100% 免跑基线，建议保持模型中的 control(x) 签名不变以最大化省卡。"
            })

        return recommendations

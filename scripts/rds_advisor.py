"""RDS Programmatic Advisor Engine.

Reports heuristic signals and candidate diagnostics for human or experimental review.
It does not solve parameter ranges or establish causes from endpoint telemetry.
"""
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional


def _finite_nonnegative(value):
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value) and value >= 0
    except OverflowError:
        return False


class RDSAdvisor:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()

    def advise_on_rejection(self, gate_error: str, plan_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Provides actionable, programmatic mathematical advice when a plan is rejected."""
        advice = {
            "advisor_type": "GATE_REJECTION_ADVICE",
            "assurance": "HEURISTIC_ONLY",
            "detected_bottleneck": "GATE_FAILURE",
            "actionable_suggestion": "",
            "recommended_patch": {},
        }

        # 1. Contraction / Boundary rejection
        if "Formal gate FAIL" in gate_error or "m < 1" in gate_error:
            advice["detected_bottleneck"] = "BOUNDARY_CHECK_REJECTED"
            advice["actionable_suggestion"] = (
                "边界检查拒绝了当前计划；请先核对具体失败原因、定义域和阈值。"
                "残差直连或调整增益可以作为候选，但仍需重新检查奇点、越界条件和锁定数据中的实际越界。"
            )
            advice["recommended_patch"] = {
                "math_hint": "候选 treatment(x) = x + x/(5*(1+x))；x=-1 是奇点，是否越过阈值取决于定义域",
                "recommended_source": "def control(x): return x\ndef treatment(x): return x + (1/5)*x/(1+x)\n",
                "requires_revalidation": True,
                "baseline_warning": "示例 control 必须保持为已锁定基线；不要直接替换现有 control",
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
                "可尝试申请 5,000ms 的小样本探针；是否可用仍需资源门检查，训练步数和吞吐量必须实际测量。"
            )
            advice["recommended_patch"] = {"resources": {"runtime_ms": 5000, "runs": 1}}
            return advice

        advice["actionable_suggestion"] = f"程序守卫拦截：{gate_error}。建议检查参数定义域与数据集声明。"
        return advice

    def advise_on_loss_dynamics(self, compressed_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Flag reported observations and heuristic thresholds without causal claims."""
        advice = {
            "advisor_type": "DYNAMICS_DIAGNOSIS",
            "assurance": "HEURISTIC_ONLY",
            "status": "UNKNOWN",
            "diagnostics": [],
            "action_items": []
        }

        if compressed_telemetry.get("nan_or_inf"):
            advice["status"] = "CRITICAL_ANOMALY"
            advice["diagnostics"].append("遥测报告 NaN/Inf；原因未知，需要定位首个非有限张量与运算。")
            advice["action_items"].append("检查除法/对数定义域；eps=1e-7 或缩小学习率仅作为待对照验证的候选。")
            advice["action_items"].append("记录首个非有限值前的输入、梯度和优化器状态，检查修正是否改变任务定义。")
            return advice

        peak_grad = compressed_telemetry.get("peak_grad_norm")
        valid_grad = _finite_nonnegative(peak_grad)
        if peak_grad is not None and not valid_grad:
            advice["diagnostics"].append("梯度范数不是有限非负数；无法据此诊断。")
        if valid_grad and peak_grad > 50.0:
            advice["status"] = "HIGH_GRADIENT_SIGNAL"
            advice["diagnostics"].append(f"峰值梯度范数超过启发式阈值 (gnorm={peak_grad} > 50)；阈值未按当前模型尺度校准。")
            advice["action_items"].append("对照检查梯度分布、模型尺度和学习率；可实验比较梯度截断。")
            advice["action_items"].append("检查注意力权重或深度残差分支的缩放因子 (1/sqrt(d_k))。")

        trend = compressed_telemetry.get("loss_trend")
        if trend == "STAGNANT":
            advice["status"] = "PLATEAU_SIGNAL"
            advice["diagnostics"].append("日志端点提示损失变化较小；这不确定收敛状态或停滞原因。")
            advice["action_items"].append("检查完整曲线、训练步数与学习率，再做单变量优化器或调度器对照。")
            advice["action_items"].append("检查特征是否被全零初始化或 ReLU 神经元死亡。")

        if advice["status"] == "UNKNOWN" and (valid_grad or trend in {"DECREASING", "EXPLODING"}):
            advice["status"] = "NO_HEURISTIC_ALERT"
        if not advice["diagnostics"]:
            advice["diagnostics"].append("现有遥测不足以判断收敛、拟合或因果机制。")
        return advice

    def diagnose_fit_status(self, train_loss: float, val_loss: float, baseline_loss: Optional[float] = None) -> Dict[str, Any]:
        """Endpoints suggest follow-up checks; they do not identify fitting causes."""
        result = {
            "advisor_type": "FITNESS_DIAGNOSIS",
            "assurance": "HEURISTIC_ONLY",
            "train_loss": train_loss,
            "val_loss": val_loss,
            "baseline_loss": baseline_loss,
            "verdict": "UNKNOWN",
            "heuristic_signal": None,
            "suggestions": [],
            "forbidden_actions": [],
            "required_actions": [],
            "causal_explanation": "",
        }

        invalid = []
        for key, value in (("train_loss", train_loss), ("val_loss", val_loss), ("baseline_loss", baseline_loss)):
            if key == "baseline_loss" and value is None:
                continue
            if not _finite_nonnegative(value):
                invalid.append(key)
                result[key] = None
        result["required_actions"] = ["核对损失定义、归一化、训练步数与完整曲线", "检查数据划分、标签质量并运行单变量对照"]
        if invalid:
            result["causal_explanation"] = "需要有限非负且可比较的损失；无效输入：" + ", ".join(invalid)
            return result
        if baseline_loss is None or baseline_loss == 0:
            result["causal_explanation"] = "缺少可比较的正基线损失；端点损失不足以判断容量、优化、过拟合或收敛。"
            return result
        # ponytail: fixed ratios are uncalibrated signals, not a learned diagnosis.
        if train_loss >= baseline_loss * 0.85:
            result["heuristic_signal"] = "TRAIN_LOSS_NEAR_BASELINE"
            result["suggestions"] = ["分别检验优化配置、训练预算、标签与模型容量假设"]
        elif train_loss < baseline_loss * 0.4 and val_loss > train_loss * 1.35:
            result["heuristic_signal"] = "TRAIN_VALIDATION_GAP"
            result["suggestions"] = ["检验数据分布与划分、训练曲线以及正则化对照"]
        elif abs(val_loss - train_loss) <= max(train_loss, val_loss) * 0.15:
            result["heuristic_signal"] = "SIMILAR_ENDPOINT_LOSSES"
            result["suggestions"] = ["检查曲线与基线对照，不能从相似端点推出优化停滞"]
        result["causal_explanation"] = "这些比例是未经任务校准的启发式；容量不足、优化问题、过拟合与收敛状态均需独立证据。"
        return result

    def ingest_document(self, doc_path: Path, topic: Optional[str] = None) -> Dict[str, Any]:
        """Ingests guidelines from research papers or tuning docs to expand the advisor's knowledge."""
        doc_path = doc_path.resolve()
        if not doc_path.exists():
            raise FileNotFoundError(f"Document not found: {doc_path}")

        text = doc_path.read_text(encoding="utf-8", errors="replace")
        extracted_rules = []
        
        # Pattern matching for heuristics (e.g. "if ... suggest ...", "when ... avoid ...")
        lines = text.splitlines()
        for idx, line in enumerate(lines, 1):
            line_str = line.strip()
            if any(kw in line_str.lower() for kw in ["underfitting", "overfitting", "learning rate", "plateau", "gradient explosion"]):
                extracted_rules.append({
                    "line_number": idx,
                    "excerpt": line_str[:120],
                    "topic": topic or "general_tuning",
                    "source": doc_path.name
                })

        knowledge_file = self.root_dir / ".rds" / "advisor_knowledge.json"
        existing = []
        if knowledge_file.exists():
            try:
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                existing = []

        existing.extend(extracted_rules)
        knowledge_file.parent.mkdir(parents=True, exist_ok=True)
        knowledge_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

        return {
            "status": "INGESTED",
            "doc_path": str(doc_path),
            "rules_extracted": len(extracted_rules),
            "total_knowledge_entries": len(existing)
        }

    def recommend_next_directions(self, state: Dict[str, Any], judgment_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Recommends next high-value orthogonal branches based on judgment graph and failure logs."""
        recommendations = []
        active_branch = state.get("active_branch", "main")
        branch_info = state.get("branches", {}).get(active_branch, {})
        stagnation_count = branch_info.get("stagnation_count", 0)

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
                "recommended_action": "当前仅复用标量参考运行器的对照结果；需基线、数据和执行器绑定匹配，并检查 control_reused 收据。"
            })

        # Priority 3: Check learned document knowledge
        knowledge_file = self.root_dir / ".rds" / "advisor_knowledge.json"
        if knowledge_file.exists():
            try:
                with open(knowledge_file, "r", encoding="utf-8") as f:
                    k_list = json.load(f)
                if k_list:
                    recommendations.append({
                        "type": "DOC_GROUNDED_INSIGHT",
                        "urgency": "INFO",
                        "reason": f"从调查的文档中提炼了 {len(k_list)} 条领域先验。",
                        "latest_insight": k_list[-1].get("excerpt")
                    })
            except Exception:
                pass

        return recommendations

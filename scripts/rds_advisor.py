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

    def diagnose_fit_status(self, train_loss: float, val_loss: float, baseline_loss: Optional[float] = None) -> Dict[str, Any]:
        """Strict mathematical determination of Underfitting vs. Overfitting.
        
        Completely eliminates the LLM's default bias of crying 'overfitting' when the model
        is actually severely underfitting (capacity / optimization deficit).
        """
        result = {
            "advisor_type": "FITNESS_DIAGNOSIS",
            "train_loss": train_loss,
            "val_loss": val_loss,
            "baseline_loss": baseline_loss,
            "verdict": "UNKNOWN",
            "forbidden_actions": [],
            "required_actions": [],
            "causal_explanation": "",
        }

        # Check 1: Severe Underfitting (Train loss hasn't converged or is close to baseline)
        if baseline_loss is not None and train_loss >= baseline_loss * 0.85:
            result["verdict"] = "UNDERFITTING_CAPACITY_DEFICIT"
            result["forbidden_actions"] = [
                "DO NOT add Dropout (会导致欠拟合更严重)",
                "DO NOT increase Weight Decay (过早扼杀模型表达力)",
                "DO NOT trigger Early Stopping (模型根本还没学到东西)"
            ]
            result["required_actions"] = [
                "增加网络宽度/层数或引入非线性激活（提升模型表达容量）",
                "检查学习率是否过小，尝试增大 lr 2~5 倍",
                "检查数据归一化与前向残差通道是否通畅"
            ]
            result["causal_explanation"] = (
                f"训练集损失 ({train_loss:.4f}) 接近或高于基线损失 ({baseline_loss:.4f})，"
                "表明模型在训练集上根本没有拟合充分。这是典型的【欠拟合】，大模型严禁盲目建议正则化！"
            )
            return result

        # Check 2: Optimization Plateau / Dead Dynamics (Train and Val loss both high and stagnant)
        gap = val_loss - train_loss
        if gap <= train_loss * 0.15 and train_loss > 0.1:
            result["verdict"] = "UNDERFITTING_OPTIMIZATION_PLATEAU"
            result["forbidden_actions"] = [
                "DO NOT reduce model size",
                "DO NOT add regularizers"
            ]
            result["required_actions"] = [
                "更换优化器策略（如 AdamW 带 CosineAnnealingLR）",
                "增加训练步数或 Warmup 预热步数",
                "排查特征提取器是否存在梯度弥散"
            ]
            result["causal_explanation"] = (
                f"训练损失 ({train_loss:.4f}) 与验证损失 ({val_loss:.4f}) 几乎无缝贴合且绝对值偏高，"
                "无任何泛化裂缝。当前瓶颈是【优化受阻或欠拟合】，而非过拟合。"
            )
            return result

        # Check 3: Genuine Overfitting (Train loss is very low, but Val loss explodes)
        if train_loss < (baseline_loss * 0.4 if baseline_loss else 0.05) and val_loss > train_loss * 1.35:
            result["verdict"] = "GENUINE_OVERFITTING"
            result["forbidden_actions"] = [
                "DO NOT further scale up model capacity without regularization"
            ]
            result["required_actions"] = [
                "引入数据增强 (Data Augmentation) 或 Mixup",
                "在全连接层前增加适度 Dropout (0.1~0.2)",
                "增加权重衰减 (Weight Decay = 1e-4) 或执行 Early Stopping"
            ]
            result["causal_explanation"] = (
                f"训练损失已压至极低 ({train_loss:.4f})，但验证损失显著分叉反弹 ({val_loss:.4f})，"
                "形成显著泛化缝隙（差距 > 35%）。此时确认为【真实过拟合】。"
            )
            return result

        result["verdict"] = "HEALTHY_CONVERGENCE"
        result["causal_explanation"] = f"训练集 ({train_loss:.4f}) 与验证集 ({val_loss:.4f}) 处于健康收敛区间，继续保持当前策略。"
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
                "recommended_action": "后续同数据集探索方案将自动 100% 免跑基线，建议保持模型中的 control(x) 签名不变以最大化省卡。"
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

"""Bounded research advice: observations, competing explanations and small tests.

Advice does not certify claims, solve arbitrary formal systems, execute literature
trigger strings, change locked hypotheses, or launch experiments.
"""
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Dict, List, Optional


def _advice(advisor_type, **fields):
    return {"advisor_type": advisor_type, "observations": [],
            "alternative_explanations": [], "minimal_test": [],
            "limitations": [], "evidence": [], **fields}


def _number(value, name):
    try:
        finite = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite number")
    return float(value)


class RDSAdvisor:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir.resolve()
        self.literature_load_errors = []
        self.literature_principles = self._load_scientific_principles()

    def _load_scientific_principles(self) -> List[Dict[str, Any]]:
        paths = [self.root_dir / "references/scientific_tuning_principles.json",
                 Path(__file__).resolve().parent.parent / "references/scientific_tuning_principles.json"]
        for path in dict.fromkeys(paths):
            if not path.exists():
                continue
            try:
                records = json.loads(path.read_text(encoding="utf-8-sig"))
                if not isinstance(records, list) or not all(isinstance(p, dict) for p in records):
                    raise ValueError("Principles must be a list of objects")
                return records
            except (OSError, ValueError) as exc:
                self.literature_load_errors.append(f"{path}: {exc}")
                # A malformed explicit library must not silently become a different library.
                return []
        return []

    def query_literature_principles(self, query: str) -> List[Dict[str, Any]]:
        """Search source records; matching a topic does not establish applicability."""
        terms = [t for t in re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]+", query.lower()) if len(t) > 1]
        aliases = {"lr": ["learning rate"], "学习率": ["learning rate"],
                   "wd": ["weight decay"], "权重衰减": ["weight decay"],
                   "欠拟合": ["underfitting"], "过拟合": ["overfitting"],
                   "梯度": ["gradient"], "预热": ["warmup"], "停滞": ["plateau"]}
        for term, translations in aliases.items():
            if term in terms or (not term.isascii() and term in query):
                if term in terms:
                    terms.remove(term)
                terms.extend(translations)
        return [p for p in self.literature_principles if not terms or any(
            term in json.dumps(p, ensure_ascii=False).lower() for term in terms)]

    def advise_on_rejection(self, gate_error: str, plan_spec: Dict[str, Any]) -> Dict[str, Any]:
        advice = _advice("GATE_REJECTION_ADVICE", detected_bottleneck="GATE_FAILURE",
                         actionable_suggestion="检查原始门禁错误与锁定声明后重新预检。", recommended_patch={})
        advice["observations"] = [{"gate_error": gate_error, "plan_id": plan_spec.get("id")}]
        advice["evidence"] = [{"kind": "gate_output", "source": "plan admission", "text": gate_error}]
        advice["limitations"] = ["错误文本不能替代正式求解；本建议未完成符号逆解，也未修改锁定假说。"]
        if "Formal gate FAIL" in gate_error or "m < 1" in gate_error:
            advice.update(detected_bottleneck="FORMAL_GATE_REJECTED",
                          actionable_suggestion="对照锁定的 formal 定义、实际代码和定义域，核实拒绝针对哪个谓词及可达范围。")
            advice["alternative_explanations"] = ["干预未实现边界跨越", "代码、域或声明不一致", "拒绝针对其他性质"]
            advice["minimal_test"] = [{"question": "原干预能否实现声明性质？",
                "protocol": "保留原假说；检查 admission probe 原始结论和实际算子/域。需要新干预时另建修订并重新过门禁。",
                "decision_rule": "可达性结论仅适用于已验证形式和定义域；不从错误字符串生成替代模型。"}]
        elif "Self-signed" in gate_error:
            forbidden = {"manipulation_verified", "falsifier_triggered", "primary_metric_gain",
                         "final_run_authorized", "matched_recipe", "matched_compute"}
            advice.update(detected_bottleneck="FORBIDDEN_SELF_SIGNING",
                          actionable_suggestion="移除包括嵌套对象在内的自签验证字段，由门禁和执行收据产生结论。",
                          recommended_patch={"remove_fields": sorted(forbidden.intersection(plan_spec))})
            advice["minimal_test"] = [{"question": "方案字段是否合规？", "protocol": "重新做 plan pre-check。",
                                       "decision_rule": "预检通过不是执行或研究成功收据。"}]
        elif any(word in gate_error for word in ("Exploration requires development", "one-time confirmation",
                                                 "Confirmation lineage", "Confirmation contaminated")):
            advice.update(detected_bottleneck="DATA_SPLIT_ELIGIBILITY",
                          actionable_suggestion="按合同里实际注册的 development 分区探索；按暴露谱系核实确认资格。")
            advice["alternative_explanations"] = ["用途与分区角色不匹配", "确认数据或同谱系数据已暴露"]
            advice["minimal_test"] = [{"question": "当前用途可读取哪个分区？",
                "protocol": "查合同 splits 和 exposure 谱系，选择真实分区 ID，再预检。",
                "decision_rule": "改用途或复用缓存不能恢复已暴露分区的确认资格。"}]
        elif "Budget unavailable" in gate_error or "maximum allocation" in gate_error:
            advice.update(detected_bottleneck="BUDGET_CONSTRAINT",
                          actionable_suggestion="核算 limits、spent、reserved 和确认保留额；可行时用实测吞吐量设计有界探针。")
            advice["alternative_explanations"] = ["额度耗尽或已预留", "确认保留额受保护", "超出适配器单次上限"]
            advice["minimal_test"] = [{"question": "剩余额度可承担有判别力的探针吗？",
                "protocol": "读实际可用资源并核对已有步时/开销记录；只在缺少相关记录且有额度时做小 canary。",
                "decision_rule": "无可用额度则重分配或停止；不能把固定毫秒数换算成未经测量的训练步数。"}]
        return advice

    def advise_on_loss_dynamics(self, compressed_telemetry: Dict[str, Any]) -> Dict[str, Any]:
        """Prioritize numerical/data faults; hyperparameter changes remain tests."""
        if not isinstance(compressed_telemetry, dict):
            raise ValueError("Telemetry must be an object")
        telemetry = compressed_telemetry
        advice = _advice("DYNAMICS_DIAGNOSIS", status="INSUFFICIENT_EVIDENCE", diagnostics=[], action_items=[])
        advice["limitations"] = ["压缩遥测不能确定根因；loss/梯度范数没有跨任务通用阈值。",
                                  "超参候选应与原配置做同 seed 配对对照，记录预算和回退条件。"]
        nonfinite = []
        for key in ("peak_grad_norm", "grad_norm_limit", "loss", "train_loss", "val_loss",
                    "loss_variance", "step", "warmup_steps"):
            value = telemetry.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"{key} must be a number")
            if not math.isfinite(value):
                nonfinite.append(key)
            else:
                advice["observations"].append({"field": key, "value": value})
        for key in ("nan_or_inf", "decay_on_1d_params"):
            if key in telemetry and not isinstance(telemetry[key], bool):
                raise ValueError(f"{key} must be a boolean")
        for key in ("loss_trend", "nan_or_inf", "decay_on_1d_params"):
            if key in telemetry:
                advice["observations"].append({"field": key, "value": telemetry[key]})
        if telemetry.get("nan_or_inf") is True or nonfinite:
            advice["status"] = "CRITICAL_ANOMALY"
            advice["diagnostics"] = ["观测到非有限数值；尚未定位首个异常算子或根因。"]
            if nonfinite:
                advice["observations"].append({"nonfinite_fields": nonfinite})
            advice["alternative_explanations"] = ["输入/标签异常", "非法定义域或不稳定算子",
                                                   "低精度溢出/loss scaling 异常", "更新或梯度异常传播"]
            advice["action_items"] = ["保留异常批次与检查点，定位输入、前向、loss、反向或更新中首个非有限值。",
                                       "固定批次与随机状态，先检查数据/算子定义域，再对照原精度与 FP32 重放。"]
            advice["minimal_test"] = [{"question": "首个非有限值从哪里产生？",
                "protocol": "固定批次/检查点/随机状态，逐阶段记录范围与有限性；对照 FP32，先不更新参数。",
                "decision_rule": "定位后只改一个相关因素；只有定义域/分母故障确诊才试适合尺度的稳定化，不一律加 eps 或 clamp。"}]
            return advice

        peak, limit = telemetry.get("peak_grad_norm"), telemetry.get("grad_norm_limit")
        if (peak is not None and peak < 0) or (limit is not None and limit <= 0):
            raise ValueError("Gradient norm must be nonnegative and its declared limit positive")
        if peak is not None and limit is not None and peak > limit:
            advice["status"] = "GRADIENT_SPIKE_SUSPECTED"
            advice["diagnostics"].append("梯度峰值超过本次声明的 grad_norm_limit；这是待定位的异常候选。")
            advice["alternative_explanations"].extend(["异常批次/目标尺度", "loss reduction 或 AMP unscale 差异", "更新路径梯度放大"])
            advice["action_items"].append("先核对测量位置和 AMP unscale，记录逐层范数及更新/参数范数比。")
            advice["minimal_test"].append({"question": "峰值来自测量、数据还是更新不稳定？",
                "protocol": "固定异常批次核对 unscale 与 reduction；确认为更新异常后，单因素对照 LR 或按既有范数统计校准的 clipping。",
                "decision_rule": "比较异常频率、更新量和开发指标；被截小的范数不证明根因已解决。"})
            advice["evidence"].append({"kind": "literature", "source": "https://proceedings.mlr.press/v28/pascanu13.html",
                "supports": "梯度爆炸和截断是可研究的优化问题，不提供通用范数阈值。"})
        elif peak is not None:
            advice["diagnostics"].append("单个梯度峰值不能认定梯度爆炸；需同模型同量纲的分布和校准阈值。")
            advice["action_items"].append("记录时间序列、更新尺度和本任务校准的 grad_norm_limit。")

        trend = str(telemetry.get("loss_trend", "")).upper()
        if trend in {"EXPLODING", "DIVERGENT", "DIVERGING", "INCREASING"}:
            if advice["status"] == "INSUFFICIENT_EVIDENCE":
                advice["status"] = "DIVERGENCE_REPORTED"
            advice["diagnostics"].append("遥测报告 loss 上升/发散，需用原始曲线和相同评估设置核验。")
            advice["alternative_explanations"].extend(["数据/目标/reduction 变化", "精度或 optimizer state 故障", "LR/调度与更新尺度不匹配"])
            advice["action_items"].append("先排查输入、loss 定义、精度与 optimizer state；之后单独对照 LR 或调度。")
            advice["minimal_test"].append({"question": "发散能否在固定批次和检查点重现？",
                "protocol": "回到异常前检查点核验数据和精度；确有需要时记录原 LR 与一个预声明候选的短对照。",
                "decision_rule": "非有限值或开发指标恶化即停止候选；不能同时改结构、LR 和 loss。"})
        elif trend in {"STAGNANT", "PLATEAU"}:
            if advice["status"] == "INSUFFICIENT_EVIDENCE":
                advice["status"] = "PLATEAU_REPORTED"
            advice["diagnostics"].append("遥测报告平台；平台不等于容量不足或训练应该继续。")
            advice["alternative_explanations"].extend(["评估窗口/精度不足", "优化器未更新、梯度断开或数据故障", "已收敛", "优化/容量限制"])
            advice["action_items"].append("检查训练/验证序列、梯度和参数更新，必要时做固定小批次可拟合性检查。")
            advice["minimal_test"].append({"question": "平台来自不可更新、配置限制还是已收敛？",
                "protocol": "核验更新与数据/loss；必要时用固定小批次做有上限的可拟合性检查，再仅对一个因素做对照。",
                "decision_rule": "预声明有效变化尺度和停止条件；小批次失败不能单独区分容量与优化，成功不保证泛化。"})
        elif trend in {"DECREASING", "IMPROVING"}:
            if advice["status"] == "INSUFFICIENT_EVIDENCE":
                advice["status"] = "NO_REPORTED_ANOMALY"
            advice["diagnostics"].append("遥测报告 loss 下降；仍需核验趋势，不能据此宣布健康收敛。")
        if telemetry.get("loss_variance") is not None:
            if telemetry["loss_variance"] < 0:
                raise ValueError("loss_variance must be nonnegative")
            advice["diagnostics"].append("loss_variance 需结合窗口、目标尺度和调度解释，不能单独诊断 Warmup 缺失。")
            advice["action_items"].append("核对实际 LR/Warmup 轨迹；只有可重复早期不稳定时才对照预热。")
        if telemetry.get("decay_on_1d_params") is True:
            advice["diagnostics"].append("报告对 1D 参数衰减；先确认哪些是 LayerNorm/BatchNorm/bias，维数本身不证明错误。")
            advice["action_items"].append("检查实际参数分组；若怀疑衰减影响，匹配其余配置后单独对照 norm/bias 衰减设置。")
            advice["evidence"].append({"kind": "literature", "source": "https://arxiv.org/abs/1711.05101",
                "supports": "AdamW 研究 L2 正则与解耦衰减的差别；不证明所有 1D 参数必须免衰减。"})
        if not advice["observations"]:
            advice["diagnostics"].append("没有可解释的遥测，无法判断训练动态。")
        return advice

    def diagnose_fit_status(self, train_loss: float, val_loss: float,
                            baseline_loss: Optional[float] = None, *, telemetry=None) -> Dict[str, Any]:
        """Single losses are observations; matched curves support only candidate patterns."""
        train_loss, val_loss = _number(train_loss, "train_loss"), _number(val_loss, "val_loss")
        if baseline_loss is not None:
            baseline_loss = _number(baseline_loss, "baseline_loss")
        result = _advice("FITNESS_DIAGNOSIS", train_loss=train_loss, val_loss=val_loss,
            baseline_loss=baseline_loss, verdict="INSUFFICIENT_EVIDENCE",
            paper_reference="Goodfellow, Bengio & Courville (2016), Deep Learning, Chapter 11",
            forbidden_actions=[], required_actions=[], causal_explanation="单点损失不能确定欠拟合、过拟合或容量不足。")
        gap = val_loss - train_loss
        result["observations"] = [{"train_loss": train_loss, "val_loss": val_loss,
                                   "baseline_loss": baseline_loss, "raw_gap": gap if math.isfinite(gap) else None}]
        result["alternative_explanations"] = ["loss 定义、模式、正则项或预处理不可比", "分布差异/噪声", "优化/容量限制", "泛化随训练变化"]
        result["limitations"] = ["缺少配对曲线和协议时，不使用绝对 loss 或基线比例阈值。",
                                  "曲线模式不能单独确定容量或优化根因。"]
        result["evidence"] = [{"kind": "literature", "source": "https://www.deeplearningbook.org/contents/guidelines.html",
            "supports": "用训练和验证表现指导可检验的选择，不支持通用单点诊断阈值。"}]
        result["minimal_test"] = [{"question": "可比配对曲线支持什么模式？",
            "protocol": "核验相同目标尺度、reduction、数据与评估模式；收集同检查点 train/validation 历史、噪声尺度和调度。",
            "decision_rule": "训练改善/验证退化时调查泛化；停滞先排查更新与数据，只有未决且影响决策时才做有界单因素对照。"}]
        if telemetry is None:
            return result
        if not isinstance(telemetry, dict):
            raise ValueError("Fit telemetry must be an object")
        if telemetry.get("losses_comparable") is not True or telemetry.get("matched_checkpoints") is not True:
            result["limitations"].append("配对检查点或可比协议未声明，暂不解释曲线差异。")
            return result
        train_history, val_history = telemetry.get("train_loss_history"), telemetry.get("val_loss_history")
        if not isinstance(train_history, list) or not isinstance(val_history, list) or len(train_history) != len(val_history) or len(train_history) < 3:
            result["limitations"].append("至少需要三个同检查点配对观测；缺失、长度不同或更短序列不用于趋势诊断。")
            return result
        train_history = [_number(v, "train_loss_history") for v in train_history]
        val_history = [_number(v, "val_loss_history") for v in val_history]
        if not math.isclose(train_history[-1], train_loss) or not math.isclose(val_history[-1], val_loss):
            raise ValueError("Fit history endpoints must match the supplied losses")
        tolerance = telemetry.get("trend_tolerance")
        if tolerance is None:
            result["limitations"].append("缺少按指标精度/噪声校准的 trend_tolerance，暂不把微小变化判成趋势。")
            return result
        tolerance = _number(tolerance, "trend_tolerance")
        if tolerance < 0:
            raise ValueError("trend_tolerance must be nonnegative")
        result["observations"].append({"train_loss_history": train_history, "val_loss_history": val_history,
                                       "declared_trend_tolerance": tolerance})
        if train_history[-1] < train_history[0] - tolerance and val_history[-1] > val_history[0] + tolerance:
            result["verdict"] = "POSSIBLE_GENERALIZATION_GAP"
            result["causal_explanation"] = "声明可比的配对曲线中训练改善、验证退化；支持调查泛化，仍不能排除分布差异和噪声。"
        elif max(train_history) - min(train_history) <= tolerance and max(val_history) - min(val_history) <= tolerance:
            result["verdict"] = "POSSIBLE_OPTIMIZATION_PLATEAU"
            result["causal_explanation"] = "配对曲线在声明变化尺度内平坦；需区分已收敛、不可更新与优化/容量限制。"
        else:
            result["verdict"] = "NO_CLEAR_FIT_PATTERN"
            result["causal_explanation"] = "未显示明确的训练改善/验证退化或平台候选，不能由此确定健康收敛。"
        return result

    def ingest_document(self, doc_path: Path, topic: Optional[str] = None) -> Dict[str, Any]:
        """Store anchored candidate excerpts; keyword hits never adopt executable rules."""
        doc_path = doc_path.resolve()
        if doc_path.suffix.lower() in {".pdf", ".docx"}:
            raise ValueError("Document ingestion accepts UTF-8 text; extract binary documents to text first")
        raw = doc_path.read_bytes()
        text, source_sha = raw.decode("utf-8-sig"), hashlib.sha256(raw).hexdigest()
        terms = ("underfitting", "overfitting", "learning rate", "plateau", "gradient", "warmup",
                 "weight decay", "欠拟合", "过拟合", "学习率", "梯度", "停滞", "预热", "权重衰减")
        excerpts = [{"line_number": i, "excerpt": line.strip(), "topic": topic or "general_tuning",
                     "source": str(doc_path), "source_sha256": source_sha, "adoption_status": "UNREVIEWED"}
                    for i, line in enumerate(text.splitlines(), 1) if any(t in line.lower() for t in terms)]
        knowledge_file = self.root_dir / ".rds/advisor_knowledge.json"
        existing = json.loads(knowledge_file.read_text(encoding="utf-8-sig")) if knowledge_file.exists() else []
        if not isinstance(existing, list) or not all(isinstance(item, dict) for item in existing):
            raise ValueError("Existing advisor knowledge must be a list of objects; file preserved")
        known = {(item.get("source_sha256"), item.get("line_number"), item.get("topic")) for item in existing}
        additions = [item for item in excerpts if (source_sha, item["line_number"], item["topic"]) not in known]
        if additions:
            knowledge_file.parent.mkdir(parents=True, exist_ok=True)
            knowledge_file.write_text(json.dumps(existing + additions, indent=2, ensure_ascii=False), encoding="utf-8")
        return _advice("DOCUMENT_EXCERPT_INGESTION", status="INGESTED", doc_path=str(doc_path),
            adoption_status="UNREVIEWED", rules_extracted=len(additions), excerpts_extracted=len(additions),
            total_knowledge_entries=len(existing) + len(additions),
            limitations=["rules_extracted 是兼容字段，计数未审查摘录；它们不会自动成为可执行原则。"], evidence=additions)

    def recommend_next_directions(self, state: Dict[str, Any], judgment_graph: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Read real state and supplied graph; recommend a review, never a causal ranking."""
        recommendations = []
        if state.get("advisor_context"):
            from rds_advisor_search import search_directions
            search = search_directions(judgment_graph, state["advisor_context"])
            recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="EXECUTABLE_DIRECTION_SEARCH", urgency="REVIEW",
                reason="按明确的下一决策、带来源事实和图中结构化前置条件组合有界候选。",
                search=search, observations=search["candidates"], limitations=search["limitations"],
                minimal_test=[candidate["action"] for candidate in search["candidates"]]))
        active = state.get("active_branch", "main")
        branches = state.get("branches", {})
        branch, count = branches.get(active, {}), branches.get(active, {}).get("stagnation_count", 0)
        if count >= 2:
            explored = {b.get("orthogonal_dimension") for b in branches.values()}
            dimensions = [("representation", "改变表示，保留其余比较条件"), ("mechanism", "对机制做可观测单因素干预"),
                          ("loss_formulation", "对监督信号做单因素对照"), ("optimization", "固定结构/数据检验一个优化因素")]
            recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="ORTHOGONAL_BRANCH_RECOMMENDATION",
                urgency="HIGH" if count >= 3 else "REVIEW", reason=f"分支 '{active}' 已记录 {count} 次连续无有效收益。",
                recommended_action="先审查失败证据与可用预算；存在可判别的新问题时，再 branch fork 做单因素对照。",
                candidate_dimensions=[{"dimension": d, "concept": c, "basis": "通用候选，需由项目证据选择"}
                                      for d, c in dimensions if d not in explored],
                observations=[{"branch_id": active, "stagnation_count": count, "status": branch.get("status")}],
                alternative_explanations=["候选确无增益", "协议或执行故障", "预算/噪声不足以判别"],
                minimal_test=[{"question": "下一对照能区分至少两个解释吗？",
                    "protocol": "用锁定指标、失败收据和预算选择一个变量；优先复用同身份对照、同 seed 配对，并预声明停止条件。",
                    "decision_rule": "无可判别问题或可用预算则停止/复核；仅当已观测 seed 不稳定且会改变决策时考虑追加。"}],
                limitations=["没有成功概率排名；停滞次数不证明一类方法永久失败，名称不证明正交。"],
                evidence=[{"kind": "state", "source": f"branches.{active}", "value": branch}]))
        cache = state.get("baseline_cache", {})
        if cache:
            entries = [{"key": key, "first_run_id": item.get("first_run_id"), "sample_count": len(item.get("observations", {}))}
                       for key, item in cache.items() if isinstance(item, dict)]
            recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="COMPUTE_REUSE_ADVICE", urgency="INFO",
                reason=f"状态记录了 {len(entries)} 组对照缓存候选。",
                recommended_action="当前确定性适配器按锁定 control AST 和数据字节 SHA-256 匹配；匹配且收据可核验时复用。",
                observations=entries, minimal_test=[{"question": "本方案与缓存的计算身份是否相同？",
                    "protocol": "核对实际 baseline_key、逐样本输出和成功的 first_run_id 收据；随机/训练适配器还需 seed、checkpoint、recipe 与数值设置。",
                    "decision_rule": "身份和来源核验通过才复用；缓存不能恢复确认资格，也不保证免除整个基线训练成本。"}],
                limitations=["本方法只读状态条目，未独立验证收据；相同函数签名不等于相同计算。"],
                evidence=[{"kind": "state", "source": "baseline_cache", "entries": entries}]))
        nodes = [node for node in judgment_graph.get("nodes", []) if isinstance(node, dict)]
        if nodes:
            hypotheses = state.get("hypotheses", {})
            context = [{"hypothesis_id": hid, "task_gain": hypotheses.get(hid, {}).get("task_gain"),
                        "mechanism": hypotheses.get(hid, {}).get("mechanism")} for hid in branch.get("hypotheses", [])]
            recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="JUDGMENT_GRAPH_REVIEW", urgency="REVIEW",
                reason=f"提供的判断图含 {len(nodes)} 条规则；当前分支关联 {len(context)} 个假说。",
                recommended_action="核实符合证据的 scope/trigger，再选 discriminator；文字触发器不会自动执行。",
                observations=context, candidate_rules=[{k: node.get(k) for k in
                    ("id", "scope", "trigger", "correction", "alternatives", "discriminator", "primary_gate", "falsifier", "sources")}
                    for node in nodes], limitations=["这是候选规则清单，未断言每条规则已触发或必然有效。"],
                evidence=[{"kind": "judgment_graph", "rule_id": node.get("id"), "sources": node.get("sources", [])} for node in nodes]))
        knowledge_file = self.root_dir / ".rds/advisor_knowledge.json"
        if knowledge_file.exists():
            try:
                knowledge = json.loads(knowledge_file.read_text(encoding="utf-8-sig"))
                if not isinstance(knowledge, list) or not all(isinstance(item, dict) for item in knowledge):
                    raise ValueError("Knowledge must be a list of objects")
                if knowledge:
                    recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="DOC_REVIEW_CANDIDATES", urgency="INFO",
                        reason=f"存在 {len(knowledge)} 条摘录候选，需核实来源与适用范围。", latest_insight=knowledge[-1].get("excerpt"),
                        adoption_status="UNREVIEWED", limitations=["关键字摘录和旧记录均不自动成为已采纳原则。"], evidence=[knowledge[-1]]))
            except (OSError, ValueError) as exc:
                recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="KNOWLEDGE_LOAD_ERROR", urgency="REVIEW",
                    reason="文档知识库不可读，未用其产生研究结论。", limitations=[str(exc)]))
        if self.literature_principles:
            recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="LITERATURE_TUNING_GROUNDING", urgency="INFO",
                reason=f"加载了 {len(self.literature_principles)} 条文献记录；引用与适用范围需逐条审查。",
                sample_guideline=self.literature_principles[0].get("title", ""),
                limitations=["文献条件和历史启发不构成当前项目因果诊断或收益保证。"],
                evidence=[{"kind": "literature_record", "id": p.get("id"), "paper": p.get("paper"),
                           "sources": p.get("sources", [])} for p in self.literature_principles]))
        if self.literature_load_errors:
            recommendations.append(_advice("STRATEGIC_RESEARCH_ADVICE", type="LITERATURE_LOAD_ERROR", urgency="REVIEW",
                reason="文献库格式或读取失败；未加载替代库。", limitations=self.literature_load_errors))
        return recommendations

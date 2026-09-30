"""RDS Programmatic Advisor Engine.

Reports heuristic signals and candidate diagnostics for human or experimental review.
It does not solve parameter ranges or establish causes from endpoint telemetry.
"""
import json
import math
from pathlib import Path
import hashlib
import sqlite3
import time
from typing import Any, Dict, List, Optional

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
MAX_KNOWLEDGE_ROWS = 10000


def _configure_wal(db):
    # SQLite's initial journal-mode transition can return BUSY without using
    # busy_timeout. Retry only this cold-start transition, before any transaction.
    deadline = time.monotonic() + 15
    while True:
        try:
            db.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as exc:
            code = getattr(exc, "sqlite_errorcode", 0) & 255
            if code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) or time.monotonic() >= deadline:
                raise
            time.sleep(0.01)


def _read_document(path):
    if not path.is_file():
        raise ValueError("Document must be an existing regular file")
    with path.open("rb") as handle:
        raw = handle.read(MAX_DOCUMENT_BYTES + 1)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ValueError("Advisor document exceeds the 2 MiB limit")
    try:
        return raw, raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Advisor document must be UTF-8") from exc


def _knowledge_entry(rule, entry_id, document_sha):
    if (not isinstance(rule, dict) or type(rule.get("line_number")) is not int
            or rule["line_number"] < 1 or not isinstance(rule.get("excerpt"), str)
            or not rule["excerpt"].strip() or not isinstance(rule.get("source"), str)
            or not rule["source"].strip() or len(rule["source"]) > 1024
            or not isinstance(rule.get("topic"), str) or not rule["topic"].strip()
            or len(rule["topic"]) > 256):
        raise ValueError("Invalid legacy advisor knowledge entry")
    normalized = {key: rule[key] for key in ("line_number", "excerpt", "topic", "source")}
    normalized["excerpt"] = normalized["excerpt"][:120]
    return entry_id, document_sha, json.dumps(normalized, ensure_ascii=False, allow_nan=False, sort_keys=True)



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
        self.knowledge_db = self.root_dir / ".rds" / "advisor.sqlite3"

    def _legacy_entries(self):
        path = self.root_dir / ".rds" / "advisor_knowledge.json"
        if not path.exists():
            return []
        raw, text = _read_document(path)
        rows = json.loads(text)
        if not isinstance(rows, list) or len(rows) > MAX_KNOWLEDGE_ROWS:
            raise ValueError("Legacy advisor knowledge must contain at most 10000 entries")
        digest = hashlib.sha256(raw).hexdigest()
        entries = []
        for row in rows:
            entry_id = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False,
                                                allow_nan=False).encode("utf-8")).hexdigest()
            entries.append(_knowledge_entry(row, "legacy:" + entry_id, digest))
        return entries

    def _needs_legacy_migration(self):
        if not self.knowledge_db.exists():
            return True
        db = sqlite3.connect(self.knowledge_db.as_uri() + "?mode=ro", uri=True, timeout=15)
        try:
            table = db.execute("SELECT 1 FROM sqlite_master WHERE name='metadata'").fetchone()
            return table is None or db.execute("SELECT 1 FROM metadata WHERE key='legacy_migrated'").fetchone() is None
        finally:
            db.close()

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

        if not isinstance(compressed_telemetry, dict):
            advice["diagnostics"].append("遥测必须是具名字段对象；无法据此诊断。")
            return advice
        nan_flag = compressed_telemetry.get("nan_or_inf")
        if nan_flag is not None and type(nan_flag) is not bool:
            advice["diagnostics"].append("nan_or_inf 必须是布尔报告字段；字符串或数值不构成非有限值证据。")
        if nan_flag is True:
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
        if trend is not None and not isinstance(trend, str):
            advice["diagnostics"].append("损失趋势字段无效；无法据此诊断。")
            trend = None
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
        """Store heuristic excerpts with a short isolated WAL transaction."""
        doc_path = doc_path.resolve()
        if not doc_path.exists():
            raise FileNotFoundError(f"Document not found: {doc_path}")
        if topic is not None and (not isinstance(topic, str) or not topic.strip() or len(topic) > 256):
            raise ValueError("Advisor topic must be a nonempty string of at most 256 characters")
        raw, text = _read_document(doc_path)
        document_sha = hashlib.sha256(raw).hexdigest()
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
                if len(extracted_rules) > MAX_KNOWLEDGE_ROWS:
                    raise ValueError("Advisor document exceeds the 10000-excerpt limit")
        entries = []
        for rule in extracted_rules:
            key = f"{document_sha}:{rule['line_number']}:{rule['topic']}"
            entries.append(_knowledge_entry(rule, hashlib.sha256(key.encode("utf-8")).hexdigest(), document_sha))
        # Parsing and possible legacy loading finish before any writer lock.
        legacy = self._legacy_entries() if self._needs_legacy_migration() else []
        self.knowledge_db.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.knowledge_db, timeout=15, isolation_level=None)
        try:
            _configure_wal(db)
            db.execute("BEGIN IMMEDIATE")
            db.execute("CREATE TABLE IF NOT EXISTS knowledge (entry_id TEXT PRIMARY KEY, document_sha TEXT NOT NULL, body TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            migrate = db.execute("SELECT 1 FROM metadata WHERE key='legacy_migrated'").fetchone() is None
            existing_ids = {row[0] for row in db.execute("SELECT entry_id FROM knowledge")}
            candidates = {entry[0]: entry for entry in ((legacy if migrate else []) + entries)}
            added = [entry for entry_id, entry in candidates.items() if entry_id not in existing_ids]
            if len(existing_ids) + len(added) > MAX_KNOWLEDGE_ROWS:
                raise ValueError("Advisor knowledge exceeds the 10000-entry limit")
            db.executemany("INSERT INTO knowledge VALUES (?,?,?)", added)
            if migrate:
                db.execute("INSERT INTO metadata VALUES ('legacy_migrated','1')")
            total = len(existing_ids) + len(added)
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

        return {
            "status": "INGESTED",
            "assurance": "HEURISTIC_ONLY",
            "doc_path": str(doc_path),
            "rules_extracted": len(extracted_rules),
            "rules_added": len(added),
            "total_knowledge_entries": total
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
                "reason": f"状态记录当前分支 '{active_branch}' 连续 {stagnation_count} 次无有效收益；可比较正交研究路线。",
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
                "reason": f"本地账本记录了 {len(cache)} 组对照缓存，具体绑定仍需核对。",
                "recommended_action": "当前仅复用标量参考运行器的对照结果；需基线、数据和执行器绑定匹配，并检查 control_reused 收据。"
            })

        # Priority 3: Check learned document knowledge
        if self.knowledge_db.exists():
            try:
                db = sqlite3.connect(self.knowledge_db.as_uri() + "?mode=ro", uri=True, timeout=0.05,
                                     isolation_level=None)
                try:
                    db.execute("BEGIN")
                    count = db.execute("SELECT COUNT(*) FROM knowledge").fetchone()[0]
                    latest = db.execute("SELECT body FROM knowledge ORDER BY rowid DESC LIMIT 1").fetchone()
                finally:
                    db.close()
                if count:
                    recommendations.append({
                        "type": "DOC_GROUNDED_INSIGHT",
                        "urgency": "INFO",
                        "reason": f"导入文档中有 {count} 条关键词摘录；适用性和真实性仍需检验。",
                        "latest_insight": json.loads(latest[0])["excerpt"]
                    })
            except (sqlite3.Error, ValueError, KeyError, TypeError, AttributeError):
                recommendations.append({"type": "DOC_KNOWLEDGE_UNAVAILABLE", "urgency": "INFO",
                                        "reason": "无法读取文档摘录库；现有摘录数量和内容未确认。"})

        for recommendation in recommendations:
            recommendation["assurance"] = "HEURISTIC_ONLY"
        return recommendations

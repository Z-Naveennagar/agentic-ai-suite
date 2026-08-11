#!/usr/bin/env python3
"""
Answer quality evaluation for copilot responses.

Three-tier evaluation:
  Tier 1: Semantic similarity (sentence-transformers, local, fast)
  Tier 2: LLM-as-a-Judge with Vivado-specific weighted rubric (via copilot CLI)
  Tier 3: ROUGE-L token overlap (cheap, supplementary)

Only evaluates queries that have an `expected_answer` field in ground truth.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Lazy-loaded heavy imports (sentence-transformers, rouge-score)
_sentence_model = None
_rouge_scorer = None


# ── Dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class RubricResult:
    """Result from the LLM-as-a-Judge Vivado-specific rubric evaluation."""
    solution_type: str = "UNKNOWN"  # TECHNICAL_SOLUTION / STATUS_UPDATE / PARTIAL_SOLUTION
    technical_accuracy: float = 0.0  # 0-100
    solution_completeness: float = 0.0  # 0-100
    practical_value: float = 0.0  # 0-100
    communication_clarity: float = 0.0  # 0-100
    weighted_score: float = 0.0  # 0-100
    letter_grade: str = "F"
    rationale: dict = field(default_factory=dict)
    judge_model: str = ""
    error: str | None = None


@dataclass
class AnswerQualityResult:
    """Aggregated answer quality result across all tiers."""
    query_id: str
    query_text: str
    device_family: str
    tool: str
    release: str
    category: str
    difficulty: str
    model: str  # the model that generated the answer

    # Tier 1: Semantic similarity
    semantic_similarity: float | None = None

    # Tier 2: LLM rubric
    solution_type: str | None = None
    technical_accuracy: float | None = None
    solution_completeness: float | None = None
    practical_value: float | None = None
    communication_clarity: float | None = None
    weighted_score: float | None = None
    letter_grade: str | None = None
    llm_judge_model: str | None = None
    llm_judge_rationale: str | None = None

    # Tier 3: ROUGE-L
    rouge_l: float | None = None

    # Composite
    composite_score: float | None = None

    error: str | None = None


# ── Tier 1: Semantic Similarity ──────────────────────────────────────────────

def _get_sentence_model(model_name: str = "all-MiniLM-L6-v2"):
    """Lazy-load the sentence-transformers model."""
    global _sentence_model
    if _sentence_model is None:
        from sentence_transformers import SentenceTransformer
        _sentence_model = SentenceTransformer(model_name)
    return _sentence_model


def compute_semantic_similarity(
    expected: str,
    generated: str,
    model_name: str = "all-MiniLM-L6-v2",
) -> float:
    """
    Compute cosine similarity between expected and generated answers
    using sentence-transformers embeddings.

    Returns a float in [0.0, 1.0].
    """
    if not expected or not generated:
        return 0.0

    model = _get_sentence_model(model_name)
    embeddings = model.encode([expected, generated], convert_to_tensor=True)

    # Cosine similarity
    from sentence_transformers.util import cos_sim
    similarity = cos_sim(embeddings[0], embeddings[1]).item()

    # Clamp to [0, 1] (cosine sim can be slightly negative for unrelated texts)
    return max(0.0, min(1.0, similarity))


# ── Tier 2: LLM-as-a-Judge with Vivado Rubric ───────────────────────────────

# The rubric prompt sent to the judge LLM
JUDGE_PROMPT_TEMPLATE = """\
You are an expert AMD/Xilinx FPGA engineer evaluating the quality of an AI assistant's response.

TASK: Compare the AI's response against the expected answer and grade it using the rubric below.

ORIGINAL QUESTION:
{query}

EXPECTED ANSWER (ground truth):
{expected_answer}

AI RESPONSE TO EVALUATE:
{generated_answer}

GRADING CRITERIA:

1. SOLUTION QUALITY ASSESSMENT:
   First, classify the expected answer into one of these types:
   - TECHNICAL_SOLUTION: The expected answer provides a complete technical solution.
     Compare AI answer against expected solution for accuracy, completeness, and improvements.
   - STATUS_UPDATE/NO_SOLUTION: The expected answer is a status update or does not provide a complete solution.
     Score AI answer on its own merit as a complete technical solution (should provide actionable guidance).
   - PARTIAL_SOLUTION: The expected answer provides an incomplete solution.
     Evaluate how well AI completes or enhances the partial solution.

2. TECHNICAL ACCURACY (40%):
   - Correctness of Vivado commands, syntax, and tool usage
   - Accuracy of technical concepts and FPGA development principles
   - Proper use of TCL commands, constraints, timing analysis, etc.
   - For status updates: Does AI provide actual technical guidance that customers can use immediately?

3. SOLUTION COMPLETENESS (30%):
   - Addresses all aspects of the customer's question
   - Provides actionable steps or commands
   - Includes relevant code examples or syntax
   - Covers edge cases and potential issues
   - For status updates: Does AI fill the gap left by the inadequate expected solution?

4. PRACTICAL VALUE (20%):
   - Immediate applicability to customer's situation
   - Clear, step-by-step guidance
   - Best practices and optimization suggestions
   - Troubleshooting insights
   - For status updates: Does AI provide real help rather than just acknowledging the issue?

5. COMMUNICATION CLARITY (10%):
   - Clear, professional language
   - Logical flow and organization
   - Appropriate technical depth for the context

GRADING SCALE:
- A (90-100%): Excellent technical solution, comprehensive and accurate
- B (80-89%): Good solution with minor gaps or improvements needed
- C (70-79%): Adequate but lacks depth or has some inaccuracies
- D (60-69%): Poor solution with significant technical errors
- F (0-59%): Unacceptable, contains major errors or is unhelpful

RESPOND WITH ONLY valid JSON in this exact format (no markdown, no code fences):
{{
  "solution_type": "TECHNICAL_SOLUTION or STATUS_UPDATE or PARTIAL_SOLUTION",
  "technical_accuracy": <0-100>,
  "solution_completeness": <0-100>,
  "practical_value": <0-100>,
  "communication_clarity": <0-100>,
  "rationale": {{
    "technical_accuracy": "<1-2 sentence justification>",
    "solution_completeness": "<1-2 sentence justification>",
    "practical_value": "<1-2 sentence justification>",
    "communication_clarity": "<1-2 sentence justification>"
  }}
}}
"""


def _compute_weighted_score(
    ta: float, sc: float, pv: float, cc: float,
    weights: dict | None = None,
) -> float:
    """Compute weighted score from rubric dimensions."""
    w = weights or {
        "technical_accuracy": 0.4,
        "solution_completeness": 0.3,
        "practical_value": 0.2,
        "communication_clarity": 0.1,
    }
    return (
        ta * w["technical_accuracy"]
        + sc * w["solution_completeness"]
        + pv * w["practical_value"]
        + cc * w["communication_clarity"]
    )


def _score_to_grade(score: float, thresholds: dict | None = None) -> str:
    """Convert a 0-100 score to a letter grade."""
    t = thresholds or {"A": 90, "B": 80, "C": 70, "D": 60, "F": 0}
    if score >= t["A"]:
        return "A"
    elif score >= t["B"]:
        return "B"
    elif score >= t["C"]:
        return "C"
    elif score >= t["D"]:
        return "D"
    else:
        return "F"


def _find_judge_bin() -> str:
    """Locate the judge CLI binary.

    Search order: opencode → copilot → agent (Cursor).
    opencode is checked at its canonical install location
    (~/.opencode/bin/opencode) before falling back to PATH.
    """
    # opencode canonical location (mirrors OpencodeSkillCLI._default_binary_lookup)
    opencode_home = Path.home() / ".opencode" / "bin" / "opencode"
    if opencode_home.is_file() and os.access(str(opencode_home), os.X_OK):
        return str(opencode_home)

    for name in ("opencode", "copilot", "agent"):
        local_bin = Path.home() / ".local" / "bin" / name
        if local_bin.exists():
            return str(local_bin)
        path = shutil.which(name)
        if path:
            return path
    return ""


def _debug_snippet(text: str, limit: int = 300) -> str:
    """Head+tail preview of *text* for embedding in a parse-failure error
    message, so the raw judge response is diagnosable without re-running."""
    text = text or ""
    if len(text) <= 2 * limit:
        return repr(text)
    return f"{text[:limit]!r} ... {text[-limit:]!r}"


def _json_loads_lenient(candidate: str) -> Any | None:
    """``json.loads`` with one repair pass for the LLM's favorite mistake:
    a trailing comma before a closing ``}``/``]``."""
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        pass
    repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None


def _iter_balanced_brace_objects(text: str):
    """Yield every top-level, string-aware balanced ``{...}`` substring of
    *text*, in the order they appear.

    String-aware so a literal ``{``/``}`` inside a quoted rationale string
    doesn't desync the depth count.
    """
    depth = 0
    start = None
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    yield text[start:i + 1]


def _parse_judge_json(text: str) -> dict | None:
    """Extract and parse JSON from the judge LLM response.

    Judge calls that go through a CLI agent (opencode/copilot/agent) rather
    than a raw API often echo the *prompt* to stdout before the real answer —
    and the prompt itself contains a JSON template that looks exactly like a
    valid (if placeholder-filled) response. So candidates are tried **last
    match first**: the model's actual answer is whatever comes last in the
    output, after any echoed prompt/transcript.
    """
    parsed = _json_loads_lenient(text.strip())
    if parsed is not None:
        return parsed

    # Markdown code fences (```json ... ``` or ``` ... ```), last one first.
    for pattern in (r'```json\s*\n(.*?)\n\s*```', r'```\s*\n(.*?)\n\s*```'):
        matches = list(re.finditer(pattern, text, re.DOTALL))
        for match in reversed(matches):
            parsed = _json_loads_lenient(match.group(1))
            if parsed is not None:
                return parsed

    # Last resort: every balanced top-level {...} object in the text, most
    # recent first.
    for candidate in reversed(list(_iter_balanced_brace_objects(text))):
        parsed = _json_loads_lenient(candidate)
        if parsed is not None:
            return parsed

    return None


def _extract_cli_answer_text(bin_name: str, stdout: str) -> str:
    """Pull the final assistant text out of an agentic CLI's structured output.

    Cursor's ``agent`` (invoked with ``--output-format json`` / ``stream-json``)
    wraps the model's answer in a terminal result envelope, e.g.
    ``{"type":"result","result":"<final assistant text>","usage":{...}}``.
    Handing that whole envelope to ``_parse_judge_json`` would parse the
    *wrapper* (wrong keys) instead of the grade, so we unwrap it here and
    return just the assistant text. For any other binary (or unrecognized
    output), the raw stdout is returned unchanged.
    """
    if bin_name != "agent":
        return stdout

    def _answer_from_envelope(obj: Any) -> str | None:
        if not isinstance(obj, dict):
            return None
        if obj.get("type") == "result" or "result" in obj:
            for key in ("result", "text", "response", "content", "message"):
                val = obj.get(key)
                if isinstance(val, str) and val.strip():
                    return val
        return None

    # --output-format json: a single (possibly multi-line) JSON object.
    try:
        whole = json.loads(stdout.strip())
    except (json.JSONDecodeError, ValueError):
        whole = None
    answer = _answer_from_envelope(whole)
    if answer is not None:
        return answer

    # --output-format stream-json: JSONL; the last result/usage line wins.
    final_obj: Any = None
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict) and (obj.get("type") == "result"
                                      or obj.get("usage")):
            final_obj = obj
    answer = _answer_from_envelope(final_obj)
    if answer is not None:
        return answer

    return stdout


def _evaluate_with_gateway(
    prompt: str,
    judge_model: str,
    gateway_cfg: dict,
    rubric_weights: dict | None,
    grade_thresholds: dict | None,
    timeout: int = 120,
) -> RubricResult:
    """
    Call an Anthropic-compatible API to judge an answer.

    Supports two modes controlled by environment variables and config:

    1. **Direct Anthropic API** -- Set ANTHROPIC_API_KEY env var. Uses the
       standard Anthropic endpoint (no custom headers needed).
    2. **Corporate gateway** -- Set LLM_GATEWAY_SUBSCRIPTION_KEY (and
       optionally LLM_GATEWAY_BASE_URL). Sends the subscription key as an
       Ocp-Apim-Subscription-Key header to a corporate proxy.

    Env vars override config.yaml values. If neither env var is set, the
    gateway returns an error and the caller falls back to the CLI path.
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        return RubricResult(
            error="anthropic package not installed (pip install anthropic)",
            judge_model=judge_model,
        )

    max_tokens = gateway_cfg.get("max_tokens", 1024)

    # Direct Anthropic API: user has their own key
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        client = Anthropic(
            api_key=anthropic_key,
            timeout=float(timeout),
        )
    else:
        # Corporate gateway: subscription key from env var or config
        base_url = (
            os.environ.get("LLM_GATEWAY_BASE_URL")
            or gateway_cfg.get("base_url", "")
        )
        subscription_key = (
            os.environ.get("LLM_GATEWAY_SUBSCRIPTION_KEY")
            or gateway_cfg.get("subscription_key", "")
        )
        api_key = gateway_cfg.get("api_key", "dummy")

        if not subscription_key:
            return RubricResult(
                error="No API key configured. Set ANTHROPIC_API_KEY or "
                      "LLM_GATEWAY_SUBSCRIPTION_KEY environment variable.",
                judge_model=judge_model,
            )

        try:
            user_login = os.getlogin()
        except OSError:
            user_login = os.environ.get("USER", "unknown")

        client = Anthropic(
            base_url=base_url,
            api_key=api_key,
            default_headers={
                "Ocp-Apim-Subscription-Key": subscription_key,
                "user": user_login,
                "anthropic-version": "2023-10-16",
            },
            timeout=float(timeout),
        )

    try:
        response = client.messages.create(
            model=judge_model,
            max_tokens=max_tokens,
            temperature=0.0,
            messages=[{"role": "user", "content": prompt}],
        )
        response_text = response.content[0].text
        actual_model = getattr(response, "model", judge_model)
    except Exception as e:
        return RubricResult(error=f"gateway API call failed: {e}", judge_model=judge_model)

    parsed = _parse_judge_json(response_text)
    if parsed is None:
        return RubricResult(
            error="could not parse judge JSON from gateway response: "
                  f"{_debug_snippet(response_text)}",
            judge_model=actual_model,
        )

    ta = float(parsed.get("technical_accuracy", 0))
    sc = float(parsed.get("solution_completeness", 0))
    pv = float(parsed.get("practical_value", 0))
    cc = float(parsed.get("communication_clarity", 0))
    ws = _compute_weighted_score(ta, sc, pv, cc, rubric_weights)

    return RubricResult(
        solution_type=parsed.get("solution_type", "UNKNOWN"),
        technical_accuracy=ta,
        solution_completeness=sc,
        practical_value=pv,
        communication_clarity=cc,
        weighted_score=round(ws, 1),
        letter_grade=_score_to_grade(ws, grade_thresholds),
        rationale=parsed.get("rationale", {}),
        judge_model=actual_model,
    )


def _evaluate_with_cli(
    prompt: str,
    judge_model: str,
    rubric_weights: dict | None,
    grade_thresholds: dict | None,
    timeout: int = 180,
) -> RubricResult:
    """
    Evaluate using a local CLI binary (opencode, copilot, or Cursor agent).
    """
    judge_bin = _find_judge_bin()
    if not judge_bin:
        return RubricResult(
            error="judge binary not found (tried 'opencode', 'copilot', 'agent')"
        )

    bin_name = Path(judge_bin).name
    if bin_name == "opencode":
        cmd = [judge_bin, "run", prompt, "--model", judge_model]
    elif bin_name == "agent":
        # Cursor's default text mode streams agentic narration ("Inspecting
        # the run artifacts...") instead of the requested JSON, and --force
        # keeps it from stalling on tool/MCP approval prompts. Ask for a
        # structured envelope and unwrap the final answer below.
        cmd = [judge_bin, "-p", "--output-format", "json", "--force",
               "--model", judge_model, prompt]
    else:  # copilot
        cmd = [judge_bin, "-p", prompt, "-s", "--model", judge_model, "--no-ask-user"]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        if result.returncode != 0:
            error_msg = result.stderr.strip() or f"exit code {result.returncode}"
            return RubricResult(error=f"judge ({bin_name}) failed: {error_msg}", judge_model=judge_model)

        answer_text = _extract_cli_answer_text(bin_name, result.stdout)
        parsed = _parse_judge_json(answer_text)
        if parsed is None:
            return RubricResult(
                error="could not parse judge JSON from response: "
                      f"{_debug_snippet(answer_text)}",
                judge_model=judge_model,
            )

        ta = float(parsed.get("technical_accuracy", 0))
        sc = float(parsed.get("solution_completeness", 0))
        pv = float(parsed.get("practical_value", 0))
        cc = float(parsed.get("communication_clarity", 0))
        ws = _compute_weighted_score(ta, sc, pv, cc, rubric_weights)

        return RubricResult(
            solution_type=parsed.get("solution_type", "UNKNOWN"),
            technical_accuracy=ta,
            solution_completeness=sc,
            practical_value=pv,
            communication_clarity=cc,
            weighted_score=round(ws, 1),
            letter_grade=_score_to_grade(ws, grade_thresholds),
            rationale=parsed.get("rationale", {}),
            judge_model=judge_model,
        )

    except subprocess.TimeoutExpired:
        return RubricResult(error=f"judge timed out after {timeout}s", judge_model=judge_model)
    except Exception as e:
        return RubricResult(error=str(e), judge_model=judge_model)


def evaluate_with_llm_judge(
    query: str,
    expected_answer: str,
    generated_answer: str,
    answer_model: str,
    config: dict,
    timeout: int = 180,
) -> RubricResult:
    """
    Evaluate the generated answer using a judge LLM.

    Dispatch order:
      1. AMD LLM Gateway (Anthropic SDK) — if gateway.enabled is True
      2. Local CLI binary (agent / copilot) — legacy fallback
    """
    judge_cfg = config.get("answer_evaluation", {}).get("llm_judge", {})
    judge_model = judge_cfg.get("model", "opus-4.6")
    fallback_model = judge_cfg.get("fallback_model", "gpt-5.2-codex")

    rubric_weights = config.get("answer_evaluation", {}).get("rubric_weights")
    grade_thresholds = config.get("answer_evaluation", {}).get("grade_thresholds")

    prompt = JUDGE_PROMPT_TEMPLATE.format(
        query=query,
        expected_answer=expected_answer,
        generated_answer=generated_answer[:8000],
    )

    # ── Try AMD LLM Gateway first ─────────────────────────────────────
    gateway_cfg = judge_cfg.get("gateway", {})
    if gateway_cfg.get("enabled", False):
        gw_model = gateway_cfg.get("model", judge_model)

        # Avoid self-evaluation bias
        answer_model_base = answer_model.lower().replace("-no-mcp", "")
        gw_fallback = gateway_cfg.get("fallback_model", fallback_model)
        if answer_model_base == gw_model.lower():
            gw_model = gw_fallback

        result = _evaluate_with_gateway(
            prompt=prompt,
            judge_model=gw_model,
            gateway_cfg=gateway_cfg,
            rubric_weights=rubric_weights,
            grade_thresholds=grade_thresholds,
            timeout=timeout,
        )
        if result.error is None:
            return result
        # Gateway failed — fall through to CLI
        print(f"  [judge] Gateway failed ({result.error}), trying CLI fallback...", flush=True)

    # ── Fallback: CLI binary ──────────────────────────────────────────
    answer_model_base = answer_model.lower().replace("-no-mcp", "")
    if answer_model_base == judge_model.lower():
        judge_model = fallback_model

    return _evaluate_with_cli(
        prompt=prompt,
        judge_model=judge_model,
        rubric_weights=rubric_weights,
        grade_thresholds=grade_thresholds,
        timeout=timeout,
    )


# ── Tier 3: ROUGE-L ─────────────────────────────────────────────────────────

def _get_rouge_scorer():
    """Lazy-load the rouge scorer."""
    global _rouge_scorer
    if _rouge_scorer is None:
        from rouge_score import rouge_scorer as rs
        _rouge_scorer = rs.RougeScorer(["rougeL"], use_stemmer=True)
    return _rouge_scorer


def compute_rouge_l(expected: str, generated: str) -> float:
    """
    Compute ROUGE-L Recall between expected and generated answers.

    We use **recall** rather than F1 because the copilot intentionally
    produces longer, more detailed responses than the concise ground-truth
    expected answers (typically 7-13x longer).  F1's precision component
    penalises the extra useful content and collapses the score to near-zero.
    Recall answers the right question: "What fraction of the expected
    answer's content appears in the generated response?"

    Returns a float in [0.0, 1.0].
    """
    if not expected or not generated:
        return 0.0

    scorer = _get_rouge_scorer()
    scores = scorer.score(expected, generated)
    return scores["rougeL"].recall


# ── Composite Scoring ────────────────────────────────────────────────────────

def compute_composite_score(
    semantic_similarity: float | None,
    rubric_weighted_score: float | None,
    rouge_l: float | None,
    weights: dict | None = None,
) -> float | None:
    """
    Compute a composite score (0-100) blending all tiers.

    Default weights: 70% rubric, 20% semantic similarity, 10% ROUGE-L.
    If rubric is not available, re-weights between Tier 1 and Tier 3.
    """
    w = weights or {
        "semantic_similarity": 0.2,
        "rubric_weighted_score": 0.7,
        "rouge_l": 0.1,
    }

    components = []
    total_weight = 0.0

    if semantic_similarity is not None:
        # Semantic similarity is 0-1, scale to 0-100
        components.append(("semantic_similarity", semantic_similarity * 100, w["semantic_similarity"]))
        total_weight += w["semantic_similarity"]

    if rubric_weighted_score is not None:
        components.append(("rubric_weighted_score", rubric_weighted_score, w["rubric_weighted_score"]))
        total_weight += w["rubric_weighted_score"]

    if rouge_l is not None:
        # ROUGE-L is 0-1, scale to 0-100
        components.append(("rouge_l", rouge_l * 100, w["rouge_l"]))
        total_weight += w["rouge_l"]

    if total_weight == 0 or not components:
        return None

    # Normalize weights and compute
    score = sum(val * (wt / total_weight) for _, val, wt in components)
    return round(score, 1)


# ── Main Scoring Function ───────────────────────────────────────────────────

def score_answer_quality(
    query: dict,
    copilot_response: str,
    answer_model: str,
    config: dict,
    skip_llm_judge: bool = False,
) -> AnswerQualityResult:
    """
    Score a copilot response against the expected answer from ground truth.

    Only evaluates if the query has an `expected_answer` field.
    """
    expected_answer = query.get("expected_answer")
    if not expected_answer:
        return AnswerQualityResult(
            query_id=query["id"],
            query_text=query["query"],
            device_family=query["device_family"],
            tool=query.get("tool", "vivado"),
            release=query["release"],
            category=query["category"],
            difficulty=query.get("difficulty", "unknown"),
            model=answer_model,
            error="no expected_answer in ground truth",
        )

    if not copilot_response or not copilot_response.strip():
        return AnswerQualityResult(
            query_id=query["id"],
            query_text=query["query"],
            device_family=query["device_family"],
            tool=query.get("tool", "vivado"),
            release=query["release"],
            category=query["category"],
            difficulty=query.get("difficulty", "unknown"),
            model=answer_model,
            error="empty copilot response",
        )

    eval_config = config.get("answer_evaluation", {})
    embedding_model = eval_config.get("embedding_model", "all-MiniLM-L6-v2")
    composite_weights = eval_config.get("composite_weights")

    # Tier 1: Semantic similarity
    try:
        sem_sim = compute_semantic_similarity(expected_answer, copilot_response, embedding_model)
    except Exception as e:
        sem_sim = None

    # Tier 3: ROUGE-L
    try:
        rouge = compute_rouge_l(expected_answer, copilot_response)
    except Exception as e:
        rouge = None

    # Tier 2: LLM-as-a-Judge (opt-in)
    rubric = None
    if not skip_llm_judge and eval_config.get("llm_judge", {}).get("enabled", False):
        rubric = evaluate_with_llm_judge(
            query=query["query"],
            expected_answer=expected_answer,
            generated_answer=copilot_response,
            answer_model=answer_model,
            config=config,
        )

    # Build result
    rubric_ws = rubric.weighted_score if rubric and not rubric.error else None
    composite = compute_composite_score(sem_sim, rubric_ws, rouge, composite_weights)

    rationale_str = None
    if rubric and rubric.rationale:
        try:
            rationale_str = json.dumps(rubric.rationale)
        except (TypeError, ValueError):
            rationale_str = str(rubric.rationale)

    return AnswerQualityResult(
        query_id=query["id"],
        query_text=query["query"],
        device_family=query["device_family"],
        tool=query.get("tool", "vivado"),
        release=query["release"],
        category=query["category"],
        difficulty=query.get("difficulty", "unknown"),
        model=answer_model,
        semantic_similarity=round(sem_sim, 4) if sem_sim is not None else None,
        solution_type=rubric.solution_type if rubric and not rubric.error else None,
        technical_accuracy=rubric.technical_accuracy if rubric and not rubric.error else None,
        solution_completeness=rubric.solution_completeness if rubric and not rubric.error else None,
        practical_value=rubric.practical_value if rubric and not rubric.error else None,
        communication_clarity=rubric.communication_clarity if rubric and not rubric.error else None,
        weighted_score=rubric.weighted_score if rubric and not rubric.error else None,
        letter_grade=rubric.letter_grade if rubric and not rubric.error else None,
        llm_judge_model=rubric.judge_model if rubric else None,
        llm_judge_rationale=rationale_str,
        rouge_l=round(rouge, 4) if rouge is not None else None,
        composite_score=composite,
        error=rubric.error if rubric and rubric.error else None,
    )

"""
``tool-execution`` family — "did the agent use the right tools, in order?"

Emits the core graders that confirm the skill was activated (``trigger``,
arm-aware by default), the tool-call sequence matched (``action_sequence``),
and — when relevant — that an external tool was actually invoked
(``tool_call_observed``).

Author YAML::

    - family: tool-execution
      id: usage
      skill: hls-array-to-stream     # optional; trigger defaults to case skill
      sequence: [Read, Skill, Bash]  # optional tool ordering
      matching: in_order_match       # exact_match | in_order_match | any_order_match
      trigger: true                  # default true; set false to skip trigger
      trigger_threshold: 0.5
      trigger_mode: positive         # optional; omit for arm-aware default
      tool: vivado_mcp               # optional; enables tool_call_observed
      min_tool_calls: 1
"""

from __future__ import annotations

from . import Family, register_family


class ToolExecutionFamily(Family):
    family_type = "tool-execution"
    required = ()  # all fields optional; `trigger` defaults on so output is non-empty

    def expand(self, params: dict, meta: dict) -> list[dict]:
        specs: list[dict] = []

        if params.get("trigger", True):
            trig = {
                "id": "skill_triggered",
                "type": "trigger",
                "threshold": params.get("trigger_threshold", 0.5),
            }
            # Default the skill name from case meta when the author omits it;
            # the trigger grader also falls back to run_meta at grade time.
            skill = params.get("skill") or meta.get("skill")
            if skill:
                trig["skill"] = skill
            if params.get("trigger_mode"):
                trig["mode"] = params["trigger_mode"]
            specs.append(trig)

        sequence = params.get("sequence")
        if sequence:
            specs.append({
                "id": "tool_sequence",
                "type": "action_sequence",
                "matching_mode": params.get("matching", "in_order_match"),
                "expected_actions": list(sequence),
            })

        if params.get("tool") or params.get("min_tool_calls"):
            specs.append({
                "id": "tool_invoked",
                "type": "tool_call_observed",
                "tool": params.get("tool", "vivado_mcp"),
                "min_calls": int(params.get("min_tool_calls", 1)),
            })

        return specs


register_family(ToolExecutionFamily())

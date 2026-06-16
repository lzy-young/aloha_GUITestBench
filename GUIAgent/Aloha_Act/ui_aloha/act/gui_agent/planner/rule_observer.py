"""
RuleObserver — hybrid observer combining ROIDiff (quantitative) + lightweight 7B LLM (semantic).

ROIDiff handles:
  - progress: pixel-level change detection near action coordinates
  - changed_elements: diff score summary

7B LLM handles:
  - observation: describe current UI state (1-2 sentences)
  - subtask: match current screen to skill subgoal

Usage:
    observer = RuleObserver(
        model="ui-tars",
        os_name="windows",
        api_keys=api_keys,
        roidiff_threshold=10,
        roidiff_window_size=80,
    )
    result = observer(task, screenshot_path, skill_guidance, action_history, logging_dir)
"""

import json
import os
import re
from typing import Dict, List, Optional, Any, Tuple

from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.llm.run_llm import run_llm
from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.llm.llm_utils import extract_data
from GUIAgent.Aloha_Act.ui_aloha.act.utils.logger_utils import LoggerUtils
from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.planner.roidiff import ROIDiff, ImageSource

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_action_points(action_history: List) -> List[Tuple[int, int]]:
    """Extract all actionable coordinates from the last action.

    Handles:
      - CLICK, MOVE:            position=[x, y]          → [(x, y)]
      - DRAG:                   start=[x1,y1], end=[x2,y2] → [(x1,y1), (x2,y2)]
      - DRAG (alt format):      from=[x1,y1], to=[x2,y2]   → [(x1,y1), (x2,y2)]
      - SCROLL with position:   position=[x, y]           → [(x, y)]
    """
    if not action_history:
        return []

    def _to_point(val) -> Optional[Tuple[int, int]]:
        if isinstance(val, (list, tuple)) and len(val) == 2:
            try:
                return int(val[0]), int(val[1])
            except (ValueError, TypeError):
                pass
        if isinstance(val, str):
            match = re.search(r"(\d+)\s*[,，]\s*(\d+)", val)
            if match:
                return int(match.group(1)), int(match.group(2))
        return None

    for entry in reversed(action_history):
        if isinstance(entry, dict):
            inner = entry.get("content", entry)
            if isinstance(inner, dict):
                # DRAG: two coordinates
                for start_key, end_key in [("start", "end"), ("from", "to")]:
                    sp = _to_point(inner.get(start_key))
                    ep = _to_point(inner.get(end_key))
                    if sp and ep:
                        return [sp, ep]
                # Single-point actions
                pos = _to_point(inner.get("position"))
                if pos:
                    return [pos]
                # Also try position on outer dict
                for key in ("position", "coord", "coordinate", "xy"):
                    pos = _to_point(entry.get(key))
                    if pos:
                        return [pos]
        elif isinstance(entry, str):
            # Try to find [x,y] or (x,y) pairs — could be one or two
            matches = re.findall(r"[\(\[]\s*(\d+)\s*[,，]\s*(\d+)\s*[\)\]]", entry)
            if len(matches) == 1:
                return [(int(matches[0][0]), int(matches[0][1]))]
            if len(matches) >= 2:
                return [(int(m[0]), int(m[1])) for m in matches[:2]]

    return []


# ------------------------------------------------------------------
# RuleObserver class
# ------------------------------------------------------------------

class RuleObserver:
    """Hybrid observer: ROIDiff (quantitative) + 7B LLM (semantic)."""

    def __init__(
        self,
        model: str,
        max_tokens: int = 512,
        os_name: str = "windows",
        api_keys: dict | None = None,
        roidiff_threshold: int = 10,
        roidiff_window_size: int = 80,
        progress_threshold: float = 0.01,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.os_name = os_name
        self.api_keys = api_keys or {}
        self.progress_threshold = progress_threshold
        self.logger = LoggerUtils(component_name="rule_observer")

        # ROIDiff instance (used in reflect)
        self._roidiff = ROIDiff(threshold=roidiff_threshold, window_size=roidiff_window_size)

    # ------------------------------------------------------------------
    # Public API (matches Observer interface)
    # ------------------------------------------------------------------

    def __call__(
        self,
        task: str,
        screenshot_path: str,
        subtask_plan: list | None = None,
        action_history: List[str] | List[dict] | None = None,
        logging_dir: str = ".cache",
        reflection_signal: dict = None,
        current_subtask_idx: int = 0,
    ) -> Dict[str, str]:
        action_history = action_history or []
        subtask_plan = subtask_plan or []

        # 从 reflection_signal 获取 ROIDiff 结果（由 reflect 计算）
        progress = reflection_signal.get("progress", "uncertain") if reflection_signal else "uncertain"
        changed_elements = reflection_signal.get("changed_elements", "") if reflection_signal else ""
        roidiff_score = float(reflection_signal.get("roidiff_score", 0.0)) if reflection_signal else 0.0

        # =================================================================
        # 7B LLM — semantic: observation + subtask matching + completion
        # =================================================================
        # Format action_history for the LLM
        history_lines = []
        for i, h in enumerate(action_history):
            history_lines.append(f"step {i + 1}: {h}")
        history_text = "\n".join(history_lines) if history_lines else "(none)"

        # 确定当前应该执行的子任务（按顺序推进）
        total_subtasks = len(subtask_plan)
        expected_subtask = None
        if current_subtask_idx < total_subtasks:
            st = subtask_plan[current_subtask_idx]
            expected_subtask = f"Subtask {st['id']}: {st['name']} — {st.get('description', '')}"
        elif current_subtask_idx >= total_subtasks and total_subtasks > 0:
            expected_subtask = "All subtasks completed — output 'Task completed'"
        else:
            expected_subtask = "(no plan provided, infer from screenshot)"

        subtask_plan_text = "\n".join(
            f"  {st['id']}. {st['name']}: {st.get('description', '')}"
            for st in subtask_plan
        ) if subtask_plan else "(no plan provided, infer from screenshot)"

        system_prompt = (
            f"You are a UI observer in a GUI test benchmark on a {self.os_name} device. "
            "Describe the current UI state based on the screenshot. "
            "You do NOT decide which subtask to execute — the subtask order is predetermined externally. "
            "Your only job: confirm whether the current screen matches the provided 'Next expected subtask'. "
            "Return only a JSON object."
        )

        # Reflection 信号：给 observer 判断 subtask 推进的参考
        reflection_hint = ""
        if reflection_signal:
            ref_success = reflection_signal.get("success", False)
            ref_subtask_complete = reflection_signal.get("subtask_complete", False)
            ref_reason = reflection_signal.get("reason", "")
            reflection_hint = (
                f"\nReflection from previous step:\n"
                f"  Action success: {ref_success}\n"
                f"  Subtask complete: {ref_subtask_complete}\n"
                f"  Reason: {ref_reason}\n"
            )

        user_text = (
            f"Task: {task}\n\n"
            f"Change Detection: {progress} (score={roidiff_score:.2%})\n"
            f"Changed Elements: {changed_elements}\n\n"
            f"Full Subtask Plan:\n{subtask_plan_text}\n\n"
            f"Next expected subtask (#{current_subtask_idx + 1} of {total_subtasks}):\n"
            f"  {expected_subtask}\n\n"
            f"Action History:\n{history_text}\n"
            f"{reflection_hint}\n\n"
            "Based on the screenshot, output JSON with:\n"
            '  "observation": one concise sentence describing current UI state\n'
            '  "subtask": Follow these rules:\n'
            "    1) If the screenshot matches the 'Next expected subtask' → output it exactly as written.\n"
            "    2) If the screenshot does NOT match (e.g., still on a previous page, recovery state, error dialog) → describe what you see as a recovery subtask.\n"
            "    3) If 'All subtasks completed' is shown → output 'Task completed'.\n"
            '  "rationale": optional brief explanation\n'
            "CRITICAL: Do NOT pick a different subtask from the plan. "
            "If the expected subtask is not visible, output a recovery description instead."
        )

        user_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": screenshot_path}},
                ],
            }
        ]

        llm_response, _ = run_llm(
            messages=user_messages,
            system=system_prompt,
            llm=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            api_keys=self.api_keys,
            response_format={"type": "json_object"},
        )
        self.logger.log_text(llm_response, "rule_observer_llm.log", logging_dir)

        try:
            llm_json = extract_data(llm_response, data_type="json")
            parsed = json.loads(llm_json)
            if not isinstance(parsed, dict):
                raise ValueError("Not a JSON object")
        except Exception as exc:
            self.logger.log_error(exc, {"response": llm_response}, target_dir=logging_dir)
            parsed = {}

        observation = str(parsed.get("observation", "") or "").strip()
        subtask = str(parsed.get("subtask", "") or "").strip()
        rationale = str(parsed.get("rationale", "") or "").strip()

        # If LLM didn't output "subtask", fall back to the expected subtask
        if not subtask and subtask_plan:
            if current_subtask_idx < len(subtask_plan):
                st = subtask_plan[current_subtask_idx]
                subtask = f"Subtask {st['id']}: {st['name']}"
            elif len(subtask_plan) > 0:
                subtask = "Task completed"

        result = {
            "observation": observation,
            "subtask": subtask,
            "progress": progress,
            "changed_elements": changed_elements,
            "rationale": rationale,
        }

        # Log full observer output for debugging
        try:
            log_path = os.path.join(logging_dir, "rule_observer_output.json")
            with open(log_path, "w") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        return result
    
    def reflect(self, before_screenshot: ImageSource, after_screenshot: ImageSource, prev_action: str, expectation: str, logging_dir: str = ".cache", current_subtask: str = "", action_history: list | None = None, task: str = "", after_ui_text: str = "", before_ui_text: str = ""):
        """Reflection method — compare before and after screenshots to verify action success
        and determine if the current subtask is fully complete.

        Args:
            before_screenshot: Screenshot BEFORE action execution.
            after_screenshot: Screenshot AFTER action execution.
            prev_action: The action that was executed.
            expectation: The expected outcome of the action.
            logging_dir: Directory for debug logs.
            current_subtask: Description of the current subtask being worked on.
                Also used to determine whether the entire subtask is now complete.
            action_history: Full action history for detecting loops and patterns.
            task: The overall task instruction to help Reflection understand the goal.
            after_ui_text: UI element text from accessibility tree (AFTER screenshot).
            before_ui_text: UI element text from accessibility tree (BEFORE screenshot).
        """

        # ROIDiff: quantitative pixel-level change detection
        progress = "uncertain"
        changed_elements = ""
        self._roidiff.reset()
        self._roidiff.set_previous(before_screenshot)
        diff = self._roidiff.compute(after_screenshot)
        roidiff_score = diff.get("mean_score", 0.0)
        regions = diff.get("regions_used", [])
        if roidiff_score > self.progress_threshold:
            progress = "progress"
        elif roidiff_score < 0.005:
            progress = "no_change"
        else:
            progress = "uncertain"

        # Changed elements summary (pixel diff only)
        changed_parts = [f"diff={roidiff_score:.0%}"]
        if not regions:
            changed_parts.append("no_regions")
        changed_elements = "; ".join(changed_parts)

        # Screen text from Android accessibility tree
        after_screen_text = after_ui_text or ""
        before_screen_text = before_ui_text or ""

        print(f"Reflection ROIDiff: progress={progress}, score={roidiff_score:.2%}, changed_elements={changed_elements}")
        print(f"Reflection UI tree (after): {after_screen_text[:200]}")
        
        system_prompt = (
            "You are a strict VERIFICATION agent in a GUI test benchmark. "
            "You are given TWO screenshots (BEFORE and AFTER), "
            "PLUS UI element text from the Android accessibility tree.\n"
            "Your job: determine whether the test action succeeded and whether the test subtask is complete.\n\n"
            "=== SUCCESS FORMULA (MUST satisfy BOTH) ===\n"
            "  success = VISUAL_MATCH(what the AFTER screenshot looks like) "
            "AND CONTENT_MATCH(what text/content the AFTER page shows)\n\n"
            "  VISUAL_MATCH: The AFTER screenshot MUST look like the EXACT screen described in the Expected Outcome. "
            "Imagine the Expected Outcome describes a specific screen — the AFTER screenshot must visually match THAT expected screen, "
            "not just 'some different screen' or 'any screen that changed'. "
            "If Expected Outcome says 'Settings page is shown', then AFTER must show a Settings page; "
            "showing a Home page or any other page is VISUAL_MATCH failure, even if the screen changed.\n"
            "  CONTENT_MATCH: The AFTER page's actual content (UI elements, text, labels, buttons) "
            "matches what the Expected Outcome says should appear. "
            "Extract key nouns from Expected Outcome and verify each one is present in the AFTER UI elements.\n\n"
            "If EITHER dimension fails → overall FAILURE.\n"
            "  - Screen changed but to a WRONG/UNEXPECTED page → FAILURE (visual mismatch, not the expected screen).\n"
            "  - Screen looks different but content is unrelated → FAILURE (content mismatch).\n"
            "  - Content seems related but visual state doesn't match expectation → FAILURE (visual mismatch).\n"
            "  - Both match the Expected Outcome → SUCCESS.\n"
            "=== END FORMULA ===\n\n"
            "RULES:\n"
            "1. CONTENT_MATCH is the MORE COMMON failure mode. ALWAYS check it first. "
            "Example: Expected 'search bar focused with keyboard' but AFTER UI elements only show "
            "'AMC-Theatres, Barnes-Noble, CVS-Pharmacy' cards → content is completely UNRELATED → FAILURE, "
            "even if the screen changed (pixel change ≠ content match).\n"
            "2. **If Pixel Change Detection = 'no_change', the action MUST be failure.** "
            "No pixel change means the action had no visible effect on the screen, so success=false. "
            "The only exception is when Expected Outcome explicitly says 'nothing visible changes'.\n"
            "3. Pixel change alone does NOT mean success. Changing to a different/UNRELATED page is FAILURE.\n"
            "4. **BEFORE/AFTER IDENTITY CHECK (CRITICAL):** If AFTER looks essentially the SAME as BEFORE, "
            "but the Expected Outcome describes a VISIBLE CHANGE (e.g., item removed, page navigated, text entered), "
            "then the action FAILED — the expected change did NOT happen. "
            "Example: Expected 'recipe list is shown' but AFTER still shows the recipe detail page "
            "same as BEFORE → the expected navigation did NOT occur → FAILURE. "
            "Do NOT say 'consistent with previous state = completed'.\n"
            "5. Do NOT assume success from prior knowledge — only judge what you SEE and what UI text shows.\n"
            "6. If Expected Outcome says 'nothing visible changes', then no change = success.\n"
            "7. Be conservative: when in doubt, report failure with low confidence.\n"
            "8. In 'reason', you MUST state: (a) which key nouns from Expected Outcome you checked, "
            "(b) whether each was FOUND or NOT FOUND in AFTER UI elements, "
            "(c) your VISUAL_MATCH and CONTENT_MATCH verdicts, "
            "(d) whether the expected CHANGE (if any) actually occurred in AFTER compared to BEFORE.\n"
            "IMPORTANT: Analyze and explain your reasoning FIRST in the 'reason' field, "
            "then set 'success' and 'subtask_complete' based on your own analysis. "
            "If your explanation concludes the action failed, success MUST be false."
        )
        output_format = """
    ```json
        {
            "reason": "VISUAL_MATCH: [yes/no because AFTER screen looks/does not look like the expected screen]; CONTENT_MATCH: [yes/no, key nouns: X=FOUND, Y=NOT FOUND]; Conclusion: action succeeded/failed because ...",
            "success": true/false,
            "subtask_complete": true/false,
            "suggested_next_step": "A natural language action description (do NOT include coordinates)",
            "confidence": 0.0-1.0
        }
    ```
        """
        subtask_hint = f"Current subtask: {current_subtask}\n" if current_subtask else ""
        history_hint = ""
        if action_history:
            # 取最近 5 步动作历史，帮助检测循环
            recent = action_history[-5:]
            history_lines = []
            for i, h in enumerate(recent):
                history_lines.append(f"  step -{len(recent)-i}: {str(h).strip()}")
            history_hint = "Action history (most recent first):\n" + "\n".join(history_lines) + "\n\n"
        task_hint = f"Overall task: {task}\n" if task else ""

        # Build screen text hint section
        screen_text_hint = ""
        if after_screen_text:
            before_text_section = ""
            if before_screen_text:
                before_text_section = f"\nUI elements on BEFORE screenshot: {before_screen_text}\n"
            screen_text_hint = (
                f"UI elements on AFTER screenshot (from accessibility tree): {after_screen_text}\n"
                f"{before_text_section}\n"
                "TEXT VERIFICATION RULES (MANDATORY — follow step by step):\n"
                "Step 1: Extract KEY NOUNS from the 'Expected outcome:' above. "
                "Example: 'The keyboard appears and the search bar is focused' → key nouns = [keyboard, search bar, focused].\n"
                "Step 2: For EACH key noun, check whether it appears in the AFTER UI elements list. "
                "Mark each as FOUND or NOT FOUND.\n"
                "Step 3: If ALL key nouns are NOT FOUND in AFTER UI elements, the expected content "
                "is NOT on screen → this is FAILURE, regardless of pixel changes.\n"
                "Step 4: If some key nouns are found but the OVERALL content does not match the Expected Outcome, "
                "it is still FAILURE. Example: Expected 'Phone search results' but AFTER UI shows unrelated cards "
                "like 'AMC-Theatres, Barnes-Noble' — FAILURE even if 'search' keyword appears somewhere.\n"
                "- The UI elements above are from the Android accessibility tree — they are EXACT text, "
                "labels, and button names visible on screen.\n"
                "- If BEFORE and AFTER UI elements are nearly identical, the action likely had no visible effect → failure.\n"
                "- MERE PRESENCE of vaguely related keywords is NOT enough if the expected SPECIFIC content "
                "is missing (e.g., expected 'Settings page' but UI shows 'Home page' → failure).\n"
                "- You MUST list the key nouns you checked and their FOUND/NOT FOUND status in your 'reason' field.\n\n"
            )
        else:
            screen_text_hint = "Screen text: not available — rely on visual inspection only.\n\n"

        reflection_prompt = (
            f"Previous action: {prev_action}\n"
            f"Expected outcome: {expectation}\n\n"
            f"{subtask_hint}"
            f"{task_hint}"
            f"{history_hint}"
            f"Pixel Change Detection: {progress} (diff_score={roidiff_score:.2%})\n"
            f"Changed Elements: {changed_elements}\n\n"
            f"{screen_text_hint}"
            "You are given TWO screenshots:\n"
            "  - BEFORE (image 1): the UI state JUST BEFORE the action was executed\n"
            "  - AFTER  (image 2): the UI state JUST AFTER the action was executed\n\n"
            "Compare the two images carefully. Determine:\n"
            "1) Whether the expected outcome was achieved (success).\n"
            "2) Whether the CURRENT SUBTASK is now fully complete (subtask_complete). "
            "A subtask may require multiple steps (e.g., 'enter formula' = click cell + type + press enter).\n"
            "Only set subtask_complete=true if the after screenshot shows the subtask goal has been fully achieved.\n\n"
            "IMPORTANT — success requires BOTH visual AND content match with 'Expected outcome:':\n"
            "- VISUAL: Does the AFTER screenshot look EXACTLY like the screen described in Expected Outcome? "
            "The AFTER screenshot must match the EXPECTED screen, not just 'any changed screen'. "
            "If Expected Outcome says 'Settings page is shown' but AFTER shows a Home page → VISUAL mismatch → FAILURE.\n"
            "- CONTENT: Does the AFTER page show the specific text/labels/buttons mentioned in Expected Outcome? "
            "Extract key nouns from Expected Outcome, check each against AFTER UI elements. "
            "If key expected content (e.g., 'keyboard', 'search bar', 'Phone results') is ABSENT from "
            "AFTER UI elements → CONTENT mismatch → FAILURE, even if screen changed.\n"
            "- Example of FAILURE: Expected 'search bar focused, keyboard appears' but AFTER UI shows "
            "'AMC-Theatres, Barnes-Noble cards' — screen content is UNRELATED to expectation → FAILURE.\n"
            "- If screen changed but the new content does NOT match Expected Outcome → FAILURE.\n"
            "- If NO visible change → failure (unless Expected Outcome says 'no change').\n"
            "- **CRITICAL: BEFORE vs AFTER comparison** — If AFTER looks essentially the SAME as BEFORE, "
            "but Expected Outcome describes a visible change (item removed, page switched, text entered, etc.), "
            "the action FAILED. The expected change did NOT happen. "
            "Example: Expected 'recipe list is shown' but AFTER still shows the recipe detail page "
            "identical to BEFORE → the expected navigation did NOT occur → FAILURE. "
            "'Same as before' is NEVER success when a change was expected.\n"
            "**CRITICAL for suggested_next_step**:\n"
            "When the action FAILED, identify the MISSING PREREQUISITE.\n"
            "Set 'suggested_next_step' to a **SINGLE atomic step in natural language** that describes "
            "exactly one operation to fix the missing prerequisite. Do NOT chain multiple actions "
            "(e.g., output 'Right-click the zip file' not 'Right-click and select Extract All'). "
            "This should read like the Planner's Action field. "
            "Do NOT include coordinates. A downstream component handles grounding.\n\n"
            "When the action SUCCEEDED:\n"
            "  - If the overall task / prerequisite issue is NOW FULLY RESOLVED (nothing more to fix),\n"
            "    set suggested_next_step to empty string.\n"
            "  - If the action succeeded but MORE RECOVERY STEPS are still needed,\n"
            "    set suggested_next_step to the NEXT step.\n\n"
            f"Output JSON exactly as:\n{output_format}\n"
        )
        user_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": reflection_prompt},
                    {"type": "image_url", "image_url": {"url": before_screenshot}},
                    {"type": "image_url", "image_url": {"url": after_screenshot}},
                ],
            }
        ]
        response,_=run_llm(
           messages=user_messages,
            system=system_prompt,
            llm=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            api_keys=self.api_keys,
            response_format={"type": "json_object"},
            use_thinking=True,
        )
        self.logger.log_text(response, "rule_observer_reflection_response.log", logging_dir)
        try:
            llm_json = extract_data(response, data_type="json")
            parsed = json.loads(llm_json)
            if not isinstance(parsed, dict):
                raise ValueError("Not a JSON object")
        except Exception as exc:
            self.logger.log_error(exc, {"response": response}, target_dir=logging_dir)
            parsed = {"success": False, "subtask_complete": False, "reason": "Failed to parse LLM response", "confidence": 0.0}

        self.logger.log_text(reflection_prompt, "rule_observer_reflection.log", logging_dir)
        parsed["progress"] = progress
        parsed["changed_elements"] = changed_elements
        parsed["roidiff_score"] = roidiff_score

        # ROIDiff no_change → 强制判定失败（除非 expectation 明确说"无变化"）
        if progress == "no_change":
            expectation_lower = (expectation or "").lower()
            no_change_keywords = ["nothing visible", "no change", "no visible change", "same page", "remain", "stay"]
            expects_no_change = any(kw in expectation_lower for kw in no_change_keywords)
            if not expects_no_change and parsed.get("success", False):
                print(f"[Reflection Override] ROIDiff=no_change but LLM said success → forcing failure")
                parsed["success"] = False
                parsed["subtask_complete"] = False
                original_reason = parsed.get("reason", "")
                parsed["reason"] = (
                    f"VISUAL_MATCH: no (ROIDiff detected no pixel change); "
                    f"CONTENT_MATCH: no (screen unchanged); "
                    f"Override: {original_reason}"
                )

        return parsed

    def reset(self) -> None:
        """Clear internal state for a new task."""
        self._roidiff.reset()

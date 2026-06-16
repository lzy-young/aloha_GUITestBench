"""BugDetector — checks tap target validity, then analyzes real bugs via LLM.

Receives the same context as Reflector (UI tree text, ROIDiff signal)
to make accurate bug classification decisions.
"""

import json
from typing import Dict

from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.llm.run_llm import run_llm
from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.llm.llm_utils import extract_data
from GUIAgent.Aloha_Act.ui_aloha.act.utils.logger_utils import LoggerUtils


class BugDetector:
    """Checks if a tap landed on a valid UI element, and if so, analyzes the bug."""

    def __init__(
        self,
        model: str,
        max_tokens: int = 1024,
        api_keys: dict | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.api_keys = api_keys or {}
        self.logger = LoggerUtils(component_name="bug_detector")

    @staticmethod
    def check_hit(position: list, ui_elements: list) -> tuple:
        """Return (hit: bool, element_name: str).

        hit=True if tap landed on a valid UI element, False if empty space.
        element_name is the text/description of the element hit.
        """
        if not position or len(position) < 2:
            return True, ""
        if not ui_elements:
            return True, ""
        x, y = position[0], position[1]
        for el in ui_elements:
            inner = getattr(el, 'ui_element', el)
            ex1 = getattr(inner, 'x1', 0) or (hasattr(inner, 'bbox_pixels') and inner.bbox_pixels.x_min) or 0
            ey1 = getattr(inner, 'y1', 0) or (hasattr(inner, 'bbox_pixels') and inner.bbox_pixels.y_min) or 0
            ex2 = getattr(inner, 'x2', 0) or (hasattr(inner, 'bbox_pixels') and inner.bbox_pixels.x_max) or 0
            ey2 = getattr(inner, 'y2', 0) or (hasattr(inner, 'bbox_pixels') and inner.bbox_pixels.y_max) or 0
            if ex1 <= x <= ex2 and ey1 <= y <= ey2:
                name = (inner.text or inner.content_description or getattr(inner, 'class_name', '') or "")
                return True, name
        return False, "empty space"

    def analyze(
        self,
        before_screenshot: str,
        after_screenshot: str,
        prev_action: str,
        expectation: str,
        task: str = "",
        ui_elements: list | None = None,
        tap_position: list | None = None,
        after_ui_text: str = "",
        before_ui_text: str = "",
        roidiff_progress: str = "uncertain",
        roidiff_score: float = 0.0,
    ) -> Dict[str, str]:
        """Analyze action failure.

        First checks if the tap hit a valid UI element.
        If miss → returns operation_error.
        If hit → calls LLM to classify as GUI_BUG or agent_error.

        Args:
            after_ui_text: UI element text from accessibility tree (AFTER screenshot).
            before_ui_text: UI element text from accessibility tree (BEFORE screenshot).
            roidiff_progress: ROIDiff change detection result ("progress"/"no_change"/"uncertain").
            roidiff_score: ROIDiff pixel diff score (0.0-1.0).

        Returns:
            {"failure_type": str, "bug_description": str, "confidence": float}
            failure_type: "operation_error" | "GUI_BUG" | "agent_error"
        """
        # Step 1: check_hit — deterministic (empty space = fast path)
        if tap_position and ui_elements is not None:
            hit_ok, hit_name = self.check_hit(tap_position, ui_elements)
            if not hit_ok:
                return {"failure_type": "operation_error",
                        "bug_description": "Tap landed on empty space",
                        "confidence": 1.0}
            if hit_name:
                prev_action = f"{prev_action} | Reached element: '{hit_name}'"

        # Step 2: LLM analysis — is this a real GUI bug or an executor error?
        system_prompt = (
            "You are a GUI Defect Verification Expert in a test benchmark. "
            "You are given TWO screenshots (BEFORE and AFTER an action was executed) "
            "plus UI element text from the accessibility tree.\n"
            "The BEFORE screenshot has a RED CIRCLE marker showing where the agent tapped.\n\n"
            "Your task: determine whether the agent encountered a real GUI defect, "
            "or whether the action's failure is due to an execution error by the agent.\n\n"
            "=== VERIFICATION CHECKLIST ===\n"
            "You MUST explicitly verify each of the following:\n\n"
            "1. Target Check: Did the agent tap the CORRECT UI element?\n"
            "   - Compare the red circle location with what 'Previous action' describes.\n"
            "   - If it hit a different element (e.g., tapped 'Edit' instead of 'Delete') → EXECUTOR_ERROR.\n\n"
            "2. Response Check: Did the app actually respond to the tap?\n"
            "   - If BEFORE and AFTER screenshots are identical (no pixel change, no UI text change) → the app did NOT respond. This could be GUI_BUG (the element is broken) OR EXECUTOR_ERROR (the element was not interactive).\n"
            "   - If the screen changed → the app DID respond. Go to step 3.\n\n"
            "3. Result Check: Does the AFTER screen match the Expected Outcome?\n"
            "   - Extract key nouns from Expected Outcome and verify against AFTER UI elements.\n"
            "   - If AFTER screen shows clearly WRONG behavior (wrong page, error dialog, incorrect data) that matches a defect pattern → GUI_BUG.\n"
            "   - If AFTER screen changed but the result is reasonable / expected → EXECUTOR_ERROR (the action didn't fail, the expectation was wrong).\n"
            "   - If the app navigated to a TOTALLY UNRELATED page → GUI_BUG (likely a navigation defect).\n\n"
            "=== FINAL VERDICT ===\n"
            "- **GUI_BUG**: The app exhibited defective behavior (wrong response, crash, unresponsive element, navigation error, unexpected content). This is a REAL defect in the app.\n"
            "- **EXECUTOR_ERROR**: The failure is due to the agent (tapped wrong element, bad timing, invalid expectation). NOT a real app defect.\n\n"
            "=== BUG TYPE (only when GUI_BUG) ===\n"
            "Classify the defect into one of these categories:\n"
            "- **ONR** (Object Not Responding): The app did NOT react at all (no screen change, no UI text change).\n"
            "- **UTR** (Unexpected Text Response): The app responded but showed wrong/unexpected content on the same or related page.\n"
            "- **NLE** (Navigation to Lost/Erroneous screen): The app navigated to a completely unrelated page.\n"
            "If agent_error, set bug_type to an empty string.\n\n"
            "=== IMPORTANT NOTES ===\n"
            "1. Be Strict: Do not assume the app has a bug just because the action failed. First rule out agent error.\n"
            "2. Action Matters: If the red circle landed on a WRONG element (not what the action described), it is EXECUTOR_ERROR regardless of what the app did.\n"
            "3. Pixel Change Detection alone is NOT enough to classify as GUI_BUG. Screen changing could mean the agent navigated to a valid but wrong page — that is still EXECUTOR_ERROR.\n\n"
            "In 'bug_description', state your checklist reasoning:\n"
            "- Target: [correct/wrong, element name]\n"
            "- Response: [changed/unchanged]\n"
            "- Result: [matches expectation / wrong behavior / unrelated page]\n"
            "- Type: [ONR / UTR / NLE] (bug category, empty if agent_error)\n"
            "- Verdict explanation\n\n"
            "In 'bug_summary', provide a concise, human-readable description of the defect:\n"
            "- If GUI_BUG: Describe WHAT went wrong in 1-2 sentences (e.g., 'Tapped the Delete button but the recipe was not removed — the delete function does not work')\n"
            "- If agent_error: Keep it brief (e.g., 'Agent tapped Edit instead of Delete')"
        )

        output_format = """
        {
            "failure_type": "GUI_BUG" | "agent_error",
            "bug_type": "ONR" | "UTR" | "NLE" | "",
            "bug_description": "Target: [...]; Response: [...]; Result: [...]; Type: [...]; Verdict: ...",
            "bug_summary": "One concise sentence describing the bug or agent error",
            "confidence": 0.0-1.0
        }
"""

        task_hint = f"Overall task: {task}\n" if task else ""

        # UI text section
        ui_text_hint = ""
        if after_ui_text:
            before_text_section = ""
            if before_ui_text:
                before_text_section = f"\nUI elements on BEFORE screenshot: {before_ui_text}\n"
            ui_text_hint = (
                f"UI elements on AFTER screenshot (from accessibility tree): {after_ui_text}\n"
                f"{before_text_section}\n"
                "- Compare AFTER UI elements against 'Expected outcome:' to check content relevance.\n"
                "- If Expected Outcome mentions specific labels/text, verify they appear in AFTER UI elements.\n"
                "- If BEFORE and AFTER UI elements are nearly identical, the app likely did not respond.\n\n"
            )
        else:
            ui_text_hint = "Screen text: not available — rely on visual inspection only.\n\n"

        # ROIDiff signal section
        roidiff_hint = (
            f"Pixel Change Detection: {roidiff_progress} (diff_score={roidiff_score:.2%})\n"
        )
        if roidiff_progress == "progress":
            roidiff_hint += (
                "The pixels DID change significantly → the app DID respond. "
                "Focus on whether the response is correct behavior or defective.\n\n"
            )
        elif roidiff_progress == "no_change":
            roidiff_hint += (
                "The pixels did NOT change → the app may NOT have responded. "
                "Consider whether the tapped element was broken (GUI_BUG) or non-interactive (EXECUTOR_ERROR).\n\n"
            )
        else:
            roidiff_hint += "Pixel change is uncertain — use visual and text comparison.\n\n"

        user_text = (
            f"Previous action: {prev_action}\n"
            f"Expected outcome: {expectation}\n"
            f"{task_hint}"
            f"{roidiff_hint}"
            f"{ui_text_hint}"
            "Analyze the TWO screenshots (BEFORE with red circle, AFTER result) "
            "using the verification checklist above. Determine if this is a GUI_BUG or agent_error."
            f"Output JSON: {output_format}"
        )
        user_messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": before_screenshot}},
                    {"type": "image_url", "image_url": {"url": after_screenshot}},
                ],
            }
        ]

        response, _ = run_llm(
            messages=user_messages,
            system=system_prompt,
            llm=self.model,
            max_tokens=self.max_tokens,
            temperature=0,
            api_keys=self.api_keys,
            response_format={"type": "json_object"},
            use_thinking=True,
        )
        self.logger.log_text(response, "bug_detector_response.log", ".cache")

        try:
            llm_json = extract_data(response, data_type="json")
            parsed = json.loads(llm_json)
            if not isinstance(parsed, dict):
                raise ValueError("Not a JSON object")
        except Exception:
            parsed = {"failure_type": "agent_error",
                      "bug_type": "",
                      "bug_description": "Failed to parse bug analysis",
                      "bug_summary": "Failed to parse bug analysis",
                      "confidence": 0.0}

        # Step 3: Code-level override — ROIDiff no_change + GUI_BUG is contradictory
        failure_type = parsed.get("failure_type", "agent_error")
        if roidiff_progress == "no_change" and failure_type == "GUI_BUG":
            print(f"[BugDetector Override] ROIDiff=no_change but LLM said GUI_BUG → overriding to agent_error")
            parsed["failure_type"] = "agent_error"
            parsed["bug_description"] = (
                f"[Override: no pixel change → likely executor error] "
                f"{parsed.get('bug_description', '')}"
            )

        return {
            "failure_type": parsed.get("failure_type", "agent_error"),
            "bug_type": parsed.get("bug_type", ""),
            "bug_description": parsed.get("bug_description", ""),
            "bug_summary": parsed.get("bug_summary", ""),
            "confidence": float(parsed.get("confidence", 0.0)),
        }

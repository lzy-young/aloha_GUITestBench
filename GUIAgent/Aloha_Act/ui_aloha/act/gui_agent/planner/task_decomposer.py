"""TaskDecomposer — Manager Agent that decomposes user instruction into structured subtask plan."""

import json
from typing import Dict, List

from jinja2 import Environment, FileSystemLoader

from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.llm.run_llm import run_llm
from GUIAgent.Aloha_Act.ui_aloha.act.gui_agent.llm.llm_utils import extract_data
from GUIAgent.Aloha_Act.ui_aloha.act.utils.path_utils import prompt_templates_path
from GUIAgent.Aloha_Act.ui_aloha.act.utils.logger_utils import LoggerUtils


class TaskDecomposer:
    """Manager-level component: decomposes a user instruction into an ordered subtask plan.

    The plan is used by:
      - Observer   → determines current_subtask_idx (match screenshot → subtask)
      - Planner    → knows which subtask stage the agent is in
    """

    def __init__(
        self,
        model: str,
        max_tokens: int = 2000,
        api_keys: dict | None = None,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.api_keys = api_keys or {}
        self.logger = LoggerUtils(component_name="task_decomposer")

        # Jinja2 template environment
        templates_dir = prompt_templates_path()
        self._jinja_env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def decompose(self, task: str, app_name: str = "", reference_trajectory: str = "") -> Dict:
        """Given a user instruction, return a structured plan.

        Args:
            task: The user instruction to decompose.
            app_name: The name of the app that is already open on screen.
            reference_trajectory: Optional trajectory from a similar historical task,
                used as a structural hint for subtask planning.

        Returns:
        {
            "goal": "one-sentence overall goal",
            "subtasks": [
                {"id": 1, "name": "...", "description": "..."},
                ...
            ]
        }
        """
        system_prompt = self._get_system_prompt(app_name=app_name)

        user_text = (
            f"Decompose the following task into subtasks:\n\n{task}\n\n"
            "Output ONLY the JSON object, no other text."
        )

        if reference_trajectory:
            user_text = (
                f"Decompose the following task into subtasks:\n\n{task}\n\n"
                "Here is the action sequence from a similar historical task "
                "(use it as a structural hint for subtask planning, but adapt to the new task):\n"
                f"{reference_trajectory}\n\n"
                "IMPORTANT: Specific values (filenames, URLs, paths, numbers, text to type, search queries) "
                "must reflect the CURRENT task, not the reference.\n"
                "Output ONLY the JSON object, no other text."
            )

        user_messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": user_text}],
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

        self.logger.log_text(llm_response, "task_decomposer_response.log")

        try:
            llm_json = extract_data(llm_response, data_type="json")
            parsed = json.loads(llm_json)
            if not isinstance(parsed, dict) or "subtasks" not in parsed:
                raise ValueError("Missing 'subtasks' in response")
            for st in parsed["subtasks"]:
                if "id" not in st:
                    st["id"] = parsed["subtasks"].index(st) + 1
                if "name" not in st:
                    st["name"] = st.get("description", f"subtask_{st['id']}")
            return parsed
        except Exception as exc:
            self.logger.log_error(exc, {"response": llm_response})
            # Fallback: treat the whole task as a single subtask
            return {
                "goal": task,
                "subtasks": [{"id": 1, "name": task, "description": task}],
            }

    def _get_system_prompt(self, app_name: str = ""):
        return self._jinja_env.get_template("task_decomposer/system.txt").render(
            app_name=app_name,
        )

    @staticmethod
    def format_subtask_plan(plan: Dict) -> str:
        """Format the subtask plan into readable text for prompts."""
        if not plan or "subtasks" not in plan:
            return ""
        lines = [f"Goal: {plan.get('goal', '')}"]
        for st in plan["subtasks"]:
            desc = st.get("description", "")
            desc_part = f" — {desc}" if desc else ""
            lines.append(f"  Subtask {st['id']}: {st['name']}{desc_part}")
        return "\n".join(lines)

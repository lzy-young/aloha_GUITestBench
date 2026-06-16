import base64
import json
import logging
import os
import re
import tempfile
import time
import xml.etree.ElementTree as ET
from http import HTTPStatus
from io import BytesIO
from typing import Dict, List
import openai
import requests
from PIL import Image
from GUIAgent.Aloha_Act.config import config
from GUIAgent.Aloha_Act.ui_aloha.act.utils.app_utils import(
     initialize_agent_components,
    load_api_keys,
)
from GUIAgent.Aloha_Act.ui_aloha.act.utils.visualize_utils import plot_action_vis

from core.data_model import Observation


class AlohaActAdapter:
    name = "Aloha-Act"
    logname = "aloha_act"

    def __init__(self, task: str, app_name: str):

        self.task = task
        self.app_name = app_name
        self.trace_dir= config.get("trace_dir", "GUIAgent/Aloha_Act/trace_data")
        self.api_keys = load_api_keys("GUIAgent/Aloha_Act/config/api_keys.json")
        self.agent_model=initialize_agent_components(config, self.trace_dir, self.api_keys)
        self.trace = []
        self.screen_width = 1080
        self.screen_height = 2400
        self.action_history = []
        self.task_id = f"{app_name}_{self.task[:30]}"
        self._cached_skill_guidance = ""
        self._cached_subgoals = []
        self._cached_subtask_plan = {"goal": "", "subtasks": []}
        self._cached_subtask_plan_text = ""
        self._cached_trajectory = ""
        # 反思 + 重试状态
        self._prev_screenshot = None
        self._prev_plan_action = None
        self._prev_expectation = None
        self._prev_actor_output = None 
        self._prev_plan_details = None
        self._retry_count = 0
        self._max_retries = 2
        self._last_action_failed = False
        self._last_reflection_reason = ""
        self._consecutive_fail_count = 0
        self._suggested_next_step = ""
        self._recovery_mode = False
        self.client_password = ""
        self._prev_observation = None
        self._reported_bugs = set()
        self._current_subtask_idx = 0


    def read_image(self, image_path: str) -> bytes:
        self.screen_width, self.screen_height = Image.open(image_path).size
        with open(image_path, "rb") as img_file:
            return (img_file.read())

    @staticmethod
    def _format_ui_text(text_desc) -> str:
        """将 UI 元素描述格式化为纯文字字符串，供 reflect 使用。"""
        if not text_desc:
            return ""
        if isinstance(text_desc, str):
            return text_desc
        if isinstance(text_desc, list):
            # SeeActElement 列表 → 提取 description
            parts = []
            for el in text_desc:
                if hasattr(el, "description"):
                    parts.append(el.description)
                elif isinstance(el, str):
                    parts.append(el)
            return " | ".join(parts)
        return str(text_desc)

    def call(self, observation: Observation) -> list[str]:
        instruction = self.task
        # experience_table=self.agent_model['experience_table']
        observer=self.agent_model['observer']
        planner=self.agent_model['planner']
        actor=self.agent_model['actor']
        task_decomposer=self.agent_model['task_decomposer']
        # ================================================================
        # Step 0 (first step only): 任务分解 — Manager Agent 生成 subtask plan
        # ================================================================
        if not self.action_history:
            # self._cached_trajectory = experience_table.retrieve_trajectory(instruction)
            subtask_plan = task_decomposer.decompose(instruction, app_name=self.app_name, reference_trajectory=self._cached_trajectory)
            self._cached_subtask_plan = subtask_plan
            self._cached_task_goal = subtask_plan.get("goal", instruction)
        else:
            subtask_plan = self._cached_subtask_plan

        task_goal = self._cached_task_goal

        actions = []

        # ================================================================
        # Step 1+: 对上一步动作做反思验证（跳过第一步）
        # 当前 obs['screenshot'] 是上一步执行后的截图
        # self._prev_screenshot 是上一步执行前的截图（带红色叉号标记）
        # 传入前后两张截图做对比
        # ================================================================
        reflection_signal = {}
        if self._prev_plan_action is not None and self._prev_expectation is not None:
            current_subtask_desc = ""
            print("start reflection")
            # 获取 UI 元素文字描述（来自 Android 无障碍树）
            after_ui_text = self._format_ui_text(observation.text_desc)
            before_ui_text = self._format_ui_text(self._prev_observation.text_desc) if self._prev_observation else ""

            reflection = self.agent_model['observer'].reflect(
                before_screenshot=self._prev_screenshot or self.read_image(observation.image_dir),
                after_screenshot=self.read_image(observation.image_dir),
                prev_action=self._prev_plan_action,
                expectation=self._prev_expectation,
                current_subtask=current_subtask_desc,
                action_history=self.action_history[-10:],
                task=task_goal,
                after_ui_text=after_ui_text,
                before_ui_text=before_ui_text,
            )
            print(f"[Reflection] step: success={reflection.get('success')}, "
                  f"subtask_complete={reflection.get('subtask_complete')}, "
                  f"reason={reflection.get('reason')}")

            reflection_success = reflection.get("success", False)
            reflection_reason = reflection.get("reason", "")
            suggested_next_step = reflection.get("suggested_next_step", "")

            reflection_signal = {
                "success": reflection_success,
                "subtask_complete": reflection.get("subtask_complete", False),
                "reason": reflection_reason,
                "progress": reflection.get("progress", "uncertain"),
                "changed_elements": reflection.get("changed_elements", ""),
            }

            # 子任务完成 → 推进到下一个
            if reflection.get("subtask_complete", False):
                self._current_subtask_idx += 1

            # BugDetector: always run after reflection
            tap_pos = self._prev_actor_output.get("position", []) if self._prev_actor_output else []
            ui_els = self._prev_observation.text_desc if self._prev_observation else None
            bug_info = self.agent_model['bug_detector'].analyze(
                before_screenshot=self._prev_screenshot or self.read_image(observation.image_dir),
                after_screenshot=self.read_image(observation.image_dir),
                prev_action=self._prev_plan_action,
                expectation=self._prev_expectation,
                task=task_goal,
                ui_elements=ui_els,
                tap_position=tap_pos,
                after_ui_text=after_ui_text,
                before_ui_text=before_ui_text,
                roidiff_progress=reflection.get("progress", "uncertain"),
                roidiff_score=reflection.get("roidiff_score", 0.0),
            )
            bug_type = bug_info.get("bug_type", "")
            bug_summary = bug_info.get("bug_summary", "")
            if bug_info.get("failure_type") == "GUI_BUG":
                print(f"[BUG-DETECTED] {bug_type}: {bug_summary}")
                bug_key = f"{bug_type}:{str(self._prev_plan_action or '')}"
                if bug_key not in self._reported_bugs:
                    self._reported_bugs.add(bug_key)
                    self.trace.append({
                        'types': 'BugDetector',
                        'observation': observation.image_dir,
                        'action': {
                            'raw_action': [str(self._prev_plan_action or "")],
                            'actions': [{"action_type": "answer", "text": f"{bug_type}: {bug_summary}"}]
                        }
                    })

            if reflection_success:
                self.action_history[-1] = "[SUCCESS] " + self.action_history[-1]
                self._retry_count = 0
                self._consecutive_fail_count = 0
                self._last_action_failed = False
                self._suggested_next_step = suggested_next_step
            else:
                # === Action failed → retry ===
                self._last_action_failed = True
                self._last_reflection_reason = reflection_reason
                self._suggested_next_step = suggested_next_step
                reason_short = reflection_reason[:120].replace("\n", " ")
                self.action_history[-1] = f"[FAILED: {reason_short}] " + self.action_history[-1]
                self._retry_count += 1
                self._consecutive_fail_count += 1
                print(f"[Reflection] failed ({self._retry_count}/{self._max_retries + 1}): {reflection_reason[:80]}... -> re-planning")

        # 保存当前截图作为下一轮反射的 "before" 截图

        # ================================================================
        # Step 2: 观察 — Observer 分析当前截图（接收 reflection 信号辅助判断 subtask）
        # ================================================================
        observer_result = observer(
                task=task_goal,
                screenshot_path=observation.image_dir,
                subtask_plan=subtask_plan.get("subtasks", []),
                action_history=self.action_history,
                reflection_signal=reflection_signal,
                current_subtask_idx=self._current_subtask_idx,
            )

        observation_hint = observer_result.get("observation", "")
        rationale = observer_result.get("rationale", "")
        if rationale:
            observation_hint += f" | Observer rationale: {rationale}"
        subtask_text = observer_result.get("subtask", "")
        progress = observer_result.get("progress", "")
        changed_elements = observer_result.get("changed_elements", "")

        # 所有子任务完成 → 终止任务
        if subtask_text == "Task completed":
            print(f">>> All subtasks completed. Task finished.")
            actions.append("NOOP")
            return actions

        # 如果上一步反思失败，通知后续流程不要重复相同动作
        if self._last_action_failed:
            observation_hint += f" | ⚠ Reflection: previous action failed — {self._last_reflection_reason} Try a different approach."
            self._last_action_failed = False
            self._last_reflection_reason = ""

        # ================================================================
        # Step 3: 规划 — Planner 决定下一步动作
        # 正常模式：Planner 自主规划
        # Recovery 模式：跳过 Planner，Reflection 的 suggested_next_step 直接作为 Action
        # （Reflection 输出的是原子动作级描述，可直接执行）
        # ================================================================
        if self._suggested_next_step and (self._consecutive_fail_count >= 1 or self._recovery_mode):
            if not self._recovery_mode:
                self._recovery_mode = True
                print(f"[RECOVERY MODE] Entered recovery mode")
            print(f"[RECOVERY MODE] Direct action: {self._suggested_next_step[:100]}...")
            planning = {
                "Observation": observation_hint,
                "Reasoning": (
                    f"Recovery mode. Reflection diagnosed: "
                    f"{self._last_reflection_reason[:200]}. "
                    f"Executing: {self._suggested_next_step}"
                ),
                "Current Step": 0,
                "Current Step Explanation": "Recovery mode — executing prerequisite fix",
                "Action": self._suggested_next_step,
                "Expectation": f"Complete: {self._suggested_next_step}"
            }
            self._suggested_next_step = ""
            self._consecutive_fail_count = 0
        else:
            if self._recovery_mode:
                self._recovery_mode = False
                print(f"[RECOVERY MODE] Exited recovery mode — no more pending fixes")
            # 正常模式：Planner 独立决策
            planning = planner(
                task=instruction,
                screenshot_path=observation.image_dir,
                trajectory=self._cached_trajectory,
                action_history=self.action_history,
                current_subtask=subtask_text,
                observation_hint=observation_hint,
                progress=progress,
                changed_elements=changed_elements,
                client_password=self.client_password,
                ui_text=self._format_ui_text(observation.text_desc),
            )
        
        
        print(planning)

        planning_observation = planning.get('Observation', '')
        planning_next_action = planning.get('Action', '')
        planning_reasoning = planning.get('Reasoning', '')
        curr_traj_step = planning.get('Current Step', 1)
        curr_traj_step_explanation = planning.get('Current Step Explanation', '')
        actor_input = planning

        # ================================================================
        # Step 4: 执行 — Actor 生成可执行代码
        # ================================================================
        model_mode=getattr(actor, "model", "oai-operator")
        action, complete_flag = actor(
            mode=model_mode,
            messages=actor_input,
            screenshot_path=observation.image_dir,
        )
        content = action.get("content", {})
        if isinstance(content, str):
            content = {}

        # 任务完成 → 返回 NOOP 通知环境结束
        act_name = content.get("action") or content.get("action_type", "")
        if act_name in ("STOP", "FINISH"):
            actions.append("NOOP")
            return actions

        android_action = self._to_android(content)
        actions.append(android_action)

        # ================================================================
        # 保存状态供下一轮反思使用
        # ================================================================
        plot_action_vis(content,observation.image_dir,observation.image_dir.replace(".png", "_action_vis.png"))
        self._prev_screenshot = self.read_image(observation.image_dir)
        self._prev_observation = observation
        plan_details = {
            "step_info": curr_traj_step_explanation,
            "observation": planning_observation,
            "reasoning": planning_reasoning,
            "action": planning_next_action
        }
        self._prev_plan_action = planning_next_action
        self._prev_expectation = planning.get('Expectation', '')
        self._prev_actor_output = content
        self._prev_plan_details = plan_details

        self.action_history.append(f"Executing guidance trajectory step [{curr_traj_step}]: {{Plan: {plan_details}, Code: {action}}}\n")

        self.trace.append({
            'types': 'Executor',
            'observation': observation.image_dir,
            'thought': f"{planning_observation}\n{planning_reasoning}",
            'action': {
                'raw_action': [str(planning_next_action)],
                'actions': [json.loads(android_action)]
            }
        })

        return actions


    def _to_android(self, content: dict) -> str:
        action = content.get("action") or content.get("action_type", "")
        position = content.get("position") or []
        value = content.get("value") or content.get("text", "")
        touch_xy = content.get("touch_xy") or []
        lift_xy = content.get("lift_xy") or []
        direction = content.get("direction", "")
        app_name = content.get("app_name", "")
        keycode = content.get("keycode", "")
        mapping = {
            "CLICK": "click",
            "ANSWER": "answer",
            "DOUBLE_CLICK": "double_tap",
            "LONG_PRESS": "long_press",
            "INPUT": "input_text",
            "SCROLL": "scroll",
            "SWIPE": "swipe",
            "DRAG": "drag_and_drop",
            "DRAG_AND_DROP": "drag_and_drop",
            "HOME": "navigate_home",
            "BACK": "navigate_back",
            "OPEN_APP": "open_app",
            "ENTER": "keyboard_enter",
            "PRESS": "press_keyboard",
            "WAIT": "wait",
        }
        android_type = mapping.get(action.upper(), action)
        result = {"action_type": android_type}

        if position and len(position) >= 2:
            result["x"] = int(position[0])
            result["y"] = int(position[1])
        if value and android_type in ("input_text", "answer"):
            result["text"] = value
        if direction:
            result["direction"] = direction
        if touch_xy and len(touch_xy) >= 2:
            result["touch_xy"] = [int(touch_xy[0]), int(touch_xy[1])]
        if lift_xy and len(lift_xy) >= 2:
            result["lift_xy"] = [int(lift_xy[0]), int(lift_xy[1])]
        if app_name:
            result["app_name"] = app_name
        if keycode and android_type == "press_keyboard":
            result["keycode"] = keycode

        return json.dumps(result, ensure_ascii=False)

    def extract_steps(self) -> list:
        return self.trace

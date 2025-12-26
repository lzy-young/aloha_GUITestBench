import re
import json

# ------------- manager use func -------------
def extract_dict_from_string(s: str) -> dict:
    match = re.search(r'\{.*\}', s, re.DOTALL)
    if not match:
        raise ValueError("No dictionary-like JSON found in the string")

    json_str = match.group(0)
    try:
        data = json.loads(json_str)
        return data
    except json.JSONDecodeError as e:
        raise ValueError(f"Failed to decode JSON: {e}") from e


def parse_plan(plan_result: str) -> dict:
    """
        {
            "plan": [
                {
                    "name": "Navigate to Login Page",
                    "info": "Open the web browser and go to http://example.com/login.",
                    "expectation": "The login page with 'Username' and 'Password' textboxes is displayed.",
                    "possible_flaws": [
                        "The login button may not trigger any action when clicked.",
                        "The login page might not load correctly, leading to a blank or error page."
                    ]
                },
                ...
            ]
        }
    """
    plan = extract_dict_from_string(plan_result)['plan']
    plan_list = []
    for subplan in plan:
        instruct = subplan.get("name", None)
        description = subplan.get("info", None)
        expectation = subplan.get("expectation", None)
        possible_flaws = subplan.get("possible_flaws", None)
        plan_list.append({
            "task": instruct + "\n\n" + description,
            "expectation": expectation,
            "possible_flaws": possible_flaws
        })
    return plan_list
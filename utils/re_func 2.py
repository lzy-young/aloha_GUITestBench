import re

def extract_ins_content(text: str) -> list[str]:
    
    pattern = r"<ins>(.*?)</ins>"
    return re.findall(pattern, text, flags=re.DOTALL)

def extract_think_content(text: str) -> list[str]:
    
    pattern = r"<think>(.*?)</think>"
    return re.findall(pattern, text, flags=re.DOTALL)

def extract_answer_content(text: str) -> list[str]:
   
    pattern = r'<answer>(.*?)</answer>'
    return re.findall(pattern, text, flags=re.DOTALL)

def extract_action_content(text: str) -> str:
    match = re.search(r"Action: (.+)", text)
    if match:
        return match.group(1).strip()
    else:
        raise ValueError("No 'Action:' found in text")

def extract_json_dict(text: str):
    
    
    markdown_pattern = re.compile(r'```(?:json)?\s*(.*?)\s*```', re.DOTALL)
    markdown_match = markdown_pattern.search(text)
    
    if markdown_match:
        
        text = markdown_match.group(1)
    
   
    def find_json_bounds(s):
        
        start_idx = s.find('{')
        if start_idx == -1:
            return None, None
        
        brace_count = 0
        in_string = False
        escape_next = False
        
        for i in range(start_idx, len(s)):
            char = s[i]
            
            
            if escape_next:
                escape_next = False
                continue
            
            if char == '\\':
                escape_next = True
                continue
            
            
            if char == '"':
                in_string = not in_string
                continue
            
            
            if not in_string:
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    
                    if brace_count == 0:
                        return start_idx, i + 1
        
        return None, None
    
    start, end = find_json_bounds(text)
    
    if start is None or end is None:
        raise ValueError("No valid JSON dict found in the text. ")
    
    json_str = text[start:end].strip()
    
    
    return json_str
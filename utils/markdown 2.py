def path2code_tag(path: str) -> str:
    checklist = {
        "typescript jsx": ['.tsx'],
        "typescript": ['.ts'],
        "jsx": ['.jsx'],
        "javascript": ['.js'],
        "python": ['.py'],
    }
    for tag in checklist:
        for suffix in checklist[tag]:
            if path.endswith(suffix):
                return tag
    return ''

markdown_split_line = '\n\n---\n\n'

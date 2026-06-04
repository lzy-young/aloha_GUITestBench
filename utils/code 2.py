import pyparsing

def remove_comments(code: str):
    op = pyparsing.cppStyleComment.suppress()
    return op.transformString(code)
import difflib
from typing import Optional, Any

from api.types import Code


class GitStyleDiffer:
    

    def __init__(self):
        pass

    def diff_repositories(self, repo1: list[Code], repo2: list[Code],
                          context_lines: int = 3) -> str:
        
        repo1_dict = {code.path: code.content for code in repo1}
        repo2_dict = {code.path: code.content for code in repo2}

        all_paths = sorted(set(repo1_dict.keys()) | set(repo2_dict.keys()))

        diff_parts = []

        for path in all_paths:
            content1 = repo1_dict.get(path)
            content2 = repo2_dict.get(path)

            file_diff = self._diff_single_file(path, content1, content2, context_lines)
            if file_diff:
                diff_parts.append(file_diff)

        return '\n\n'.join(diff_parts)  

    def _diff_single_file(self, path: str, content1: Optional[str],
                          content2: Optional[str], context_lines: int) -> str:
        
        if content1 is None and content2 is None:
            return ""

        if content1 is None:
            
            return self._format_new_file(path, content2)

        if content2 is None:
            
            return self._format_deleted_file(path, content1)

        if content1 == content2:
            return ""

        
        return self._format_modified_file(path, content1, content2, context_lines)

    def _format_new_file(self, path: str, content: str) -> str:
        
        lines = content.splitlines()
        result = [
            f"diff --git a/{path} b/{path}",
            "new file mode 100644",
            f"index 0000000..{self._generate_hash(content)[:7]}",
            "--- /dev/null",
            f"+++ b/{path}",
            f"@@ -0,0 +1,{len(lines)} @@"
        ]

        for line in lines:
            result.append(f"+{line}")

        return '\n'.join(result)

    def _format_deleted_file(self, path: str, content: str) -> str:
        """格式化删除的文件"""
        lines = content.splitlines()
        result = [
            f"diff --git a/{path} b/{path}",
            "deleted file mode 100644",
            f"index {self._generate_hash(content)[:7]}..0000000",
            f"--- a/{path}",
            "+++ /dev/null",
            f"@@ -1,{len(lines)} +0,0 @@"
        ]

        for line in lines:
            result.append(f"-{line}")

        return '\n'.join(result)

    def _format_modified_file(self, path: str, content1: str, content2: str,
                              context_lines: int) -> str:
        
        lines1 = content1.splitlines()
        lines2 = content2.splitlines()

        
        diff_lines = list(difflib.unified_diff(
            lines1,
            lines2,
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            n=context_lines,
            lineterm=''
        ))

        if not diff_lines:
            return ""

        
        result = [
            f"diff --git a/{path} b/{path}",
            f"index {self._generate_hash(content1)[:7]}..{self._generate_hash(content2)[:7]} 100644"
        ]
        result.extend(diff_lines)

        return '\n'.join(result)

    def _generate_hash(self, content: str) -> str:
        
        import hashlib
        return hashlib.sha1(content.encode('utf-8')).hexdigest()

    def get_stats(self, repo1: list[Code], repo2: list[Code]) -> dict[str, Any]:
        
        repo1_dict = {code.path: code.content for code in repo1}
        repo2_dict = {code.path: code.content for code in repo2}

        all_paths = set(repo1_dict.keys()) | set(repo2_dict.keys())

        stats = {
            'files_changed': 0,
            'insertions': 0,
            'deletions': 0,
            'added_files': [],
            'deleted_files': [],
            'modified_files': []
        }

        for path in all_paths:
            content1 = repo1_dict.get(path)
            content2 = repo2_dict.get(path)

            if content1 is None:
                
                stats['added_files'].append(path)
                stats['files_changed'] += 1
                stats['insertions'] += len(content2.splitlines())
            elif content2 is None:
                
                stats['deleted_files'].append(path)
                stats['files_changed'] += 1
                stats['deletions'] += len(content1.splitlines())
            elif content1 != content2:
                
                stats['modified_files'].append(path)
                stats['files_changed'] += 1

                
                insertions, deletions = self._count_line_changes(content1, content2)
                stats['insertions'] += insertions
                stats['deletions'] += deletions

        return stats

    def _count_line_changes(self, content1: str, content2: str) -> tuple[int, int]:
        
        lines1 = content1.splitlines()
        lines2 = content2.splitlines()

        
        diff = list(difflib.unified_diff(lines1, lines2, lineterm=''))

        insertions = sum(1 for line in diff if line.startswith('+') and not line.startswith('+++'))
        deletions = sum(1 for line in diff if line.startswith('-') and not line.startswith('---'))

        return insertions, deletions

    def format_stats(self, stats: dict[str, Any]) -> str:
        
        result = []

        if stats['added_files']:
            for file in stats['added_files']:
                result.append(f" {file} | (new file)")

        if stats['deleted_files']:
            for file in stats['deleted_files']:
                result.append(f" {file} | (deleted)")

        if stats['modified_files']:
            for file in stats['modified_files']:
                result.append(f" {file} | (modified)")

        if result:  
            result.append("")  

        summary = f" {stats['files_changed']} file(s) changed"
        if stats['insertions'] > 0:
            summary += f", {stats['insertions']} insertion(s)(+)"
        if stats['deletions'] > 0:
            summary += f", {stats['deletions']} deletion(s)(-)"

        result.append(summary)
        return '\n'.join(result)
    
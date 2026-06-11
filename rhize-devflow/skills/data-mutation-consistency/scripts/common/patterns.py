"""
Pattern Detection for Mutation Consistency Analysis

Contains regex patterns and detection logic for various mutation patterns.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .models import MutationInfo, MutationCategory


@dataclass
class PatternDefinition:
    """Definition of a detection pattern."""
    name: str
    regex: re.Pattern
    category: MutationCategory
    extract_table: bool = True
    context_required: Optional[str] = None  # Path pattern for context


# Platform patterns (Vercel/Next.js/Supabase)
PLATFORM_PATTERNS = {
    # Supabase mutations
    "supabase_insert": PatternDefinition(
        name="supabase_insert",
        regex=re.compile(
            r"supabase\s*\.\s*from\s*\(\s*['\"](\w+)['\"]\s*\)\s*\.\s*insert",
            re.MULTILINE
        ),
        category=MutationCategory.CLIENT_MUTATION,
    ),
    "supabase_update": PatternDefinition(
        name="supabase_update",
        regex=re.compile(
            r"supabase\s*\.\s*from\s*\(\s*['\"](\w+)['\"]\s*\)\s*\.\s*update",
            re.MULTILINE
        ),
        category=MutationCategory.CLIENT_MUTATION,
    ),
    "supabase_delete": PatternDefinition(
        name="supabase_delete",
        regex=re.compile(
            r"supabase\s*\.\s*from\s*\(\s*['\"](\w+)['\"]\s*\)\s*\.\s*delete",
            re.MULTILINE
        ),
        category=MutationCategory.CLIENT_MUTATION,
    ),
    "supabase_upsert": PatternDefinition(
        name="supabase_upsert",
        regex=re.compile(
            r"supabase\s*\.\s*from\s*\(\s*['\"](\w+)['\"]\s*\)\s*\.\s*upsert",
            re.MULTILINE
        ),
        category=MutationCategory.CLIENT_MUTATION,
    ),

    # Server actions
    "server_action": PatternDefinition(
        name="server_action",
        regex=re.compile(r"['\"]use server['\"]", re.MULTILINE),
        category=MutationCategory.SERVER_ACTION,
        extract_table=False,
    ),

    # Cache revalidation
    "revalidate_tag": PatternDefinition(
        name="revalidate_tag",
        regex=re.compile(r"revalidateTag\s*\(\s*['\"](\w+)['\"]", re.MULTILINE),
        category=MutationCategory.SERVER_ACTION,
        extract_table=False,
    ),
    "revalidate_path": PatternDefinition(
        name="revalidate_path",
        regex=re.compile(r"revalidatePath\s*\(\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
        category=MutationCategory.SERVER_ACTION,
        extract_table=False,
    ),
}

# React Query patterns
REACT_QUERY_PATTERNS = {
    "use_mutation": PatternDefinition(
        name="use_mutation",
        regex=re.compile(r"useMutation\s*\(\s*\{", re.MULTILINE),
        category=MutationCategory.REACT_QUERY,
        extract_table=False,
    ),
    "query_key_factory": PatternDefinition(
        name="query_key_factory",
        regex=re.compile(r"export\s+const\s+(\w+)Keys\s*=", re.MULTILINE),
        category=MutationCategory.REACT_QUERY,
        extract_table=False,
    ),
    "inline_query_key": PatternDefinition(
        name="inline_query_key",
        regex=re.compile(r"queryKey:\s*\[['\"][^'\"]+['\"]", re.MULTILINE),
        category=MutationCategory.REACT_QUERY,
        extract_table=False,
    ),
    "on_mutate": PatternDefinition(
        name="on_mutate",
        regex=re.compile(r"onMutate\s*:", re.MULTILINE),
        category=MutationCategory.REACT_QUERY,
        extract_table=False,
    ),
    "on_error": PatternDefinition(
        name="on_error",
        regex=re.compile(r"onError\s*:", re.MULTILINE),
        category=MutationCategory.REACT_QUERY,
        extract_table=False,
    ),
    "on_settled": PatternDefinition(
        name="on_settled",
        regex=re.compile(r"onSettled\s*:", re.MULTILINE),
        category=MutationCategory.REACT_QUERY,
        extract_table=False,
    ),
    "invalidate_queries": PatternDefinition(
        name="invalidate_queries",
        regex=re.compile(r"invalidateQueries\s*\(", re.MULTILINE),
        category=MutationCategory.REACT_QUERY,
        extract_table=False,
    ),
}

# Payload CMS patterns
PAYLOAD_PATTERNS = {
    "collection_config": PatternDefinition(
        name="collection_config",
        regex=re.compile(r"CollectionConfig\s*=\s*\{", re.MULTILINE),
        category=MutationCategory.PAYLOAD_HOOK,
        extract_table=False,
    ),
    "after_change_hook": PatternDefinition(
        name="after_change_hook",
        regex=re.compile(r"afterChange\s*:\s*\[", re.MULTILINE),
        category=MutationCategory.PAYLOAD_HOOK,
        extract_table=False,
    ),
    "after_delete_hook": PatternDefinition(
        name="after_delete_hook",
        regex=re.compile(r"afterDelete\s*:\s*\[", re.MULTILINE),
        category=MutationCategory.PAYLOAD_HOOK,
        extract_table=False,
    ),
    "before_change_hook": PatternDefinition(
        name="before_change_hook",
        regex=re.compile(r"beforeChange\s*:\s*\[", re.MULTILINE),
        category=MutationCategory.PAYLOAD_HOOK,
        extract_table=False,
    ),
    "empty_hooks": PatternDefinition(
        name="empty_hooks",
        regex=re.compile(r"hooks\s*:\s*\{\s*\}", re.MULTILINE),
        category=MutationCategory.PAYLOAD_HOOK,
        extract_table=False,
    ),
}

# Error handling patterns
ERROR_HANDLING_PATTERNS = {
    "try_catch": re.compile(r"try\s*\{", re.MULTILINE),
    "error_check": re.compile(r"if\s*\(\s*error\s*\)", re.MULTILINE),
    "destructure_error": re.compile(r"\{\s*data\s*,\s*error\s*\}", re.MULTILINE),
    "throw_error": re.compile(r"throw\s+(new\s+)?Error", re.MULTILINE),
    "toast_error": re.compile(r"toast\.(error|warning)", re.MULTILINE),
}


class PatternMatcher:
    """Matches code against defined patterns."""

    def __init__(self, sub_skills: list[str] = None):
        self.sub_skills = sub_skills or []
        self.patterns = dict(PLATFORM_PATTERNS)

        # Load sub-skill patterns
        if "react-query-mutations" in self.sub_skills:
            self.patterns.update(REACT_QUERY_PATTERNS)
        if "payload-cms-hooks" in self.sub_skills:
            self.patterns.update(PAYLOAD_PATTERNS)

    def find_mutations(self, file_path: Path, content: str) -> list[MutationInfo]:
        """Find all mutations in a file."""
        mutations = []

        # Find Supabase mutations
        for pattern_name in ["supabase_insert", "supabase_update", "supabase_delete", "supabase_upsert"]:
            pattern = self.patterns.get(pattern_name)
            if not pattern:
                continue

            for match in pattern.regex.finditer(content):
                line_num = content[:match.start()].count('\n') + 1
                table = match.group(1) if match.groups() else "unknown"
                mutation_type = pattern_name.replace("supabase_", "")

                # Get surrounding context for snippet
                lines = content.split('\n')
                start_line = max(0, line_num - 2)
                end_line = min(len(lines), line_num + 5)
                snippet = '\n'.join(lines[start_line:end_line])

                # Determine category based on file path
                category = self._determine_category(file_path, content)

                mutation = MutationInfo(
                    file_path=file_path,
                    line_number=line_num,
                    mutation_type=mutation_type,
                    table_or_entity=table,
                    category=category,
                    code_snippet=snippet,
                    function_name=self._extract_function_name(content, line_num),
                )

                # Check for required elements
                self._check_elements(mutation, content)

                mutations.append(mutation)

        return mutations

    def find_react_query_mutations(self, file_path: Path, content: str) -> list[MutationInfo]:
        """Find React Query mutations specifically."""
        mutations = []

        pattern = self.patterns.get("use_mutation")
        if not pattern:
            return mutations

        for match in pattern.regex.finditer(content):
            line_num = content[:match.start()].count('\n') + 1

            # Extract the full mutation block
            snippet = self._extract_block(content, match.start())

            mutation = MutationInfo(
                file_path=file_path,
                line_number=line_num,
                mutation_type="react_query_mutation",
                table_or_entity=self._extract_mutation_entity(snippet),
                category=MutationCategory.REACT_QUERY,
                code_snippet=snippet,
                function_name=self._extract_function_name(content, line_num),
            )

            # Check React Query specific elements
            mutation.has_on_error = bool(REACT_QUERY_PATTERNS["on_error"].regex.search(snippet))
            mutation.has_on_settled = bool(REACT_QUERY_PATTERNS["on_settled"].regex.search(snippet))
            mutation.has_optimistic_update = bool(REACT_QUERY_PATTERNS["on_mutate"].regex.search(snippet))

            # Check for query key factory usage
            mutation.has_query_key_factory = bool(re.search(r"\w+Keys\.", snippet))

            # Check for cache invalidation
            mutation.has_cache_revalidation = bool(
                REACT_QUERY_PATTERNS["invalidate_queries"].regex.search(snippet)
            )

            # Check for rollback in onError
            if mutation.has_optimistic_update:
                mutation.has_rollback_logic = bool(
                    re.search(r"context\??\.\w+|setQueryData", snippet)
                )

            self._check_elements(mutation, snippet)
            mutations.append(mutation)

        return mutations

    def find_payload_collections(self, file_path: Path, content: str) -> list[MutationInfo]:
        """Find Payload CMS collections and their hooks."""
        mutations = []

        pattern = self.patterns.get("collection_config")
        if not pattern:
            return mutations

        for match in pattern.regex.finditer(content):
            line_num = content[:match.start()].count('\n') + 1

            # Extract slug
            slug_match = re.search(r"slug\s*:\s*['\"](\w+)['\"]", content[match.start():])
            slug = slug_match.group(1) if slug_match else "unknown"

            snippet = self._extract_block(content, match.start())

            mutation = MutationInfo(
                file_path=file_path,
                line_number=line_num,
                mutation_type="payload_collection",
                table_or_entity=slug,
                category=MutationCategory.PAYLOAD_HOOK,
                code_snippet=snippet,
            )

            # Check Payload specific elements
            mutation.has_after_change_hook = bool(
                PAYLOAD_PATTERNS["after_change_hook"].regex.search(snippet)
            )
            mutation.has_after_delete_hook = bool(
                PAYLOAD_PATTERNS["after_delete_hook"].regex.search(snippet)
            )
            mutation.has_before_change_hook = bool(
                PAYLOAD_PATTERNS["before_change_hook"].regex.search(snippet)
            )

            # Check for cache revalidation in hooks
            mutation.has_cache_revalidation = bool(
                re.search(r"revalidate(Tag|Path)", snippet)
            )

            # Empty hooks is a problem
            has_empty_hooks = bool(PAYLOAD_PATTERNS["empty_hooks"].regex.search(snippet))
            if has_empty_hooks:
                mutation.has_after_change_hook = False
                mutation.has_after_delete_hook = False

            mutations.append(mutation)

        return mutations

    def _determine_category(self, file_path: Path, content: str) -> MutationCategory:
        """Determine mutation category based on file and content."""
        path_str = str(file_path).lower()

        if "'use server'" in content or '"use server"' in content:
            return MutationCategory.SERVER_ACTION
        if "/api/" in path_str:
            return MutationCategory.API_ROUTE
        if "collection" in path_str or "payload" in path_str:
            return MutationCategory.PAYLOAD_HOOK
        if "hook" in path_str or "use" in file_path.stem.lower():
            return MutationCategory.REACT_QUERY

        return MutationCategory.CLIENT_MUTATION

    def _check_elements(self, mutation: MutationInfo, content: str) -> None:
        """Check for required elements in mutation code."""
        # Error handling
        mutation.has_error_handling = any(
            pattern.search(content) for pattern in ERROR_HANDLING_PATTERNS.values()
        )

        # Cache revalidation (already set for RQ/Payload)
        if not mutation.has_cache_revalidation:
            mutation.has_cache_revalidation = bool(
                re.search(r"revalidate(Tag|Path)", content)
            )

        # Type safety
        mutation.has_type_safety = bool(
            re.search(r":\s*\w+(?:<[^>]+>)?(?:\s*\||\s*\)|\s*=>|\s*\{)", content)
        )

        # Input validation
        mutation.has_input_validation = bool(
            re.search(r"\.parse\(|\.safeParse\(|validate|schema\.", content, re.IGNORECASE)
        )

        # User feedback
        mutation.has_user_feedback = bool(
            re.search(r"toast\.|notification\.|alert\(|showMessage", content, re.IGNORECASE)
        )

    def _extract_function_name(self, content: str, line_num: int) -> Optional[str]:
        """Extract the function name containing the line."""
        lines = content.split('\n')
        for i in range(line_num - 1, -1, -1):
            line = lines[i]
            # Match function/const declarations
            match = re.search(r"(?:function|const|async function)\s+(\w+)", line)
            if match:
                return match.group(1)
            # Match export function
            match = re.search(r"export\s+(?:async\s+)?function\s+(\w+)", line)
            if match:
                return match.group(1)
        return None

    def _extract_block(self, content: str, start_pos: int, max_lines: int = 50) -> str:
        """Extract a code block starting from a position."""
        remainder = content[start_pos:]
        lines = remainder.split('\n')[:max_lines]

        # Try to find matching braces
        brace_count = 0
        result_lines = []
        started = False

        for line in lines:
            result_lines.append(line)
            brace_count += line.count('{') - line.count('}')
            if '{' in line:
                started = True
            if started and brace_count <= 0:
                break

        return '\n'.join(result_lines)

    def _extract_mutation_entity(self, snippet: str) -> str:
        """Extract entity name from mutation snippet."""
        # Look for mutationFn that calls an API function
        match = re.search(r"(?:create|update|delete|upsert)(\w+)", snippet, re.IGNORECASE)
        if match:
            return match.group(1)

        # Look for query key references
        match = re.search(r"(\w+)Keys\.", snippet)
        if match:
            return match.group(1)

        return "unknown"


def detect_sub_skills(project_root: Path) -> list[str]:
    """Detect which sub-skills should be loaded based on package.json."""
    sub_skills = []

    package_json = project_root / "package.json"
    if not package_json.exists():
        return sub_skills

    import json
    with open(package_json) as f:
        try:
            pkg = json.load(f)
        except json.JSONDecodeError:
            return sub_skills

    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

    if "@tanstack/react-query" in deps or "react-query" in deps:
        sub_skills.append("react-query-mutations")

    if "payload" in deps or "@payloadcms/next" in deps:
        sub_skills.append("payload-cms-hooks")

    if "@reduxjs/toolkit" in deps:
        sub_skills.append("redux-toolkit-mutations")  # Planned

    if "@sanity/client" in deps:
        sub_skills.append("sanity-cms-hooks")  # Planned

    return sub_skills

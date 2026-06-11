"""
Scoring Calculator for Mutation Consistency Analysis

Calculates scores based on configurable weights and thresholds.
"""

from pathlib import Path
from typing import Optional
import yaml

from .models import (
    MutationInfo,
    MutationScore,
    MutationIssue,
    MutationCategory,
    Severity,
)


# Default weights (can be overridden by config)
DEFAULT_WEIGHTS = {
    # Platform (Vercel/Next.js/Supabase) - Required
    "error_handling": 1.5,
    "cache_revalidation": 1.5,
    "type_safety": 1.3,
    "input_validation": 1.0,

    # User experience
    "optimistic_ui": 1.2,
    "rollback_logic": 1.4,
    "user_feedback": 0.8,

    # Audit/compliance
    "audit_trail": 0.6,

    # React Query specific
    "query_key_factory": 1.5,
    "on_error_handler": 1.3,
    "on_settled_handler": 1.4,

    # Payload CMS specific
    "after_change_hook": 1.5,
    "after_change_cache": 1.5,
    "after_delete_hook": 1.3,
    "after_delete_cache": 1.3,
    "before_change_validation": 1.0,
}

DEFAULT_THRESHOLDS = {
    "warning": 9.0,
    "critical": 7.0,
}


class ScoreCalculator:
    """Calculates mutation consistency scores."""

    def __init__(self, config_path: Optional[Path] = None):
        self.weights = dict(DEFAULT_WEIGHTS)
        self.thresholds = dict(DEFAULT_THRESHOLDS)

        if config_path and config_path.exists():
            self._load_config(config_path)

    def _load_config(self, config_path: Path) -> None:
        """Load scoring weights from YAML config."""
        with open(config_path) as f:
            config = yaml.safe_load(f)

        if "weights" in config:
            # Flatten nested weight categories
            for category, weights in config["weights"].items():
                if isinstance(weights, dict):
                    self.weights.update(weights)
                else:
                    self.weights[category] = weights

        if "thresholds" in config:
            self.thresholds.update(config["thresholds"])

    def score_mutation(self, mutation: MutationInfo) -> MutationScore:
        """Calculate score for a single mutation."""
        elements_present = []
        elements_missing = []
        issues = []

        raw_score = 0.0
        max_score = 0.0

        # Determine which elements to check based on category
        checks = self._get_checks_for_category(mutation.category, mutation.is_user_facing)

        for element, weight in checks.items():
            is_present = self._check_element(mutation, element)
            max_score += weight

            if is_present:
                raw_score += weight
                elements_present.append(element)
            else:
                elements_missing.append(element)
                issues.append(self._create_issue(mutation, element, weight))

        # Calculate final score (normalized to 10-point scale)
        final_score = (raw_score / max_score * 10) if max_score > 0 else 0.0

        return MutationScore(
            mutation=mutation,
            raw_score=raw_score,
            max_score=max_score,
            final_score=round(final_score, 1),
            elements_present=elements_present,
            elements_missing=elements_missing,
            issues=issues,
        )

    def _get_checks_for_category(
        self,
        category: MutationCategory,
        is_user_facing: bool
    ) -> dict[str, float]:
        """Get the elements to check based on mutation category."""

        # Base platform checks (always required)
        checks = {
            "error_handling": self.weights["error_handling"],
            "type_safety": self.weights["type_safety"],
        }

        if category == MutationCategory.SERVER_ACTION:
            checks["cache_revalidation"] = self.weights["cache_revalidation"]
            checks["input_validation"] = self.weights["input_validation"]

        elif category == MutationCategory.API_ROUTE:
            checks["input_validation"] = self.weights["input_validation"]

        elif category == MutationCategory.CLIENT_MUTATION:
            if is_user_facing:
                checks["optimistic_ui"] = self.weights["optimistic_ui"]
                checks["rollback_logic"] = self.weights["rollback_logic"]
                checks["user_feedback"] = self.weights["user_feedback"]

        elif category == MutationCategory.REACT_QUERY:
            checks["query_key_factory"] = self.weights["query_key_factory"]
            checks["on_error_handler"] = self.weights["on_error_handler"]
            checks["on_settled_handler"] = self.weights["on_settled_handler"]

            if is_user_facing:
                checks["optimistic_ui"] = self.weights["optimistic_ui"]
                checks["rollback_logic"] = self.weights["rollback_logic"]
                checks["user_feedback"] = self.weights["user_feedback"]

        elif category == MutationCategory.PAYLOAD_HOOK:
            checks["after_change_hook"] = self.weights["after_change_hook"]
            checks["after_change_cache"] = self.weights["after_change_cache"]
            checks["after_delete_hook"] = self.weights["after_delete_hook"]
            checks["after_delete_cache"] = self.weights["after_delete_cache"]
            checks["before_change_validation"] = self.weights["before_change_validation"]

        return checks

    def _check_element(self, mutation: MutationInfo, element: str) -> bool:
        """Check if a mutation has a specific element."""
        element_map = {
            "error_handling": mutation.has_error_handling,
            "cache_revalidation": mutation.has_cache_revalidation,
            "type_safety": mutation.has_type_safety,
            "input_validation": mutation.has_input_validation,
            "optimistic_ui": mutation.has_optimistic_update,
            "rollback_logic": mutation.has_rollback_logic,
            "user_feedback": mutation.has_user_feedback,
            "audit_trail": mutation.has_audit_trail,

            # React Query
            "query_key_factory": mutation.has_query_key_factory,
            "on_error_handler": mutation.has_on_error,
            "on_settled_handler": mutation.has_on_settled,

            # Payload
            "after_change_hook": mutation.has_after_change_hook,
            "after_change_cache": mutation.has_cache_revalidation and mutation.has_after_change_hook,
            "after_delete_hook": mutation.has_after_delete_hook,
            "after_delete_cache": mutation.has_cache_revalidation and mutation.has_after_delete_hook,
            "before_change_validation": mutation.has_before_change_hook,
        }

        return element_map.get(element, False)

    def _create_issue(
        self,
        mutation: MutationInfo,
        element: str,
        weight: float
    ) -> MutationIssue:
        """Create an issue for a missing element."""
        # Determine severity based on weight
        if weight >= 1.4:
            severity = Severity.CRITICAL
        elif weight >= 1.0:
            severity = Severity.WARNING
        else:
            severity = Severity.INFO

        # Get issue details
        details = ISSUE_DETAILS.get(element, {
            "message": f"Missing {element}",
            "fix_suggestion": f"Add {element} to mutation",
        })

        return MutationIssue(
            mutation=mutation,
            element=element,
            severity=severity,
            message=details["message"],
            fix_suggestion=details["fix_suggestion"],
            fix_code=details.get("fix_code"),
        )

    def calculate_overall_score(self, scores: list[MutationScore]) -> float:
        """Calculate weighted average score across all mutations."""
        if not scores:
            return 10.0  # No mutations = perfect score

        total_weighted = sum(s.final_score * s.max_score for s in scores)
        total_weight = sum(s.max_score for s in scores)

        return round(total_weighted / total_weight, 1) if total_weight > 0 else 0.0


# Detailed issue information for each element
ISSUE_DETAILS = {
    "error_handling": {
        "message": "Missing error handling for mutation",
        "fix_suggestion": "Add try/catch or check error in response",
        "fix_code": """
// Add error handling:
const { data, error } = await supabase.from('table').update(data);
if (error) throw error;
// Or use try/catch for more control
""",
    },
    "cache_revalidation": {
        "message": "No cache revalidation after mutation",
        "fix_suggestion": "Add revalidateTag() or revalidatePath() after mutation",
        "fix_code": """
// After mutation, invalidate cache:
revalidateTag('entity-name');
revalidatePath('/entity-path');
""",
    },
    "type_safety": {
        "message": "Missing type annotations",
        "fix_suggestion": "Add TypeScript types for mutation parameters and return value",
    },
    "input_validation": {
        "message": "No input validation before mutation",
        "fix_suggestion": "Add zod schema validation before mutation",
        "fix_code": """
// Validate input with zod:
const validated = schema.parse(input);
""",
    },
    "optimistic_ui": {
        "message": "Missing optimistic update for user-facing mutation",
        "fix_suggestion": "Add onMutate with optimistic cache update",
        "fix_code": """
onMutate: async (variables) => {
  await queryClient.cancelQueries({ queryKey: entityKeys.detail(id) });
  const previous = queryClient.getQueryData(entityKeys.detail(id));
  queryClient.setQueryData(entityKeys.detail(id), (old) => ({ ...old, ...variables }));
  return { previous };
},
""",
    },
    "rollback_logic": {
        "message": "Optimistic update without rollback on error",
        "fix_suggestion": "Add rollback in onError using context",
        "fix_code": """
onError: (error, variables, context) => {
  if (context?.previous) {
    queryClient.setQueryData(entityKeys.detail(id), context.previous);
  }
  toast.error('Update failed');
},
""",
    },
    "user_feedback": {
        "message": "No user feedback on mutation result",
        "fix_suggestion": "Add toast or notification on success/error",
        "fix_code": """
onSuccess: () => { toast.success('Updated successfully'); },
onError: (error) => { toast.error(error.message); },
""",
    },
    "query_key_factory": {
        "message": "Using inline query keys instead of factory",
        "fix_suggestion": "Create and use query key factory",
        "fix_code": """
// Create lib/query-keys/entity-keys.ts:
export const entityKeys = {
  all: ['entities'] as const,
  lists: () => [...entityKeys.all, 'list'] as const,
  list: (filters) => [...entityKeys.lists(), filters] as const,
  details: () => [...entityKeys.all, 'detail'] as const,
  detail: (id) => [...entityKeys.details(), id] as const,
};
""",
    },
    "on_error_handler": {
        "message": "Missing onError handler in mutation",
        "fix_suggestion": "Add onError with rollback and user feedback",
    },
    "on_settled_handler": {
        "message": "Missing onSettled for cache invalidation",
        "fix_suggestion": "Add onSettled with invalidateQueries",
        "fix_code": """
onSettled: () => {
  queryClient.invalidateQueries({ queryKey: entityKeys.detail(id) });
  queryClient.invalidateQueries({ queryKey: entityKeys.lists() });
},
""",
    },
    "after_change_hook": {
        "message": "Missing afterChange hook in Payload collection",
        "fix_suggestion": "Add afterChange hook with cache invalidation",
        "fix_code": """
hooks: {
  afterChange: [
    createAfterChangeInvalidator({
      tags: ['entity'],
      paths: ['/entity', '/entity/{id}'],
    }),
  ],
},
""",
    },
    "after_change_cache": {
        "message": "afterChange hook missing cache invalidation",
        "fix_suggestion": "Add revalidateTag/revalidatePath in afterChange hook",
    },
    "after_delete_hook": {
        "message": "Missing afterDelete hook in Payload collection",
        "fix_suggestion": "Add afterDelete hook with cache invalidation and cleanup",
        "fix_code": """
hooks: {
  afterDelete: [
    createAfterDeleteInvalidator({
      tags: ['entity'],
      paths: ['/entity'],
    }),
  ],
},
""",
    },
    "after_delete_cache": {
        "message": "afterDelete hook missing cache invalidation",
        "fix_suggestion": "Add revalidateTag in afterDelete to prevent stale cache",
    },
    "before_change_validation": {
        "message": "No beforeChange validation hook",
        "fix_suggestion": "Add beforeChange hook with input validation",
    },
}

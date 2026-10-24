# Research notes

Reviewed official material on 2026-10-23; recommendations below are design choices, not measured
Rhize performance claims. API examples inform architecture without authorizing API billing.

- [Anthropic: Building effective agents](https://www.anthropic.com/research/building-effective-agents):
  use simple workflows first; orchestrator/workers suit tasks whose subtasks are discovered.
- [Anthropic: Effective harnesses for long-running agents](https://www.anthropic.com/research/effective-harnesses-for-long-running-agents):
  explicit feature completion, incremental checkpoints and continuity.
- [Anthropic: Scaling Managed Agents](https://www.anthropic.com/research/managed-agents):
  separate durable session evidence from execution/context; revisit model-specific harness
  assumptions. Its hosted service and performance results are not dependencies or Rhize claims.
- [Anthropic: Demystifying evals for AI agents](https://www.anthropic.com/research/demystifying-evals-for-ai-agents):
  distinguish tasks, trials, traces and independently checked outcomes.
- [Anthropic: Multi-agent research system](https://www.anthropic.com/research/multi-agent-research-system):
  scoped parallel delegation, artifact handoff and substantial orchestration/token overhead.
- [Claude Code: Dynamic workflows](https://code.claude.com/docs/en/workflows):
  native orchestration and worktrees; replay/retry/null-result/model substitution caveats mean
  native convenience does not establish exactly-once execution or enforced token caps.
- [Claude: A harness for every task](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code):
  use native code orchestration when its actual capability matches the contract.
- [Claude Code: Subagents](https://code.claude.com/docs/en/sub-agents):
  verify real checkout/base behavior; inherited permissions are not service isolation.
- [OpenAI: Harness engineering](https://openai.com/index/harness-engineering/):
  concise maps, observable environments and mechanically enforced invariants.
- [OpenAI: Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices):
  representative/held-out tasks, continuous regression checks and calibrated judges.
- [OpenAI: Multi-agent orchestration](https://openai.github.io/openai-agents-python/multi_agent/):
  structured planning plus code-controlled execution, explicit dependencies and handoffs.
- [OpenAI: Optimizing cost and quality](https://developers.openai.com/cookbook/examples/agent_optimization/optimizing_agents_for_cost_and_quality):
  establish correctness first, then measure model/routing changes on the same workload.
- [LangGraph: Workflows and agents](https://docs.langchain.com/oss/python/langgraph/workflows-agents):
  dynamic Send-style workers with isolated inputs support the bounded-template design.
  No LangGraph dependency is required.
- [Git worktree](https://git-scm.com/docs/git-worktree): checkout separation shares repository
  metadata; it is not a credentials or external-service sandbox.

Local source review also covered saved Obsidian Inbox articles titled “Agentic Systems A
Practitioner's Guide to 6 Advanced Architectural Patterns”, “Cut Long-Horizon Agent Costs by
50%”, “Agentic E2E Testing Without Giving Up Determinism”, “I Tried (New) Claude Code Plugin
Evals (Stop Building Fake Skills)”, and “JEV is Missing Control Plane for Software Factories”.
Useful themes: bounded state projection, structured outputs, deterministic scaffolds and
control-plane evidence. Their numerical cost claims are setup-specific and are not Rhize
benchmark results. Private vault paths and article text are intentionally excluded.

Existing Rhize parallel-agent-optimization and workflow-selection contracts supply host
admission and decision provenance. ECC continuous-agent-loop, loop-design-check, eval-harness
and agent-harness-construction supplied comparison points for bounded loops, evidence and
failure taxonomies. This skill closes the reusable graph-authoring/dynamic-admission gap;
it does not vendor those skills or add another agent framework.

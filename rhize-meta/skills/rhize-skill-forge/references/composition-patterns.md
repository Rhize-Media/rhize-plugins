# Composition Patterns — wrap vs. absorb vs. reference vs. chain

The [[Skill Customizer & Organizer]] idea proposes four ways a *custom* skill can be built from
*resource* skills. This file maps each to an existing Forge mechanism and says **which to actually
reach for**. The headline: favor the patterns that copy *least*, because every copy is a future
drift/maintenance cost (see `drift-boundaries.md`).

## The four patterns → Forge mechanisms

| Pattern | What it is | Forge mechanism | Reach for it when |
|---------|-----------|-----------------|-------------------|
| **Wrapper** | Custom skill injects Rhize context, then delegates to a resource skill | **DEFER+wrap** (a DEFER variant) | The resource is high-quality + actively maintained and you only need to add company context. Stays current by *not copying*. |
| **Merge & override** | Combine the best parts of N overlapping resources; user overrides win | **N-way ABSORB** via `skill-refinement` patches | `overlap_scan.py --set-mode` shows 2+ resources covering one domain and you want one custom skill. **Human-gated — never silent.** |
| **Reference library** | Written fresh, informed by indexed resource docs | **DEFER / WATCH + references** | You're authoring something new but want resources as citations. Already supported; no new mechanism. |
| **Composable chain** | A pipeline that chains resources with glue logic | *(defer — a command/workflow concern)* | Rare. Use a command or the `project-launcher` pipeline; don't build a chain engine until a real case repeats. |

## DEFER+wrap (the wrapper, made honest)

There is **no runtime delegation primitive** in the skill system — a "wrapper" is mechanically a
thin custom skill whose body says *"apply `<resource>` with this Rhize context"* plus a `consumes:`
edge to that resource. So:

- It is a **DEFER** (you don't copy the resource) **+ a context layer** (the Rhize-specific
  wrapper body).
- Record it like a DEFER in `SOURCES.md`, but set `tier: custom` and `consumes: [<resource>]` so
  the dependency graph and drift classifier can see the link.
- Its upside (stays synced with upstream) is exactly why it's preferred over FORK when the resource
  is well-maintained.

## N-way ABSORB (merge & override, kept safe)

Extends ABSORB from one source to several:

1. `overlap_scan.py --set-mode` surfaces the overlapping cluster (e.g. multiple SEO skills).
2. For each section, pick the strongest source (the score is *where to look*, not the verdict —
   open the bodies; see `overlap-analysis.md`).
3. Hand the chosen parts to `skill-refinement` as patches against the target custom skill.
4. **Verify beats baseline** (Step 5 eval loop) before keeping it.

**Guardrail:** the merge is a *scored proposal a human approves*, never an automatic write. Silent
auto-merge is gated to a later, product-only phase and is in tension with the verify-first doctrine
(`dev-flow-foundations`).

## What not to do

- Don't build a composable-chain engine speculatively — it's a workflow concern with a command-
  shaped solution.
- Don't FORK when DEFER+wrap would keep you synced with a maintained upstream.
- Don't let `--set-mode` auto-act on a high score — it points; the human decides.

---

*Related: `decision-matrix.md` (the five verbs + variants), `capability-schema.md` (`tier` /
`consumes` that make wrap/merge legible), `overlap-analysis.md` (reading the score).*

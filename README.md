# SpecKit Solo Orchestrator

A small native Extension and prepend Preset that route governed work from
current repository artifacts and human approvals. Commands become agent skills
through native SpecKit generation; there is no hand-authored skill or agent
runner. Stage behavior belongs to the installed SpecKit, Greenfield, Feature,
MVP and existing UX/UI interfaces.

Requires SpecKit 0.16.2, Greenfield foundation 0.1.0 and lifecycle 0.2.0 (source
commit `49a469356c76a96df55b270ce771c9c27947f5f6`), Greenfield preset 0.4.1,
Feature Governance Guard 1.0.1 and MVP Complexity Guard 1.1.0 with their existing
governance presets. Native Core Feature context must identify exactly one
linked active Feature; ambiguous context blocks routing. For Feature work the
existing Greenfield lifecycle configuration must explicitly use
`completion_mode: human` and `approval_registry: .specify/governance/hitl.json`.
Solo does not change that configuration.

From an initialized project with the required Feature Governance and MVP
Governance prerequisites installed, clone this repository and install its
native Extension and prepend Preset:

```bash
mkdir -p ~/src
git clone --depth 1 https://github.com/ahhakopian/speckit-solo-orchestrator.git ~/src/speckit-solo-orchestrator
specify extension add --dev ~/src/speckit-solo-orchestrator/extension
specify preset add --dev ~/src/speckit-solo-orchestrator/preset --priority 5
```

Invoke generated `speckit.solo-orchestrator.route` through the normal native
agent invocation. Foundation work stops at Architecture approval and Project
Ready approval / PROJECT READY. Feature work delegates Specify → Clarify →
Spec approval → Plan → Plan + UX approval → Tasks + Feature Guard → Tasks / Guard
approval → Analyze → Implement (ordered guards and Readiness approval) → MVP
Simplification → Post-Implementation approval → Converge → completion verification
→ Human Acceptance → Greenfield Complete / Feature DONE. The installed mandatory
hooks supply existing guards. Optional Checklist is applicability-driven.
Authority decisions and blockers always stop the caller.

The sole project-owned registry is `.specify/governance/hitl.json`, outside
the component directories. It stores only the Greenfield current-fact schema,
with a restricted approval vocabulary in that same shape. Foundation HITL
subjects are `foundation`: `architecture` and `project-ready`. Feature HITL
subjects are Feature IDs: `spec`, `plan-ux`, `tasks-guard`,
`implementation-readiness`, `post-implementation` and `human-acceptance`.
These are authority decisions, never stage-completion records. The shared
`prd` declaration is an already-approved input fact with subject `foundation`,
not a Solo HITL gate. No other approval boundaries are accepted on load or save.
These approval categories do not replace delegated stage behavior or checks.
Reinstall/removal does not own the registry. Approval recording requires an
explicit human declaration and current verification, supplied by the native
command's human interaction. These facts are content-bound declarations, not
cryptographic proof of the human or verification execution.

Spec approval binds the current post-Clarify `spec.md` with the installed
Greenfield helper's single-document (`prd`) fingerprint mode; this is content
hashing, not PRD authorization. Current Project Ready authorization is checked
separately. Missing or stale Spec approval stops at Spec HITL before Plan.
Clarify may rerun without a completion fact; the caller rechecks routing after
it and before Plan so an edit invalidates the earlier Plan selection. Optional
Checklist remains applicability-driven and adds no completion/skipped fact.

Plan + UX binds the foundation, Spec, Plan, existing native design documents,
contracts, Feature UX/design artifacts, and applicable `DESIGN.md`. Tasks / Guard
also binds `tasks.md`. Their fingerprints aggregate the installed helper's
document fingerprints in the existing current-approval field. Tasks / Guard
normalizes only native task completion checkboxes when hashing task scope.
Changes, additions
or deletions to these authority inputs require renewed approval; task generation
and implementation writes do not invalidate Plan approval by themselves.
Native Tasks runs its existing mandatory after-tasks Guard before the approval
stop. A fresh invocation with no current Tasks / Guard approval repeats the
installed Guard, retaining no verdict ledger. Post-Implementation similarly
requires current native MVP Simplification before approval and Converge.

All Greenfield validation and authority content hashing use installed
`governance_facts.py`. Implementation Readiness and Post-Implementation reuse its conservative
`human-acceptance` fingerprint, binding foundation and Feature authorities,
applicable UX, and the project tree. Code, evidence and task changes invalidate
readiness on a subsequent invocation, including partial implementation; it
must be explicitly approved again before another Core implementation invocation.
This conservative binding avoids a second fingerprint protocol. Guard and
Preflight results remain transient and must PASS afresh before readiness.

The prepend Preset fixes Core 0.16.2's inline hook enumeration by using the
existing HookExecutor's priority order and agent invocation rendering. Native
priority 5 Guard → 10 Preflight → 15 Solo Readiness precedes Core implementation.
Validation uses native PresetResolver source layers to require the effective
Solo `prepend` above the Core base, and checks resolved placement before Core.
Appended, displaced, missing or unprovable composition blocks implementation.
Failing, absent, disabled or conditional required hooks block implementation.
An isolated uv/pipx SpecKit console launcher supplies its existing Python
interpreter for hook inspection when the caller's Python cannot import SpecKit.
Other launcher forms require a Python interpreter exposing installed SpecKit.
Enforcement uses native generated agent instructions, as do the existing guards;
the deterministic tests do not claim live-agent or OS-level execution isolation.

Run focused deterministic tests with the Python exposing installed SpecKit:

```bash
/home/art/.local/share/uv/tools/specify-cli/bin/python -B -m unittest discover -s tests -v
```

Tests use disposable project fixtures and existing sibling prerequisite source
packages. They install/generate only inside those fixtures and never dispatch
a live agent. Resolved and generated Implement placement, native hook ordering
and standalone readiness failures are deterministic checks; they do not prove
live-agent enforcement. No real-project installation, publication or live acceptance has
been performed.

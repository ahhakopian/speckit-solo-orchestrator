## Solo Implementation Hook Ordering

Before any Core implementation, run from the project root:
`python3 .specify/extensions/solo-orchestrator/scripts/solo.py hooks`.
Failure, missing hooks or invalid configuration blocks implementation.
Use the returned native HookExecutor ordering and integration-specific
invocations for `before_implement`. Actually invoke every mandatory hook,
sequentially, and wait for each current successful result before the next.
The required order is Feature Governance Guard → MVP Complexity Preflight →
Solo Implementation Readiness → Core implementation. BLOCK, missing approval,
uncertain results or authority escalation stops before Core implementation.

This replaces Core's inline `before_implement` enumeration for this invocation;
do not dispatch that event twice. Continue with the existing Core instructions
and post-implementation hooks only after all mandatory pre-hooks pass.

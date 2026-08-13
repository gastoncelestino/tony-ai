# Tony AI — Phase Capabilities

The orchestrator only needs this routing map. Executor implementation details belong to the phase prompt, not here.

- `sdd-init`: initialize SDD state and choose artifact/session mode.
- `sdd-explore`: investigate the question/codebase and compare approaches.
- `sdd-propose`: turn exploration into a scoped proposal.
- `sdd-spec`: turn the proposal into acceptance-oriented technical specification.
- `sdd-design`: turn the proposal/spec into an implementation design.
- `sdd-tasks`: turn spec/design into ordered implementation tasks and delivery slices.
- `sdd-apply`: implement the assigned task slice.
- `sdd-verify`: validate the implementation against the specification and tests.
- `sdd-archive`: close the change and persist the final state.
- `sdd-onboard`: guide a project through the SDD workflow.
- `review-*`: inspect the requested review dimension.
- `jd-judge-a`: judge the change against the first judgment contract.
- `jd-judge-b`: independently judge the change against the second judgment contract.
- `jd-fix-agent`: apply a targeted fix requested by judgment.

Routing rule: delegate by capability and current phase state. Do not perform phase work inline and do not load another phase's implementation prompt merely to decide where to delegate.
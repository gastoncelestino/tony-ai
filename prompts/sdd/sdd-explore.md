# SDD Explore

This file is an SDD phase contract loaded as the prompt of the `sdd-explore` phase agent. It is **not a Skill** and must never be invoked through the `skill` tool. The identifier `sdd-explore` names the phase agent only. Do not search for, load, or invoke a skill named `sdd-explore`; execute this phase directly from this contract.

## Objective
Investigate the active project workspace and produce the exploration artifact required by the SDD workflow.

## Questions
- Where does the requested capability or behavior live?
- Which existing components participate?
- What current behavior, tests, configuration, and documentation constrain the change?
- Which implementation approaches are consistent with the existing codebase?
- What risks, unknowns, or open questions remain?

## Output
Produce an exploration report containing:

| Section | Content |
|---|---|
| **Question** | What was investigated |
| **Findings** | Key discoveries with code pointers (`file:line`) |
| **Options** | Relevant approaches and trade-offs |
| **Recommendation** | Suggested approach with rationale |
| **Risks** | Known unknowns and technical debt |

## Boundary
Explore only. Do not implement the requested change.

The Tony Kernel owns phase selection, execution permissions, scope, transitions, and artifact lifecycle. This contract defines the meaning and expected output of the Explore phase; it does not define runtime tool policy.

One directory per workflow, e.g. `feature-v1/`.
Each holds workflow.yaml, defaults.yaml, prompts/, templates/ and a README.
See docs/WORKFLOW_SPEC.md section 5.4.

- `feature-v1/`: ticket to branch: context, spec, plan, GATE 1, build loop, regression, final report, GATE 2 (section 2).
- `regression-v1/`: regression only: a branch against its fork point on the suites and cases a ticket names, then a final report (section 10).

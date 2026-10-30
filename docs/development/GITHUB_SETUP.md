# GitHub CI setup and Phase 1 release gates

Roadmap 4.0 · Instruction 003 · 30 October 2026.

## Current evidence
`git remote -v` returned no remote. Workflow YAML trigger/job/permission/locked-install/integration/cleanup structure checks passed. Official actionlint 1.7.11 was downloaded to ignored `.tools/`, checked against the official release SHA-256 checksum and executed successfully:

```powershell
.tools/actionlint-1.7.11/actionlint.exe -version
.tools/actionlint-1.7.11/actionlint.exe -shellcheck= -pyflakes= .github/workflows/ci.yml
```

No actionlint findings. External ShellCheck/Pyflakes integrations were explicitly disabled because they are not installed; Ruff and mypy cover Python application checks separately. This is local workflow validation, not GitHub Actions execution, repository setting verification or proof an action download will succeed on a runner.

## Required repository-owner setup — not executed
1. Choose the GitHub account/organization, repository name and visibility; create an empty repository without generated README/license files that would conflict with this initial history. Confirm permissions and plan support for intended branch protection/rulesets.
2. Obtain explicit authorization before adding a remote or pushing this local repository. Then use the actual owner/repository URL, not a guessed account. Configure HTTPS credential management or approved SSH keys; never put access tokens in remote URLs.
3. Push the reviewed initial `main` history only after authorization. The existing workflow triggers on push and pull_request. No paid AI/payment secrets are needed for the foundation jobs; service passwords in CI are disposable test values.
4. Inspect the actual run of `Foundation validation`: quality job (locked install, Ruff, format, mypy, Bandit, pip-audit, enabled PostgreSQL/Redis tests) and containers job (Compose/build/readiness/storage/worker). Record run URL, commit SHA and all job results; fix any failures before accepting CI.
5. Create a test pull request with an intentional harmless check failure, verify the required check blocks integration, then correct it and verify the passing PR can merge. Do not merge an intentional failure.
6. Protect `main` with required pull requests/review appropriate to team size, required successful `quality` and `containers` check contexts as they actually appear in the first run, conversation resolution, restrictions on force pushes/deletion and controlled bypass permissions. Document who can approve/bypass; ensure branch/ruleset enforcement matches the repository plan.
7. Independently repeat clean setup on a separate developer machine or CI runner and retain evidence. A same-machine isolated environment is useful but does not establish second-host setup.

Reference commands for a future explicitly authorized remote operation (not performed by Instruction 003):
```powershell
git remote add origin https://github.com/OWNER/REPOSITORY.git
git push -u origin main
```

## Remaining Phase 1 acceptance
The roadmap requires a documented clean setup, passing automated tests and CI that rejects broken changes. Local tests and isolated same-machine setup are verified. Actual remote CI execution, enforcement/negative-test evidence and repository branch workflow remain blocking gates. Do not label Phase 1 complete based on YAML lint alone.

## Sources
[Official actionlint installation](https://github.com/rhysd/actionlint/blob/main/docs/install.md) and [usage](https://github.com/rhysd/actionlint/blob/main/docs/usage.md). Recheck GitHub repository/ruleset availability for the chosen account and plan when remote setup is authorized.

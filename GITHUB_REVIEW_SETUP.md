# Checks before merging into dev

For [PR #2](https://github.com/Shkirmantsev/ProjectExpert/pull/2),
`FirstBaseRuleset` requires CodeQL results and at least one approving review.
Automatic Copilot review is already enabled, including reviews after new pushes.
A separate GitHub Code Quality rule is also enabled, with a `notes` threshold.
These settings were verified on October 4, 2026 and may change.

The [.github/workflows/codeql.yml](.github/workflows/codeql.yml) workflow scans
Python and uploads results to Code Scanning. It runs for pull requests targeting
`dev` and `main`, on pushes to those branches, and when triggered manually.
Pull requests that change only documentation also receive a scan.
The workflow does not submit a human approval.

## 1. Publish the commit

After creating the local commit, run:

```bash
git push origin feature/generate-init-project
```

Open PR #2 → **Checks**. Look for **CodeQL / Analyze Python** and wait for it
to finish. If the check fails, open it → **Details** to see the cause.

## 2. Check the CodeQL configuration

Open [Settings → Advanced Security](https://github.com/Shkirmantsev/ProjectExpert/settings/security_analysis).
In the **CodeQL analysis** row, check the setup type.

- If **Default setup** is active, open the row's menu → **Switch to advanced**
  → confirm **Disable CodeQL**. This disables default setup so that our workflow
  can upload results. Do not create a second CodeQL workflow from a GitHub template.
- If CodeQL is not configured yet, our file provides the advanced setup
  configuration. After pushing, check its run under **Actions**.
- If Actions are disabled, open **Settings → Actions → General** and allow
  GitHub Actions, including `actions/checkout` and `github/codeql-action`.
  Save the settings.

See the [official GitHub setup instructions](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning).

## 3. If GitHub is still waiting for results for dev

At the time of verification, `dev` did not contain this workflow. If the PR has
been scanned but GitHub still shows **Waiting for Code Scanning results**, an
initial baseline scan of `dev` may be needed. GitHub compares the PR's results
with results from the target branch.

1. Open **Code** → select **dev** in the branch selector.
2. Click **Add file → Create new file**.
3. Enter `.github/workflows/codeql.yml` in the filename field.
4. Copy the complete contents of that file from `feature/generate-init-project`.
5. Click **Commit changes…**. If your ruleset bypass permissions allow it,
   choose to commit directly to `dev`. If GitHub requires a PR, create a separate
   branch and a PR targeting `dev` with only this file. A user with ruleset bypass
   permission must perform this initial merge; approval alone does not resolve
   the missing baseline scan.
6. Open **Actions → CodeQL** and wait for a successful run for `dev`.
7. Under **Actions**, open the CodeQL run for PR #2 → **Re-run all jobs**.
   Check the PR's merge status again.

Do not disable the entire ruleset for this. If nobody has bypass permission,
an administrator must agree on how to install the initial workflow.
To use **Run workflow** for a manual run, the file must also exist on `main`,
the default branch. Automatic scans on pushes to `dev` require the file on `dev`.

See [how GitHub triggers and compares scans](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options).

## 4. Get an approving review

Open **Conversation** in PR #2. In **Reviewers** on the right, click the gear
icon and select another collaborator with write access. If nobody is listed,
open **Settings → Collaborators → Add people**, invite the appropriate user,
and wait for them to accept the invitation.

The reviewer opens the PR → **Files changed → Review changes → Approve →
Submit review**. If CODEOWNERS defines owners for the changed files, approval
from the relevant code owner is required because the current ruleset also
requires it. Authors cannot approve their own pull requests.

See [GitHub's approval rules](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews).

If you work alone and want to allow PRs without another reviewer, that is a
separate project policy decision: open **Settings → Rules → Rulesets →
FirstBaseRuleset → Require a pull request before merging**. Set
**Required approvals** to `0` and disable **Require review from Code Owners**
if you do not intend to require that approval. Click **Save changes**.
This relaxes approval requirements for **both main and dev**, because the
ruleset targets both branches. The workflow does not change this setting.

If you want Copilot to submit approvals rather than only comments, open
**Settings → Copilot → Code review → Auto-approval**. If these options are
available, enable **Allow Copilot to approve pull requests** and
**Allow Copilot approvals to count toward merge requirements**.
Check the **File paths** restrictions: approvals count only for PRs that match
them. This feature is in public preview; requesting a review does not guarantee
approval or remove other ruleset requirements.
To request a review manually, open **Reviewers** in the PR and select **Copilot**.
To request another review, use the re-request button beside Copilot.
See [Copilot review and approval settings](https://docs.github.com/en/copilot/how-tos/copilot-on-github/set-up-copilot/configure-code-review).

## 5. If Code Quality blocks merging

CodeQL and GitHub Code Quality are separate checks. Open
**Settings → Code quality** under **Security / Security and quality**.
If the service is not configured, click **Enable code quality**, review the
selected languages and runner, then click **Save changes**.
If the service is unavailable for your account, an administrator needs to
review **Require code quality results** under
**Settings → Rules → Rulesets → FirstBaseRuleset**.
Do not change the threshold merely to hide reported issues.

See [enabling Code Quality](https://docs.github.com/en/code-security/how-tos/maintain-quality-code/enable-code-quality)
and the [description of the separate check rules](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).

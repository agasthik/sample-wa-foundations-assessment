# Contributing Guidelines

Thank you for your interest in contributing to our project. Whether it's a bug report, new feature, correction, or additional
documentation, we greatly value feedback and contributions from our community.

Please read through this document before submitting any issues or pull requests so that we have all the necessary
information to effectively respond to your bug report or contribution.


## Reporting Bugs/Feature Requests

We welcome you to use the GitHub issue tracker to report bugs or suggest features.

When filing an issue, please check existing open, or recently closed, issues to make sure somebody else hasn't already
reported the issue. Please try to include as much information as you can. Details like these are incredibly useful:

* A reproducible test case or series of steps
* The version of our code being used
* Any modifications you've made relevant to the bug
* Anything unusual about your environment or deployment


## Contributing through Pull Requests
Contributions through pull requests are much appreciated. Before sending us a pull request, make sure that:

1. You are working against the latest source on the *main* branch.
2. You check existing open, and recently merged, pull requests to make sure someone else hasn't addressed the problem already.
3. You open an issue to discuss any significant work - we would hate for your time to be wasted.

To send us a pull request, please:

1. Fork the repository.
2. Modify the source; please focus on the specific change you are contributing. If you also reformat all the code, it will be hard for us to focus on your change.
3. Make sure local tests pass.
4. Run linting, formatting, and tests locally before pushing:

   ```bash
   # Create a Python 3.12 virtual environment once, then use it for all tooling.
   python3.12 -m venv .venv
   PYTHON="$PWD/.venv/bin/python"
   RUFF="$PWD/.venv/bin/ruff"

   $PYTHON -m pip install --upgrade pip
   $PYTHON -m pip install -r requirements-dev.txt
   $PYTHON -m pip check

   # Lint and format checks (CI runs these against src and tests).
   $RUFF check src tests
   $RUFF format --check src tests

   # Static syntax checks.
   $PYTHON -m compileall -q src tests
   bash -n deploy.sh run-local.sh

   # Run the unit test suite (fast, mocked with moto — no real AWS calls).
   $PYTHON -m pytest tests/unit/ -v

   # Optional: with coverage, matching CI.
   $PYTHON -m pytest tests/unit/ --cov=src --cov-report=term-missing
   ```

   If your change modifies the CloudFormation template, also validate it:

   ```bash
   $PYTHON -m pip install cfn-lint
   cfn-lint deployment/wafa-stack.yaml
   ```

   WAFA is a **read-only** tool — it must only ever call read/describe/list AWS
   APIs and must never mutate the AWS environment. Please preserve this
   invariant in both the code and the IAM role in `deployment/wafa-stack.yaml`.

   When adding or changing a check, follow the check contract documented in
   [CLAUDE.md](CLAUDE.md): every check returns a flat dict with a stable `check`
   name, wraps its body in `try/except`, and reports failures as
   `status: "error"` rather than raising. Renaming a check also means updating
   the level lists in `src/checks/maturity.py` and `CAPABILITY_AXES` in
   `src/report/html_report.py`, which reference checks by exact name string.
   Reconcile new or changed checks with the specs in `.kiro/specs/`.

5. Commit to your fork using clear commit messages.
6. Send us a pull request, answering any default questions in the pull request interface.
7. Pay attention to any automated CI failures reported in the pull request, and stay involved in the conversation.

### Automated CI Checks

The following checks run automatically on every pull request:

- **Lint** — `ruff check` and `ruff format --check` on `src` and `tests`, plus `python -m compileall` and `bash -n` syntax checks on the shell scripts
- **Test** — the `pytest` unit suite on Python 3.12 with coverage reporting
- **pip-audit** — dependency vulnerability scan
- **cfn-lint** — CloudFormation validation of `deployment/wafa-stack.yaml` (runs when that template changes)

All checks must pass before a pull request can be merged.

GitHub provides additional document on [forking a repository](https://help.github.com/articles/fork-a-repo/) and
[creating a pull request](https://help.github.com/articles/creating-a-pull-request/).


## Finding contributions to work on
Looking at the existing issues is a great way to find something to contribute on. As our projects, by default, use the default GitHub issue labels (enhancement/bug/duplicate/help wanted/invalid/question/wontfix), looking at any 'help wanted' issues is a great place to start.


## Code of Conduct
This project has adopted the [Amazon Open Source Code of Conduct](https://aws.github.io/code-of-conduct).
For more information see the [Code of Conduct FAQ](https://aws.github.io/code-of-conduct-faq) or contact
opensource-codeofconduct@amazon.com with any additional questions or comments.


## Security issue notifications
If you discover a potential security issue in this project we ask that you notify AWS/Amazon Security through our [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public github issue.


## Licensing

See the [LICENSE](LICENSE.md) file for our project's licensing. We ask you to confirm the licensing of your contribution.

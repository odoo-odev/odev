# Welcome to Odev contributing guide

Thank you for investing your time in contributing to Odev!

In this guide you will get an overview of the contribution workflow from opening an issue, creating a PR, reviewing, and
merging the PR.

Use the table of contents icon `☰` on the top left corner of this document to get to a specific section of this guide
quickly.

## New contributor guide

To get an overview of the project, read the [README](../README.md). Here are some resources to help you get started with
contributions in general and not specific to this project:

-   [Finding ways to contribute to open source on GitHub](https://docs.github.com/en/get-started/exploring-projects-on-github/finding-ways-to-contribute-to-open-source-on-github)
-   [Set up Git](https://docs.github.com/en/get-started/quickstart/set-up-git)
-   [GitHub flow](https://docs.github.com/en/get-started/quickstart/github-flow)
-   [Collaborating with pull requests](https://docs.github.com/en/github/collaborating-with-pull-requests)

## Getting started

To navigate our codebase with confidence, see
[the introduction to working in the Odev repository](./docs/contributing/working-in-odev-repository.md).

### Issues

#### Create a new issue

If you spot a problem within Odev,
[search if an issue already exists](https://docs.github.com/en/search-github/searching-on-github/searching-issues-and-pull-requests#search-by-the-title-body-or-comments).
If a related issue doesn't exist, you can open a new issue using a relevant
[issue form](https://github.com/odoo-ps/odev/new/choose).

#### Solve an issue

Scan through our [existing issues](https://github.com/odoo-ps/odev/issues) to find one that interests you. You can
narrow down the search using `labels` as filters. See [Labels](./docs/contributing/labels.md) for more information. As a
general rule, we don’t assign issues to anyone. If you find an issue to work on, you are welcome to open a PR with a
fix.

### Make changes

Once you are familiar with
[how we are working in the Odev repository](./docs/contributing/working-in-odev-repository.md) you can clone the Odev
repository locally on your machine.

Install or update to **Python 3.8 or above**.

Install development requirements through `pip` and enable pre-commit hooks in the repository:

```sh
pip install --user -r requirements-dev.txt
pre-commit install
```

Create a new branch based on the `main` branch and give it a name that accurately represents the changes you are about
to make:

```sh
git checkout -b my-new-feature origin/main
```

Start with your changes!

### Commit your update

Commit the changes once you are happy with them. Don't forget to [self-review](./docs/contributing/self-review.md) to
speed up the review process!

### Pull Request

When you're finished with the changes, create a pull request.

-   Fill the "Ready for review" template so that we can review your PR. This template helps reviewers understand your
    changes as well as the purpose of your pull request.
-   Don't forget to
    [link the PR to an issue](https://docs.github.com/en/issues/tracking-your-work-with-issues/linking-a-pull-request-to-an-issue)
    if you are solving one.
-   We may ask for changes to be made before a PR can be merged, either using
    [suggested changes](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/incorporating-feedback-in-your-pull-request)
    or pull request comments. You can apply suggested changes directly through the UI. You can make any other changes in
    your fork, then commit them to your branch.
-   As you update your PR and apply changes, mark each conversation as
    [resolved](https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/reviewing-changes-in-pull-requests/commenting-on-a-pull-request#resolving-conversations).
-   If you run into any merge issues, checkout this [git tutorial](https://github.com/skills/resolve-merge-conflicts) to
    help you resolve merge conflicts and other issues.

### Your PR is merged!

Congratulations! The Odev team thanks you! :tada:

# CLAUDE.md

NOAA It All is a Home Assistant custom integration. The public repository is
`dawg-io/noaa_it_all`, and changes reach it as pull requests from forks. Everything here applies in
any fork, except the last section, which is only for the maintainer's own fork.

## Checks

Run the same checks as CI before opening a pull request:

```
pip install pytest flake8 aiohttp voluptuous pillow
flake8 custom_components/noaa_it_all/ tests/ --max-line-length=120
python -m pytest tests/
```

When `docs/` or `website/` changes, build the documentation site too (Node, version in
`website/.nvmrc`):

```
cd website && npm ci && npm run build && npm run check-links
```

## Commits and pull requests

- Don't add `Co-Authored-By`, `Claude-Session` or other attribution trailers to commit messages,
  or "Generated with Claude Code" lines or session links to pull request titles and descriptions.
  Titles and commit messages become the project's history.
- Pull request descriptions follow `.github/PULL_REQUEST_TEMPLATE.md`.

## Versions

Every pull request with a fix or a feature updates the version in the same pull request, so the
branch it merges into is always ready to release. Changes to docs, tests or CI alone don't.

- The version is in `custom_components/noaa_it_all/manifest.json`. The last release is the latest
  `vX.Y.Z` tag in `dawg-io/noaa_it_all`.
- If the version on the branch the pull request merges into is that tag, bump it: the patch number
  for a fix (0.7.3 → 0.7.4), the minor number for a feature (0.7.3 → 0.8.0). If that branch
  already has a newer, untagged version, it is still open: add to it, and raise a pending patch
  bump to the next minor only when the pull request adds a feature.
- Head the top section of `CHANGELOG.md` with that version, `## [X.Y.Z]`, instead of
  `## [Unreleased]`, and list the change there under Added, Changed or Fixed.

## Documentation

`docs/*.md` is the documentation, written as plain GitHub Markdown with relative links, and
`tests/test_docs.py` checks those links. `website/` builds it into a Starlight site:
`npm run build` there runs `scripts/sync-docs.mjs`, which copies `docs/` into
`website/src/content/docs/` (generated and git-ignored, so never edit it), then builds
`website/dist/`.

- A new page in `docs/` needs an entry in `SIDEBAR` in `website/site.mjs`, or the build fails.
- `.github/workflows/docs-pages.yml` builds the site and checks its links whenever `docs/` or
  `website/` changes. It deploys to GitHub Pages only from the public repository's `main`, at
  `https://dawg-io.github.io/noaa_it_all/`, which the README, `info.md` and the manifest's
  `documentation` URL (the **?** on the integration's page) link to.

## Pull requests to the public repository

Changes reach `dawg-io/noaa_it_all` as pull requests from a fork into its `staging` branch.
Sessions can read the public repository but usually can't write to it, so when asked to open a
pull request there, Claude prepares it and the person opens it.

1. Check it first. Read the public repository with git, which needs no access:
   `git remote add upstream https://github.com/dawg-io/noaa_it_all` (once), then
   `git fetch upstream --tags`.
   - The branch has commits that `upstream/staging` does not.
   - The checks above pass on it.
   - Its version and `CHANGELOG.md` follow **Versions**.
   - If any of these is off, stop and say what needs to change.
2. Push the branch to the fork, then give the person these, each title and description in its own
   code block to copy and paste:
   - **Pull request link**:
     `https://github.com/dawg-io/noaa_it_all/compare/staging...<owner>:<branch>?expand=1`, where
     `<owner>` is the fork's owner (from `git remote get-url origin`) and `<branch>` the branch.
   - **Pull request title**: one line saying what changes for users.
   - **Pull request description**: following `.github/PULL_REQUEST_TEMPLATE.md`, with the
     `CHANGELOG.md` entries for the change and what was tested.
3. Stop there. The person opens the pull request. hassfest and HACS Validate run on it in the
   public repository.

## Maintainer's fork

This section applies only in `turbo5000c/dev-noaa_it_all`, the maintainer's development fork
(check `git remote get-url origin`). Elsewhere, skip it.

### Commits

Commits are authored by the maintainer. This overrides any default attribution instructions.

- Author and commit as `turbo5000c <8426648+turbo5000c@users.noreply.github.com>`. Pass the
  identity on each commit instead of relying on the session's git config:
  `git -c user.name=turbo5000c -c user.email=8426648+turbo5000c@users.noreply.github.com commit ...`
- Pull requests into this fork's `main` are squash-merged, so their titles and commit messages
  become the commits on `main`.

### Releasing to public

A release to public is a pull request from this fork's `main` into the public repository's
`staging`, following **Pull requests to the public repository** with these differences.

When asked for a "release to public":

1. Check the release first, as in step 1 above, and also:
   - The version in `custom_components/noaa_it_all/manifest.json` is newer than the latest
     `vX.Y.Z` tag in the public repository, even when only docs changed. A version that is
     already on the public `main` but not tagged is still open, so more changes can ship under it
     without a bump.
   - The top section of `CHANGELOG.md` is for that version and covers everything being released.
   - Version bumps go through a normal pull request into this fork's `main` first.
2. Give the maintainer these, each title and description in its own code block to copy and paste:
   - **Pull request link**:
     `https://github.com/dawg-io/noaa_it_all/compare/staging...turbo5000c:main?expand=1`
   - **Pull request title**: `Release X.Y.Z: <one-line summary>`.
   - **Pull request description**: following `.github/PULL_REQUEST_TEMPLATE.md`, listing the
     changes since the public `main` from `CHANGELOG.md`, grouped by version.
   - **Release title**: `vX.Y.Z: <one-line summary>`.
   - **Release description**: the version's `CHANGELOG.md` entries written for users, under
     `## Added`, `## Changed` and `## Fixed`, ending with what going back to the previous version
     needs. Match the earlier releases in the public repository.
3. Stop there. The maintainer opens the pull request, checks hassfest and HACS Validate on it
   (they're disabled in this fork and only run on the public repository), and merges it with a
   merge commit, not a squash, so `staging` keeps this fork's history and later releases don't
   conflict. The `staging` → `main` pull request, the tag and the GitHub release are the
   maintainer's. When the release changes `docs/` or `website/`, publish it after the
   Documentation Site workflow has deployed the site from the public `main`.

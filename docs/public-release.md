# Public release checklist

This repository is public. Keep it free of judgment text, downloaded archives,
generated corpora, and credentials. The public artifact is **code and
documentation**, not a legal database.

## What must never be committed

- `data/` (legislation archives, `hk_law.db`, WAL/SHM files)
- `*.db`, `*.sqlite`, `*.sqlite3`, `*.db-wal`, `*.db-shm`
- `*.zip` bulk archives
- `*.jsonl` / `*.ndjson` judgment exports
- `semantic_map/data*/`, `semantic_map/dist*/` generated atlas output
- `.env`, `.env.*`, `~/.config/hk-law-sync.env`, permission references
- Any judgment text you imported or fetched, in any format

`.gitignore` covers these paths. Do not use `git add -f` on them.

## Pre-push audit

Run all four commands from the repository root and expect the first two to
print nothing:

```bash
# 1. No tracked data, database, archive, or judgment export.
git ls-files | grep -Ei '(^data/|\.(db|sqlite|sqlite3|zip|jsonl|ndjson)$)' || true

# 2. None of those paths in any commit on any branch.
git log --all --name-only --pretty=format: \
  | sort -u \
  | grep -Ei '(^data/|\.(db|sqlite|sqlite3|zip|jsonl|ndjson)$)' || true

# 3. Ignored runtime data is present only locally.
git status --short --ignored | grep -E 'data/|\.db|\.zip|semantic_map/(data|dist)' || true

# 4. The worktree is what you intend to publish.
git status --short
```

Then scan the files you intend to commit for copied judgment paragraphs. A
short citation or case name is fine; a paragraph of judgment text is not.

## What the public repo may contain

- Source code under Apache-2.0.
- Skills and documentation under CC BY 4.0.
- Synthetic test fixtures (clearly fake case names and text).
- The legislation-only prebuilt database release, if you publish one. It must
  contain no `cases`, `case_paragraphs`, or note-up text.
- The semantic-atlas **source**, not its generated `dist*/` or `data*/`.

## The HKLII adapter

The public repo may include the permission-gated adapter because it refuses to
run without `HK_LAW_CASE_PERMISSION_REF` and an explicit citation list. It is
not a crawler. Do not enable it, do not publish a permission reference, and do
not put a permitted corpus in the repository or a release asset.

If you later obtain written permission, keep the corpus local, keep the
permission reference in a mode-0600 environment file outside the repo, and do
not add it to CI or release assets.

## Release assets

Before publishing a release:

- [ ] The database contains legislation only (`cases` count is 0 and `doj_docs`
      count is 0) if a database asset is published.
- [ ] No archive, judgment export, DOJ page export, or semantic `dist*/` is
      attached.
- [ ] No `.env`, permission reference, or credential is attached.
- [ ] The README links to the [fully local pipeline](full-local-pipeline.md)
      and [permission request template](permission-request-template.md).
- [ ] The license and attribution sections are unchanged.

## Related

[Fully local pipeline](full-local-pipeline.md) ·
[Data sources and licensing](data-sources-and-licensing.md) ·
[Coverage](coverage.md)

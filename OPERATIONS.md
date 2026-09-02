# Operations, recovery, and migration runbook

This runbook is subordinate to the human gates and invariants in `AGENTS.md`.
Commands that mutate Internet Archive or GitHub must not be run until the exact
consolidated publication proposal has been approved.

## Reproduce and validate locally

Use Python 3.10 or newer from the repository root:

```bash
python scripts/generate_site.py
python scripts/generate_site.py --check
python -m unittest discover -s tests -v
python scripts/validate_repo.py
git diff --check
git diff --exit-code
```

The feed and landing page have no clock-derived fields. Regeneration from the
same metadata and code must be byte-identical. `data/publication.json` is the
authoritative feed/URL/identity configuration. `data/lectures.json`,
`data/media-manifest.json`, and `provenance/source-map.csv` jointly define the
20 episodes.

The public cover was produced from `scripts/generate_cover.py`. Recreating it
requires Pillow plus DejaVu Sans and must be treated as an intentional artwork
change: visually inspect it, confirm 3000×3000 RGB JPEG output, and update the
golden cover hash in the validator only after review.

## Publication gate

Before any mutation, verify and obtain approval for all of these together:

1. authenticated GitHub login and repository name;
2. Internet Archive identifier availability and authenticated uploader;
3. exact title, Internet Archive metadata, and public file allowlist in
   `data/archive-item.json`;
4. Pages, feed, artwork, and enclosure URLs in `data/publication.json`;
5. licence/unofficial wording and the decision to omit a public contact email.

If either proposed identifier already exists, stop. Do not overwrite, delete,
repurpose, or silently select a new identifier.

## Internet Archive publication

Immediately before creation, re-check that the approved identifier does not
exist. Upload only this explicit allowlist:

- `lecture01.m4a` through `lecture20.m4a` from the verified media staging
  directory;
- `docs/cover.jpg` as `cover.jpg`;
- `NOTICE.md` and `LICENSE-MEDIA.md`;
- `provenance/source-map.csv` as `source-map.csv`;
- `provenance/media-verification-2026-09-02.json` under the same basename;
- `provenance/SHA256SUMS` as `SHA256SUMS`.

Do not upload transport ZIPs, reconstruction ZIPs, repository history, source
correspondence, credentials, cookies, local configuration, or any unlisted
file. Do not use an overwrite/clobber option. Upload each M4A as its own
original file and keep every source byte unchanged.

Apply the exact metadata in `data/archive-item.json`. The creator field says
“Andrew Ng (lecturer)”; it does not identify the uploader or project as
Stanford. The recording term is Autumn 2007; 2008 refers only to the SEE
initiative's launch/publication era. The item is independent, unofficial,
non-commercial, and not endorsed.

After upload, inspect the Internet Archive metadata endpoint and item file list.
Require all 20 M4As to be marked as originals, with exact sizes. Compare its
server-reported MD5 and SHA-1 values with `data/archive-hashes.json`; keep
`provenance/SHA256SUMS` as the stronger local preservation digest. If an exposed
algorithm is unavailable, perform a full download and compare SHA-256 rather
than claiming an unverified match. Confirm the stable URLs use:

```text
https://archive.org/download/cs229-machine-learning-unofficial-audio-preservation/lectureNN.m4a
```

For each file require HTTPS `HEAD` with the exact full length and a one-byte
`Range: bytes=0-0` response with status 206 and
`Content-Range: bytes 0-0/TOTAL`. Never substitute an Internet Archive-derived
MP3 or Ogg file for an enclosure.

## GitHub and Pages publication

Only after every enclosure passes live verification:

1. regenerate and re-run the complete local validation suite;
2. inspect the exact commit and prove the worktree is clean;
3. create the approved empty public repository—stop if it exists and is
   non-empty;
4. push the local `main` history once;
5. enable Pages from the `main` branch and `/docs` directory;
6. wait for CI and the Pages deployment tied to the exact pushed head SHA;
7. do not push a correction while review, CI, or Pages is evaluating that SHA.

Then run:

```bash
python scripts/check_online.py --output online-report.json
python scripts/generate_site.py --check
git diff --exit-code
test -z "$(git status --porcelain=v1)"
```

Tie remote evidence to the exact immutable head, for example:

```bash
final_sha="$(git rev-parse HEAD)"
gh run list --workflow validate.yml --commit "$final_sha" --json databaseId,headSha,status,conclusion,url
gh run watch RUN_ID --exit-status
gh api repos/OWNER/REPOSITORY/pages/builds/latest --jq '{commit,status,error,message,updated_at}'
```

Require the workflow `headSha` and the Pages build `commit` to equal
`final_sha`; a green run or deployment for any other revision is not evidence.
Then require the live feed, landing page, and artwork bytes to match the local
files exactly. Before the first push, run `python scripts/audit_history.py` to
scan every reachable Git blob and commit identity, not only the current tree.

The online check is read-only. Exit 1 means a semantic failure; exit 2 means
bounded retries ended in network unavailability. Keep the generated online
report outside Git.

## Recovery

The Git repository is fully reconstructible from any trusted clone: run the
generator, tests, and validator. The public M4As are independently recoverable
only from a trusted byte-for-byte source matching `provenance/SHA256SUMS`.
Never regenerate a replacement under an existing filename/GUID/enclosure URL
unless it matches the recorded hash exactly.

If GitHub Pages is temporarily unavailable, restore the same repository commit
and `/docs` Pages source. If the Internet Archive item is unavailable, do not
silently point existing episodes at new URLs. Restore the original archive item
or perform a separately approved feed/media migration that preserves identity
semantics and informs clients.

## Future feed-domain migration

Do not start migration until a user-controlled domain and permanent hosting are
approved and live. Keep all 20 episode GUIDs, the channel `podcast:guid`, and
all Internet Archive enclosure URLs byte-for-byte unchanged.

1. Publish and validate the byte-equivalent feed at the new HTTPS URL.
2. Change only URL fields that identify the feed/site/artwork host; do not
   change identity seeds or enclosure URLs.
3. Add the standard channel element below to the old feed, pointing at the new
   feed:

   ```xml
   <itunes:new-feed-url>https://NEW-DOMAIN.example/feed.xml</itunes:new-feed-url>
   ```

4. Update the new feed's Atom `rel="self"` to its new canonical URL.
5. Arrange a real permanent HTTP redirect (301) from the old feed URL to the
   new URL and retain both the redirect and `itunes:new-feed-url` for at least
   four weeks. A later custom-domain configuration can make the original
   GitHub Pages project URL redirect to that domain; test the actual response.
6. Validate clients before retiring any compatibility path. Never reuse the old
   URL for another show.

GitHub Pages alone cannot emit an arbitrary 301 for one static file, so a future
migration must include hosting/DNS capable of the required redirect or retain
the old static feed with `itunes:new-feed-url` until that capability exists.

## Remaining human acceptance

After all machine checks pass, manually add the HTTPS feed URL to an iPhone
podcast application and verify streaming, seeking, downloading, artwork, and
Lecture 1→20 ordering. Machine completion is not end-user acceptance until that
test is reported.

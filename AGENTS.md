# Repository invariants for maintainers and agents

This repository publishes metadata, tooling and a static RSS feed for an
unofficial, non-commercial preservation edition of Stanford SEE's CS229
lectures. GitHub Releases hold the versioned media; Git history never does.

## Non-negotiable invariants

- Keep all M4A/MP4 media, master/transport ZIPs and extracted staging trees out
  of Git. Release assets are not repository blobs.
- Never commit credentials, tokens, cookies, private configuration, unapproved
  contact addresses or private correspondence.
- Never change episode GUIDs, the GUID namespace/seed, release tag, canonical
  asset names, enclosure URLs or enclosure lengths casually. Podcast clients
  treat GUIDs as episode identity and enclosure URLs as durable media identity.
- Do not invent publication dates, lecture dates, titles, ownership or
  provenance. Preserve ordering through deterministic item order and
  `itunes:episode` in a serial feed.
- Preserve Andrew Ng as lecturer and Stanford Engineering Everywhere as the
  original source. Do not imply endorsement or ownership by this project.
- Preserve CC BY-NC-SA 4.0 attribution, licence link, adaptation notice,
  ShareAlike terms and the no-commercial-purpose posture.
- Do not submit the feed to Apple Podcasts, Spotify, Castbox, Podcast Index or
  another directory, and never send the prepared restoration correspondence,
  unless a separately authorized task explicitly says so.
- Do not alter or delete the partial Internet Archive item created during an
  abandoned publication attempt. It is not an enclosure source for this feed.

## Fixed v1.0 identities

- Repository: `smartnuf/stanford-cs229-audio`
- Pages: `https://smartnuf.github.io/stanford-cs229-audio/`
- Feed: `https://smartnuf.github.io/stanford-cs229-audio/feed.xml`
- Release tag: `audio-v1.0.0`
- Release assets: `CS229-lecture01.m4a` through `CS229-lecture20.m4a`, the
  canonical v1.0 ZIP, and the exact sidecars in `data/release-assets.json`
- Canonical ZIP: `stanford-cs229-machine-learning-audio-edition-v1.0.zip`
- Zenodo record: `https://zenodo.org/records/22261678`; DOI:
  `10.5281/zenodo.22261678`. Version 1.0 is published and immutable; do not open
  an edit or new version casually.
- Podcast channel GUID: `469b7cc4-06ab-5668-9474-0d72dac20367`, derived
  once before first publication with UUIDv5 namespace
  `ead4c236-bf58-58c6-a2c6-a6b28d128cb6` and seed
  `smartnuf.github.io/stanford-cs229-audio/feed.xml`. A later feed move retains
  this pinned GUID; it is not re-derived from the new URL.

## Human gates

Explicit human approval is required before:

- creating the initial public repository, pushing its first public history,
  uploading/publishing its first release, or activating Pages, unless the
  current execution request already explicitly authorizes the exact target and
  allowlisted inventory;
- publishing a Zenodo record or otherwise minting a DOI;
- disclosing a new public contact email;
- overwriting/deleting an existing remote repository, release, asset or record;
- changing public feed identity, GUIDs, enclosure URLs or release asset bytes;
- starting a feed migration or custom-domain change;
- sending correspondence or submitting the feed to a directory.

A Zenodo draft may be created and populated when existing authentication is
available. Its exact metadata, inventory and hashes must be shown for approval
before publication.

The v1.0 execution was explicitly authorized on 2026-09-02 for public repository
`smartnuf/stanford-cs229-audio`, release tag `audio-v1.0.0`, the 27 files in
`data/release-assets.json`, and GitHub Pages from `main` `/docs`. That grant does
not authorize overwriting/deleting remote objects, changing bytes or identities,
publishing Zenodo, sending correspondence, or directory submission.

## Bounded engineering review

For tooling, feed-generator, site or CI work, identify the work item and use a
purpose-specific branch from the current default branch. Routine preservation
or provenance-only updates do not require code review solely because they use
a PR; the preservation invariants and human gates above always apply.

Automatic Codex review is not assumed. After implementation, affected validation
and self-review of the complete diff, push a genuine candidate HEAD and ensure
its PR is open and ready for review. The authoring agent should post
`@codex review` itself when it has comment permission; otherwise report that
permission gap. This request means the author considers this exact commit ready
for independent integration review. Do not request review for routine
intermediate pushes.

Record the candidate SHA and wait for completed review of that exact commit.
Explicitly disposition material findings with fixes or evidence-backed reasons.
After material changes, rerun affected validation and self-review. Every commit
pushed after review creates a new candidate HEAD and requires fresh
`@codex review`, including a non-material edit; an older review is not evidence
for the new HEAD. Inspect and check non-material edits proportionately before
pushing them. Avoid duplicate requests while review is running. A clean review
does not replace tests, CI, domain validation or owner-reserved approval. Merge
only with the repository's required evidence and owner/authorised merge authority.

## Required validation

Use Python 3.10 or newer:

```bash
python scripts/generate_site.py --check
python -m unittest discover -s tests -v
python scripts/validate_repo.py
python scripts/audit_history.py
git diff --check
git diff --exit-code
```

Package validation must use fresh output/extraction paths and the commands in
`OPERATIONS.md`. After publication run:

```bash
python scripts/check_online.py --output online-report.json
```

The online checker is bounded and read-only. It must distinguish transport
unavailability from semantic failure and must test both the first and last byte
of all 20 enclosures. GitHub CDN's generic `application/octet-stream` is an
explicit P3 warning, accepted only alongside exact Release API `audio/mp4`,
digests, lengths, HTTPS, `HEAD`, and range evidence; never report the CDN header
itself as audio-specific.

Client-level validation uses `scripts/check_client.py` and the
`Client compatibility` workflow. Keep its weekly mode bounded to the documented
smoke subset; full 20-file downloads are manual only. The gPodder profile and
downloads must be isolated temporary state, never committed or reused. Preserve
the JSON trace, exact tool versions, feed/GUID checks, download hashes and
FFmpeg probe/seek/decode results. This complements but does not impersonate an
Apple Podcasts client acceptance test.

## Repository safety

- Keep every tracked file below 5 MiB.
- Validation must reject forbidden media/archive/key types, credential
  filenames/signatures, symlinks and generated staging directories.
- Audit every reachable Git blob and commit identity before the first push.
- GitHub Actions have read-only permissions, pinned actions and no persisted
  checkout credentials. Scheduled checks never commit, push or mutate anything.
- Do not tag or release a commit until its complete local validation passes.
- Tie CI and Pages evidence to the exact public head SHA.

## Recovery and migration

Follow `OPERATIONS.md`. The canonical master ZIP and its SHA-256 are the
preservation unit; the 20 individual release assets must match its audio files.
Any future host/domain migration retains every GUID. Publish and validate the
new feed first, then use `itunes:new-feed-url` and a real permanent redirect
while retaining the old URL for a documented transition. Never reuse this feed
URL for another show.

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
- Podcast channel GUID: `469b7cc4-06ab-5668-9474-0d72dac20367`, derived
  once before first publication with UUIDv5 namespace
  `ead4c236-bf58-58c6-a2c6-a6b28d128cb6` and seed
  `smartnuf.github.io/stanford-cs229-audio/feed.xml`. A later feed move retains
  this pinned GUID; it is not re-derived from the new URL.

## Human gates

Explicit human approval is required before:

- publishing a Zenodo record or otherwise minting a DOI;
- disclosing a new public contact email;
- overwriting/deleting an existing remote repository, release, asset or record;
- changing public feed identity, GUIDs, enclosure URLs or release asset bytes;
- starting a feed migration or custom-domain change;
- sending correspondence or submitting the feed to a directory.

A Zenodo draft may be created and populated when existing authentication is
available. Its exact metadata, inventory and hashes must be shown for approval
before publication.

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
of all 20 enclosures.

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

# Repository invariants for maintainers and agents

This repository publishes metadata and a static RSS feed for an unofficial,
non-commercial preservation edition of Stanford SEE's CS229 lectures. It never
stores the lecture media.

## Non-negotiable invariants

- Keep all M4A/MP4 media and transport ZIPs outside this repository.
- Never commit credentials, tokens, cookies, private configuration, contact
  addresses that have not been approved for disclosure, or private
  correspondence.
- Do not change an episode GUID, its GUID seed, filename, enclosure URL, or
  enclosure length casually. Podcast clients treat those values as identity.
- Do not invent publication dates, lecture dates, descriptions, ownership, or
  provenance. Episode order is represented by deterministic item order and
  `itunes:episode` in a serial feed.
- Preserve Andrew Ng as lecturer and Stanford Engineering Everywhere as source.
  Do not imply Stanford or Andrew Ng endorses this edition or that this project
  owns the underlying lectures.
- Preserve CC BY-NC-SA 4.0 attribution, licence link, adaptation notice, and the
  non-commercial/no-advertising/no-sponsorship posture.
- Never submit the feed to Apple Podcasts, Spotify, Castbox, Podcast Index, or
  another directory unless a separately authorized task explicitly says so.
- Never send the draft Stanford or Castbox correspondence from this repository.

## Human gates

Explicit human approval is required before any of these operations:

- creating or uploading an Internet Archive item;
- creating a public GitHub repository, pushing the initial history, or enabling
  GitHub Pages;
- disclosing a contact email address;
- changing the Internet Archive identifier;
- overwriting or deleting any existing remote item or repository;
- changing public feed identity, GUIDs, or enclosure URLs;
- starting a feed migration.

The initial publication approval must name the exact Internet Archive
identifier, GitHub owner/repository, Pages/feed URLs, title, metadata, public
files, contact-email decision, licence, and unofficial wording.

## Required validation

Use Python 3.10 or newer; the repository has no third-party runtime dependency.

```bash
python scripts/generate_site.py --check
python -m unittest discover -s tests -v
python scripts/validate_repo.py
git diff --check
```

After publication, run the read-only network integration check:

```bash
python scripts/check_online.py --output online-report.json
```

The online checker must remain bounded, read-only, and distinguish transport
unavailability from semantic failures. It must never rewrite feeds or remote
resources.

## Publication limits

- The Internet Archive item contains the 20 canonical `lectureNN.m4a` files,
  cover, notice, media-licence statement, source map, verification report, and
  checksums—nothing credential-bearing or private.
- The Git repository contains only metadata, provenance, generator/validator
  code, tests, CI, documentation, artwork, and generated static pages.
- Keep every tracked file below 5 MiB. Validation must fail on forbidden media,
  archives, credential filenames/signatures, or files at/above that threshold.
- GitHub Actions use read-only default permissions. Scheduled link checks do not
  commit, push, upload, or mutate external resources.

## Feed migration

The initial feed is served from GitHub Pages without a custom domain. A future
migration must retain all item GUIDs and enclosure URLs. Follow `OPERATIONS.md`:
publish the new feed first, validate it, then add the standard
`itunes:new-feed-url` migration element to the old feed and retain the old URL
for a documented transition. Never repurpose the old feed URL for a different
show.

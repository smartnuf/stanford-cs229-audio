# Operations, release, recovery and migration

This runbook is subordinate to `AGENTS.md`. It never authorizes overwriting an
existing remote object, publishing a Zenodo record, sending correspondence or
submitting the feed to a directory.

Initial public repository/release/Pages mutation requires an explicit grant for
the exact owner, repository, tag and file allowlist. The 2026-09-02 v1.0 grant
is recorded in `AGENTS.md`; it is narrow and is not reusable for later versions.

## Validate the small repository

```bash
python scripts/generate_site.py --check
python -m unittest discover -s tests -v
python scripts/validate_repo.py
python scripts/audit_history.py
git diff --check
git diff --exit-code
test -z "$(git status --porcelain=v1)"
```

`data/publication.json` pins the site, feed, artwork, release tag and enclosure
base URL. Episode metadata is joined deterministically from
`data/lectures.json`, `data/media-manifest.json` and
`provenance/source-map.csv`. Do not hand-edit `docs/feed.xml` or
`docs/index.html`; run `python scripts/generate_site.py`.

## Build the canonical preservation ZIP

Use the verified `lecture01.m4a` through `lecture20.m4a` source set outside Git.
The builder refuses to overwrite output or write inside this repository.

```bash
python scripts/build_preservation.py \
  --media-dir /ABSOLUTE/PATH/TO/media \
  --output-dir /ABSOLUTE/NEW/PATH/build \
  --ffprobe /ABSOLUTE/PATH/TO/ffprobe
```

The builder verifies every source size, SHA-256, duration, codec/profile,
sample rate, channel count and embedded tag. It copies each source byte-for-byte
to `audio/CS229-lectureNN.m4a`, writes deterministic metadata/checksums, and
creates a ZIP with fixed ordering, ZIP-epoch timestamps, fixed Unix modes, no
host extras and `ZIP_STORED` for every entry.

Validate with a fresh extraction path:

```bash
python scripts/validate_preservation.py \
  --archive /ABSOLUTE/PATH/build/stanford-cs229-machine-learning-audio-edition-v1.0.zip \
  --tree /ABSOLUTE/PATH/build/stanford-cs229-machine-learning-audio-edition-v1.0 \
  --extract-dir /ABSOLUTE/NEW/PATH/extracted \
  --report /ABSOLUTE/NEW/PATH/archive-validation.json
```

For a reproducibility proof, build again in a second new directory and compare
both ZIPs with `cmp` and `sha256sum`. Generate the committed release contract:

```bash
python scripts/generate_release_manifest.py \
  --build-dir /ABSOLUTE/PATH/build \
  --output data/release-assets.json
```

## Publish and recover GitHub Release `audio-v1.0.0`

The exact allowlist is `data/release-assets.json`: 20 canonical M4As, the master
ZIP, its checksum sidecar, `MANIFEST.json`, `SHA256SUMS`, `README.md`,
`LICENSE.md` and `PROVENANCE.md`. Never upload the five transport ZIPs.

Create the release only after the exact tag target is pushed and CI is green.
Use `.github/release-notes-audio-v1.0.0.md` as the release body. Before creation,
prove that neither the tag nor release exists. Supply each asset by explicit
path—never by a broad glob. A failed partial creation is reviewed asset by
asset; do not overwrite or delete it without human authorization.

Before creating even a draft, open repository **Settings**, find **Releases**,
and select **Enable release immutability**. GitHub applies this only to future
releases. Create a draft, upload and verify all 27 allowlisted assets, then
publish it. Do not create a mutable release and enable the setting afterward.
After publication, the release API must report `immutable: true`, every asset
must expose the exact expected `sha256:` digest and browser URL, and the tag ref
must resolve (peeling an annotated tag if necessary) to the intended commit.
Run the first check with `--expected-release-commit` set to that full SHA. Then
add that SHA as `media.release_commit` in `data/publication.json` in the first
post-release metadata commit. This checked-in pin deliberately differs from a
later main/Pages SHA (for example after adding a Zenodo DOI) and keeps scheduled
release verification stable.

Recovery starts from the canonical master ZIP and its checksum. Extract into a
new directory, run the archive validator, and compare the 20 individual release
assets with the master `audio/` hashes. Never replace a published filename with
different bytes; create a newly versioned release after review.

## Publish and verify GitHub Pages

Pages serves `main` `/docs`. After activation, wait for the build tied to the
exact head SHA. Then run:

```bash
python scripts/check_online.py --output online-report.json
python scripts/generate_site.py --check
git diff --exit-code
test -z "$(git status --porcelain=v1)"
```

The online checker requires exact live feed/site/artwork bytes; the exact public
immutable release inventory and mandatory GitHub SHA-256 digests; source and
transcript reachability; actual successful `HEAD`; exact length; HTTPS
redirects; and first/last `206` byte ranges for every enclosure and the master
ZIP. GitHub's Release API must preserve `audio/mp4` for every M4A. Its download
CDN may return the generic `application/octet-stream` only when all stronger
identity, digest, length, HTTPS, `HEAD`, and range checks pass; the report must
record that P3 compatibility warning and the iPhone test remains mandatory. It
resolves the release tag to the separately pinned release commit. Exit 1 is a
semantic failure; exit 2 is bounded network unavailability.

Tie every external status to the same full SHA:

```bash
EXPECTED_SHA="$(git rev-parse HEAD)"
test "$(gh api repos/smartnuf/stanford-cs229-audio/commits/main --jq .sha)" = "$EXPECTED_SHA"
gh run list --repo smartnuf/stanford-cs229-audio --workflow validate.yml \
  --commit "$EXPECTED_SHA" --json headSha,status,conclusion,url
gh api repos/smartnuf/stanford-cs229-audio/pages/builds/latest \
  --jq '{commit: .commit, status: .status}'
python scripts/check_online.py --expected-release-commit \
  "$(python -c 'import json; print(json.load(open("data/publication.json"))["media"]["release_commit"])')" \
  --output online-report.json
```

The online report records the peeled tag target, release immutability, asset
digests, actual content types, headers and range results. Remote main, CI
`headSha` and the Pages build commit must equal `EXPECTED_SHA`; the tag target
must equal the separately pinned `media.release_commit`.

If GitHub Release delivery fails range or media compatibility, do not advertise
the feed. Preserve the release and recommend Cloudflare R2 behind a future
controlled domain. Do not move media to Git LFS, Pages, Drive, Dropbox or a
proxy.

## Repeatable client compatibility

The headless client harness provides a repeatable layer above raw HTTP checks.
It parses and cross-checks the live RSS feed, uses a clean gPodder profile for
real subscription/update/list/download behavior, and uses FFprobe/FFmpeg to
open the public enclosures, seek remotely and decode short segments.

For a local smoke run with gPodder and FFmpeg installed:

```bash
python scripts/check_client.py \
  --scope smoke \
  --output client-compatibility-report.json
```

Smoke mode lists all 20 canonical GUIDs, downloads and hashes Lecture 1 through
gPodder, and probes/decodes start, five-minute and near-end segments from
Lectures 1, 10 and 20. The manual `full` workflow mode performs the FFmpeg checks
and gPodder downloads/hashes for all 20 files, transferring approximately 1.8
GB. Do not schedule full mode.

Every run records UTC timestamps, public URLs, exact tool versions, commands,
elapsed times, feed bytes/hash, probe metadata, decoded durations, gPodder
results and downloaded hashes. Exit 1 is a semantic/client failure; exit 2 is
bounded network unavailability. GitHub Actions retains the JSON trace for 30
days. Temporary gPodder profiles and downloads are removed after the run.

This harness does not reproduce Apple Podcasts' private parser, caching or UI.
Continue to record manual iPhone streaming, seeking, downloading, artwork and
ordering acceptance separately.

## Zenodo

Version 1.0 is published at <https://doi.org/10.5281/zenodo.22261678> and
<https://zenodo.org/records/22261678>. `zenodo/metadata.json` preserves the
submitted metadata and `data/zenodo-record.json` pins the verified public file
inventory, sizes, SHA-256 and Zenodo MD5 values. The deposit contains the
canonical master ZIP and seven separately readable sidecars; it does not
duplicate the 20 individual GitHub podcast enclosures.

Treat the published record as immutable. Any correction or new version requires
a fresh human checkpoint, an exact inventory review and complete validation.
Never edit the v1.0 record merely to follow a moving repository branch. The
feed's Atom `related` link may cite the DOI, but episode GUIDs and enclosure URLs
remain independent and unchanged.

## Future feed-domain migration

No custom domain is configured. A later migration must retain all episode GUIDs
and published enclosure URLs unless a separately reviewed media migration is
necessary.

1. Publish and validate an equivalent feed at the new HTTPS URL.
2. Change only feed/site/artwork host fields; do not change identity seeds.
3. Add `<itunes:new-feed-url>https://NEW-DOMAIN.example/feed.xml</itunes:new-feed-url>`
   to the old feed.
4. Point the new feed's Atom `rel="self"` to itself.
5. Configure a real HTTP 301 from the old feed URL and retain both mechanisms
   for at least four weeks. GitHub Pages alone cannot emit an arbitrary
   per-file 301, so retain the old feed when necessary.
6. Validate actual clients before retiring any compatibility path.

## Manual acceptance

After machine checks pass, add the feed URL to an iPhone podcast application
and test streaming, seeking, downloading, artwork and Lecture 1→20 ordering.

## CI history scope

Pull-request CI keeps GitHub's synthetic merge checkout for unit tests and
site/feed/repository validation. The history audit separately uses
`python scripts/audit_history.py --revision <real-PR-head-SHA>` to inspect that
commit and all of its ancestors. Push and manual CI use the real event commit.
The synthetic merge identity is not part of the proposed repository history;
no identity allowlist or blob-safety rule is relaxed.

The local command without `--revision` still audits every local ref. Both modes
require complete, non-shallow history. An explicit revision must resolve to one
available commit; bad identities or forbidden historical blobs still fail even
when removed from the final tree. Keep full-depth checkout and do not switch
integration validation to the PR-head tree merely to satisfy the history audit.

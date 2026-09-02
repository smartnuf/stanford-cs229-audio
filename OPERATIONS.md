# Operations, release, recovery and migration

This runbook is subordinate to `AGENTS.md`. It never authorizes overwriting an
existing remote object, publishing a Zenodo record, sending correspondence or
submitting the feed to a directory.

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
redirects; an audio-specific M4A content type; and first/last `206` byte ranges
for every enclosure and the master ZIP. It resolves the release tag to the
separately pinned release commit. Exit 1 is a semantic failure; exit 2 is
bounded network unavailability.

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

## Zenodo

`zenodo/README.md` and `zenodo/metadata.json` define the proposed deposit. A
draft may be created and populated with the master ZIP plus separately readable
metadata when authentication is available. Publishing/minting the DOI requires
explicit human approval after reviewing the exact draft metadata, file list,
hashes and residual uncertainties.

After DOI publication, add the DOI to project documentation and appropriate
feed metadata without changing episode GUIDs or enclosure URLs, then rerun the
complete validation and deployment review.

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

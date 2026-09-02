# CS229 Machine Learning — Unofficial Audio Preservation Edition

This repository is the authoritative metadata and reproducible publishing
source for an independent, non-commercial audio preservation of Andrew Ng's
20-lecture Stanford CS229 Machine Learning course. Stanford Engineering
Everywhere (SEE) is the original source. This project is not endorsed by
Stanford University or Andrew Ng and does not claim ownership of the lectures.

The Git history contains no lecture media. Versioned M4A enclosures and the
canonical preservation ZIP are GitHub Release assets; the deterministic RSS
feed and landing page are served by GitHub Pages.

## Published locations

- Project page: <https://smartnuf.github.io/stanford-cs229-audio/>
- RSS feed: <https://smartnuf.github.io/stanford-cs229-audio/feed.xml>
- Release: <https://github.com/smartnuf/stanford-cs229-audio/releases/tag/audio-v1.0.0>
- Zenodo preservation record: <https://doi.org/10.5281/zenodo.22261678>
- Canonical Stanford course: <https://see.stanford.edu/Course/CS229>

Podcast clients that support direct URL subscriptions can add the RSS URL
without this feed being submitted to a directory.

## Repository layout

- `data/` — canonical course, episode, media, release, feed and identity data
- `provenance/` — source map, historical Apple references and verification evidence
- `preservation/` — documentation embedded in the canonical v1.0 ZIP
- `scripts/build_preservation.py` — deterministic package builder
- `scripts/validate_preservation.py` — independent ZIP extraction/verification
- `scripts/generate_site.py` — deterministic RSS and landing-page generator
- `scripts/validate_repo.py` — offline repository/feed/safety validation
- `scripts/check_online.py` — bounded, read-only deployment and link checks
- `scripts/check_client.py` — traceable gPodder subscription/download and
  FFmpeg remote probe/seek/decode checks
- `zenodo/` — published deposit metadata, DOI and verification instructions
- `contact/castbox-restoration.md` — prepared but unsent restoration message
- `docs/` — generated GitHub Pages site
- `FUTURE-DIRECTIONS.md` — parked maintenance, reuse and discoverability ideas

## Local verification

Python 3.10+ is sufficient for feed and repository checks:

```bash
python scripts/generate_site.py --check
python -m unittest discover -s tests -v
python scripts/validate_repo.py
python scripts/audit_history.py
git diff --check
```

Building the preservation package additionally requires FFprobe and the 20
verified source M4As outside Git. See `OPERATIONS.md` for exact commands,
release recovery, online verification and later feed-domain migration.

Possible future work is recorded in [`FUTURE-DIRECTIONS.md`](FUTURE-DIRECTIONS.md).
It separates collection-specific maintenance from a potential reusable
preservation toolkit and does not authorize publication or outreach.

The `Client compatibility` workflow runs a weekly smoke test and offers a
manual `full` mode. Smoke mode checks all RSS identities, uses a fresh gPodder
profile to subscribe/update/list the feed and download/hash Lecture 1, and uses
FFmpeg to probe and decode three remote seek points from Lectures 1, 10 and 20.
Full mode applies the media checks and verified gPodder downloads to all 20
lectures. Each run retains a machine-readable JSON trace as an Actions artifact.

## Licensing

The scripts and tests use the MIT licence in `LICENSE-CODE`. Stanford's SEE
reuse page states that SEE material is CC BY-NC-SA 4.0 unless otherwise
indicated. The adapted media, original artwork and added metadata are therefore
offered under the same licence as documented in `LICENSE-MEDIA.md`, `NOTICE.md`
and `preservation/LICENSE.md`. No monetization, advertising, sponsorship or
commercial purpose is intended.

The source term is Autumn 2007. References to 2008 describe the launch/publication
era of Stanford Engineering Everywhere, not invented lecture dates.

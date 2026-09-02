# CS229 Machine Learning — Unofficial Audio Preservation Edition

This small repository is the authoritative metadata and publishing source for
an independent, non-commercial audio preservation of Andrew Ng's 20-lecture
Stanford CS229 Machine Learning course. Stanford Engineering Everywhere (SEE)
is the source. This project is not endorsed by Stanford University or Andrew
Ng, and it does not claim ownership of the underlying lectures.

The generated feed is designed for manual subscription in podcast clients. The
lecture media is deliberately hosted outside Git and is never committed here.

## Published locations

- Landing page: <https://smartnuf.github.io/cs229-unofficial-audio-feed/>
- RSS feed: <https://smartnuf.github.io/cs229-unofficial-audio-feed/feed.xml>
- Canonical Stanford course: <https://see.stanford.edu/Course/CS229>
- Proposed preservation item: <https://archive.org/details/cs229-machine-learning-unofficial-audio-preservation>

These URLs are proposals until the publication checkpoint has been approved
and deployment has completed.

## Repository layout

- `data/` — canonical course, episode, media, feed, licence, and identity data
- `provenance/` — source map, historical Apple references, checksums, and
  machine verification evidence
- `scripts/generate_site.py` — deterministic RSS and landing-page generator
- `scripts/validate_repo.py` — offline repository/feed/safety validation
- `scripts/check_online.py` — bounded, read-only live integration checks
- `tests/` — offline behavioural and invariant tests
- `docs/` — GitHub Pages output
- `OPERATIONS.md` — regeneration, publication, recovery, and migration runbook

## Local verification

Python 3.10+ is the only runtime dependency.

```bash
python scripts/generate_site.py --check
python -m unittest discover -s tests -v
python scripts/validate_repo.py
git diff --check
```

To regenerate the deterministic static output:

```bash
python scripts/generate_site.py
```

Run the network integration check only after the proposed URLs are live:

```bash
python scripts/check_online.py --output online-report.json
```

See `OPERATIONS.md` before publication, recovery, or feed migration.

## Licensing

The scripts and tests use the MIT licence in `LICENSE-CODE`. The adapted media,
artwork, and derived editorial metadata are documented under CC BY-NC-SA 4.0
in `LICENSE-MEDIA.md` and `NOTICE.md`. Copyright in the source lectures and
course materials remains with Stanford University and/or the identified rights
holders. No monetization, advertising, sponsorship, or commercial purpose is
intended.

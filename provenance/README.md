# Provenance records

These files preserve the evidence used to construct the feed:

- `source-map.csv` maps each lecture to Stanford's canonical MP4 and HTML/PDF
  transcripts.
- `apple-itunes-enclosures.json` records historical iTunes U enclosure URLs
  recovered from the public Castbox representation. They are provenance only,
  not enclosure sources for this feed.
- `source-verification-2026-09-02.json` records the prior live-source check and
  its stated limitations.
- `media-verification-2026-09-02.json` is the Milestone 0 machine audit of the
  immutable inputs and all canonical M4As.
- `SHA256SUMS` contains the canonical public lecture filenames and exact hashes.

Historical Apple catalogue/feed endpoint wording in the source research was an
explicit inference, not a recovered feed response. This edition does not claim
or alter Apple's old listing and is not submitted to podcast directories.

The source lecture term and SEE publication era are kept distinct. Stanford's
official [`schedule.pdf`](https://see.stanford.edu/materials/aimlcs229/schedule.pdf)
aligns with Autumn 2007, as do the course's dated
[`cs229-linalg.pdf`](https://see.stanford.edu/materials/aimlcs229/cs229-linalg.pdf)
and [`cs229-cvxopt.pdf`](https://see.stanford.edu/materials/aimlcs229/cs229-cvxopt.pdf)
notes. Stanford reports that the SEE initiative launched in 2008. Neither date
is used to invent per-episode publication dates.

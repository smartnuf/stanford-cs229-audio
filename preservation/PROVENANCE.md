# Provenance

## Source and attribution

- Course: CS229 — Machine Learning
- Lecturer: Andrew Ng
- Original publisher/source: Stanford Engineering Everywhere (SEE)
- Course page: https://see.stanford.edu/Course/CS229
- Source term: Autumn 2007
- SEE publication context: the SEE initiative launched in 2008
- SEE reuse policy: https://see.stanford.edu/UsingSEE
- Reuse-policy access date: 2026-09-02

This is an independent, non-commercial preservation/adaptation edition. It is
not endorsed by Stanford University or Andrew Ng and does not transfer or claim
ownership of the original lectures.

## Reconstruction method and evidence

The reconstruction tool selected the sole AAC audio stream from each Stanford
MP4 and invoked FFmpeg with `-map 0:a:0 -vn -c:a copy -movflags +faststart`.
`-c:a copy` remuxes the compressed AAC packets without decoding or re-encoding.
It also added descriptive M4A container tags.

The immutable embedded comment in each M4A refers to `NOTICE.md`, the notice in
the original reconstruction/transport set. This canonical package consolidates
the same attribution and licence information into `PROVENANCE.md` and
`LICENSE.md`; the media was not remuxed merely to change that comment.

On 2026-09-02, the recorded source verification found all 20 Stanford MP4
sources complete and probeable, each with AAC-LC audio at 48 kHz in stereo and
approximately 157 kbit/s. The resulting 20 M4As have the same codec/profile,
sample rate, channel count, and expected duration; each parses with FFprobe and
has a stable SHA-256 digest. The reconstruction implementation and its stream-
copy test are retained in the project history.

The source MP4s were remotely probed and size-checked but were not retained or
fully hashed. Therefore the no-transcoding conclusion is supported by the
recorded command, successful reconstruction tests, matching source/output
stream signatures and full output validation—not by a retained packet-by-
packet comparison with all 24.4 GB of source video.

Historical Apple iTunes U enclosure references are preserved separately for
context. They are not the source of this edition: historical Lectures 14 and 17
were known to return four-second failures, while these files match the complete
Stanford SEE sources and run approximately 80 and 77 minutes respectively.

See `MANIFEST.json` for the per-file technical metadata, hashes, source URLs and
transcript links.

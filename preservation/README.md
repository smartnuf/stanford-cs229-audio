# CS229 Machine Learning — Unofficial Audio Preservation Edition v1.0

This package preserves the audio from 20 Stanford Engineering Everywhere
CS229 Machine Learning lectures taught by Andrew Ng. It is an independently
prepared, non-commercial audio adaptation and is not endorsed by Stanford
University or Andrew Ng.

The files in `audio/` use stable zero-padded names. The AAC-LC audio packets
were copied from Stanford's source MP4 containers into M4A containers without
decoding or re-encoding. See `PROVENANCE.md` and `MANIFEST.json` for the limits
and evidence supporting that statement.

Verify the package from this directory with:

```text
sha256sum --check SHA256SUMS
```

`SHA256SUMS` intentionally excludes itself, because a checksum file cannot
contain its own stable digest. It covers all 20 audio files and every other
supporting file in this package.

Source course: https://see.stanford.edu/Course/CS229

Licence: CC BY-NC-SA 4.0. See `LICENSE.md`.

# Published Zenodo v1.0 deposit

Version 1.0 was published on 2026-09-02:

- DOI: <https://doi.org/10.5281/zenodo.22261678>
- Record: <https://zenodo.org/records/22261678>

`metadata.json` is the exact submitted legacy Zenodo deposit metadata. Zenodo's
API classifies `upload_type: video` as “Video/Audio”; the record uses
`cc-by-nc-sa-4.0`. The sole creator entry is the preservation
curator/depositor `smartnuf`, with no supplied ORCID or affiliation. Andrew Ng
and Stanford Engineering Everywhere retain their separately stated roles.

The prepared deposit bundle contains only:

1. `stanford-cs229-machine-learning-audio-edition-v1.0.zip`
2. `stanford-cs229-machine-learning-audio-edition-v1.0.zip.sha256`
3. `MANIFEST.json`
4. `SHA256SUMS`
5. `README.md`
6. `LICENSE.md`
7. `PROVENANCE.md`
8. `ZENODO-METADATA.json`

Reconstruct the exact local upload bundle outside Git with:

```bash
python scripts/prepare_zenodo.py \
  --build-dir /ABSOLUTE/PATH/TO/build \
  --output-dir /ABSOLUTE/NEW/PATH/zenodo-upload \
  --report /ABSOLUTE/NEW/PATH/zenodo-deposit-report.json
```

The script first proves that all 27 candidate release files in the selected
build match `data/release-assets.json`. It writes only the eight upload files to
the output directory; the local verification report is deliberately separate,
so selecting the whole upload directory cannot accidentally add it to Zenodo.
All three paths must be outside the Git repository.

The public API representation, file inventory and checksums are pinned in
`../data/zenodo-record.json`. Re-verification should retrieve the unauthenticated
record API, compare all eight server sizes and MD5 values, download and SHA-256
the seven small sidecars, and issue bounded first/last-byte range requests to
the master ZIP. Do not edit or create a new version without explicit approval.

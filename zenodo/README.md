# Zenodo deposit procedure and publication gate

`metadata.json` is the exact proposed legacy Zenodo deposit metadata. Zenodo's
official API classifies `upload_type: video` as “Video/Audio”; its current
licence vocabulary confirms `cc-by-nc-sa-4.0`.

The prepared deposit bundle contains only:

1. `stanford-cs229-machine-learning-audio-edition-v1.0.zip`
2. `stanford-cs229-machine-learning-audio-edition-v1.0.zip.sha256`
3. `MANIFEST.json`
4. `SHA256SUMS`
5. `README.md`
6. `LICENSE.md`
7. `PROVENANCE.md`
8. `ZENODO-METADATA.json`

Create it outside Git with:

```bash
python scripts/prepare_zenodo.py \
  --build-dir /ABSOLUTE/PATH/TO/build \
  --output-dir /ABSOLUTE/NEW/PATH/zenodo-draft
```

No Zenodo CLI or credential is assumed. If an access token is configured later,
use Zenodo's official deposition API over HTTPS with the token only in the
`Authorization: Bearer` header—never in a URL, command log or repository.

1. `POST https://zenodo.org/api/deposit/depositions` to create an empty draft.
2. Upload exactly the eight files listed by the generated `deposit-report.json`
   to the draft's returned bucket URL.
3. `PUT` the exact object in `metadata.json` to the draft deposition endpoint.
4. Read the draft back and compare its metadata, file names, sizes and checksums
   with the local report.
5. Stop and present the exact public metadata, file inventory/checksums and any
   residual uncertainty for explicit human approval.
6. Only after approval, `POST` the draft's `links.publish` endpoint. Publishing
   registers the DOI and is intentionally not automated by this repository.

Zenodo's sandbox uses separate credentials and does not authorize production
publication. Never reserve or cite a DOI as published until the record is
actually published and independently retrievable.

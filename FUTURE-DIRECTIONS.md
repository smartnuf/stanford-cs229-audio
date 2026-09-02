# Future directions

This document preserves possible next steps and lessons from the CS229 audio
preservation project. It is advisory rather than a release plan: an item listed
here is not a commitment, an authorization to publish or contact anyone, or a
change to the repository invariants in `AGENTS.md`.

The current repository should remain a focused, reproducible record of this
specific collection. It is also a useful real-world reference implementation,
but its CS229-specific assumptions should not become an accidental general
specification.

## What belongs in this repository

Project-specific maintenance and evidence should stay here:

- canonical CS229 episode, media, release, feed and preservation metadata;
- provenance, source mapping, attribution and collection-specific licensing;
- deterministic preservation-package and site generation;
- offline, HTTP and client-level validation for the published feed;
- recovery, feed migration and release-verification procedures;
- known delivery limitations and bounded maintenance work; and
- the prepared, explicitly unsent Castbox restoration material.

Reasonable future work within that boundary includes:

1. Periodically review scheduled link and client-compatibility results, treating
   transient network failures separately from semantic failures.
2. Complete the remaining manual iPhone checks for explicit download, seeking,
   artwork and Lecture 1→20 ordering. Automated gPodder and FFmpeg checks remain
   complementary evidence, not a substitute for Apple Podcasts acceptance.
3. Monitor GitHub Release delivery. Its CDN currently identifies M4A responses
   as `application/octet-stream`, although the feed and Release API identify
   them as `audio/mp4` and current clients successfully stream them. Reconsider
   enclosure hosting if this becomes a compatibility problem.
4. Reassess a controlled domain or alternate object host only as a separately
   planned migration. Preserve every episode GUID and use the migration process
   in `OPERATIONS.md`; never repurpose the existing feed URL.
5. Keep the published Zenodo v1.0 record stable. Create a new Zenodo version
   only for a substantive preservation release, not for speculative roadmap
   changes or routine website edits.

Any action that changes public identities, release bytes or enclosure URLs,
sends correspondence, or submits the feed to a directory remains subject to the
human gates in `AGENTS.md`.

## What belongs in a separate reusable project

A general preservation toolkit would be useful, but should be developed in a
separate repository rather than by parameterizing this live publication in
place. A possible name is `podcast-preservation-kit`. This repository can then
serve as an evidence-backed example and, eventually, a conformance fixture.

Candidate components for that project are:

- a normative `SPECIFICATION.md` using clearly scoped MUST, SHOULD and MAY
  requirements;
- an adaptation guide starting from a new collection's source evidence and
  rights assessment;
- JSON Schemas for project, episode, media, provenance, package, release and
  archival-deposit metadata;
- declarative project configuration with provider-specific publication modules;
- deterministic feed and preservation-package builders;
- guarded, resumable publication tooling for GitHub Releases/Pages and Zenodo;
- the existing layers of offline, HTTP, gPodder and FFmpeg validation;
- dependency packaging, supported-platform documentation and bootstrap checks;
- a small, synthetic or unambiguously redistributable media fixture;
- a provenance and rights checklist, threat model, publication gates and
  recovery exercises; and
- contribution, security and maintenance policies suitable for reuse.

Extraction should preserve two important boundaries:

- The toolkit's code licence cannot grant rights to media processed with it.
  Every collection needs an independent rights and provenance assessment.
- Collection facts must be configuration or evidence, not framework defaults.
  The CS229 count of 20 episodes, byte total, names, titles, URLs, licence, tag,
  DOI and publisher identity are not generic requirements.

The reusable project should begin only when there is intent to maintain it. A
small tested specification and fixture are preferable to copying the present
scripts into an apparently generic but still collection-coupled repository.

## What should not be public project material

Keep credentials, tokens, cookies, local authentication details, private
addresses, private analytics, unpublished deposit identifiers, and private or
personally identifying correspondence out of Git. Unresolved legal advice and
contact strategy should also remain private until deliberately converted into
non-sensitive, evidence-based public documentation.

Public templates may be retained when they contain no private information and
are unmistakably marked as drafts. Their presence does not authorize sending
them.

## Discoverability and promotion

Modest promotion of the preservation record is reasonable. The safest initial
emphasis is the project, its verification evidence and the Zenodo DOI—not a
claim to be an official or replacement Stanford channel.

Low-risk improvements could include:

- setting the GitHub repository homepage to the GitHub Pages project page;
- adding accurate repository topics such as `digital-preservation`, `podcast`,
  `rss`, `open-education`, `machine-learning`, `ffmpeg`, `zenodo`,
  `reproducible-builds` and `podcasting-20`;
- adding concise Listen, Verify and Reuse signposts to the README;
- adding CI, DOI and licence badges plus a `CITATION.cff`; and
- sharing the repository and DOI in relevant digital-preservation or open
  education communities with the existing non-endorsement wording.

Broader feed promotion and podcast-directory submission should remain deferred
until the remaining manual client checks, contact requirements, hosting posture
and coexistence with historical listings have been considered. No Stanford,
Apple, Castbox or other third-party logos or implied approval should be used.

## Decision guide

Use this repository for work necessary to preserve, verify, operate or explain
this CS229 edition. Use a future toolkit repository for collection-independent
specification, schemas and reusable software. Keep sensitive deliberation and
credentials private. Preserve the Zenodo record as the immutable v1.0 archival
snapshot.

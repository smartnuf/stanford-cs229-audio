#!/usr/bin/env python3
"""Shared deterministic data loading and rendering for the CS229 feed."""

from __future__ import annotations

import csv
import html
import json
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin, urlparse

ROOT = Path(__file__).resolve().parents[1]
NS_ATOM = "http://www.w3.org/2005/Atom"
NS_ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
NS_PODCAST = "https://podcastindex.org/namespace/1.0"
NAMESPACES = {"atom": NS_ATOM, "itunes": NS_ITUNES, "podcast": NS_PODCAST}
PODCAST_GUID_NAMESPACE = uuid.UUID("ead4c236-bf58-58c6-a2c6-a6b28d128cb6")

for prefix, namespace in NAMESPACES.items():
    ET.register_namespace(prefix, namespace)


@dataclass(frozen=True)
class Episode:
    number: int
    title: str
    duration_seconds: float
    duration: str
    source_filename: str
    filename: str
    size_bytes: int
    sha256: str
    source_video_url: str
    transcript_html_url: str
    transcript_pdf_url: str
    enclosure_url: str
    guid: str


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def duration_text(seconds: float) -> str:
    total = int(round(seconds))
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def channel_guid(publication: dict) -> str:
    return str(uuid.UUID(publication["identity"]["channel_guid"]))


def derived_channel_guid(publication: dict) -> str:
    """Derive the Podcasting 2.0 channel GUID from its one-time canonical seed."""
    identity = publication["identity"]
    namespace = uuid.UUID(identity["channel_guid_namespace"])
    return str(uuid.uuid5(namespace, identity["channel_guid_seed"]))


def episode_guid(publication: dict, number: int) -> str:
    name = publication["identity"]["episode_name_template"].format(number=number)
    namespace = uuid.UUID(publication["identity"]["episode_namespace"])
    return f"urn:uuid:{uuid.uuid5(namespace, name)}"


def load_catalog(root: Path = ROOT) -> tuple[dict, list[Episode]]:
    publication = read_json(root / "data" / "publication.json")
    lecture_document = read_json(root / "data" / "lectures.json")
    media_document = read_json(root / "data" / "media-manifest.json")
    with (root / "provenance" / "source-map.csv").open(encoding="utf-8", newline="") as handle:
        source_rows = list(csv.DictReader(handle))

    lectures = lecture_document["lectures"]
    media_rows = media_document["records"]
    lecture_numbers = [record["number"] for record in lectures]
    media_numbers = [record["lecture"] for record in media_rows]
    source_numbers = [int(record["lecture"]) for record in source_rows]
    expected_numbers = list(range(1, 21))
    if lecture_numbers != expected_numbers:
        raise ValueError("Lecture metadata must contain unique sequential rows 01 through 20")
    if sorted(media_numbers) != expected_numbers or len(set(media_numbers)) != 20:
        raise ValueError("Media manifest must contain unique rows 01 through 20")
    if sorted(source_numbers) != expected_numbers or len(set(source_numbers)) != 20:
        raise ValueError("Source map must contain unique rows 01 through 20")
    media_by_number = {record["lecture"]: record for record in media_rows}
    source_by_number = {int(record["lecture"]): record for record in source_rows}
    episodes: list[Episode] = []
    for lecture in lectures:
        number = lecture["number"]
        media = media_by_number[number]
        source = source_by_number[number]
        release_filename = f"CS229-lecture{number:02d}.m4a"
        if source["title"] != lecture["title"]:
            raise ValueError(f"Source-map title mismatch for lecture {number}")
        if source["duration"] != duration_text(lecture["duration_seconds"]):
            raise ValueError(f"Source-map duration mismatch for lecture {number}")
        if int(source["video_size_bytes"]) != lecture["video_size_bytes"]:
            raise ValueError(f"Source-map video size mismatch for lecture {number}")
        if abs(media["duration_seconds"] - lecture["duration_seconds"]) >= 0.001:
            raise ValueError(f"Media duration mismatch for lecture {number}")
        if media["audio"] != {"codec": "aac", "profile": "LC", "sample_rate_hz": 48000, "channels": 2}:
            raise ValueError(f"Media audio signature mismatch for lecture {number}")
        episodes.append(Episode(
            number=number,
            title=lecture["title"],
            duration_seconds=lecture["duration_seconds"],
            duration=duration_text(lecture["duration_seconds"]),
            source_filename=media["filename"],
            filename=release_filename,
            size_bytes=media["size_bytes"],
            sha256=media["sha256"],
            source_video_url=source["video_url"],
            transcript_html_url=source["transcript_html_url"],
            transcript_pdf_url=source["transcript_pdf_url"],
            enclosure_url=urljoin(publication["media"]["base_url"], release_filename),
            guid=episode_guid(publication, number),
        ))
    return publication, episodes


def validate_catalog(publication: dict, episodes: list[Episode]) -> None:
    if publication.get("schema_version") != 1:
        raise ValueError("Unsupported publication schema")
    required_sections = {"feed", "course", "media", "preservation", "license", "identity"}
    if not required_sections.issubset(publication):
        raise ValueError("Publication metadata is incomplete")
    if [episode.number for episode in episodes] != list(range(1, 21)):
        raise ValueError("Episodes must be exactly 01 through 20")
    if len({episode.title for episode in episodes}) != 20:
        raise ValueError("Episode titles must be unique")
    if len({episode.filename for episode in episodes}) != 20:
        raise ValueError("Episode filenames must be unique")
    if len({episode.guid for episode in episodes}) != 20:
        raise ValueError("Episode GUIDs must be unique")
    if len({episode.enclosure_url for episode in episodes}) != 20:
        raise ValueError("Enclosure URLs must be unique")
    if sum(episode.size_bytes for episode in episodes) != 1_798_240_224:
        raise ValueError("Canonical enclosure total has changed")
    if publication["feed"]["type"] != "serial":
        raise ValueError("Ordered lecture series must use serial feed type")
    for key in ("site_url", "feed_url", "artwork_url"):
        if urlparse(publication["feed"][key]).scheme != "https":
            raise ValueError(f"Feed {key} must use HTTPS")
    if urlparse(publication["media"]["base_url"]).scheme != "https":
        raise ValueError("Media base URL must use HTTPS")
    preservation = publication["preservation"]
    if preservation != {
        "version": "1.0",
        "zenodo_record_id": 22261678,
        "doi": "10.5281/zenodo.22261678",
        "doi_url": "https://doi.org/10.5281/zenodo.22261678",
        "record_url": "https://zenodo.org/records/22261678",
    }:
        raise ValueError("Published Zenodo preservation identity changed")
    identity = publication["identity"]
    normalized_feed_url = re.sub(r"^https?://", "", publication["feed"]["feed_url"]).rstrip("/")
    if uuid.UUID(identity["channel_guid_namespace"]) != PODCAST_GUID_NAMESPACE:
        raise ValueError("Podcasting 2.0 channel GUID namespace changed")
    if (publication.get("publication_status") == "prepared"
            and identity["channel_guid_seed"] != normalized_feed_url):
        raise ValueError("Channel GUID seed must match the first public feed URL")
    if channel_guid(publication) != derived_channel_guid(publication):
        raise ValueError("Pinned channel GUID does not match its one-time derivation")
    for episode in episodes:
        if episode.source_filename != f"lecture{episode.number:02d}.m4a":
            raise ValueError(f"Unexpected source filename for lecture {episode.number}")
        if episode.filename != f"CS229-lecture{episode.number:02d}.m4a":
            raise ValueError(f"Unexpected filename for lecture {episode.number}")
        if episode.duration != duration_text(episode.duration_seconds):
            raise ValueError(f"Duration mismatch for lecture {episode.number}")
        if not all(urlparse(url).scheme == "https" for url in (
            episode.source_video_url, episode.transcript_html_url,
            episode.transcript_pdf_url, episode.enclosure_url,
        )):
            raise ValueError(f"Lecture {episode.number} contains a non-HTTPS URL")


def add_text(parent: ET.Element, tag: str, value: str, attributes: dict[str, str] | None = None) -> ET.Element:
    element = ET.SubElement(parent, tag, attributes or {})
    element.text = value
    return element


def build_feed(publication: dict, episodes: list[Episode]) -> bytes:
    validate_catalog(publication, episodes)
    feed = publication["feed"]
    course = publication["course"]
    licence = publication["license"]

    rss = ET.Element("rss", {"version": "2.0"})
    channel = ET.SubElement(rss, "channel")
    add_text(channel, "title", feed["title"])
    add_text(channel, "link", course["source_url"])
    add_text(channel, "description", feed["description"])
    add_text(channel, "language", feed["language"])
    add_text(channel, "copyright", f"Source lectures © Stanford University and/or identified rights holders; adaptation {licence['short_name']}")
    add_text(channel, "generator", "stanford-cs229-audio deterministic generator")
    ET.SubElement(channel, f"{{{NS_ATOM}}}link", {
        "href": feed["feed_url"], "rel": "self", "type": "application/rss+xml",
    })
    ET.SubElement(channel, f"{{{NS_ATOM}}}link", {
        "href": publication["preservation"]["doi_url"], "rel": "related",
        "type": "text/html", "title": "Zenodo preservation record",
    })
    add_text(channel, f"{{{NS_ITUNES}}}author", f"{course['lecturer']} (lecturer)")
    add_text(channel, f"{{{NS_ITUNES}}}type", feed["type"])
    add_text(channel, f"{{{NS_ITUNES}}}explicit", "false")
    add_text(channel, f"{{{NS_ITUNES}}}summary", feed["description"])
    ET.SubElement(channel, f"{{{NS_ITUNES}}}category", {"text": feed["category"]})
    ET.SubElement(channel, f"{{{NS_ITUNES}}}image", {"href": feed["artwork_url"]})
    add_text(channel, f"{{{NS_PODCAST}}}guid", channel_guid(publication))
    add_text(channel, f"{{{NS_PODCAST}}}medium", "course")
    add_text(channel, f"{{{NS_PODCAST}}}license", licence["identifier"], {"url": licence["url"]})

    image = ET.SubElement(channel, "image")
    add_text(image, "url", feed["artwork_url"])
    add_text(image, "title", feed["title"])
    add_text(image, "link", course["source_url"])

    for episode in episodes:
        item = ET.SubElement(channel, "item")
        add_text(item, "title", f"Lecture {episode.number:02d} — {episode.title}")
        add_text(item, "link", episode.source_video_url)
        add_text(item, "guid", episode.guid, {"isPermaLink": "false"})
        description = (
            f"Lecture {episode.number:02d} of Stanford CS229 Machine Learning, taught by Andrew Ng. "
            f"Source lecture: {episode.source_video_url} Transcript (HTML): {episode.transcript_html_url} "
            f"Transcript (PDF): {episode.transcript_pdf_url} This is an unofficial audio-only adaptation "
            f"from Stanford Engineering Everywhere; it is not endorsed by Stanford University or Andrew Ng. "
            f"Licensed {licence['short_name']}: {licence['url']}"
        )
        add_text(item, "description", description)
        add_text(item, f"{{{NS_ITUNES}}}author", f"{course['lecturer']} (lecturer)")
        add_text(item, f"{{{NS_ITUNES}}}episode", str(episode.number))
        add_text(item, f"{{{NS_ITUNES}}}episodeType", "full")
        add_text(item, f"{{{NS_ITUNES}}}duration", episode.duration)
        add_text(item, f"{{{NS_ITUNES}}}explicit", "false")
        ET.SubElement(item, "enclosure", {
            "url": episode.enclosure_url,
            "length": str(episode.size_bytes),
            "type": publication["media"]["mime_type"],
        })
        ET.SubElement(item, f"{{{NS_PODCAST}}}transcript", {
            "url": episode.transcript_html_url, "type": "text/html", "language": "en-US",
        })
    ET.indent(rss, space="  ")
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True, short_empty_elements=True) + b"\n"


def build_index(publication: dict, episodes: list[Episode]) -> bytes:
    validate_catalog(publication, episodes)
    feed = publication["feed"]
    course = publication["course"]
    licence = publication["license"]
    items = "\n".join(
        f'          <li><span>{episode.number:02d}</span> <a href="{html.escape(episode.source_video_url)}">'
        f'{html.escape(episode.title)}</a> <small>{episode.duration}</small></li>'
        for episode in episodes
    )
    document = f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{html.escape(feed['title'])}</title>
    <meta name="description" content="{html.escape(feed['description'])}">
    <link rel="alternate" type="application/rss+xml" title="RSS feed" href="feed.xml">
    <style>
      :root {{ color-scheme: light dark; font-family: ui-sans-serif, system-ui, sans-serif; }}
      body {{ margin: 0; background: #101827; color: #eaf0f8; }}
      main {{ width: min(880px, calc(100% - 2rem)); margin: 3rem auto; }}
      header {{ display: grid; grid-template-columns: minmax(140px, 240px) 1fr; gap: 2rem; align-items: center; }}
      img {{ width: 100%; border-radius: 1rem; box-shadow: 0 1rem 3rem #0008; }}
      h1 {{ font-size: clamp(2rem, 6vw, 4rem); line-height: 1; margin: 0 0 1rem; }}
      a {{ color: #75c8ff; }}
      .subscribe {{ display: inline-block; padding: .8rem 1rem; background: #d64045; color: white; border-radius: .5rem; font-weight: 700; text-decoration: none; }}
      ol {{ list-style: none; padding: 0; columns: 2 18rem; column-gap: 2rem; }}
      li {{ break-inside: avoid; padding: .55rem 0; border-bottom: 1px solid #ffffff22; }}
      li span {{ display: inline-block; width: 2rem; color: #9fb1c7; font-variant-numeric: tabular-nums; }}
      small {{ color: #9fb1c7; white-space: nowrap; }}
      footer {{ margin-top: 3rem; color: #b9c5d3; }}
      @media (max-width: 620px) {{ header {{ grid-template-columns: 1fr; }} header img {{ max-width: 220px; }} ol {{ columns: 1; }} }}
    </style>
  </head>
  <body>
    <main>
      <header>
        <img src="cover.jpg" width="3000" height="3000" alt="CS229 audio preservation cover">
        <div>
          <h1>{html.escape(feed['title'])}</h1>
          <p>{html.escape(feed['description'])}</p>
          <p><a class="subscribe" href="feed.xml">Open or copy the RSS feed</a></p>
          <p><a href="{html.escape(publication['media']['release_url'])}">Download the verified audio and canonical preservation ZIP</a></p>
          <p><a href="{html.escape(publication['preservation']['doi_url'])}">Permanent preservation record: {html.escape(publication['preservation']['doi'])}</a></p>
          <p>Add the feed URL manually in a podcast application that supports URL subscriptions.</p>
        </div>
      </header>
      <section>
        <h2>Lectures</h2>
        <ol>
{items}
        </ol>
      </section>
      <footer>
        <p>Lecturer: Andrew Ng. Source: <a href="{html.escape(course['source_url'])}">Stanford Engineering Everywhere CS229</a>.</p>
        <p><a href="https://github.com/{html.escape(publication['media']['repository'])}">Metadata, source map, checksums and validation tooling</a>.</p>
        <p>Unofficial audio-only adaptation; not endorsed by Stanford University or Andrew Ng. Licensed <a href="{html.escape(licence['url'])}">{html.escape(licence['short_name'])}</a>. No monetization, advertising, sponsorship, or commercial purpose.</p>
      </footer>
    </main>
  </body>
</html>
"""
    return document.encode("utf-8")


def outputs(root: Path = ROOT) -> dict[Path, bytes]:
    publication, episodes = load_catalog(root)
    return {
        root / "docs" / "feed.xml": build_feed(publication, episodes),
        root / "docs" / "index.html": build_index(publication, episodes),
    }

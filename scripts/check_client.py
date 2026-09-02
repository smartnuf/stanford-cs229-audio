#!/usr/bin/env python3
"""Traceable headless podcast-client, download, seek, and decode checks."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from feedlib import NS_ITUNES, ROOT, load_catalog

USER_AGENT = "stanford-cs229-audio-client-check/1.0"
TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}
NETWORK_MARKERS = (
    "connection reset", "connection timed out", "connection refused",
    "temporary failure", "network is unreachable", "name or service not known",
    "server returned 5", "http error 429", "i/o error",
)


class NetworkUnavailable(RuntimeError):
    """A bounded network operation could not complete."""


class SemanticFailure(RuntimeError):
    """A client observed incorrect feed or media behavior."""


@dataclass(frozen=True)
class FeedEpisode:
    number: int
    title: str
    guid: str
    enclosure_url: str
    size_bytes: int
    mime_type: str


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_feed(url: str, retries: int = 3, timeout: int = 20) -> tuple[bytes, dict]:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept-Encoding": "identity"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read(5 * 1024 * 1024 + 1)
                if response.status != 200:
                    raise SemanticFailure(f"feed GET returned HTTP {response.status}")
                if not url.startswith("https://") or not response.url.startswith("https://"):
                    raise SemanticFailure("feed request or redirect is not HTTPS")
                if len(body) > 5 * 1024 * 1024:
                    raise SemanticFailure("feed exceeds the 5 MiB safety bound")
                return body, {
                    "url": url,
                    "final_url": response.url,
                    "status": response.status,
                    "content_type": response.headers.get_content_type(),
                    "size_bytes": len(body),
                    "sha256": hashlib.sha256(body).hexdigest(),
                    "attempts": attempt + 1,
                }
        except urllib.error.HTTPError as error:
            if error.code not in TRANSIENT_HTTP:
                raise SemanticFailure(f"feed GET returned HTTP {error.code}") from error
            last_error = error
        except SemanticFailure:
            raise
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            last_error = error
        if attempt + 1 < retries:
            time.sleep(2 ** attempt)
    raise NetworkUnavailable(
        f"feed unavailable after {retries} attempts ({type(last_error).__name__})")


def parse_feed(raw: bytes, expected_url: str) -> list[FeedEpisode]:
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as error:
        raise SemanticFailure(f"feed XML is malformed: {error}") from error
    channel = root.find("channel")
    if root.tag != "rss" or channel is None:
        raise SemanticFailure("document is not an RSS channel")
    episodes = []
    for item in channel.findall("item"):
        episode_text = item.findtext(f"{{{NS_ITUNES}}}episode")
        enclosure = item.find("enclosure")
        guid = item.find("guid")
        if (episode_text is None or enclosure is None or guid is None or not guid.text
                or guid.get("isPermaLink") != "false"):
            raise SemanticFailure("episode lacks podcast number, enclosure, or stable GUID")
        try:
            number = int(episode_text)
            size_bytes = int(enclosure.attrib["length"])
            url = enclosure.attrib["url"]
            mime_type = enclosure.attrib["type"]
        except (KeyError, ValueError) as error:
            raise SemanticFailure("episode enclosure metadata is malformed") from error
        episodes.append(FeedEpisode(
            number=number,
            title=item.findtext("title", ""),
            guid=guid.text,
            enclosure_url=url,
            size_bytes=size_bytes,
            mime_type=mime_type,
        ))
    if [episode.number for episode in episodes] != list(range(1, 21)):
        raise SemanticFailure("client feed order is not exactly Lecture 01 through 20")
    if len({episode.guid for episode in episodes}) != 20:
        raise SemanticFailure("client feed contains duplicate GUIDs")
    if len({episode.enclosure_url for episode in episodes}) != 20:
        raise SemanticFailure("client feed contains duplicate enclosure URLs")
    if any(not episode.enclosure_url.startswith("https://") for episode in episodes):
        raise SemanticFailure("client feed contains a non-HTTPS enclosure")
    publication, canonical = load_catalog()
    if publication["feed"]["feed_url"] != expected_url:
        raise SemanticFailure("requested feed URL differs from canonical publication metadata")
    expected = [
        (episode.number, f"Lecture {episode.number:02d} — {episode.title}", episode.guid,
         episode.enclosure_url, episode.size_bytes, "audio/mp4")
        for episode in canonical
    ]
    observed = [
        (episode.number, episode.title, episode.guid, episode.enclosure_url,
         episode.size_bytes, episode.mime_type)
        for episode in episodes
    ]
    if observed != expected:
        raise SemanticFailure("live RSS episode identities differ from canonical metadata")
    return episodes


def selected_numbers(scope: str) -> list[int]:
    if scope == "smoke":
        return [1, 10, 20]
    if scope == "full":
        return list(range(1, 21))
    raise ValueError(f"unsupported scope: {scope}")


def seek_offsets(duration_seconds: float, segment_seconds: float) -> list[float]:
    points = (0.0, min(300.0, duration_seconds / 2),
              max(0.0, duration_seconds - segment_seconds - 20.0))
    return list(dict.fromkeys(round(point, 3) for point in points))


def output_tail(value: str, limit: int = 16000) -> str:
    clean = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", value)
    return clean[-limit:]


def command_trace(command: list[str], timeout: int, env: dict[str, str] | None = None) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=timeout, env=env)
    except FileNotFoundError as error:
        raise SemanticFailure(f"required client executable is unavailable: {command[0]}") from error
    except subprocess.TimeoutExpired as error:
        raise NetworkUnavailable(f"client command timed out after {timeout}s: {command[0]}") from error
    trace = {
        "command": command,
        "exit_code": result.returncode,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "stdout_tail": output_tail(result.stdout),
        "stderr_tail": output_tail(result.stderr),
    }
    if result.returncode:
        combined = (result.stdout + "\n" + result.stderr).lower()
        error_type = NetworkUnavailable if any(marker in combined for marker in NETWORK_MARKERS) else SemanticFailure
        raise error_type(
            f"{command[0]} exited {result.returncode}: {output_tail(result.stderr or result.stdout, 800)}")
    return trace


def tool_version(executable: str) -> str:
    trace = command_trace([executable, "-version"], timeout=20)
    first_line = (trace["stdout_tail"] or trace["stderr_tail"]).splitlines()
    return first_line[0] if first_line else "version output unavailable"


def execution_identity() -> dict:
    revision = "unavailable"
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=False,
            capture_output=True, text=True, timeout=10)
        candidate = result.stdout.strip()
        if result.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", candidate):
            revision = candidate
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return {
        "git_commit": revision,
        "github_run_id": os.environ.get("GITHUB_RUN_ID"),
        "github_run_attempt": os.environ.get("GITHUB_RUN_ATTEMPT"),
        "github_workflow": os.environ.get("GITHUB_WORKFLOW"),
        "operating_system": platform.platform(),
        "python": sys.version.splitlines()[0],
    }


def probe_episode(executable: str, episode: FeedEpisode, expected_duration: float,
                  timeout: int) -> dict:
    command = [
        executable, "-v", "error", "-rw_timeout", "30000000", "-user_agent", USER_AGENT,
        "-show_entries", "format=format_name,duration,size:"
        "stream=codec_type,codec_name,profile,sample_rate,channels",
        "-of", "json", episode.enclosure_url,
    ]
    trace = command_trace(command, timeout=timeout)
    try:
        data = json.loads(trace["stdout_tail"])
        media_format = data["format"]
    except (json.JSONDecodeError, KeyError) as error:
        raise SemanticFailure(f"Lecture {episode.number:02d} FFprobe output is invalid") from error
    audio = [stream for stream in data.get("streams", []) if stream.get("codec_type") == "audio"]
    if len(audio) != 1:
        raise SemanticFailure(f"Lecture {episode.number:02d} does not expose one audio stream")
    stream = audio[0]
    signature = (
        stream.get("codec_name"), stream.get("profile"), stream.get("sample_rate"),
        stream.get("channels"),
    )
    if signature != ("aac", "LC", "48000", 2):
        raise SemanticFailure(f"Lecture {episode.number:02d} audio signature changed: {signature}")
    if "m4a" not in media_format.get("format_name", "").split(","):
        raise SemanticFailure(f"Lecture {episode.number:02d} is not detected as M4A")
    duration = float(media_format["duration"])
    if abs(duration - expected_duration) >= 0.01:
        raise SemanticFailure(f"Lecture {episode.number:02d} duration changed")
    if int(media_format["size"]) != episode.size_bytes:
        raise SemanticFailure(f"Lecture {episode.number:02d} remote size changed")
    return {
        "command": trace["command"],
        "exit_code": trace["exit_code"],
        "elapsed_seconds": trace["elapsed_seconds"],
        "format_name": media_format["format_name"],
        "duration_seconds": duration,
        "size_bytes": int(media_format["size"]),
        "audio": {
            "codec": stream["codec_name"],
            "profile": stream["profile"],
            "sample_rate_hz": int(stream["sample_rate"]),
            "channels": stream["channels"],
        },
    }


def decoded_seconds(progress: str) -> float:
    values = []
    for line in progress.splitlines():
        if line.startswith("out_time_us="):
            try:
                values.append(int(line.split("=", 1)[1]) / 1_000_000)
            except ValueError:
                pass
    return max(values, default=0.0)


def decode_segment(executable: str, episode: FeedEpisode, offset: float,
                   segment_seconds: float, timeout: int) -> dict:
    command = [
        executable, "-nostdin", "-hide_banner", "-loglevel", "error", "-xerror",
        "-rw_timeout", "30000000", "-user_agent", USER_AGENT,
        "-ss", f"{offset:.3f}", "-i", episode.enclosure_url,
        "-t", f"{segment_seconds:.3f}", "-map", "0:a:0",
        "-progress", "pipe:1", "-nostats", "-f", "null", "-",
    ]
    trace = command_trace(command, timeout=timeout)
    decoded = decoded_seconds(trace["stdout_tail"])
    if decoded < segment_seconds - 0.2:
        raise SemanticFailure(
            f"Lecture {episode.number:02d} decoded only {decoded:.3f}s at {offset:.3f}s")
    return {
        "command": trace["command"],
        "exit_code": trace["exit_code"],
        "elapsed_seconds": trace["elapsed_seconds"],
        "offset_seconds": offset,
        "requested_seconds": segment_seconds,
        "decoded_seconds": round(decoded, 3),
    }


def validate_gpodder_listing(output: str, episodes: list[FeedEpisode]) -> None:
    missing = [episode.number for episode in episodes if output.count(episode.guid) != 1]
    if missing:
        raise SemanticFailure(f"gPodder did not list each canonical GUID exactly once: {missing}")


def download_files(root: Path) -> set[Path]:
    return {path for path in root.rglob("*") if path.is_file() and not path.is_symlink()}


def run_gpodder(executable: str, feed_url: str, episodes: list[FeedEpisode],
                 download_numbers: list[int], timeout: int) -> dict:
    with tempfile.TemporaryDirectory(prefix="cs229-gpodder-") as temporary:
        temp = Path(temporary)
        home = temp / "profile"
        downloads = temp / "downloads"
        home.mkdir()
        downloads.mkdir()
        env = os.environ.copy()
        env.update({
            "GPODDER_HOME": str(home),
            "GPODDER_DOWNLOAD_DIR": str(downloads),
            "PAGER": "cat",
            "LC_ALL": "C.UTF-8",
        })
        traces = []
        for arguments in (
            ["subscribe", feed_url],
            ["update", feed_url],
            ["episodes", "--guid", feed_url],
        ):
            traces.append(command_trace([executable, *arguments], timeout=timeout, env=env))
        validate_gpodder_listing(traces[-1]["stdout_tail"], episodes)
        by_number = {episode.number: episode for episode in episodes}
        downloads_report = []
        before = download_files(downloads)
        for number in download_numbers:
            episode = by_number[number]
            trace = command_trace(
                [executable, "download", feed_url, episode.guid], timeout=timeout, env=env)
            after = download_files(downloads)
            new_files = after - before
            candidates = [path for path in new_files if path.stat().st_size == episode.size_bytes]
            if len(candidates) != 1:
                raise SemanticFailure(
                    f"gPodder Lecture {number:02d} download file identity is ambiguous")
            downloaded = candidates[0]
            digest = sha256(downloaded)
            _, canonical = load_catalog()
            expected_digest = canonical[number - 1].sha256
            if digest != expected_digest:
                raise SemanticFailure(f"gPodder Lecture {number:02d} download hash mismatch")
            downloads_report.append({
                "lecture": number,
                "guid": episode.guid,
                "filename": downloaded.name,
                "size_bytes": downloaded.stat().st_size,
                "sha256": digest,
                "elapsed_seconds": trace["elapsed_seconds"],
                "exit_code": trace["exit_code"],
            })
            before = after
        return {
            "result": "pass",
            "profile_isolated": True,
            "profile_removed_after_test": True,
            "listed_episode_guids": len(episodes),
            "commands": [{
                "command": trace["command"],
                "exit_code": trace["exit_code"],
                "elapsed_seconds": trace["elapsed_seconds"],
                "stdout_tail": trace["stdout_tail"],
                "stderr_tail": trace["stderr_tail"],
            } for trace in traces],
            "downloads": downloads_report,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("smoke", "full"), default="smoke")
    parser.add_argument("--feed-url")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ffprobe", default="ffprobe")
    parser.add_argument("--ffmpeg", default="ffmpeg")
    parser.add_argument("--gpo", default="gpo")
    parser.add_argument("--skip-gpodder", action="store_true",
                        help="development-only: omit the real podcatcher layer")
    parser.add_argument("--segment-seconds", type=float, default=5.0)
    parser.add_argument("--command-timeout", type=int, default=180)
    parser.add_argument("--download-timeout", type=int, default=1200)
    args = parser.parse_args()
    publication, canonical = load_catalog()
    feed_url = args.feed_url or publication["feed"]["feed_url"]
    report = {
        "schema_version": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "scope": args.scope,
        "feed_url": feed_url,
        "execution": execution_identity(),
        "result": "pass",
        "network_failures": [],
        "semantic_failures": [],
        "tools": {},
        "feed": None,
        "ffmpeg_streaming": [],
        "gpodder": None,
    }
    exit_code = 0
    try:
        report["tools"]["ffprobe"] = tool_version(args.ffprobe)
        report["tools"]["ffmpeg"] = tool_version(args.ffmpeg)
        raw, fetch_trace = fetch_feed(feed_url)
        episodes = parse_feed(raw, feed_url)
        fetch_trace["episodes"] = len(episodes)
        fetch_trace["ordered_lectures"] = [episode.number for episode in episodes]
        report["feed"] = fetch_trace
        by_number = {episode.number: episode for episode in episodes}
        for number in selected_numbers(args.scope):
            episode = by_number[number]
            technical = canonical[number - 1]
            record = {
                "lecture": number,
                "guid": episode.guid,
                "url": episode.enclosure_url,
                "probe": probe_episode(
                    args.ffprobe, episode, technical.duration_seconds, args.command_timeout),
                "segments": [],
            }
            for offset in seek_offsets(technical.duration_seconds, args.segment_seconds):
                record["segments"].append(decode_segment(
                    args.ffmpeg, episode, offset, args.segment_seconds, args.command_timeout))
            report["ffmpeg_streaming"].append(record)
        if args.skip_gpodder:
            report["gpodder"] = {"result": "skipped_by_operator"}
        else:
            version_trace = command_trace([args.gpo, "help"], timeout=30)
            module_trace = command_trace(
                [sys.executable, "-c", "import gpodder; print(gpodder.__version__)"], timeout=30)
            report["tools"]["gpodder"] = {
                "version": module_trace["stdout_tail"].strip(),
                "gpo_executable": shutil.which(args.gpo) or args.gpo,
                "help_command_passed": version_trace["exit_code"] == 0,
            }
            downloads = [1] if args.scope == "smoke" else list(range(1, 21))
            report["gpodder"] = run_gpodder(
                args.gpo, feed_url, episodes, downloads, args.download_timeout)
    except NetworkUnavailable as error:
        report["network_failures"].append(str(error))
        report["result"], exit_code = "network_unavailable", 2
    except (SemanticFailure, ValueError, KeyError) as error:
        report["semantic_failures"].append(str(error))
        report["result"], exit_code = "semantic_failure", 1
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["summary"] = {
        "feed_episodes": report["feed"]["episodes"] if report["feed"] else 0,
        "ffmpeg_episodes": len(report["ffmpeg_streaming"]),
        "ffmpeg_segments": sum(len(row["segments"]) for row in report["ffmpeg_streaming"]),
        "gpodder_downloads": len(report["gpodder"].get("downloads", []))
        if report["gpodder"] else 0,
        "network_failures": len(report["network_failures"]),
        "semantic_failures": len(report["semantic_failures"]),
    }
    requested_output = args.output.absolute()
    if requested_output.is_symlink():
        raise ValueError(f"Refusing to overwrite symlink report: {requested_output}")
    output = requested_output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"result": report["result"], **report["summary"]}, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

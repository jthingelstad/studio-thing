"""Read-only data model for Studio's private Thingy operations pages.

The public Thingy client must never receive AWS credentials or operator data.
This module runs inside Studio's loopback-only, Tailscale-gated web process and
turns the existing Librarian admin reads into compact operational summaries.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
from dotenv import load_dotenv

from .operator_report import (
    DEFAULT_OWNER_EMAIL,
    DEFAULT_STACK,
    Conversation,
    compact,
    email_hash,
    iso_days_ago,
    load_turns,
    parse_iso,
    scan_conversations,
    stack_resource,
    utc_now,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_BUCKET = "weekly-thing-librarian"
_CACHE_SECONDS = 300


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    object_key: str
    count_field: str


SOURCE_SPECS = (
    SourceSpec("weekly_thing", "Weekly Thing", "artifacts/corpus.json", "issue_count"),
    SourceSpec("blog", "Thingelstad.com", "artifacts/blog_corpus.json", "post_count"),
    SourceSpec("podcast", "Another Thing", "artifacts/podcast_corpus.json", "episode_count"),
)


def _display_time(value: Any) -> str:
    dt = parse_iso(value)
    if not dt:
        return str(value or "Unknown")
    return dt.astimezone().strftime("%b %-d, %Y, %-I:%M %p %Z")


def _display_count(value: int | None) -> str:
    return f"{value:,}" if value is not None else "—"


def _display_bytes(value: int | None) -> str:
    if value is None:
        return "Unknown"
    amount = float(value)
    for unit in ("B", "KB", "MB", "GB"):
        if amount < 1024 or unit == "GB":
            return f"{amount:.0f} {unit}" if unit == "B" else f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


@dataclass(frozen=True)
class SourceMirror:
    count: int
    latest_content_at: str = ""
    changed_at: str = ""


@dataclass(frozen=True)
class CorpusStatus:
    key: str
    label: str
    status: str
    status_label: str
    object_key: str
    generated_at: str = ""
    uploaded_at: str = ""
    source_latest_at: str = ""
    source_changed_at: str = ""
    deployed_count: int | None = None
    source_count: int | None = None
    chunk_count: int | None = None
    link_count: int | None = None
    size_bytes: int | None = None
    embedding_model: str = ""
    reasons: tuple[str, ...] = ()
    error: str = ""

    @property
    def generated_display(self) -> str:
        return _display_time(self.generated_at)

    @property
    def uploaded_display(self) -> str:
        return _display_time(self.uploaded_at)

    @property
    def source_latest_display(self) -> str:
        return _display_time(self.source_latest_at)

    @property
    def source_changed_display(self) -> str:
        return _display_time(self.source_changed_at)

    @property
    def size_display(self) -> str:
        return _display_bytes(self.size_bytes)

    @property
    def deployed_count_display(self) -> str:
        return _display_count(self.deployed_count)

    @property
    def source_count_display(self) -> str:
        return _display_count(self.source_count)

    @property
    def chunk_count_display(self) -> str:
        return _display_count(self.chunk_count)

    @property
    def link_count_display(self) -> str:
        return _display_count(self.link_count)


@dataclass(frozen=True)
class FindingExample:
    conversation_id: str
    updated_at: str
    mode: str
    scope: str
    reader_label: str
    note: str

    @property
    def updated_display(self) -> str:
        return _display_time(self.updated_at)


@dataclass(frozen=True)
class ImprovementFinding:
    key: str
    label: str
    priority: str
    occurrences: int
    conversation_count: int
    latest_at: str
    modes: tuple[str, ...]
    scopes: tuple[str, ...]
    sources: tuple[str, ...]
    regression_candidate: bool
    examples: tuple[FindingExample, ...]

    @property
    def latest_display(self) -> str:
        return _display_time(self.latest_at)


@dataclass(frozen=True)
class QualitySummary:
    conversations: int = 0
    reviewed: int = 0
    needs_attention: int = 0
    downvotes: int = 0
    feedback: int = 0
    real_readers: int = 0
    quality_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ThingyDashboard:
    generated_at: str
    days: int
    corpora: tuple[CorpusStatus, ...]
    findings: tuple[ImprovementFinding, ...]
    quality: QualitySummary
    modes: tuple[str, ...]
    scopes: tuple[str, ...]
    errors: tuple[str, ...] = ()

    @property
    def generated_display(self) -> str:
        return _display_time(self.generated_at)

    @property
    def healthy_corpora(self) -> int:
        return sum(1 for corpus in self.corpora if corpus.status == "ready")

    @property
    def action_findings(self) -> int:
        return sum(1 for finding in self.findings if finding.priority in {"critical", "high"})


_FLAG_LABELS = {
    "citation_mismatch": "Citation mismatch",
    "unsupported_claim": "Unsupported claim",
    "source_gap": "Source gap",
    "refusal_issue": "Refusal issue",
    "privacy_boundary": "Privacy boundary",
    "prompt_leak": "Prompt leak",
    "tool_gap": "Tool gap",
    "ux_confusion": "UX confusion",
    "runtime_timeout": "Runtime exhaustion",
    "answer_too_long": "Answer too long",
    "answer_too_thin": "Answer too thin",
    "reader_downvote": "Reader downvote",
    "quality_problem": "Unclassified problem",
    "quality_watch": "Unclassified watch item",
}
_CRITICAL_FLAGS = {"privacy_boundary", "prompt_leak"}
_POSITIVE_FLAGS = {"reader_delight"}
_PRIORITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def _source_kinds(conversation: Conversation) -> set[str]:
    kinds: set[str] = set()
    for turn in conversation.turns:
        for citation in turn.citations:
            kind = str(citation.get("source_kind") or "").strip()
            if not kind and citation.get("issue_number"):
                kind = "weekly_thing"
            if kind in {"chunk", "issue", "newsletter"}:
                kind = "weekly_thing"
            if kind:
                kinds.add(kind)
    return kinds


def _finding_note(conversation: Conversation) -> str:
    if conversation.eval_improvements:
        return compact(conversation.eval_improvements[0], 320)
    return compact(conversation.eval_takeaway or conversation.summary, 320)


def build_quality_queue(conversations: list[Conversation]) -> tuple[ImprovementFinding, ...]:
    """Group structured evaluator/reader signals into a prioritized queue.

    Suggestions on otherwise clean conversations stay out of the queue. The
    queue is deliberately driven by evaluator flags, watch/problem quality,
    and reader downvotes so it remains small and action-oriented.
    """

    groups: dict[str, dict[str, Any]] = {}

    def add(
        key: str,
        conversation: Conversation,
        *,
        note: str = "",
        occurrence_count: int = 1,
    ) -> None:
        group = groups.setdefault(
            key,
            {
                "occurrences": 0,
                "conversations": set(),
                "modes": set(),
                "scopes": set(),
                "sources": set(),
                "examples": [],
                "latest_at": "",
                "problem": False,
                "downvote": False,
            },
        )
        group["occurrences"] += occurrence_count
        group["conversations"].add(conversation.conversation_id)
        group["modes"].add(conversation.mode or "thingy")
        group["scopes"].add(conversation.scope or "all")
        group["sources"].update(_source_kinds(conversation))
        group["problem"] = group["problem"] or conversation.eval_quality == "problem"
        group["downvote"] = group["downvote"] or key == "reader_downvote"
        if not group["latest_at"] or (
            parse_iso(conversation.updated_at) or datetime.min.replace(tzinfo=UTC)
        ) > (parse_iso(group["latest_at"]) or datetime.min.replace(tzinfo=UTC)):
            group["latest_at"] = conversation.updated_at
        if len(group["examples"]) < 4:
            group["examples"].append(
                FindingExample(
                    conversation_id=conversation.conversation_id,
                    updated_at=conversation.updated_at,
                    mode=conversation.mode or "thingy",
                    scope=conversation.scope or "all",
                    reader_label=conversation.reader_label,
                    note=compact(note or _finding_note(conversation), 320),
                )
            )

    for conversation in conversations:
        flags = [flag for flag in conversation.eval_flags if flag not in _POSITIVE_FLAGS]
        for flag in dict.fromkeys(flags):
            add(flag, conversation)

        downvote_turns = [turn for turn in conversation.turns if turn.feedback_reaction == "down"]
        for turn in downvote_turns:
            add(
                "reader_downvote",
                conversation,
                note=turn.feedback_comment or compact(turn.question, 240),
            )

        if conversation.eval_quality in {"watch", "problem"} and not flags:
            add(f"quality_{conversation.eval_quality}", conversation)

    findings: list[ImprovementFinding] = []
    for key, group in groups.items():
        occurrences = int(group["occurrences"])
        repeated = occurrences >= 2
        if key in _CRITICAL_FLAGS:
            priority = "critical"
        elif group["problem"] or group["downvote"] or occurrences >= 3:
            priority = "high"
        elif repeated:
            priority = "medium"
        else:
            priority = "low"
        examples = sorted(
            group["examples"],
            key=lambda item: parse_iso(item.updated_at) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        findings.append(
            ImprovementFinding(
                key=key,
                label=_FLAG_LABELS.get(key, key.replace("_", " ").title()),
                priority=priority,
                occurrences=occurrences,
                conversation_count=len(group["conversations"]),
                latest_at=group["latest_at"],
                modes=tuple(sorted(group["modes"])),
                scopes=tuple(sorted(group["scopes"])),
                sources=tuple(sorted(group["sources"])),
                regression_candidate=repeated,
                examples=tuple(examples),
            )
        )
    return tuple(
        sorted(
            findings,
            key=lambda item: (
                _PRIORITY_ORDER[item.priority],
                -item.occurrences,
                -(parse_iso(item.latest_at) or datetime.min.replace(tzinfo=UTC)).timestamp(),
            ),
        )
    )


def quality_summary(conversations: list[Conversation]) -> QualitySummary:
    qualities = Counter(conversation.eval_quality or "unreviewed" for conversation in conversations)
    return QualitySummary(
        conversations=len(conversations),
        reviewed=sum(count for quality, count in qualities.items() if quality != "unreviewed"),
        needs_attention=sum(1 for conversation in conversations if conversation.attention_reasons),
        downvotes=sum(
            1
            for conversation in conversations
            for turn in conversation.turns
            if turn.feedback_reaction == "down"
        ),
        feedback=sum(conversation.feedback_count for conversation in conversations),
        real_readers=len(
            {
                conversation.subscriber_hash
                for conversation in conversations
                if not conversation.is_owner
            }
        ),
        quality_counts=dict(qualities),
    )


def _load_conversations(days: int) -> list[Conversation]:
    stack_name = os.environ.get("LIBRARIAN_STACK_NAME", DEFAULT_STACK)
    table_name = os.environ.get("LIBRARIAN_TABLE_NAME") or stack_resource(
        "LibrarianTable", stack_name=stack_name
    )
    conversations = scan_conversations(table_name, since_iso=iso_days_ago(days), max_pages=30)
    owner_hash = email_hash(os.environ.get("THINGY_OPERATOR_OWNER_EMAIL", DEFAULT_OWNER_EMAIL))
    for conversation in conversations:
        conversation.is_owner = conversation.subscriber_hash == owner_hash
    if conversations:
        with ThreadPoolExecutor(max_workers=min(10, len(conversations))) as pool:
            turns = pool.map(
                lambda conversation: load_turns(table_name, conversation), conversations
            )
            for conversation, conversation_turns in zip(conversations, turns, strict=True):
                conversation.turns = conversation_turns
    return conversations


def _git_changed_at(path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%cI", "--", path],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except OSError, subprocess.SubprocessError:
        return ""
    return result.stdout.strip()


_PUBLISH_DATE_RE = re.compile(r"^publish_date:\s*[\"']?([^\"'\s]+)", re.MULTILINE)
_BLOG_PATH_DATE_RE = re.compile(r"/(\d{4}-\d{2}-\d{2})-")


def _weekly_mirror() -> SourceMirror:
    paths = list((REPO_ROOT / "apps" / "site" / "archive").glob("*.md"))
    dates: list[str] = []
    for path in paths:
        try:
            match = _PUBLISH_DATE_RE.search(path.read_text(encoding="utf-8")[:3000])
        except OSError:
            continue
        if match:
            dates.append(match.group(1))
    changed_at = _git_changed_at("apps/site/archive")
    if not changed_at:
        try:
            local_corpus = json.loads(
                (REPO_ROOT / "data" / "librarian" / "corpus.json").read_text(encoding="utf-8")
            )
            changed_at = str(local_corpus.get("generated_at") or "")
        except OSError, ValueError, TypeError:
            pass
    return SourceMirror(
        count=len(paths),
        latest_content_at=max(dates, default=""),
        changed_at=changed_at,
    )


def _blog_mirror() -> SourceMirror:
    root = REPO_ROOT / "data" / "blog"
    paths = list((root / "posts").glob("**/*.md"))
    dates = [
        match.group(1) for path in paths if (match := _BLOG_PATH_DATE_RE.search(path.as_posix()))
    ]
    changed_at = ""
    try:
        index = json.loads((root / "index.json").read_text(encoding="utf-8"))
        changed_at = str(index.get("generated_at") or "")
    except OSError, ValueError, TypeError:
        changed_at = _git_changed_at("data/blog")
    return SourceMirror(
        count=len(paths),
        latest_content_at=max(dates, default=""),
        changed_at=changed_at,
    )


def _podcast_mirror() -> SourceMirror:
    paths = list((REPO_ROOT / "data" / "podcast" / "another-thing" / "episodes").glob("*.json"))
    dates: list[str] = []
    for path in paths:
        try:
            item = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError, TypeError:
            continue
        value = str(item.get("published_at") or item.get("publish_date") or "")
        if value:
            dates.append(value)
    return SourceMirror(
        count=len(paths),
        latest_content_at=max(dates, default=""),
        changed_at=_git_changed_at("data/podcast"),
    )


def _source_mirrors() -> dict[str, SourceMirror]:
    return {
        "weekly_thing": _weekly_mirror(),
        "blog": _blog_mirror(),
        "podcast": _podcast_mirror(),
    }


_METADATA_FIELDS = (
    "version",
    "generated_at",
    "embedding_model",
    "embedding_dimensions",
    "issue_count",
    "post_count",
    "episode_count",
    "chunk_count",
    "link_count",
)


def parse_artifact_metadata(prefix: str) -> dict[str, Any]:
    """Parse the scalar header fields that precede large corpus arrays."""

    metadata: dict[str, Any] = {}
    for field_name in _METADATA_FIELDS:
        match = re.search(
            rf'"{re.escape(field_name)}"\s*:\s*(?:"([^"\\]*(?:\\.[^"\\]*)*)"|(-?\d+)|null)',
            prefix,
        )
        if not match:
            continue
        if match.group(1) is not None:
            metadata[field_name] = bytes(match.group(1), "utf-8").decode("unicode_escape")
        elif match.group(2) is not None:
            metadata[field_name] = int(match.group(2))
        else:
            metadata[field_name] = None
    return metadata


def _corpus_status(spec: SourceSpec, mirror: SourceMirror, bucket: str) -> CorpusStatus:
    try:
        client = boto3.client("s3")
        head = client.head_object(Bucket=bucket, Key=spec.object_key)
        prefix = (
            client.get_object(Bucket=bucket, Key=spec.object_key, Range="bytes=0-8191")["Body"]
            .read()
            .decode("utf-8", errors="ignore")
        )
        metadata = parse_artifact_metadata(prefix)
    except (BotoCoreError, ClientError, NoCredentialsError, OSError) as exc:
        return CorpusStatus(
            key=spec.key,
            label=spec.label,
            status="unavailable",
            status_label="Unavailable",
            object_key=spec.object_key,
            source_latest_at=mirror.latest_content_at,
            source_changed_at=mirror.changed_at,
            source_count=mirror.count,
            reasons=("The deployed corpus could not be inspected.",),
            error=f"{type(exc).__name__}: {compact(exc, 180)}",
        )

    uploaded_at = (
        head["LastModified"].astimezone(UTC).isoformat().replace("+00:00", "Z")
        if head.get("LastModified")
        else ""
    )
    deployed_count = metadata.get(spec.count_field)
    reasons: list[str] = []
    status = "ready"
    status_label = "Current"
    if deployed_count is None or not metadata.get("generated_at"):
        status = "partial"
        status_label = "Partial metadata"
        reasons.append("The artifact header is missing expected coverage metadata.")
    elif int(deployed_count) < mirror.count:
        status = "stale"
        status_label = "Upload behind mirror"
        reasons.append(
            f"The deployed artifact has {deployed_count:,} items; the source mirror has {mirror.count:,}."
        )
    elif int(deployed_count) > mirror.count:
        status = "partial"
        status_label = "Mirror behind upload"
        reasons.append(
            f"The deployed artifact has {deployed_count:,} items; this checkout has {mirror.count:,}."
        )
    elif (
        parse_iso(mirror.changed_at)
        and parse_iso(uploaded_at)
        and parse_iso(mirror.changed_at) > parse_iso(uploaded_at)
    ):
        status = "stale"
        status_label = "Upload behind mirror"
        reasons.append("The source mirror changed after the deployed corpus was uploaded.")
    else:
        reasons.append("Deployed coverage matches the current source mirror.")

    return CorpusStatus(
        key=spec.key,
        label=spec.label,
        status=status,
        status_label=status_label,
        object_key=spec.object_key,
        generated_at=str(metadata.get("generated_at") or ""),
        uploaded_at=uploaded_at,
        source_latest_at=mirror.latest_content_at,
        source_changed_at=mirror.changed_at,
        deployed_count=int(deployed_count) if deployed_count is not None else None,
        source_count=mirror.count,
        chunk_count=int(metadata["chunk_count"])
        if metadata.get("chunk_count") is not None
        else None,
        link_count=int(metadata["link_count"]) if metadata.get("link_count") is not None else None,
        size_bytes=int(head["ContentLength"]) if head.get("ContentLength") is not None else None,
        embedding_model=str(metadata.get("embedding_model") or ""),
        reasons=tuple(reasons),
    )


def load_corpus_status() -> tuple[CorpusStatus, ...]:
    bucket = os.environ.get("LIBRARIAN_BUCKET", DEFAULT_BUCKET)
    mirrors = _source_mirrors()
    with ThreadPoolExecutor(max_workers=len(SOURCE_SPECS)) as pool:
        statuses = pool.map(
            lambda spec: _corpus_status(spec, mirrors[spec.key], bucket), SOURCE_SPECS
        )
        return tuple(statuses)


_cache: dict[int, tuple[float, ThingyDashboard]] = {}
_cache_lock = threading.Lock()


def load_dashboard(*, days: int = 90, force_refresh: bool = False) -> ThingyDashboard:
    days = days if days in {30, 90, 180} else 90
    if not force_refresh:
        with _cache_lock:
            cached = _cache.get(days)
            if cached and time.monotonic() - cached[0] < _CACHE_SECONDS:
                return cached[1]

    load_dotenv(REPO_ROOT / ".env")
    errors: list[str] = []
    corpora: tuple[CorpusStatus, ...] = ()
    conversations: list[Conversation] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        corpus_future = pool.submit(load_corpus_status)
        quality_future = pool.submit(_load_conversations, days)
        try:
            corpora = corpus_future.result()
        except Exception as exc:  # noqa: BLE001 - partial operator view is preferable
            errors.append(f"Corpus status unavailable: {type(exc).__name__}: {compact(exc, 180)}")
        try:
            conversations = quality_future.result()
        except Exception as exc:  # noqa: BLE001 - partial operator view is preferable
            errors.append(f"Quality data unavailable: {type(exc).__name__}: {compact(exc, 180)}")

    dashboard = ThingyDashboard(
        generated_at=utc_now().isoformat().replace("+00:00", "Z"),
        days=days,
        corpora=corpora,
        findings=build_quality_queue(conversations),
        quality=quality_summary(conversations),
        modes=tuple(sorted({conversation.mode or "thingy" for conversation in conversations})),
        scopes=tuple(sorted({conversation.scope or "all" for conversation in conversations})),
        errors=tuple(errors),
    )
    with _cache_lock:
        _cache[days] = (time.monotonic(), dashboard)
    return dashboard

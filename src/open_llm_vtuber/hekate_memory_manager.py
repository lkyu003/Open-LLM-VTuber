from __future__ import annotations

import re
import random
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List

from loguru import logger


MEMORY_ROOT = Path("memory")
SHORT_TERM_DIR = MEMORY_ROOT / "short-term"
LONG_TERM_DIR = MEMORY_ROOT / "long-term"
FLASH_DIR = MEMORY_ROOT / "flash"
REFERENCE_DIR = MEMORY_ROOT / "reference"
EMOTION_DIR = MEMORY_ROOT / "emotion"
PRUNING_DIR = MEMORY_ROOT / "pruning"
INDEX_PATH = MEMORY_ROOT / "MEMORY_INDEX.md"
EMOTION_LOG_PATH = EMOTION_DIR / "emotion-log.md"
PRUNE_LOG_PATH = PRUNING_DIR / "prune-log.md"

EMOTIONS = ("anger", "sadness", "joy", "embarrassment", "fear", "desire", "love")
SHORT_TERM_MAX_FILES = 100
LONG_TERM_PROMOTION_TOTAL_THRESHOLD = 2.8
LONG_TERM_PROMOTION_SINGLE_THRESHOLD = 0.92
FLASH_TOTAL_THRESHOLD = 3.2
FLASH_SINGLE_THRESHOLD = 0.98
MEMORY_MATCH_LIMIT = 5

KEYWORD_STOPWORDS = {
    "the",
    "and",
    "you",
    "your",
    "that",
    "this",
    "with",
    "for",
    "are",
    "was",
    "were",
    "have",
    "has",
    "from",
    "about",
    "what",
    "when",
    "where",
    "how",
    "session",
    "memory",
    "created_from_session",
    "emotional_snapshot",
    "importance_weight",
    "emotion_index",
    "never_delete",
    "dominant_emotion",
    "conf_uid",
    "history_uid",
    "high-intensity",
    "emotional",
    "왜",
    "뭐",
    "무엇",
    "어떻게",
    "그냥",
    "정말",
    "진짜",
    "조금",
    "너무",
    "오늘",
    "내일",
    "지금",
    "그리고",
    "하지만",
    "그래서",
    "그러니까",
    "있어",
    "있어요",
    "없어",
    "없어요",
    "해주세요",
    "말해줘",
    "알려줘",
    "해줘",
    "좋아",
    "다시",
    "읽는",
    "알겠",
}

SINGLE_KOREAN_KEYWORDS = {
    "책",
    "별",
    "꿈",
    "몸",
    "밥",
    "집",
    "옷",
    "말",
    "빛",
    "눈",
    "손",
}

DEFAULT_EMOTION_INDEX = {
    "anger": 0.0,
    "sadness": 0.0,
    "joy": 0.4,
    "embarrassment": 0.2,
    "fear": 0.1,
    "desire": 0.3,
    "love": 0.4,
}

EMOTION_KEYWORDS = {
    "anger": (
        "angry",
        "mad",
        "annoying",
        "irritated",
        "hate",
        "화나",
        "짜증",
        "빡",
        "열받",
        "싫어",
    ),
    "sadness": (
        "sad",
        "lonely",
        "tired",
        "hurt",
        "cry",
        "슬퍼",
        "외로",
        "힘들",
        "아파",
        "울",
    ),
    "joy": (
        "happy",
        "glad",
        "fun",
        "nice",
        "great",
        "좋아",
        "기뻐",
        "재밌",
        "웃",
        "행복",
    ),
    "embarrassment": (
        "embarrass",
        "awkward",
        "shy",
        "oops",
        "민망",
        "부끄",
        "어색",
        "쑥스",
    ),
    "fear": (
        "scared",
        "afraid",
        "worry",
        "danger",
        "risk",
        "무서",
        "불안",
        "걱정",
        "위험",
    ),
    "desire": (
        "want",
        "wish",
        "need",
        "try",
        "make",
        "원해",
        "하고 싶",
        "해보고",
        "만들",
    ),
    "love": (
        "love",
        "care",
        "warm",
        "dear",
        "miss",
        "사랑",
        "좋아해",
        "소중",
        "따뜻",
        "보고 싶",
    ),
}


@dataclass
class MemoryRecord:
    session_id: str
    date: str
    summary: str
    key_events: List[str]
    emotion_index: Dict[str, float]
    dominant_emotion: str
    emotion_score_total: float
    importance_weight: float
    promotion_candidate: bool
    flash_candidate: bool
    keywords: List[str]
    user_text: str
    assistant_text: str


@dataclass(frozen=True)
class MemoryStorePaths:
    root: Path
    short_term: Path
    long_term: Path
    flash: Path
    reference: Path
    emotion: Path
    pruning: Path
    index: Path
    emotion_log: Path
    prune_log: Path


def _sanitize_memory_uid(conf_uid: str) -> str:
    safe_uid = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (conf_uid or "").strip())
    safe_uid = safe_uid.strip(". ")
    return safe_uid or "_default"


def get_memory_store_paths(conf_uid: str = "") -> MemoryStorePaths:
    root = MEMORY_ROOT / _sanitize_memory_uid(conf_uid)
    emotion = root / "emotion"
    pruning = root / "pruning"
    return MemoryStorePaths(
        root=root,
        short_term=root / "short-term",
        long_term=root / "long-term",
        flash=root / "flash",
        reference=root / "reference",
        emotion=emotion,
        pruning=pruning,
        index=root / "MEMORY_INDEX.md",
        emotion_log=emotion / "emotion-log.md",
        prune_log=pruning / "prune-log.md",
    )


def ensure_memory_store(conf_uid: str = "") -> MemoryStorePaths:
    store = get_memory_store_paths(conf_uid)
    for directory in (
        store.root,
        store.short_term,
        store.long_term,
        store.flash,
        store.reference,
        store.emotion,
        store.pruning,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    if not store.index.exists():
        store.index.write_text(
            "# MEMORY_INDEX\n\n"
            "## Current Session Count\n"
            "- total_sessions: 0\n"
            "- last_session_id: session-0000\n\n"
            "## Active Short-Term Memories\n\n"
            "## Long-Term Memories\n\n"
            "## Flash Memories\n",
            encoding="utf-8",
        )
    if not store.emotion_log.exists():
        store.emotion_log.write_text("# Emotion Log\n", encoding="utf-8")
    if not store.prune_log.exists():
        store.prune_log.write_text("# Prune Log\n", encoding="utf-8")
    return store


def load_memory_context(
    input_text: str = "",
    max_chars: int = 4000,
    proactive_recall: bool = False,
    conf_uid: str = "",
) -> str:
    """Load keyword-relevant Hekate markdown memories for the next LLM turn."""
    store = get_memory_store_paths(conf_uid)
    if not store.root.exists():
        return ""

    ensure_memory_store(conf_uid)
    input_keywords = extract_keywords(input_text)
    selected_memories = _select_memories_for_input(
        input_keywords,
        store,
        proactive_recall=proactive_recall,
    )
    reference_memories = _select_reference_memories(input_keywords, store)
    selected_memories = [*reference_memories, *selected_memories]

    if not selected_memories:
        return ""

    parts = []
    for memory in selected_memories:
        matched_keywords = sorted(set(input_keywords) & set(memory["keywords"]))
        match_note = (
            f"matched keywords: {', '.join(matched_keywords)}"
            if matched_keywords
            else "spontaneous recall"
        )
        parts.append(
            f"## {memory['kind']}: {memory['path'].as_posix()}\n"
            f"- {match_note}\n"
            f"{_trim(memory['text'], 900)}"
        )

    context = "\n\n".join(parts)
    if not context.strip():
        return ""

    if proactive_recall:
        instruction = (
            "The following items are past memories, not current user messages. "
            "You are speaking proactively because the user has not said anything. "
            "Let one or more of these memories quietly inspire a natural first remark, "
            "as if an old memory came to mind. Do not quote the memory dump or say you received a prompt.\n\n"
        )
    else:
        instruction = (
            "Use the following recalled memory context silently. It is not a user message. "
            "These are past memories. Let them affect continuity, tone, and emotional consistency "
            "without quoting them by default. Only bring them up naturally if they are relevant "
            "to the current conversation.\n\n"
        )

    return _trim(f"{instruction}{context}", max_chars)


def record_conversation_turn(
    user_text: str,
    assistant_text: str,
    conf_uid: str = "",
    history_uid: str = "",
) -> MemoryRecord | None:
    """Persist one completed conversation turn into the Hekate memory store."""
    user_text = (user_text or "").strip()
    assistant_text = (assistant_text or "").strip()
    if not user_text or not assistant_text:
        return None

    store = ensure_memory_store(conf_uid)
    session_number = _next_session_number(store)
    session_id = f"session-{session_number:04d}"
    today = datetime.now().strftime("%Y-%m-%d")

    emotion_index = estimate_emotion_index(user_text, assistant_text)
    keywords = extract_keywords(f"{user_text}\n{assistant_text}")
    dominant_emotion = max(EMOTIONS, key=lambda key: emotion_index[key])
    emotion_score_total = round(sum(emotion_index.values()), 2)
    max_emotion = max(emotion_index.values())
    flash_candidate = (
        max_emotion >= FLASH_SINGLE_THRESHOLD
        or emotion_score_total >= FLASH_TOTAL_THRESHOLD
    )
    promotion_candidate = (
        max_emotion >= LONG_TERM_PROMOTION_SINGLE_THRESHOLD
        or emotion_score_total >= LONG_TERM_PROMOTION_TOTAL_THRESHOLD
        or flash_candidate
    )

    record = MemoryRecord(
        session_id=session_id,
        date=today,
        summary=_summarize_turn(user_text, assistant_text),
        key_events=_extract_key_events(user_text, assistant_text),
        emotion_index=emotion_index,
        dominant_emotion=dominant_emotion,
        emotion_score_total=emotion_score_total,
        importance_weight=0.4,
        promotion_candidate=promotion_candidate,
        flash_candidate=flash_candidate,
        keywords=keywords,
        user_text=user_text,
        assistant_text=assistant_text,
    )

    short_path = store.short_term / f"{session_id}.md"
    short_path.write_text(_render_session_log(record), encoding="utf-8")

    if promotion_candidate:
        long_id = f"long-{_next_memory_number(store.long_term, 'long'):04d}"
        long_path = store.long_term / f"{long_id}.md"
        long_path.write_text(
            _render_promoted_memory(record, long_id, conf_uid, history_uid),
            encoding="utf-8",
        )

    if flash_candidate:
        flash_id = f"flash-{_next_memory_number(store.flash, 'flash'):04d}"
        flash_path = store.flash / f"{flash_id}.md"
        flash_path.write_text(
            _render_flash_memory(record, flash_id, conf_uid, history_uid),
            encoding="utf-8",
        )

    prune_short_term_memories(conf_uid=conf_uid, max_files=SHORT_TERM_MAX_FILES)
    _append_emotion_log(record, store)
    _write_memory_index(session_number, record, store)

    logger.info(
        f"Recorded Hekate memory {session_id} "
        f"(dominant={dominant_emotion}, score={emotion_score_total})."
    )
    return record


def estimate_emotion_index(user_text: str, assistant_text: str) -> Dict[str, float]:
    combined = f"{user_text}\n{assistant_text}".lower()
    scores = dict(DEFAULT_EMOTION_INDEX)

    for emotion, keywords in EMOTION_KEYWORDS.items():
        hits = sum(1 for keyword in keywords if keyword.lower() in combined)
        if hits:
            scores[emotion] = min(1.0, scores[emotion] + 0.18 * hits)

    for emotion in ("anger", "sadness", "joy", "fear"):
        tag_hits = len(re.findall(rf"\[{emotion}\]", combined))
        if tag_hits:
            scores[emotion] = min(1.0, scores[emotion] + 0.2 * tag_hits)

    if "?" in combined:
        scores["fear"] = min(1.0, scores["fear"] + 0.05)
    if "!" in combined:
        scores["joy"] = min(1.0, scores["joy"] + 0.06)

    return {emotion: round(scores[emotion], 2) for emotion in EMOTIONS}


def extract_keywords(text: str, limit: int = 12) -> List[str]:
    """Extract lightweight Korean/English keywords without external dependencies."""
    normalized = re.sub(r"\[[^\]]+\]", " ", (text or "").lower())
    candidates = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}|[가-힣]+", normalized)
    scores: Dict[str, int] = {}

    for candidate in candidates:
        keyword = _normalize_keyword(candidate)
        if not keyword or keyword in KEYWORD_STOPWORDS:
            continue
        if len(keyword) < 2 and keyword not in SINGLE_KOREAN_KEYWORDS:
            continue
        scores[keyword] = scores.get(keyword, 0) + 1
        if keyword in SINGLE_KOREAN_KEYWORDS:
            scores[keyword] += 2

    return [
        keyword
        for keyword, _ in sorted(
            scores.items(),
            key=lambda item: (-item[1], -len(item[0]), item[0]),
        )[:limit]
    ]


def prune_short_term_memories(
    max_files: int = SHORT_TERM_MAX_FILES,
    conf_uid: str = "",
) -> List[Path]:
    """Keep short-term memory bounded by deleting low-score older logs first."""
    store = ensure_memory_store(conf_uid)
    entries = []
    for path in _recent_markdown_files(store.short_term, limit=10000):
        text = _read_if_exists(path)
        score = _extract_float(text, "emotion_score_total", default=0.0)
        session_number = _extract_session_number(path)
        entries.append(
            {
                "path": path,
                "score": score,
                "session_number": session_number,
                "mtime": path.stat().st_mtime,
            }
        )

    if len(entries) <= max_files:
        return []

    delete_count = len(entries) - max_files
    delete_candidates = sorted(
        entries,
        key=lambda item: (
            item["score"],
            item["session_number"],
            item["mtime"],
        ),
    )[:delete_count]

    deleted_paths = []
    for item in delete_candidates:
        path = item["path"]
        try:
            path.unlink()
            deleted_paths.append(path)
        except Exception as e:
            logger.error(f"Failed to prune short-term memory {path}: {e}")

    with store.prune_log.open("a", encoding="utf-8") as file:
        file.write(f"\n## {datetime.now().isoformat(timespec='seconds')}\n")
        file.write(f"- reviewed: {len(entries)}\n")
        file.write(f"- max_files: {max_files}\n")
        file.write(f"- deleted: {len(deleted_paths)}\n")
        for path in deleted_paths:
            file.write(f"  - {path.as_posix()}\n")

    return deleted_paths


def run_short_term_pruning(conf_uid: str = "") -> None:
    prune_short_term_memories(conf_uid=conf_uid, max_files=SHORT_TERM_MAX_FILES)


def _read_if_exists(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    return path.read_text(encoding="utf-8")


def _recent_markdown_files(directory: Path, limit: int) -> List[Path]:
    if not directory.exists():
        return []
    files = [path for path in directory.glob("*.md") if path.is_file()]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)[:limit]


def _select_memories_for_input(
    input_keywords: List[str],
    store: MemoryStorePaths,
    proactive_recall: bool = False,
) -> List[Dict[str, object]]:
    memories = _collect_memory_candidates(store)
    if not memories:
        return []

    if input_keywords:
        keyword_set = set(input_keywords)
        matched = []
        for memory in memories:
            overlap = keyword_set & set(memory["keywords"])
            if overlap:
                matched.append(
                    {
                        **memory,
                        "overlap_count": len(overlap),
                    }
                )

        if matched:
            kind_priority = {"flash": 0, "long-term": 1, "short-term": 2}
            return sorted(
                matched,
                key=lambda item: (
                    -item["overlap_count"],
                    kind_priority.get(item["kind"], 9),
                    -item["emotion_score"],
                    -item["mtime"],
                ),
            )[:MEMORY_MATCH_LIMIT]

    random_pool = [
        memory
        for memory in memories
        if memory["kind"] in {"short-term", "long-term"}
    ]
    if proactive_recall:
        if len(random_pool) <= 2:
            return random_pool
        recall_count = min(len(random_pool), random.randint(2, 3))
        return random.sample(random_pool, recall_count)

    if not random_pool or random.randint(0, 1) == 0:
        return []
    return [random.choice(random_pool)]


def _select_reference_memories(
    input_keywords: List[str],
    store: MemoryStorePaths,
) -> List[Dict[str, object]]:
    if not input_keywords:
        return []

    keyword_set = set(input_keywords)
    matched = []
    for memory in _collect_reference_memory_candidates(store):
        overlap = keyword_set & set(memory["keywords"])
        if overlap:
            matched.append(
                {
                    **memory,
                    "overlap_count": len(overlap),
                }
            )

    return sorted(
        matched,
        key=lambda item: (
            -item["overlap_count"],
            -item["mtime"],
            item["path"].as_posix(),
        ),
    )


def _collect_memory_candidates(store: MemoryStorePaths) -> List[Dict[str, object]]:
    candidates = []
    for kind, directory in (
        ("long-term", store.long_term),
        ("flash", store.flash),
        ("short-term", store.short_term),
    ):
        for path in _recent_markdown_files(directory, limit=10000):
            text = _read_if_exists(path)
            if not text.strip():
                continue
            candidates.append(
                {
                    "kind": kind,
                    "path": path,
                    "text": text,
                    "keywords": _extract_keywords_from_memory_text(text),
                    "emotion_score": _extract_float(
                        text, "emotion_score_total", default=0.0
                    ),
                    "mtime": path.stat().st_mtime,
                }
            )
    return candidates


def _collect_reference_memory_candidates(
    store: MemoryStorePaths,
) -> List[Dict[str, object]]:
    candidates = []
    for path in _recent_markdown_files(store.reference, limit=10000):
        if path.name.lower() == "readme.md":
            continue
        text = _read_if_exists(path)
        if not text.strip():
            continue
        candidates.append(
            {
                "kind": "reference",
                "path": path,
                "text": text,
                "keywords": _extract_keywords_from_memory_text(text),
                "emotion_score": 0.0,
                "mtime": path.stat().st_mtime,
            }
        )
    return candidates


def _extract_keywords_from_memory_text(text: str) -> List[str]:
    match = re.search(r"(?:##\s*)?keywords:?\s*\n((?:\s*-\s*.+\n?)+)", text, re.I)
    if match:
        keywords = []
        for line in match.group(1).splitlines():
            keyword = _normalize_keyword(line.split("-", 1)[-1].strip().strip('"'))
            if keyword:
                keywords.append(keyword)
        if keywords:
            return keywords
    return extract_keywords(_memory_keyword_source(text))


def _memory_keyword_source(text: str) -> str:
    snippets = []
    for key in ("summary", "trigger", "title", "reason_saved"):
        for match in re.finditer(rf'{key}:\s*"([^"]+)"', text):
            snippets.append(match.group(1))

    for section in ("Context Summary", "Key Events", "Stable Rules", "Notes For Next Session"):
        match = re.search(
            rf"## {re.escape(section)}\n(.+?)(?=\n## |\Z)",
            text,
            re.S,
        )
        if match:
            snippets.append(match.group(1))

    return "\n".join(snippets) if snippets else text


def _normalize_keyword(keyword: str) -> str:
    keyword = keyword.strip().lower()
    keyword = re.sub(r"^[^0-9a-zA-Z가-힣]+|[^0-9a-zA-Z가-힣]+$", "", keyword)
    for suffix in (
        "입니다",
        "이에요",
        "예요",
        "해요",
        "어요",
        "아요",
        "으로",
        "에게",
        "에서",
        "부터",
        "까지",
        "하고",
        "처럼",
        "보다",
        "이랑",
        "랑",
        "이나",
        "나",
        "걸",
        "은",
        "는",
        "이",
        "가",
        "을",
        "를",
        "에",
        "의",
        "도",
    ):
        if len(keyword) >= len(suffix) + 1 and keyword.endswith(suffix):
            keyword = keyword[: -len(suffix)]
            break
    return keyword


def _trim(text: str, max_chars: int) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _next_session_number(store: MemoryStorePaths) -> int:
    existing_numbers = []
    for path in store.short_term.glob("session-*.md"):
        match = re.search(r"session-(\d+)", path.stem)
        if match:
            existing_numbers.append(int(match.group(1)))
    return max(existing_numbers, default=0) + 1


def _extract_session_number(path: Path) -> int:
    match = re.search(r"session-(\d+)", path.stem)
    return int(match.group(1)) if match else 0


def _next_memory_number(directory: Path, prefix: str) -> int:
    existing_numbers = []
    for path in directory.glob("*.md"):
        candidates = [path.stem, _read_if_exists(path)]
        for candidate in candidates:
            for match in re.finditer(rf"{re.escape(prefix)}-(\d+)", candidate):
                existing_numbers.append(int(match.group(1)))
    return max(existing_numbers, default=0) + 1


def _summarize_turn(user_text: str, assistant_text: str) -> str:
    user = _compact(user_text, 160)
    assistant = _compact(assistant_text, 160)
    return f"User said: {user} / Hekate replied: {assistant}"


def _extract_key_events(user_text: str, assistant_text: str) -> List[str]:
    events = []
    for text in (user_text, assistant_text):
        for sentence in re.split(r"(?<=[.!?。！？])\s+|\n+", text):
            sentence = sentence.strip()
            if len(sentence) >= 12:
                events.append(_compact(sentence, 120))
            if len(events) >= 4:
                return events
    return events or [_compact(user_text or assistant_text, 120)]


def _compact(text: str, max_chars: int) -> str:
    return _trim(re.sub(r"\s+", " ", text).strip(), max_chars)


def _render_emotion_yaml(emotion_index: Dict[str, float]) -> str:
    return "\n".join(f"  {emotion}: {emotion_index[emotion]:.2f}" for emotion in EMOTIONS)


def _render_session_log(record: MemoryRecord) -> str:
    key_events = "\n".join(f"- {event}" for event in record.key_events)
    keywords = "\n".join(f"- {keyword}" for keyword in record.keywords) or "- none"
    return (
        f"# Session Log: {record.session_id}\n\n"
        "## Date\n"
        f"{record.date}\n\n"
        "## Context Summary\n"
        f"{record.summary}\n\n"
        "## Key Events\n"
        f"{key_events}\n\n"
        "## Keywords\n"
        f"{keywords}\n\n"
        "## Emotion Index\n"
        "```yaml\n"
        f"{_render_emotion_yaml(record.emotion_index)}\n"
        f"  dominant_emotion: \"{record.dominant_emotion}\"\n"
        f"  emotion_score_total: {record.emotion_score_total:.2f}\n"
        "```\n\n"
        "## Dominant Emotion\n"
        f"{record.dominant_emotion}\n\n"
        "## Emotional Summary\n"
        f"Hekate's response was shaped mostly by {record.dominant_emotion}.\n\n"
        "## Memory Decision\n"
        f"- short_term: true\n"
        f"- long_term_candidate: {str(record.promotion_candidate).lower()}\n"
        f"- flash_candidate: {str(record.flash_candidate).lower()}\n"
        f"- delete_candidate_after_prune: {str(record.emotion_score_total < 1.0).lower()}\n\n"
        "## Notes For Next Session\n"
        f"- Continue from this emotional context if the topic returns.\n"
    )


def _render_promoted_memory(
    record: MemoryRecord, memory_id: str, conf_uid: str, history_uid: str
) -> str:
    keywords = "\n".join(f"  - \"{_escape_yaml(keyword)}\"" for keyword in record.keywords)
    keyword_lines = keywords or '  - "none"'
    return (
        f"# Long-Term Memory: {record.session_id}\n\n"
        "```yaml\n"
        f"memory_id: \"{memory_id}\"\n"
        f"created_from_session: \"{record.session_id}\"\n"
        "title: \"High-emotion conversation memory\"\n"
        f"summary: \"{_escape_yaml(record.summary)}\"\n"
        "reason_saved: \"high emotional score / repeated context candidate\"\n"
        "keywords:\n"
        f"{keyword_lines}\n"
        "emotion_index:\n"
        f"{_render_emotion_yaml(record.emotion_index)}\n"
        "importance_weight: 0.5\n"
        f"last_referenced: \"{record.date}\"\n"
        f"conf_uid: \"{_escape_yaml(conf_uid)}\"\n"
        f"history_uid: \"{_escape_yaml(history_uid)}\"\n"
        "```\n"
    )


def _render_flash_memory(
    record: MemoryRecord, memory_id: str, conf_uid: str, history_uid: str
) -> str:
    keywords = "\n".join(f"  - \"{_escape_yaml(keyword)}\"" for keyword in record.keywords)
    keyword_lines = keywords or '  - "none"'
    return (
        f"# Flash Memory: {record.session_id}\n\n"
        "```yaml\n"
        f"memory_id: \"{memory_id}\"\n"
        f"created_from_session: \"{record.session_id}\"\n"
        "title: \"High-intensity emotional memory\"\n"
        f"trigger: \"{_escape_yaml(record.key_events[0] if record.key_events else record.summary)}\"\n"
        f"emotional_snapshot: \"dominant={record.dominant_emotion}, total={record.emotion_score_total:.2f}\"\n"
        "keywords:\n"
        f"{keyword_lines}\n"
        "emotion_index:\n"
        f"{_render_emotion_yaml(record.emotion_index)}\n"
        "importance_weight: 0.5\n"
        "never_delete: true\n"
        f"conf_uid: \"{_escape_yaml(conf_uid)}\"\n"
        f"history_uid: \"{_escape_yaml(history_uid)}\"\n"
        "```\n"
    )


def _append_emotion_log(record: MemoryRecord, store: MemoryStorePaths) -> None:
    with store.emotion_log.open("a", encoding="utf-8") as file:
        file.write(f"\n## {record.session_id} - {record.date}\n")
        file.write(f"- dominant_emotion: {record.dominant_emotion}\n")
        file.write(f"- emotion_score_total: {record.emotion_score_total:.2f}\n")
        for emotion in EMOTIONS:
            file.write(f"- {emotion}: {record.emotion_index[emotion]:.2f}\n")


def _write_memory_index(
    session_number: int,
    record: MemoryRecord,
    store: MemoryStorePaths,
) -> None:
    long_files = _recent_markdown_files(store.long_term, 20)
    flash_files = _recent_markdown_files(store.flash, 20)
    short_files = _recent_markdown_files(store.short_term, 20)

    def render_files(files: Iterable[Path]) -> str:
        lines = []
        for path in files:
            lines.append(f"- {path.stem}: {path.as_posix()}")
        return "\n".join(lines) if lines else "- none"

    store.index.write_text(
        "# MEMORY_INDEX\n\n"
        "## Current Session Count\n"
        f"- total_sessions: {session_number}\n"
        f"- last_session_id: {record.session_id}\n\n"
        "## Active Short-Term Memories\n"
        f"- latest_summary: {record.summary}\n"
        f"- dominant_emotion: {record.dominant_emotion}\n"
        f"- emotion_score: {record.emotion_score_total:.2f}\n"
        f"- keep_candidate: {str(record.promotion_candidate).lower()}\n\n"
        "## Recent Short-Term Memory Files\n"
        f"{render_files(short_files)}\n\n"
        "## Long-Term Memories\n"
        f"{render_files(long_files)}\n\n"
        "## Flash Memories\n"
        f"{render_files(flash_files)}\n",
        encoding="utf-8",
    )


def _extract_float(text: str, key: str, default: float) -> float:
    match = re.search(rf"{re.escape(key)}:\s*([0-9.]+)", text)
    if not match:
        return default
    try:
        return float(match.group(1))
    except ValueError:
        return default


def _escape_yaml(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"')

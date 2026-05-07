"""Persistent Working Memory -- JSON disk storage for MemoryStore and session context.

Provides:
  1. MemoryStorePersistence: JSON persistence adapter for MemoryStore
  2. WorkingMemory: Session-level context that persists across restarts
  3. Auto-save on mutation with configurable debounce
"""
from __future__ import annotations
import json, os, time, threading
from dataclasses import dataclass, field, asdict
from typing import Optional

PERSIST_FILE = "memory_store.json"
WORKING_MEM_FILE = "working_memory.json"


@dataclass
class WorkingMemoryItem:
    """A single working memory entry."""
    key: str
    value: str
    category: str = "general"   # general | goal | constraint | insight | lesson
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    ttl: float = 0              # 0 = never expire, else seconds
    importance: float = 0.5     # [0,1]

    def is_expired(self) -> bool:
        if self.ttl <= 0:
            return False
        return (time.time() - self.updated_at) > self.ttl


class WorkingMemory:
    """Session-level persistent working memory with categories.

    Stores goals, constraints, insights, lessons that persist across restarts.
    All mutations auto-save to disk.
    """
    CATEGORIES = ("general", "goal", "constraint", "insight", "lesson", "state")

    def __init__(self, persist_dir: str = "."):
        self._path = os.path.join(persist_dir, WORKING_MEM_FILE)
        self._items: dict[str, WorkingMemoryItem] = {}
        self._lock = threading.Lock()
        self._load()

    # ---------- CRUD ----------
    def set(self, key: str, value: str, category: str = "general",
            importance: float = 0.5, ttl: float = 0) -> None:
        with self._lock:
            now = time.time()
            if key in self._items:
                old = self._items[key]
                old.value = value
                old.category = category
                old.importance = importance
                old.ttl = ttl
                old.updated_at = now
            else:
                self._items[key] = WorkingMemoryItem(
                    key=key, value=value, category=category,
                    importance=importance, ttl=ttl,
                    created_at=now, updated_at=now,
                )
            self._save()

    def get(self, key: str, default: str = "") -> str:
        item = self._items.get(key)
        if item is None or item.is_expired():
            return default
        return item.value

    def get_all(self, category: str = None) -> list[WorkingMemoryItem]:
        """Get all items, optionally filtered by category. Expired items excluded."""
        result = []
        for item in self._items.values():
            if item.is_expired():
                continue
            if category and item.category != category:
                continue
            result.append(item)
        return sorted(result, key=lambda x: x.importance, reverse=True)

    def remove(self, key: str) -> bool:
        with self._lock:
            if key in self._items:
                del self._items[key]
                self._save()
                return True
            return False

    def prune_expired(self) -> int:
        """Remove all expired items. Returns count removed."""
        with self._lock:
            expired = [k for k, v in self._items.items() if v.is_expired()]
            for k in expired:
                del self._items[k]
            if expired:
                self._save()
            return len(expired)

    def to_context_string(self, max_items: int = 20) -> str:
        """Format working memory as context string for prompts."""
        items = self.get_all()
        if not items:
            return ""
        lines = ["## Working Memory"]
        for item in items[:max_items]:
            expire_note = ""
            if item.ttl > 0:
                remain = item.ttl - (time.time() - item.updated_at)
                if remain > 0:
                    expire_note = f" (expires in {remain:.0f}s)"
            lines.append(f"- [{item.category}] {item.key}: {item.value}{expire_note}")
        return "\n".join(lines)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
            self._save()

    @property
    def count(self) -> int:
        return sum(1 for i in self._items.values() if not i.is_expired())

    # ---------- Persistence ----------
    def _load(self) -> None:
        if not os.path.exists(self._path):
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for entry in data:
                item = WorkingMemoryItem(**entry)
                if not item.is_expired():
                    self._items[item.key] = item
        except Exception:
            pass  # corrupt file, start fresh

    def _save(self) -> None:
        try:
            data = [asdict(item) for item in self._items.values()]
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            # atomic replace
            if os.path.exists(self._path):
                os.replace(tmp, self._path)
            else:
                os.rename(tmp, self._path)
        except Exception:
            pass


class MemoryStorePersistence:
    """JSON persistence adapter for MemoryStore.

    Hooks into MemoryStore to auto-save/load items to disk.
    Call install(store) to attach.
    """
    def __init__(self, persist_dir: str = "."):
        self._path = os.path.join(persist_dir, PERSIST_FILE)
        self._store = None
        self._dirty = False
        self._debounce_sec = 2.0
        self._last_save = 0.0

    def install(self, store) -> None:
        """Attach to a MemoryStore instance. Monkey-patches add/remove for auto-save."""
        self._store = store
        self._load_into_store()
        # Monkey-patch mutations
        orig_add = store.add
        orig_remove = store.remove

        def patched_add(*args, **kwargs):
            result = orig_add(*args, **kwargs)
            self._mark_dirty()
            return result

        def patched_remove(*args, **kwargs):
            result = orig_remove(*args, **kwargs)
            self._mark_dirty()
            return result

        store.add = patched_add
        store.remove = patched_remove
        store._persistence = self  # attach reference
        store.working_memory = None  # will be set by agent

    def save_now(self) -> None:
        """Force immediate save."""
        self._save_store()

    def _mark_dirty(self) -> None:
        self._dirty = True
        now = time.time()
        if now - self._last_save >= self._debounce_sec:
            self._save_store()

    def _save_store(self) -> None:
        if not self._dirty or not self._store:
            return
        try:
            items = []
            for item in self._store._items.values():
                items.append({
                    "id": item.id,
                    "content": item.content,
                    "layer": item.layer,
                    "domain": item.domain,
                    "tags": item.tags,
                    "created_at": item.created_at,
                    "accessed_at": item.accessed_at,
                    "access_count": item.access_count,
                    "importance": item.importance,
                    "embedding": item.embedding,
                    "source": item.source,
                })
            tmp = self._path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            if os.path.exists(self._path):
                os.replace(tmp, self._path)
            else:
                os.rename(tmp, self._path)
            self._dirty = False
            self._last_save = time.time()
        except Exception:
            pass

    def _load_into_store(self) -> None:
        if not os.path.exists(self._path) or not self._store:
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                items = json.load(f)
            for data in items:
                from .store import MemoryItem
                item = MemoryItem(
                    id=data["id"],
                    content=data["content"],
                    layer=data.get("layer", 0),
                    domain=data.get("domain", "general"),
                    tags=data.get("tags", []),
                    created_at=data.get("created_at", time.time()),
                    accessed_at=data.get("accessed_at", time.time()),
                    access_count=data.get("access_count", 0),
                    importance=data.get("importance", 0.5),
                    embedding=data.get("embedding"),
                    source=data.get("source", "persisted"),
                )
                self._store._items[item.id] = item
        except Exception:
            pass


# Aliases
PersistenceAdapter = MemoryStorePersistence

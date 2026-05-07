"""Tool Registry — Dynamic tool discovery and execution.

Provides 9 atomic tools following GenericAgent's philosophy:
  code_run, file_read, file_write, file_patch, web_search, 
  web_scan, shell_exec, memory_op, skill_op
"""
from __future__ import annotations
import json, os, re, subprocess, time, hashlib
from typing import Any, Callable
from pathlib import Path


class ToolRegistry:
    """Registry for agent tools with auto-discovery."""
    
    def __init__(self, cwd: str = "./temp"):
        self.cwd = Path(cwd).resolve()
        self.cwd.mkdir(parents=True, exist_ok=True)
        self._tools: dict[str, dict] = {}   # name → {fn, schema, description}
        self._register_builtin()
    
    def _register_builtin(self):
        """Register all built-in tools."""
        self.register("code_run", self._code_run, 
            "Execute Python/PowerShell code and return stdout/stderr.",
            {"type": "object", "properties": {
                "code": {"type": "string", "description": "Code to execute"},
                "lang": {"type": "string", "enum": ["python", "powershell"], "default": "python"},
                "timeout": {"type": "integer", "default": 60},
            }, "required": ["code"]})
        
        self.register("file_read", self._file_read,
            "Read file content with optional line range.",
            {"type": "object", "properties": {
                "path": {"type": "string", "description": "File path"},
                "start": {"type": "integer", "description": "Start line (1-based)"},
                "count": {"type": "integer", "description": "Number of lines", "default": 200},
                "keyword": {"type": "string", "description": "Search keyword with context"},
            }, "required": ["path"]})
        
        self.register("file_write", self._file_write,
            "Create or overwrite a file.",
            {"type": "object", "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "mode": {"type": "string", "enum": ["overwrite", "append"], "default": "overwrite"},
            }, "required": ["path", "content"]})
        
        self.register("file_patch", self._file_patch,
            "Replace unique old_content with new_content in a file.",
            {"type": "object", "properties": {
                "path": {"type": "string"},
                "old_content": {"type": "string"},
                "new_content": {"type": "string"},
            }, "required": ["path", "old_content", "new_content"]})
        
        self.register("web_search", self._web_search,
            "Search the web using Google (via httpx).",
            {"type": "object", "properties": {
                "query": {"type": "string"},
                "num": {"type": "integer", "default": 5},
            }, "required": ["query"]})
        
        self.register("shell_exec", self._shell_exec,
            "Execute a shell command.",
            {"type": "object", "properties": {
                "command": {"type": "string"},
                "timeout": {"type": "integer", "default": 30},
            }, "required": ["command"]})
        
        self.register("memory_op", self._memory_op,
            "Operate on memory: add/search/compress/stats.",
            {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["add", "search", "compress", "stats", "index"]},
                "content": {"type": "string"},
                "query": {"type": "string"},
                "layer": {"type": "integer"},
                "domain": {"type": "string"},
                "tags": {"type": "array", "items": {"type": "string"}},
            }, "required": ["action"]})
        
        self.register("skill_op", self._skill_op,
            "Skill operations: list/search/upgrade/create.",
            {"type": "object", "properties": {
                "action": {"type": "string", "enum": ["list", "search", "upgrade", "create", "merge"]},
                "skill_name": {"type": "string"},
                "content": {"type": "string"},
                "query": {"type": "string"},
            }, "required": ["action"]})
    
    def register(self, name: str, fn: Callable, description: str, parameters: dict):
        self._tools[name] = {
            "fn": fn,
            "description": description,
            "schema": {
                "type": "function",
                "function": {"name": name, "description": description, "parameters": parameters}
            }
        }
    
    def get_schemas(self) -> list[dict]:
        return [t["schema"] for t in self._tools.values()]
    
    def execute(self, name: str, args: dict, context: dict = None) -> str:
        """Execute a tool by name with arguments."""
        if name not in self._tools:
            return json.dumps({"error": f"Unknown tool: {name}"})
        try:
            result = self._tools[name]["fn"](args, context or {})
            return result if isinstance(result, str) else json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    # ── Built-in Tool Implementations ───────────────────────────────
    
    def _code_run(self, args: dict, ctx: dict) -> str:
        code = args["code"]
        lang = args.get("lang", "python")
        timeout = args.get("timeout", 60)
        
        if lang == "python":
            # Write to temp file and execute
            tmp = self.cwd / "_tmp_exec.py"
            tmp.write_text(code, encoding="utf-8")
            try:
                result = subprocess.run(
                    ["python", str(tmp)], capture_output=True, text=True,
                    timeout=timeout, cwd=str(self.cwd)
                )
                output = result.stdout
                if result.stderr:
                    output += f"\n[STDERR]\n{result.stderr}"
                return output[:8000]
            except subprocess.TimeoutExpired:
                return "[ERROR] Execution timed out"
            finally:
                tmp.unlink(missing_ok=True)
        elif lang == "powershell":
            result = subprocess.run(
                ["powershell", "-Command", code], capture_output=True,
                text=True, timeout=timeout, cwd=str(self.cwd)
            )
            return (result.stdout + result.stderr)[:8000]
        return f"[ERROR] Unsupported language: {lang}"
    
    def _file_read(self, args: dict, ctx: dict) -> str:
        path = Path(args["path"])
        if not path.is_absolute():
            path = self.cwd / path
        if not path.exists():
            return json.dumps({"error": f"File not found: {path}"})
        
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(1, args.get("start", 1)) - 1
        count = args.get("count", 200)
        keyword = args.get("keyword")
        
        if keyword:
            # Search for keyword with context
            results = []
            for i, line in enumerate(lines):
                if keyword.lower() in line.lower():
                    ctx_start = max(0, i - 2)
                    ctx_end = min(len(lines), i + 3)
                    chunk = "\n".join(f"{j+1}| {lines[j]}" for j in range(ctx_start, ctx_end))
                    results.append(chunk)
                    if len(results) >= 5:
                        break
            return "\n---\n".join(results) if results else f"[No matches for '{keyword}']"
        
        selected = lines[start:start + count]
        return "\n".join(f"{start+i+1}| {line}" for i, line in enumerate(selected))
    
    def _file_write(self, args: dict, ctx: dict) -> str:
        path = Path(args["path"])
        if not path.is_absolute():
            path = self.cwd / path
        path.parent.mkdir(parents=True, exist_ok=True)
        mode = args.get("mode", "overwrite")
        
        if mode == "append":
            with open(path, "a", encoding="utf-8") as f:
                f.write(args["content"])
        else:
            path.write_text(args["content"], encoding="utf-8")
        return json.dumps({"success": True, "path": str(path), "bytes": len(args["content"].encode())})
    
    def _file_patch(self, args: dict, ctx: dict) -> str:
        path = Path(args["path"])
        if not path.is_absolute():
            path = self.cwd / path
        if not path.exists():
            return json.dumps({"error": f"File not found: {path}"})
        
        content = path.read_text(encoding="utf-8")
        old = args["old_content"]
        new = args["new_content"]
        
        if old not in content:
            return json.dumps({"error": "old_content not found in file"})
        if content.count(old) > 1:
            return json.dumps({"error": "old_content is not unique"})
        
        content = content.replace(old, new, 1)
        path.write_text(content, encoding="utf-8")
        return json.dumps({"success": True, "path": str(path)})
    
    def _web_search(self, args: dict, ctx: dict) -> str:
        query = args["query"]
        num = args.get("num", 5)
        try:
            import httpx
            # Use DuckDuckGo HTML (no API key needed)
            resp = httpx.get(
                "https://html.duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "Mozilla/5.0"},
                timeout=15.0,
                follow_redirects=True,
            )
            # Simple extraction
            results = []
            for m in re.finditer(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', resp.text):
                url = m.group(1)
                title = re.sub(r'<[^>]+>', '', m.group(2)).strip()
                if title and url:
                    results.append({"title": title, "url": url})
                if len(results) >= num:
                    break
            return json.dumps(results, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    def _shell_exec(self, args: dict, ctx: dict) -> str:
        command = args["command"]
        timeout = args.get("timeout", 30)
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=str(self.cwd)
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]\n{result.stderr}"
            return output[:8000]
        except subprocess.TimeoutExpired:
            return "[ERROR] Command timed out"
    
    def _memory_op(self, args: dict, ctx: dict) -> str:
        """Memory operations — connects to MemoryStore via context."""
        store = ctx.get("memory_store")
        if not store:
            return json.dumps({"error": "Memory store not initialized"})
        
        action = args["action"]
        
        if action == "add":
            item = store.add(
                args["content"],
                layer=args.get("layer", 0),
                domain=args.get("domain", ""),
                tags=args.get("tags", []),
                source="tool:memory_op",
            )
            return json.dumps({"added": item.id, "layer": item.layer})
        
        elif action == "search":
            query = args.get("query", args.get("content", ""))
            ranked = store.csa_rank(query, top_k=5)
            return json.dumps([{
                "id": it.id, "content": it.content[:200],
                "layer": it.layer, "score": round(sc, 4),
            } for it, sc in ranked], ensure_ascii=False)
        
        elif action == "compress":
            actions = store.hca_compress()
            return json.dumps({"compressed": actions})
        
        elif action == "stats":
            return json.dumps(store.get_stats())
        
        elif action == "index":
            from memory.index import L1Index
            idx = L1Index(store)
            return idx.build_index()
        
        return json.dumps({"error": f"Unknown action: {action}"})
    
    def _skill_op(self, args: dict, ctx: dict) -> str:
        """Skill operations — manages the skill store (L3 memory)."""
        store = ctx.get("memory_store")
        if not store:
            return json.dumps({"error": "Memory store not initialized"})
        
        action = args["action"]
        
        if action == "list":
            skills = store.get_by_layer(layer=3)
            return json.dumps([{
                "id": s.id, "domain": s.domain,
                "content": s.content[:150],
            } for s in skills], ensure_ascii=False)
        
        elif action == "search":
            query = args.get("query", "")
            ranked = store.csa_rank(query, layer=3, top_k=5)
            return json.dumps([{
                "id": it.id, "domain": it.domain,
                "content": it.content[:200], "score": round(sc, 4),
            } for it, sc in ranked], ensure_ascii=False)
        
        elif action == "create":
            item = store.add(
                args["content"],
                layer=3,
                domain=args.get("domain", "general"),
                source="tool:skill_op",
                importance=0.7,
            )
            return json.dumps({"created": item.id})
        
        elif action == "upgrade":
            # Find existing skill and update
            query = args.get("skill_name", "")
            ranked = store.csa_rank(query, layer=3, top_k=1)
            if ranked:
                item, _ = ranked[0]
                item.content = args.get("content", item.content)
                item.importance = min(item.importance + 0.1, 1.0)
                item.touch()
                return json.dumps({"upgraded": item.id})
            return json.dumps({"error": "Skill not found"})
        
        elif action == "merge":
            # Find similar skills and merge
            query = args.get("query", "")
            ranked = store.csa_rank(query, layer=3, top_k=10)
            if len(ranked) < 2:
                return json.dumps({"error": "Not enough similar skills to merge"})
            # Keep highest scored, merge others into it
            primary, _ = ranked[0]
            merged_ids = []
            for item, score in ranked[1:]:
                if score > 0.3:  # similarity threshold
                    primary.content += f"\n- {item.content}"
                    primary.importance = max(primary.importance, item.importance)
                    store.remove(item.id)
                    merged_ids.append(item.id)
            return json.dumps({"merged_into": primary.id, "removed": merged_ids})
        
        return json.dumps({"error": f"Unknown action: {action}"})

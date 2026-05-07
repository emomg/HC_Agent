"""Browser tools -- web_scan / web_execute_js for HC-Agent.

Wraps TMWebDriver + simphtml to provide browser automation
compatible with ToolRegistry.register(name, fn, desc, schema).
"""
from __future__ import annotations
import importlib, json, os, sys, time, traceback
from typing import Any

# Lazy-loaded singletons (initialized on first call)
_driver = None
_simphtml = None


def _ensure_driver():
    """Lazy-init TMWebDriver + simphtml (same pattern as GA ga.py)."""
    global _driver, _simphtml
    if _driver is not None:
        return
    from TMWebDriver import TMWebDriver
    _driver = TMWebDriver()
    for _ in range(20):
        time.sleep(1)
        sess = _driver.get_all_sessions()
        if sess:
            break
    if not sess:
        print("[browser_tool] WARNING: no browser session after 20s")


def _get_simphtml():
    global _simphtml
    if _simphtml is None:
        import simphtml
        _simphtml = simphtml
    else:
        _simphtml = importlib.reload(_simphtml)
    return _simphtml


def _format_error(e: Exception) -> str:
    exc_type, exc_value, exc_tb = sys.exc_info()
    tb = traceback.extract_tb(exc_tb)
    if tb:
        f = tb[-1]
        return f"{exc_type.__name__}: {e} @ {os.path.basename(f.filename)}:{f.lineno}, {f.name}"
    return f"{exc_type.__name__}: {e}"


def _smart_format(s: str, max_len: int = 10000) -> str:
    if len(s) <= max_len:
        return s
    half = max_len // 2
    return s[:half] + f"\n\n[...{len(s) - max_len} chars omitted...]\n\n" + s[-half:]


# ── Tool functions (match ToolRegistry.register signature) ────────────

def web_scan(tabs_only: bool = False, switch_tab_id: str = None,
             text_only: bool = False) -> dict:
    """Get simplified HTML content and tab list from the active browser.
    
    tabs_only: if True, only return tab list (save tokens).
    switch_tab_id: optional, switch to this tab before scanning.
    text_only: if True, return plain text (no HTML tags).
    """
    try:
        _ensure_driver()
        if _driver is None or len(_driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": "No browser tab available. Check TMWebDriver status."}

        tabs = []
        for sess in _driver.get_all_sessions():
            s = dict(sess)
            s.pop('connected_at', None)
            s.pop('type', None)
            url = s.get('url', '')
            s['url'] = url[:50] + ("..." if len(url) > 50 else "")
            tabs.append(s)

        if switch_tab_id:
            _driver.default_session_id = switch_tab_id

        result = {
            "status": "success",
            "metadata": {
                "tabs_count": len(tabs),
                "tabs": tabs,
                "active_tab": _driver.default_session_id,
            },
        }

        if not tabs_only:
            sh = _get_simphtml()
            content = sh.get_html(_driver, cutlist=True, maxchars=35000, text_only=text_only)
            if text_only:
                content = _smart_format(content, max_len=10000)
            result["content"] = content

        return result
    except Exception as e:
        return {"status": "error", "msg": _format_error(e)}


def web_execute_js(script: str, switch_tab_id: str = None,
                   no_monitor: bool = False) -> dict:
    """Execute JavaScript in the active browser tab and capture result + page changes.
    
    script: JS code to execute.
    switch_tab_id: optional, switch to this tab before executing.
    no_monitor: if True, skip page-change monitoring (faster, read-only).
    """
    try:
        _ensure_driver()
        if _driver is None or len(_driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": "No browser tab available."}
        if switch_tab_id:
            _driver.default_session_id = switch_tab_id
        sh = _get_simphtml()
        return sh.execute_js_rich(script, _driver, no_monitor=no_monitor)
    except Exception as e:
        return {"status": "error", "msg": _format_error(e)}


# ── Navigation tool functions ─────────────────────────────────────────

def web_navigate(url: str, switch_tab_id: str = None) -> dict:
    """Navigate the active browser tab to a URL."""
    try:
        _ensure_driver()
        if _driver is None or len(_driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": "No browser tab available."}
        if switch_tab_id:
            _driver.default_session_id = switch_tab_id
        _driver.execute_cdp_cmd("Page.navigate", {"url": url})
        time.sleep(2)
        return {"status": "success", "url": url}
    except Exception as e:
        return {"status": "error", "msg": _format_error(e)}


def web_back(switch_tab_id: str = None) -> dict:
    """Go back one page in browser history."""
    try:
        _ensure_driver()
        if _driver is None or len(_driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": "No browser tab available."}
        if switch_tab_id:
            _driver.default_session_id = switch_tab_id
        _driver.back()
        time.sleep(1)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "msg": _format_error(e)}


def web_forward(switch_tab_id: str = None) -> dict:
    """Go forward one page in browser history."""
    try:
        _ensure_driver()
        if _driver is None or len(_driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": "No browser tab available."}
        if switch_tab_id:
            _driver.default_session_id = switch_tab_id
        _driver.forward()
        time.sleep(1)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "msg": _format_error(e)}


def web_refresh(switch_tab_id: str = None) -> dict:
    """Refresh the active browser tab."""
    try:
        _ensure_driver()
        if _driver is None or len(_driver.get_all_sessions()) == 0:
            return {"status": "error", "msg": "No browser tab available."}
        if switch_tab_id:
            _driver.default_session_id = switch_tab_id
        _driver.refresh()
        time.sleep(1)
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "msg": _format_error(e)}


def web_close(session_id: str) -> dict:
    """Close a browser tab by session ID."""
    try:
        _ensure_driver()
        if _driver is None:
            return {"status": "error", "msg": "No browser available."}
        _driver.close_session(session_id)
        return {"status": "success", "closed": session_id}
    except Exception as e:
        return {"status": "error", "msg": _format_error(e)}


# ── ToolRegistry-compatible wrappers (fn(args: dict, ctx: dict)) ──────

def _web_scan_wrapper(args: dict, ctx: dict) -> str:
    """ToolRegistry-compatible wrapper for web_scan."""
    result = web_scan(
        tabs_only=args.get("tabs_only", False),
        switch_tab_id=args.get("switch_tab_id"),
        text_only=args.get("text_only", False),
    )
    import json
    return json.dumps(result, ensure_ascii=False)


def _web_close_wrapper(args: dict, ctx: dict) -> str:
    return json.dumps(web_close(args.get("session_id", "")))


def _web_navigate_wrapper(args: dict, ctx: dict) -> str:
    return json.dumps(web_navigate(args.get("url", ""), args.get("switch_tab_id")))


def _web_back_wrapper(args: dict, ctx: dict) -> str:
    return json.dumps(web_back(args.get("switch_tab_id")))


def _web_forward_wrapper(args: dict, ctx: dict) -> str:
    return json.dumps(web_forward(args.get("switch_tab_id")))


def _web_refresh_wrapper(args: dict, ctx: dict) -> str:
    return json.dumps(web_refresh(args.get("switch_tab_id")))


def _web_execute_js_wrapper(args: dict, ctx: dict) -> str:
    """ToolRegistry-compatible wrapper for web_execute_js."""
    result = web_execute_js(
        script=args["script"],
        switch_tab_id=args.get("switch_tab_id"),
        no_monitor=args.get("no_monitor", False),
    )
    import json
    return json.dumps(result, ensure_ascii=False)


# ── Registration helper ───────────────────────────────────────────────

def register_browser_tools(registry) -> None:
    """Register web_scan and web_execute_js into a ToolRegistry instance.
    
    ToolRegistry.execute() calls fn(args: dict, ctx: dict) -> str,
    so we use wrapper functions that unpack kwargs.
    """
    registry.register("web_scan", _web_scan_wrapper,
        "Get simplified HTML content and tab list from the active browser. "
        "tabs_only=true to only get tab list. switch_tab_id to switch tab. text_only=true for plain text.",
        {"type": "object", "properties": {
            "tabs_only": {"type": "boolean", "description": "Only return tab list", "default": False},
            "switch_tab_id": {"type": "string", "description": "Tab ID to switch to before scan"},
            "text_only": {"type": "boolean", "description": "Return plain text only", "default": False},
        }, "required": []})

    registry.register("web_navigate", _web_navigate_wrapper,
        "Navigate the active browser tab to a URL. Use this to open new pages.",
        {"type": "object", "properties": {
            "url": {"type": "string", "description": "URL to navigate to"},
            "switch_tab_id": {"type": "string", "description": "Tab ID to switch to before navigating"},
        }, "required": ["url"]})

    registry.register("web_back", _web_back_wrapper,
        "Go back one page in the active browser tab history.",
        {"type": "object", "properties": {
            "switch_tab_id": {"type": "string", "description": "Tab ID to switch to"},
        }, "required": []})

    registry.register("web_forward", _web_forward_wrapper,
        "Go forward one page in the active browser tab history.",
        {"type": "object", "properties": {
            "switch_tab_id": {"type": "string", "description": "Tab ID to switch to"},
        }, "required": []})

    registry.register("web_refresh", _web_refresh_wrapper,
        "Refresh the active browser tab.",
        {"type": "object", "properties": {
            "switch_tab_id": {"type": "string", "description": "Tab ID to switch to"},
        }, "required": []})

    registry.register("web_close", _web_close_wrapper,
        "Close a browser tab by session ID.",
        {"type": "object", "properties": {
            "session_id": {"type": "string", "description": "Session/tab ID to close"},
        }, "required": ["session_id"]})

    registry.register("web_execute_js", _web_execute_js_wrapper,
        "Execute JavaScript in the active browser tab and capture result + page changes. "
        "no_monitor=true to skip page monitoring (faster, for read-only queries).",
        {"type": "object", "properties": {
            "script": {"type": "string", "description": "JavaScript code to execute"},
            "switch_tab_id": {"type": "string", "description": "Tab ID to switch to before executing"},
            "no_monitor": {"type": "boolean", "description": "Skip page-change monitoring", "default": False},
        }, "required": ["script"]})

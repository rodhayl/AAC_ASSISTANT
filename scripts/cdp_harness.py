import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, Optional

import requests
import websockets


@dataclass(frozen=True)
class CDPTarget:
    url: str
    ws_url: str


def get_first_page_target(host: str = "127.0.0.1", port: int = 9222) -> CDPTarget:
    return get_page_target(host=host, port=port)


def get_page_target(
    *,
    host: str = "127.0.0.1",
    port: int = 9222,
    url_regex: str | None = r"^https?://(localhost|127\\.0\\.0\\.1):8086",
) -> CDPTarget:
    items = requests.get(f"http://{host}:{port}/json", timeout=5).json()
    pages = [it for it in items if it.get("type") == "page" and it.get("webSocketDebuggerUrl")]
    if not pages:
        raise RuntimeError(f"No page targets found at http://{host}:{port}/json")

    if url_regex:
        import re

        pat = re.compile(url_regex)
        match = next((p for p in pages if pat.search(p.get("url", ""))), None)
        if match:
            return CDPTarget(url=match.get("url", ""), ws_url=match["webSocketDebuggerUrl"])

    page = pages[0]
    return CDPTarget(url=page.get("url", ""), ws_url=page["webSocketDebuggerUrl"])


class CDP:
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}
        self._events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def __aenter__(self):
        self.ws = await websockets.connect(self.ws_url, max_size=2**25)
        self._recv_task = asyncio.create_task(self._recv_loop())
        return self

    async def __aexit__(self, *exc):
        self._recv_task.cancel()
        await self.ws.close()

    async def _recv_loop(self):
        async for msg in self.ws:
            data = json.loads(msg)
            if "id" in data and data["id"] in self._pending:
                fut = self._pending.pop(data["id"])
                if not fut.done():
                    fut.set_result(data)
            else:
                await self._events.put(data)

    async def wait_for_event(self, method: str, timeout_s: float = 10) -> dict[str, Any]:
        end = time.time() + timeout_s
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for event: {method}")
            try:
                ev = await asyncio.wait_for(self._events.get(), timeout=remaining)
            except asyncio.TimeoutError as e:
                raise TimeoutError(f"Timed out waiting for event: {method}") from e
            if ev.get("method") == method:
                return ev

    async def wait_for_request(self, url_substring: str, timeout_s: float = 10) -> dict[str, Any]:
        end = time.time() + timeout_s
        while True:
            remaining = end - time.time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for request containing: {url_substring}")
            try:
                ev = await asyncio.wait_for(self._events.get(), timeout=remaining)
            except asyncio.TimeoutError as e:
                raise TimeoutError(f"Timed out waiting for request containing: {url_substring}") from e
            if ev.get("method") != "Network.requestWillBeSent":
                continue
            req = (ev.get("params") or {}).get("request") or {}
            url = req.get("url", "")
            if url_substring in url:
                return ev

    async def call(self, method: str, params: Optional[dict[str, Any]] = None, timeout: float = 30) -> dict[str, Any]:
        self._id += 1
        mid = self._id
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[mid] = fut
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        data = await asyncio.wait_for(fut, timeout=timeout)
        if "error" in data:
            raise RuntimeError(f"CDP error calling {method}: {data['error']}")
        return data.get("result", {})

    async def enable(self):
        await self.call("Page.enable")
        await self.call("Runtime.enable")
        await self.call("Network.enable")

    async def eval(self, expression: str, *, await_promise: bool = True, timeout: float = 30) -> Any:
        res = await self.call(
            "Runtime.evaluate",
            {
                "expression": expression,
                "awaitPromise": await_promise,
                "returnByValue": True,
            },
            timeout=timeout,
        )
        if res.get("exceptionDetails"):
            details = res["exceptionDetails"]
            text = details.get("text", "Uncaught")
            exc = (details.get("exception") or {}).get("description") or ""
            raise RuntimeError(f"Runtime.evaluate exception: {text} {exc}".strip())
        return (res.get("result") or {}).get("value")

    async def goto(self, url: str):
        await self.call("Page.navigate", {"url": url})

    async def wait_for_js(self, js_predicate: str, timeout_s: float = 15) -> bool:
        start = time.time()
        while time.time() - start < timeout_s:
            ok = await self.eval(js_predicate, await_promise=False)
            if ok:
                return True
            await asyncio.sleep(0.2)
        return False

    async def wait_for_selector(self, selector: str, timeout_s: float = 15) -> bool:
        sel = json.dumps(selector)
        return await self.wait_for_js(f"Boolean(document.querySelector({sel}))", timeout_s=timeout_s)

    async def click(self, selector: str):
        sel = json.dumps(selector)
        await self.eval(
            f"""(() => {{
  const el = document.querySelector({sel});
  if (!el) return false;
  el.click();
  return true;
}})()""",
            await_promise=False,
        )

    async def click_mouse(self, selector: str):
        """
        Click an element via real mouse events (useful for APIs requiring a user gesture,
        like Fullscreen).
        """
        sel = json.dumps(selector)
        point = await self.eval(
            f"""(() => {{
  const el = document.querySelector({sel});
  if (!el) return null;
  try {{ el.scrollIntoView({{ block: "center", inline: "center" }}); }} catch {{}}
  const r = el.getBoundingClientRect();
  return {{ x: r.left + r.width / 2, y: r.top + r.height / 2 }};
}})()""",
            await_promise=False,
        )
        if not point or "x" not in point or "y" not in point:
            raise RuntimeError(f"Could not find element for mouse click: {selector}")

        x = float(point["x"])
        y = float(point["y"])
        await self.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y, "button": "none", "clickCount": 0})
        await self.call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
        await self.call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})

    async def click_text(self, regex: str, *, tag: str = "*"):
        pat = json.dumps(regex)
        tag_js = json.dumps(tag)
        ok = await self.eval(
            f"""(() => {{
  const r = new RegExp({pat}, "i");
  const els = Array.from(document.querySelectorAll({tag_js}));
  const el = els.find(e => r.test((e.innerText || e.textContent || "").trim()));
  if (!el) return false;
  el.click();
  return true;
}})()""",
            await_promise=False,
        )
        if not ok:
            raise RuntimeError(f"Could not find element by text /{regex}/")

    async def set_value(self, selector: str, value: str):
        sel = json.dumps(selector)
        val = json.dumps(value)
        ok = await self.eval(
            f"""(() => {{
  const el = document.querySelector({sel});
  if (!el) return false;
  el.focus();
  const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  if (desc && desc.set) desc.set.call(el, {val});
  else el.value = {val};
  el.dispatchEvent(new Event("input", {{ bubbles: true }}));
  el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  return true;
}})()""",
            await_promise=False,
        )
        if not ok:
            raise RuntimeError(f"Could not set value for selector: {selector}")

    async def set_select_value(self, selector: str, value: str):
        sel = json.dumps(selector)
        val = json.dumps(value)
        ok = await self.eval(
            f"""(() => {{
  const el = document.querySelector({sel});
  if (!el) return false;
  if (el.tagName !== "SELECT") return false;
  el.focus();
  el.value = {val};
  el.dispatchEvent(new Event("input", {{ bubbles: true }}));
  el.dispatchEvent(new Event("change", {{ bubbles: true }}));
  return true;
}})()""",
            await_promise=False,
        )
        if not ok:
            raise RuntimeError(f"Could not set select value for selector: {selector}")

    async def set_input_files(self, selector: str, file_paths: list[str]):
        await self.call("DOM.enable")
        doc = await self.call("DOM.getDocument", {"depth": 1})
        root_id = doc["root"]["nodeId"]
        node = await self.call("DOM.querySelector", {"nodeId": root_id, "selector": selector})
        node_id = node.get("nodeId")
        if not node_id:
            raise RuntimeError(f"Could not find file input for selector: {selector}")
        await self.call("DOM.setFileInputFiles", {"nodeId": node_id, "files": file_paths})

    async def emulate_offline(self, offline: bool):
        await self.call(
            "Network.emulateNetworkConditions",
            {
                "offline": bool(offline),
                "latency": 0,
                "downloadThroughput": -1,
                "uploadThroughput": -1,
            },
        )

    async def set_blocked_urls(self, urls: list[str]):
        await self.call("Network.setBlockedURLs", {"urls": urls})

    async def clear_origin_data(self, origin: str):
        await self.call("Network.clearBrowserCookies")
        await self.call("Network.clearBrowserCache")
        await self.call(
            "Storage.clearDataForOrigin",
            {
                "origin": origin,
                "storageTypes": "all",
            },
        )

    async def set_download_dir(self, download_dir: str):
        await self.call(
            "Page.setDownloadBehavior",
            {"behavior": "allow", "downloadPath": download_dir},
        )

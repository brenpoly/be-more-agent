"""Optional Parallel Search MCP support for the voice agent."""

import asyncio
import json
import math
import uuid
from urllib.parse import urlsplit


PARALLEL_MCP_URL = "https://search.parallel.ai/mcp"
USER_AGENT = "be-more-agent/ParallelSearch (https://github.com/brenpoly/be-more-agent)"


class SearchCancelled(Exception):
    """The user interrupted the current search."""


class SearchConversation:
    """Keep one opaque search identity until the agent's memory is reset."""

    def __init__(self):
        self.session_id = str(uuid.uuid4())

    def search(self, query, interrupted, timeout=15):
        if interrupted.is_set():
            raise SearchCancelled()
        if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
                or not math.isfinite(timeout) or not 0 < timeout <= 120):
            raise ValueError("search_timeout_seconds must be between 0 and 120")
        # asyncio.run() waits for its default executor at shutdown, even after
        # cancellation. An OS DNS lookup cannot be interrupted, so let it finish
        # in the background instead of holding the voice-agent call open.
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._controlled_search(query, interrupted, timeout))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            finally:
                loop.close()

    async def _controlled_search(self, query, interrupted, timeout):
        import anyio

        # Keep cancellation active during SDK teardown too. A single asyncio
        # task.cancel() can be consumed before the SDK awaits its session DELETE.
        scope = anyio.CancelScope()

        async def request():
            with scope:
                return await self._request(query, timeout)

        task = asyncio.create_task(request())
        deadline = asyncio.get_running_loop().time() + timeout
        try:
            while True:
                if interrupted.is_set():
                    raise SearchCancelled()
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0:
                    raise TimeoutError("Parallel search timed out")
                done, _ = await asyncio.wait({task}, timeout=min(0.05, remaining))
                if done:
                    if interrupted.is_set():
                        raise SearchCancelled()
                    return task.result()
        finally:
            if not task.done():
                scope.cancel()
                await asyncio.gather(task, return_exceptions=True)

    async def _request(self, query, timeout):
        # Lazy imports keep the default DuckDuckGo path usable on Python 3.9
        # without installing the optional MCP SDK (which needs Python 3.10+).
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=timeout,
        ) as client:
            async with streamable_http_client(
                PARALLEL_MCP_URL, http_client=client,
            ) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    if not any(tool.name == "web_search" for tool in tools.tools):
                        raise RuntimeError("Parallel MCP does not offer web_search")
                    result = await session.call_tool("web_search", {
                        "objective": query,
                        "search_queries": [query],
                        "session_id": self.session_id,
                    })
                    if result.isError:
                        raise RuntimeError("Parallel search failed: " + str(result.content))
                    data = result.structuredContent
                    if data is None:
                        text = "\n".join(
                            block.text for block in result.content if block.type == "text"
                        )
                        data = json.loads(text)
                    return format_results(query, data)


def format_results(query, data):
    """Bound the context sent to the small local summarization model."""
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Invalid Parallel search response")
    if not data["results"]:
        return "SEARCH_EMPTY"
    results = []
    for row in data["results"][:3]:
        if not isinstance(row, dict):
            raise ValueError("Invalid Parallel search result")
        url = row.get("url")
        if not isinstance(url, str) or len(url) > 2048:
            raise ValueError("Invalid search result URL")
        parsed = urlsplit(url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname
                or parsed.username or parsed.password or any(c.isspace() for c in url)):
            raise ValueError("Invalid search result URL")
        excerpts = row.get("excerpts")
        if not isinstance(excerpts, list) or any(not isinstance(s, str) for s in excerpts):
            raise ValueError("Invalid search result excerpts")
        title = row.get("title") or "No Title"
        if not isinstance(title, str):
            raise ValueError("Invalid search result title")
        snippet = "\n".join(excerpts)[:1000]
        results.append(f"Title: {title[:160]}\nURL: {url}\nSnippet: {snippet}")
    return f"SEARCH RESULTS for '{query}':\n" + "\n\n".join(results)

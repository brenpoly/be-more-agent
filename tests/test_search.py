import sys
from common import result

def test_search():
    try:
        from ddgs import DDGS
    except ImportError:
        return result("web search lib installed", False, "pip install ddgs")

    try:
        with DDGS() as ddgs:
            results = list(ddgs.text("latest news about robots", region="us-en", max_results=1))
        if results:
            print(f"  Top result: {results[0].get('title')}")
            return result("Web search returns results", True, results[0].get("title", "")[:60])
        return result("Web search returns results", False, "no results")
    except Exception as e:
        return result("Web search", False, str(e))

if __name__ == "__main__":
    sys.exit(0 if test_search() else 1)
"""FileNest 搜索命中摘要库。

用法：
    import filenest_snippet
    pq = filenest_snippet.prepare('a AND "b c"')
    snippet = pq.select(text)   # None 表示无命中
"""

from .api import PreparedQuery, Snippet, prepare

__all__ = ["PreparedQuery", "Snippet", "prepare"]

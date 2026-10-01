"""FileNest 搜索命中摘要库。

上层直接调用：先 prepare_query 得到可复用的查询对象，
再对每篇正文调用 select 选择最短命中摘要。
"""

from .query import PreparedQuery, prepare_query
from .engine import Snippet

__all__ = ["PreparedQuery", "prepare_query", "Snippet"]

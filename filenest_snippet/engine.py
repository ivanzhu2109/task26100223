"""正文匹配与最短命中摘要选择。

核心思路：为每个查询节点计算"阶梯函数" minEnd(s) ——
起点 >= s 且满足该节点的片段的最小终点。
  叶子：minEnd(s) = 起点 >= s 的匹配中最早结束者的终点（终点取后缀最小值）。
  AND ：max(minEnd_L(s), minEnd_R(s))（片段须同时包含两侧的证据）。
  OR  ：min(minEnd_L(s), minEnd_R(s))。
阶梯函数用升序断点 (starts[i], ends[i]) 表示：
s 落在 (starts[i-1], starts[i]] 时取值为 ends[i]。
最优片段起点必为某个断点，扫描根节点断点取 (终点-起点) 最小、
同长起点最早者即可。
"""

from __future__ import annotations

import re
from array import array
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from .query import And, Node, Phrase, PreparedQuery, Word

_TOKEN_RE = re.compile(rb"[A-Za-z0-9]+")

_MAX_BYTES = 2**31 - 1

# 阶梯函数：两条等长升序断点数组
_Step = Tuple[array, array]


@dataclass(frozen=True)
class Snippet:
    """命中摘要：原文片段及其 UTF-8 字节区间 [start, end)。"""

    text: str
    start: int
    end: int


class _Document:
    """单篇正文的分词结果与叶子匹配。"""

    def __init__(self, data: bytes) -> None:
        tok_start = array("i")
        tok_end = array("i")
        tok_id = array("I")
        word_ids: Dict[bytes, int] = {}
        for m in _TOKEN_RE.finditer(data):
            word = m.group().lower()
            wid = word_ids.get(word)
            if wid is None:
                wid = len(word_ids)
                word_ids[word] = wid
            tok_start.append(m.start())
            tok_end.append(m.end())
            tok_id.append(wid)
        self.tok_start = tok_start
        self.tok_end = tok_end
        self.tok_id = tok_id
        self.word_ids = word_ids
        # 每个词 id 的出现位置（升序）
        positions: List[array] = [array("I") for _ in range(len(word_ids))]
        for idx, wid in enumerate(tok_id):
            positions[wid].append(idx)
        self.positions = positions

    def release(self) -> None:
        """叶子匹配完成后释放分词数据，降低合并阶段峰值内存。"""
        self.tok_start = array("i")
        self.tok_end = array("i")
        self.tok_id = array("I")
        self.positions = []

    def word_step(self, text: str) -> _Step:
        wid = self.word_ids.get(text.encode("ascii"))
        if wid is None:
            return array("i"), array("i")
        pos = self.positions[wid]
        tok_start, tok_end = self.tok_start, self.tok_end
        starts = array("q", (tok_start[p] for p in pos))
        ends = array("q", (tok_end[p] for p in pos))
        return starts, ends

    def phrase_step(self, words: Tuple[str, ...]) -> _Step:
        wids = []
        for w in words:
            wid = self.word_ids.get(w.encode("ascii"))
            if wid is None:
                return array("i"), array("i")
            wids.append(wid)
        k = len(wids)
        if k == 1:
            return self.word_step(words[0])
        target = array("I", wids)
        tok_id, tok_start, tok_end = self.tok_id, self.tok_start, self.tok_end
        starts = array("i")
        ends = array("i")
        for p in self.positions[wids[0]]:
            if tok_id[p : p + k] == target:
                starts.append(tok_start[p])
                ends.append(tok_end[p + k - 1])
        return _suffix_min(starts, ends)


def _suffix_min(starts: array, ends: array) -> _Step:
    """对按起点升序的匹配取终点后缀最小值，得到叶子阶梯函数。"""
    rs = array("i")
    re_ = array("i")
    best = None
    for i in range(len(starts) - 1, -1, -1):
        e = ends[i]
        if best is None or e < best:
            best = e
            rs.append(starts[i])
            re_.append(e)
    rs.reverse()
    re_.reverse()
    return rs, re_


def _merge(a: _Step, b: _Step, is_and: bool) -> _Step:
    """合并两个阶梯函数。AND 取 max、OR 取 min，自右向左扫描断点。"""
    (a_s, a_e), (b_s, b_e) = a, b
    i, j = len(a_s) - 1, len(b_s) - 1
    rs = array("i")
    re_ = array("i")
    va = vb = 0
    have_a = have_b = False
    last = None
    append_s = rs.append
    append_e = re_.append
    while i >= 0 or j >= 0:
        sa = a_s[i] if i >= 0 else -1
        sb = b_s[j] if j >= 0 else -1
        if sa >= sb:
            p = sa
            va = a_e[i]
            have_a = True
            i -= 1
        if sb >= sa:
            p = sb
            vb = b_e[j]
            have_b = True
            j -= 1
        if is_and:
            if not (have_a and have_b):
                continue
            v = va if va >= vb else vb
        elif have_a and have_b:
            v = va if va <= vb else vb
        elif have_a:
            v = va
        else:
            v = vb
        if v != last:
            last = v
            append_s(p)
            append_e(v)
    rs.reverse()
    re_.reverse()
    return rs, re_


def select_snippet(query: PreparedQuery, text: str) -> Optional[Snippet]:
    """在满足整条查询的连续片段中，选 UTF-8 字节最短、同长起点最早者。"""
    data = text.encode("utf-8")
    if len(data) > _MAX_BYTES:
        raise ValueError("正文超过支持的最大字节数")
    doc = _Document(data)
    leaf_cache: Dict[object, _Step] = {}

    def build_leaf(node: Node) -> None:
        if isinstance(node, Word):
            if node not in leaf_cache:
                leaf_cache[node] = doc.word_step(node.text)
        elif isinstance(node, Phrase):
            if node not in leaf_cache:
                leaf_cache[node] = doc.phrase_step(node.words)
        else:
            build_leaf(node.left)
            build_leaf(node.right)

    build_leaf(query.root)
    doc.release()

    def evaluate(node: Node) -> _Step:
        if isinstance(node, (Word, Phrase)):
            return leaf_cache[node]
        left = evaluate(node.left)
        right = evaluate(node.right)
        return _merge(left, right, isinstance(node, And))

    starts, ends = evaluate(query.root)
    best_len = None
    best_s = best_e = 0
    for idx in range(len(starts)):
        length = ends[idx] - starts[idx]
        if best_len is None or length < best_len:
            best_len = length
            best_s = starts[idx]
            best_e = ends[idx]
    if best_len is None:
        return None
    return Snippet(text=data[best_s:best_e].decode("utf-8"), start=best_s, end=best_e)

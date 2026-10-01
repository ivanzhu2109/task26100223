"""对外 API：准备可复用的查询，为单篇正文选择命中摘要。"""

from __future__ import annotations

from array import array
from typing import Dict, List, NamedTuple, Optional, Tuple

from . import document as _document
from . import engine as _engine
from .query import And, Leaf, Node, Or, Phrase, Word, parse


class Snippet(NamedTuple):
    """命中摘要：原文连续片段及其 UTF-8 字节区间 [start, end)。"""

    text: str
    start: int
    end: int


def _collect_leaves(node: Node, leaves: List[Leaf],
                    index: Dict[Leaf, int]) -> Node:
    """给每个叶子条件分配下标；相同叶子共享同一个下标。"""
    if isinstance(node, (Word, Phrase)):
        if node not in index:
            index[node] = len(leaves)
            leaves.append(node)
        return node
    children = tuple(_collect_leaves(c, leaves, index) for c in node.children)
    return type(node)(children)


class PreparedQuery:
    """可复用的已解析查询。"""

    __slots__ = ("_root", "_leaves", "_index")

    def __init__(self, root: Node, leaves: List[Leaf],
                 index: Dict[Leaf, int]) -> None:
        self._root = root
        self._leaves = leaves
        self._index = index

    def select(self, text: str) -> Optional[Snippet]:
        """为单篇正文选择最短命中摘要；无命中返回 None。"""
        doc = _document.tokenize(text)
        frontiers = self._leaf_frontiers(doc)
        frontier = self._evaluate(self._root, frontiers)
        best = _engine.best_window(frontier)
        if best is None:
            return None
        start, end = best
        return Snippet(doc.data[start:end].decode("utf-8"), start, end)

    def _leaf_frontiers(self, doc: _document.Document) -> List[array]:
        vocab = doc.vocab
        needed = set()
        leaf_wids: List[Tuple[int, ...]] = []
        for leaf in self._leaves:
            if isinstance(leaf, Word):
                wids = (vocab.get(leaf.text.encode("ascii"), -1),)
            else:
                wids = tuple(
                    vocab.get(w.encode("ascii"), -1) for w in leaf.words
                )
            leaf_wids.append(wids)
            needed.update(w for w in wids if w >= 0)
        positions = _document.word_positions(doc, needed)
        return [
            self._leaf_frontier(doc, leaf, wids, positions)
            for leaf, wids in zip(self._leaves, leaf_wids)
        ]

    @staticmethod
    def _leaf_frontier(doc, leaf, wids, positions) -> array:
        empty = array("q")
        if any(w < 0 for w in wids):
            return empty
        starts = doc.word_starts
        ends = doc.word_ends
        if isinstance(leaf, Word):
            wid = wids[0]
            return array(
                "q",
                (_engine.pack(starts[p], ends[p]) for p in positions[wid]),
            )
        # 短语：以出现次数最少的词为锚点，向两侧核对词序连续性
        k = len(wids)
        anchor = min(range(k), key=lambda i: len(positions[wids[i]]))
        word_ids = doc.word_ids
        n_words = len(word_ids)
        out = array("q")
        for p in positions[wids[anchor]]:
            base = p - anchor
            if base < 0 or base + k > n_words:
                continue
            if list(word_ids[base : base + k]) == list(wids):
                out.append(_engine.pack(starts[base], ends[base + k - 1]))
        return out

    def _evaluate(self, node: Node, frontiers: List[array]) -> array:
        if isinstance(node, (Word, Phrase)):
            return frontiers[self._index[node]]
        if isinstance(node, Or):
            combine = _engine.combine_or
        else:
            combine = _engine.combine_and
            # AND 任一子式为空则整体为空，提前短路
            child_frontiers = [self._evaluate(c, frontiers) for c in node.children]
            if any(len(f) == 0 for f in child_frontiers):
                return array("q")
            return _balanced_fold(child_frontiers, combine)
        return _balanced_fold(
            [self._evaluate(c, frontiers) for c in node.children], combine
        )

def _balanced_fold(frontiers: List[array], combine) -> array:
    """平衡二叉折叠，控制中间前沿的规模与总工作量。"""
    while len(frontiers) > 1:
        nxt = []
        for i in range(0, len(frontiers) - 1, 2):
            nxt.append(combine(frontiers[i], frontiers[i + 1]))
        if len(frontiers) % 2:
            nxt.append(frontiers[-1])
        frontiers = nxt
    return frontiers[0]


def prepare(query: str) -> PreparedQuery:
    """解析查询并返回可复用的 PreparedQuery。"""
    root = parse(query)
    leaves: List[Leaf] = []
    index: Dict[Leaf, int] = {}
    root = _collect_leaves(root, leaves, index)
    return PreparedQuery(root, leaves, index)

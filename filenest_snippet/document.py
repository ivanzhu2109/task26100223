"""正文词法分析：把正文切分为词，并记录每个词的 UTF-8 字节区间。

词是 ASCII 字母或数字组成的最大连续段，其余字符（含中文、emoji、
换行等）均为分隔符。比较时只忽略 ASCII 大小写。
"""

from __future__ import annotations

import re
from array import array
from typing import Dict, Set

_WORD_RE = re.compile(rb"[0-9A-Za-z]+")


class Document:
    """已词法分析的正文。

    data:        正文的 UTF-8 编码
    word_starts: 每个词的起始字节偏移（含）
    word_ends:   每个词的结束字节偏移（不含）
    word_ids:    每个词规范化后的词型 id
    vocab:       规范化词型 -> 词型 id
    """

    __slots__ = ("data", "word_starts", "word_ends", "word_ids", "vocab")

    data: bytes
    word_starts: array
    word_ends: array
    word_ids: array
    vocab: Dict[bytes, int]


def tokenize(text: str) -> Document:
    """把正文切分为词序列，记录字节区间与规范化词型。"""
    doc = Document()
    doc.data = text.encode("utf-8")
    doc.word_starts = array("i")
    doc.word_ends = array("i")
    doc.word_ids = array("i")
    doc.vocab = {}
    starts = doc.word_starts
    ends = doc.word_ends
    ids = doc.word_ids
    vocab = doc.vocab
    for m in _WORD_RE.finditer(doc.data):
        word = m.group().lower()  # bytes.lower 只影响 ASCII 字母
        wid = vocab.get(word)
        if wid is None:
            wid = len(vocab)
            vocab[word] = wid
        starts.append(m.start())
        ends.append(m.end())
        ids.append(wid)
    return doc


def word_positions(doc: Document, needed: Set[int]) -> Dict[int, array]:
    """返回 needed 中每个词型 id 在正文中的词下标列表（升序）。"""
    positions: Dict[int, array] = {wid: array("i") for wid in needed}
    appenders = {wid: pos.append for wid, pos in positions.items()}
    for idx, wid in enumerate(doc.word_ids):
        append = appenders.get(wid)
        if append is not None:
            append(idx)
    return positions

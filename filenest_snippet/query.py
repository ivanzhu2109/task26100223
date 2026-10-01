"""查询解析：单词、英文双引号短语、AND/OR、圆括号。

AND 优先于 OR，括号改变结合范围；输入查询保证合法。
词与短语在解析时统一归一化为 ASCII 小写。
同优先级链构造成平衡二叉树，保证后续求值深度为 O(log n)。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple, Union

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class Word:
    text: str


@dataclass(frozen=True)
class Phrase:
    words: Tuple[str, ...]


@dataclass(frozen=True)
class And:
    left: "Node"
    right: "Node"


@dataclass(frozen=True)
class Or:
    left: "Node"
    right: "Node"


Node = Union[Word, Phrase, And, Or]

# 词法单元：('word', 归一化文本) / ('phrase', 归一化词组) / '(' / ')' / 'AND' / 'OR'
_Token = Tuple[str, object]


def _lex(query: str) -> List[_Token]:
    tokens: List[_Token] = []
    i, n = 0, len(query)
    while i < n:
        ch = query[i]
        if ch.isspace():
            i += 1
        elif ch == "(":
            tokens.append(("(", None))
            i += 1
        elif ch == ")":
            tokens.append((")", None))
            i += 1
        elif ch == '"':
            j = query.index('"', i + 1)
            words = tuple(m.group().lower() for m in _WORD_RE.finditer(query[i + 1 : j]))
            tokens.append(("phrase", words))
            i = j + 1
        else:
            m = _WORD_RE.match(query, i)
            if m is None:
                # 查询保证合法；其他字符视为空白跳过
                i += 1
                continue
            text = m.group()
            if text == "AND":
                tokens.append(("AND", None))
            elif text == "OR":
                tokens.append(("OR", None))
            else:
                tokens.append(("word", text.lower()))
            i = m.end()
    return tokens


def _balanced(op, items: Sequence[Node]) -> Node:
    if len(items) == 1:
        return items[0]
    mid = len(items) // 2
    return op(_balanced(op, items[:mid]), _balanced(op, items[mid:]))


class _Parser:
    def __init__(self, tokens: List[_Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def parse_expr(self) -> Node:
        items = [self.parse_and()]
        while self._peek("OR"):
            self.pos += 1
            items.append(self.parse_and())
        return _balanced(Or, items)

    def parse_and(self) -> Node:
        items = [self.parse_atom()]
        while self._peek("AND"):
            self.pos += 1
            items.append(self.parse_atom())
        return _balanced(And, items)

    def parse_atom(self) -> Node:
        kind, value = self.tokens[self.pos]
        if kind == "(":
            self.pos += 1
            node = self.parse_expr()
            self.pos += 1  # 消费 ')'
            return node
        self.pos += 1
        if kind == "word":
            return Word(value)  # type: ignore[arg-type]
        return Phrase(value)  # type: ignore[arg-type]

    def _peek(self, kind: str) -> bool:
        return self.pos < len(self.tokens) and self.tokens[self.pos][0] == kind


class PreparedQuery:
    """可复用的已解析查询。"""

    def __init__(self, root: Node, source: str) -> None:
        self.root = root
        self.source = source

    def select(self, text: str):
        """为单篇正文选择摘要；无满足条件的片段时返回 None。"""
        from .engine import select_snippet

        return select_snippet(self, text)


def prepare_query(query: str) -> PreparedQuery:
    """解析查询字符串，返回可复用的 PreparedQuery。"""
    tokens = _lex(query)
    if not tokens:
        raise ValueError("空查询")
    parser = _Parser(tokens)
    root = parser.parse_expr()
    if parser.pos != len(tokens):
        raise ValueError("查询解析未消费全部输入")
    return PreparedQuery(root, query)

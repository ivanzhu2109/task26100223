"""查询解析：把查询字符串解析为表达式树。

语法（输入保证合法）：
    or_expr  := and_expr (OR and_expr)*
    and_expr := atom (AND atom)*
    atom     := WORD | '"' PHRASE '"' | '(' or_expr ')'
AND 优先级高于 OR，圆括号改变结合范围。
同级的 AND / OR 链会被展平为 n 元节点，便于后续平衡求值。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Union


@dataclass(frozen=True)
class Word:
    """单词叶子条件，text 已按 ASCII 小写规范化。"""

    text: str


@dataclass(frozen=True)
class Phrase:
    """短语叶子条件，words 为规范化后的词序列（1..8 个）。"""

    words: Tuple[str, ...]


@dataclass(frozen=True)
class And:
    children: Tuple["Node", ...]


@dataclass(frozen=True)
class Or:
    children: Tuple["Node", ...]


Leaf = Union[Word, Phrase]
Node = Union[Word, Phrase, And, Or]


def _normalize(text: str) -> str:
    """只忽略 ASCII 大小写的规范化。"""
    return "".join(chr(ord(c) + 32) if "A" <= c <= "Z" else c for c in text)


def _tokenize(query: str) -> list:
    """把查询切为词法单元：'(' / ')' / 'AND' / 'OR' / ('w', word) / ('p', phrase)。"""
    tokens = []
    i, n = 0, len(query)
    while i < n:
        c = query[i]
        if c.isspace():
            i += 1
        elif c == "(":
            tokens.append("(")
            i += 1
        elif c == ")":
            tokens.append(")")
            i += 1
        elif c == '"':
            j = query.index('"', i + 1)
            tokens.append(("p", query[i + 1 : j]))
            i = j + 1
        else:
            j = i
            while j < n and not query[j].isspace() and query[j] not in '()"':
                j += 1
            word = query[i:j]
            if word in ("AND", "OR"):
                tokens.append(word)
            else:
                tokens.append(("w", word))
            i = j
    return tokens


class _Parser:
    def __init__(self, tokens: list) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def next(self):
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def parse_or(self) -> Node:
        children = [self.parse_and()]
        while self.peek() == "OR":
            self.next()
            children.append(self.parse_and())
        return children[0] if len(children) == 1 else Or(tuple(children))

    def parse_and(self) -> Node:
        children = [self.parse_atom()]
        while self.peek() == "AND":
            self.next()
            children.append(self.parse_atom())
        return children[0] if len(children) == 1 else And(tuple(children))

    def parse_atom(self) -> Node:
        tok = self.next()
        if tok == "(":
            node = self.parse_or()
            self.next()  # 消费 ')'
            return node
        kind, text = tok
        if kind == "w":
            return Word(_normalize(text))
        return Phrase(tuple(_normalize(w) for w in text.split()))


def parse(query: str) -> Node:
    """把查询字符串解析为表达式树。"""
    return _Parser(_tokenize(query)).parse_or()

"""正确性测试：业务规则用例 + 随机用例暴力对照。"""

import random
import re
import unittest
from array import array

from filenest_snippet import prepare_query
from filenest_snippet.query import And, Or, Phrase, Word

_TOKEN_RE = re.compile(rb"[A-Za-z0-9]+")


def oracle_matches(node, tokens):
    """叶子条件在正文中的全部匹配 [(start_byte, end_byte)]，tokens 为 (s, e, word)。"""
    if isinstance(node, Word):
        return [(s, e) for s, e, w in tokens if w == node.text]
    words = list(node.words)
    k = len(words)
    out = []
    for i in range(len(tokens) - k + 1):
        if [t[2] for t in tokens[i : i + k]] == words:
            out.append((tokens[i][0], tokens[i + k - 1][1]))
    return out


def oracle_satisfies(node, matches_cache, s, e):
    """窗口 [s, e) 是否满足整条查询（叶子须含完整匹配）。"""
    if isinstance(node, (Word, Phrase)):
        return any(s <= ms and me <= e for ms, me in matches_cache[node])
    if isinstance(node, And):
        return oracle_satisfies(node.left, matches_cache, s, e) and oracle_satisfies(
            node.right, matches_cache, s, e
        )
    return oracle_satisfies(node.left, matches_cache, s, e) or oracle_satisfies(
        node.right, matches_cache, s, e
    )


def oracle_best(query, text):
    """暴力枚举所有词界窗口，返回 (text, start, end) 或 None。"""
    data = text.encode("utf-8")
    tokens = [
        (m.start(), m.end(), m.group().lower().decode())
        for m in _TOKEN_RE.finditer(data)
    ]
    leaves = {}

    def collect(node):
        if isinstance(node, (Word, Phrase)):
            leaves[node] = oracle_matches(node, tokens)
        else:
            collect(node.left)
            collect(node.right)

    collect(query.root)
    best = None
    for i in range(len(tokens)):
        for j in range(i, len(tokens)):
            s, e = tokens[i][0], tokens[j][1]
            length = e - s
            if best is not None and (length, s) >= (best[2] - best[1], best[1]):
                continue
            if oracle_satisfies(query.root, leaves, s, e):
                best = (data[s:e].decode("utf-8"), s, e)
    return best


class RuleTests(unittest.TestCase):
    def test_emoji_separator_acceptance(self):
        q = prepare_query("a AND b")
        s = q.select("a💡b----a  b")
        self.assertEqual((s.text, s.start, s.end), ("a  b", 10, 14))

    def test_cjk_emoji_newline_offsets(self):
        text = "中文前缀\nkey💡\n词\n\nvalue\t尾"
        q = prepare_query("key AND value")
        s = q.select(text)
        data = text.encode("utf-8")
        self.assertEqual(data[s.start : s.end].decode("utf-8"), s.text)
        self.assertEqual(s.text, "key💡\n词\n\nvalue")
        self.assertEqual(s.start, data.index("key".encode()))
        self.assertEqual(s.end, data.index("value".encode()) + 5)

    def test_repeated_term_shares_occurrence(self):
        q = prepare_query("a AND a")
        s = q.select("xx a yy")
        self.assertEqual((s.text, s.start, s.end), ("a", 3, 4))

    def test_overlapping_phrases_share_words(self):
        q = prepare_query('"a b" AND "b c"')
        s = q.select("a b c")
        self.assertEqual((s.text, s.start, s.end), ("a b c", 0, 5))

    def test_phrase_allows_any_separators(self):
        q = prepare_query('"new york"')
        s = q.select("new---\n york!")
        self.assertEqual((s.text, s.start, s.end), ("new---\n york", 0, 12))

    def test_nested_and_or_multiple_evidence(self):
        # 两个 OR 分支都成立，选更短者
        q = prepare_query("(alpha AND beta) OR (gamma AND delta)")
        s = q.select("alpha xxxxx beta ... gamma delta")
        self.assertEqual(s.text, "gamma delta")
        # 嵌套内层再选最短
        q2 = prepare_query("a AND (b OR (c AND d))")
        s2 = q2.select("a . c d")
        self.assertEqual(s2.text, "a . c d")

    def test_or_does_not_require_other_branch(self):
        q = prepare_query("a AND (b OR c)")
        s = q.select("a .... c")
        self.assertEqual(s.text, "a .... c")

    def test_case_insensitive_ascii_only(self):
        q = prepare_query("Hello AND WORLD")
        s = q.select("hELLo, world!")
        self.assertEqual((s.text, s.start, s.end), ("hELLo, world", 0, 12))

    def test_no_match_returns_none(self):
        self.assertIsNone(prepare_query("a AND b").select("only a here"))
        self.assertIsNone(prepare_query('"a b"').select("a x b"))
        self.assertIsNone(prepare_query("(a OR b) AND (c OR d)").select("a b ... nope"))
        # 部分成立的证据出现在正文末尾也不得返回
        self.assertIsNone(prepare_query("qq AND a").select("a " * 5 + "zz qq".replace(" qq", "")))

    def test_window_cannot_fabricate_matches(self):
        # "ab" 是一个词，不等于 a 与 b
        self.assertIsNone(prepare_query("a AND b").select("ab"))
        # 短语 "a b" 不匹配单词 ab
        self.assertIsNone(prepare_query('"a b"').select("ab"))

    def test_tie_breaks_to_earliest_start(self):
        q = prepare_query("a AND b")
        s = q.select("a b xx a b")
        self.assertEqual((s.text, s.start, s.end), ("a b", 0, 3))

    def test_prepared_query_reusable_across_documents(self):
        q = prepare_query("foo AND bar")
        self.assertEqual(q.select("bar foo").text, "bar foo")
        self.assertIsNone(q.select("foo only"))
        self.assertEqual(q.select("foo bar").text, "foo bar")


class RandomCrossCheckTests(unittest.TestCase):
    def test_random_against_oracle(self):
        rng = random.Random(20261001)
        vocab = ["a", "b", "c", "dd", "e"]
        seps = [" ", "  ", "\n", "--", "💡", "，", "\t", " / "]
        for _ in range(300):
            n = rng.randint(0, 12)
            words = [rng.choice(vocab) for _ in range(n)]
            text = ""
            for i, w in enumerate(words):
                if i:
                    text += rng.choice(seps)
                text += w
                if rng.random() < 0.1:
                    text += rng.choice(["中", "🙂"])
            query = self._random_query(rng, vocab, depth=0)
            prepared = prepare_query(query)
            got = prepared.select(text)
            want = oracle_best(prepared, text)
            if want is None:
                self.assertIsNone(got, f"query={query!r} text={text!r}")
            else:
                self.assertIsNotNone(got, f"query={query!r} text={text!r}")
                self.assertEqual(
                    (got.text, got.start, got.end),
                    want,
                    f"query={query!r} text={text!r}",
                )
                # 返回片段自身必须满足整条查询
                leaves = {}
                self._collect(prepared.root, text, leaves)
                self.assertTrue(
                    oracle_satisfies(prepared.root, leaves, got.start, got.end)
                )

    def _collect(self, node, text, leaves):
        data = text.encode("utf-8")
        tokens = [
            (m.start(), m.end(), m.group().lower().decode())
            for m in _TOKEN_RE.finditer(data)
        ]

        def walk(n):
            if isinstance(n, (Word, Phrase)):
                leaves[n] = oracle_matches(n, tokens)
            else:
                walk(n.left)
                walk(n.right)

        walk(node)

    def _random_query(self, rng, vocab, depth):
        if depth >= 3 or rng.random() < 0.4:
            if rng.random() < 0.3:
                k = rng.randint(2, 3)
                return '"' + " ".join(rng.choice(vocab) for _ in range(k)) + '"'
            return rng.choice(vocab)
        op = " AND " if rng.random() < 0.5 else " OR "
        left = self._random_query(rng, vocab, depth + 1)
        right = self._random_query(rng, vocab, depth + 1)
        return "(" + left + op + right + ")"


if __name__ == "__main__":
    unittest.main()

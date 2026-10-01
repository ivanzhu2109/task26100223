"""命中摘要正确性测试。

测试用一个独立的暴力求解器：枚举所有“词边界对齐”的连续窗口，
检查窗口是否满足整条查询，取 (字节长度, 起点) 最小者。由于任何
最优窗口都可以收缩到词边界而不失效，暴力解即全局最优解。
"""

import random
import re
import unittest

import filenest_snippet as fn
from filenest_snippet.query import And, Or, Phrase, Word, parse

_WORD_RE = re.compile(r"[0-9A-Za-z]+")


def _norm(word):
    return word.lower()


def _satisfies(node, words):
    """窗口内的规范化词序列是否满足子表达式。"""
    if isinstance(node, Word):
        return node.text in words
    if isinstance(node, Phrase):
        k = len(node.words)
        return any(
            list(node.words) == words[i : i + k]
            for i in range(len(words) - k + 1)
        )
    if isinstance(node, And):
        return all(_satisfies(c, words) for c in node.children)
    assert isinstance(node, Or)
    return any(_satisfies(c, words) for c in node.children)


def brute_force(text, query):
    """独立暴力求解：返回 (start, end) 或 None。"""
    data = text.encode("utf-8")
    matches = list(re.finditer(rb"[0-9A-Za-z]+", data))
    words = [_norm(m.group().decode("ascii")) for m in matches]
    ast = parse(query)
    best = None
    n = len(matches)
    for i in range(n):
        for j in range(i, n):
            if _satisfies(ast, words[i : j + 1]):
                start = matches[i].start()
                end = matches[j].end()
                key = (end - start, start)
                if best is None or key < best[0]:
                    best = (key, (start, end))
    return best[1] if best else None


def check(case, text, query):
    pq = fn.prepare(query)
    snippet = pq.select(text)
    expected = brute_force(text, query)
    if expected is None:
        case.assertIsNone(snippet, "应无命中: %r on %r" % (query, text))
        return
    case.assertIsNotNone(snippet, "应有命中: %r on %r" % (query, text))
    case.assertEqual(snippet.start, expected[0])
    case.assertEqual(snippet.end, expected[1])
    data = text.encode("utf-8")
    case.assertEqual(data[snippet.start:snippet.end].decode("utf-8"),
                     snippet.text)
    words = [_norm(m) for m in _WORD_RE.findall(snippet.text)]
    case.assertTrue(_satisfies(parse(query), words),
                    "片段不满足查询: %r vs %r" % (snippet.text, query))


class AcceptanceTest(unittest.TestCase):
    def test_acceptance_example(self):
        snippet = fn.prepare("a AND b").select("a💡b----a  b")
        self.assertEqual(snippet, fn.Snippet("a  b", 10, 14))

    def test_repeated_terms_share_occurrence(self):
        check(self, "x a y", "a AND a")
        check(self, "a b a", "a AND a AND a")

    def test_overlapping_phrases_share_words(self):
        check(self, "a b c", '"a b" AND "b c"')
        check(self, "z a b c z a b z c", '"a b" AND "b c"')

    def test_nested_and_or_multiple_evidence(self):
        check(self, "c d x x x a b", "(a AND b) OR (c AND d)")
        check(self, "a b x x x c d", "(a AND b) OR (c AND d)")
        check(self, "a c b d a d b c", "((a AND b) OR c) AND d")
        check(self, "p a q b r c s d", "(a AND (b OR c)) OR (c AND d)")

    def test_or_excludes_unneeded_branch(self):
        check(self, "a b", "a OR b")
        check(self, "b a", "a OR b")
        check(self, "b x x x a", "a OR b")

    def test_and_requires_both_sides(self):
        check(self, "a c a c b", "a AND b")
        check(self, "b b b a", "a AND b")

    def test_no_hit_returns_none(self):
        self.assertIsNone(fn.prepare("a AND b").select("a a a"))
        self.assertIsNone(fn.prepare("a AND b").select("b b b"))
        self.assertIsNone(fn.prepare('"a b"').select("a c b"))
        self.assertIsNone(fn.prepare("(a OR b) AND (c OR d)").select("a b x"))

    def test_case_insensitive_ascii_only(self):
        check(self, "Apple aPpLe", "apple AND apple")
        check(self, "X A1b a1B y", "a1b AND a1b")

    def test_unicode_separators_and_offsets(self):
        check(self, "你好alpha💡\nbeta世界", "alpha AND beta")
        check(self, "αα x\n\ny 💡 z", "x AND z")
        check(self, "a中b", '"a b"')
        check(self, "一x💡y\nz二 x  y  z", "x AND y AND z")

    def test_phrase_arbitrary_separators(self):
        check(self, "a,\n b💡c", '"a b" AND c')
        check(self, "a---b---c", '"a b c"')

    def test_tie_break_earliest_start(self):
        check(self, "a b x a b", "a AND b")
        check(self, "a x b a x b", "a AND b")

    def test_reusable_prepared_query(self):
        pq = fn.prepare("a AND b")
        self.assertEqual(pq.select("a b"), fn.Snippet("a b", 0, 3))
        self.assertEqual(pq.select("b a"), fn.Snippet("b a", 0, 3))
        self.assertIsNone(pq.select("nothing"))


class PropertyTest(unittest.TestCase):
    """随机小样本上与暴力解对比。"""

    def test_random_against_brute_force(self):
        rng = random.Random(20261001)
        vocab = ["a", "b", "c", "d"]
        seps = [" ", "  ", "\n", "💡", "中", "--", ", "]

        def rand_leaf():
            if rng.random() < 0.4:
                k = rng.randint(2, 3)
                return '"' + " ".join(rng.choice(vocab) for _ in range(k)) + '"'
            return rng.choice(vocab)

        def rand_expr(depth):
            if depth == 0 or rng.random() < 0.4:
                return rand_leaf()
            op = rng.choice([" AND ", " OR "])
            parts = [rand_expr(depth - 1) for _ in range(rng.randint(2, 3))]
            return "(" + op.join(parts) + ")"

        for _ in range(300):
            n = rng.randint(1, 12)
            text = ""
            for i in range(n):
                text += rng.choice(vocab + ["x", "y"])
                if i + 1 < n:
                    text += rng.choice(seps)
            query = rand_expr(3)
            check(self, text, query)


if __name__ == "__main__":
    unittest.main()

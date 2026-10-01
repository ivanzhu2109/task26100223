"""资源测试：8MiB / 100 万词正文，64 叶子查询，验证 CPU 与新增峰值内存。

直接运行：python3 tests/test_perf.py
每个场景分别测量 CPU 时间（无追踪开销）与 tracemalloc 新增峰值内存。
"""

import os
import sys
import time
import tracemalloc
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from filenest_snippet import prepare_query

WORD_COUNT = 1_000_000
CPU_LIMIT = 10.0
MEM_LIMIT = 64 * 1024 * 1024


def build_text(words):
    """由词序列构造正文，校验规模约束。"""
    text = " ".join(words)
    assert len(text.encode("utf-8")) <= 8 * 1024 * 1024, "正文超过 8MiB"
    return text


def measure(query, text):
    """返回 (snippet, cpu_seconds, peak_new_bytes)。"""
    prepared = prepare_query(query)
    start = time.process_time()
    snippet = prepared.select(text)
    cpu = time.process_time() - start
    tracemalloc.start()
    prepared.select(text)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return snippet, cpu, peak


def scenario_or_pairs():
    """32 组二选一以 AND 连接（64 叶子），全部正文词参与匹配。"""
    left = [f"wa{i:02d}" for i in range(32)]
    right = [f"xb{i:02d}" for i in range(32)]
    vocab = left + right
    reps = WORD_COUNT // len(vocab)
    words = (vocab * (reps + 1))[:WORD_COUNT]
    query = " AND ".join(f"({l} OR {r})" for l, r in zip(left, right))
    return query, build_text(words)


def scenario_repeated_terms():
    """64 个叶子全为同一词项（大量重复词项）。"""
    vocab = [f"r{i:02d}" for i in range(8)]
    reps = WORD_COUNT // len(vocab)
    words = (vocab * (reps + 1))[:WORD_COUNT]
    query = " AND ".join(["r00"] * 64)
    return query, build_text(words)


def scenario_overlapping_phrases():
    """64 个交叠短语叶子，相邻短语共享正文词。"""
    vocab = [f"p{i:02d}" for i in range(64)]
    reps = WORD_COUNT // len(vocab)
    words = (vocab * (reps + 1))[:WORD_COUNT]
    # 正文词序 p00 p01 ... p63 循环，短语 "p_i p_{i+1}" 按模 64 闭合
    query = " AND ".join(f'"{vocab[i]} {vocab[(i + 1) % 64]}"' for i in range(64))
    return query, build_text(words)


def scenario_late_evidence():
    """32 组二选一 AND，其中一组的完整证据直到正文末尾才出现。"""
    left = [f"la{i:02d}" for i in range(32)]
    right = [f"rb{i:02d}" for i in range(32)]
    vocab = left + right[1:]  # rb00 不出现在主体中
    reps = (WORD_COUNT - 2) // len(vocab)
    words = (vocab * (reps + 1))[: WORD_COUNT - 2]
    words += ["la00", "rb00"]  # 最后一组 OR 的证据在末尾才完整
    query = " AND ".join(f"({l} OR {r})" for l, r in zip(left, right))
    return query, build_text(words)


def scenario_no_match():
    """高命中密度但缺一个叶子，不得返回部分成立的摘要。"""
    vocab = [f"n{i:02d}" for i in range(63)]
    reps = WORD_COUNT // len(vocab)
    words = (vocab * (reps + 1))[:WORD_COUNT]
    query = " AND ".join([f"n{i:02d}" for i in range(63)] + ["absent"])
    return query, build_text(words)


SCENARIOS = {
    "or_pairs_32": scenario_or_pairs,
    "repeated_terms": scenario_repeated_terms,
    "overlapping_phrases": scenario_overlapping_phrases,
    "late_evidence": scenario_late_evidence,
    "no_match": scenario_no_match,
}


class PerfTests(unittest.TestCase):
    def test_resource_limits(self):
        for name, builder in SCENARIOS.items():
            with self.subTest(scenario=name):
                query, text = builder()
                snippet, cpu, peak = measure(query, text)
                print(
                    f"[perf] {name}: cpu={cpu:.2f}s "
                    f"peak_new={peak / 1024 / 1024:.1f}MiB "
                    f"hit={snippet is not None}"
                )
                self.assertLess(cpu, CPU_LIMIT, name)
                self.assertLess(peak, MEM_LIMIT, name)
                if name == "no_match":
                    self.assertIsNone(snippet)
                else:
                    self.assertIsNotNone(snippet, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)

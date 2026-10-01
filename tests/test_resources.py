"""资源测试：规定规模下的 CPU 时间与新增峰值内存。

规模：单篇正文 100 万个词（< 8MiB），查询 64 个叶子条件
（32 组二选一以 AND 连接），至少一半正文词参与匹配。
限制：单篇 CPU 时间 <= 10 秒，新增峰值内存 <= 64MiB
（不计调用方持有的输入正文与返回片段）。
"""

import time
import tracemalloc
import unittest

import filenest_snippet as fn

WORD_COUNT = 1_000_000
LEAF_COUNT = 64
CPU_LIMIT_S = 10.0
MEM_LIMIT = 64 * 1024 * 1024


def build_query():
    pairs = ["(w%d OR w%d)" % (i, i + 1) for i in range(0, LEAF_COUNT, 2)]
    return " AND ".join(pairs)


def build_text(word_count):
    # 一半的词是查询词（w0..w63 循环），另一半是填充词
    parts = []
    for i in range(word_count):
        if i % 2 == 0:
            parts.append("w%d" % ((i // 2) % LEAF_COUNT))
        else:
            parts.append("zz")
    return " ".join(parts)


class ResourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.query = build_query()
        cls.text = build_text(WORD_COUNT)
        cls.size_mib = len(cls.text.encode("utf-8")) / 2**20
        assert len(cls.text.encode("utf-8")) <= 8 * 2**20

    def measure(self, text, query):
        pq = fn.prepare(query)
        # CPU 时间单独测量，避免 tracemalloc 的插桩开销计入
        start = time.process_time()
        snippet = pq.select(text)
        cpu = time.process_time() - start
        tracemalloc.start()
        snippet = pq.select(text)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return snippet, cpu, peak

    def report(self, label, cpu, peak):
        print("[resource] %s: CPU %.2f s, 新增峰值内存 %.1f MiB"
              % (label, cpu, peak / 2**20))

    def test_high_match_density(self):
        snippet, cpu, peak = self.measure(self.text, self.query)
        self.report("高命中密度(%.1f MiB, %d 词)" % (self.size_mib, WORD_COUNT),
                    cpu, peak)
        self.assertIsNotNone(snippet)
        self.assertLessEqual(cpu, CPU_LIMIT_S)
        self.assertLessEqual(peak, MEM_LIMIT)

    def test_evidence_near_end(self):
        # 完整证据直到正文末尾才出现
        text = "zz " * (WORD_COUNT - LEAF_COUNT) + " ".join(
            "w%d" % i for i in range(LEAF_COUNT)
        )
        snippet, cpu, peak = self.measure(text, self.query)
        self.report("证据在末尾", cpu, peak)
        self.assertIsNotNone(snippet)
        # 每组二选一只需一个词：最优窗口为 w1..w62（共 62 个词）
        self.assertEqual(snippet.text,
                         " ".join("w%d" % i for i in range(1, LEAF_COUNT - 1)))
        self.assertLessEqual(cpu, CPU_LIMIT_S)
        self.assertLessEqual(peak, MEM_LIMIT)

    def test_no_hit_large_document(self):
        # 整组 (w62 OR w63) 都不出现，任何片段都不满足整条查询，
        # 不得返回部分成立的摘要
        text = self.text.replace("w62", "zz").replace("w63", "zz")
        snippet, cpu, peak = self.measure(text, self.query)
        self.report("大规模无命中", cpu, peak)
        self.assertIsNone(snippet)
        self.assertLessEqual(cpu, CPU_LIMIT_S)
        self.assertLessEqual(peak, MEM_LIMIT)


if __name__ == "__main__":
    unittest.main()

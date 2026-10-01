# FileNest 搜索命中摘要库

为搜索命中的长文档选择一段最短、完整、可定位回原文的摘要。纯内存、纯标准库，无接口层。

## 用法

```python
from filenest_snippet import prepare_query

query = prepare_query('a AND ("b c" OR d)')   # 可复用
snippet = query.select(text)                   # 每篇正文独立调用
if snippet is None:
    ...                                        # 无满足整条查询的片段
else:
    snippet.text                               # 原文连续片段
    snippet.start, snippet.end                 # UTF-8 字节区间 [start, end)
```

## 规则

- 查询：单词、英文双引号短语、大写 `AND`/`OR`、圆括号；`AND` 优先于 `OR`。
- 正文词为 ASCII 字母数字的最大连续段，仅忽略 ASCII 大小写；短语要求词序连续，词间允许任意分隔符。
- 摘要为满足整条查询的最短 UTF-8 字节片段，同长取起点最早者；不补上下文、不拼接。

## 测试

```sh
python3 -m unittest discover -s tests        # 全部测试（含资源测试）
python3 -m unittest tests.test_snippet -v    # 仅正确性
python3 -m unittest tests.test_perf -v       # 仅资源（CPU / 峰值内存报告）
```

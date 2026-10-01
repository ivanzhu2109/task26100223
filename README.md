# FileNest 搜索命中摘要库

为搜索命中的长文档选出最短、完整、可定位回原文的摘要片段。
纯内存库，无接口层，由上层直接调用。

## 用法

```python
import filenest_snippet

pq = filenest_snippet.prepare('apple AND "red fruit" OR (banana AND grape)')
snippet = pq.select(text)   # 可复用同一查询处理多篇正文
if snippet is not None:
    snippet.text            # 原文连续片段
    snippet.start           # 起始 UTF-8 字节偏移（含）
    snippet.end             # 结束 UTF-8 字节偏移（不含）
```

- 查询支持单词、英文双引号短语、大写 `AND` / `OR`、圆括号；`AND` 优先于 `OR`。
- 正文中的词是 ASCII 字母数字的最大连续段，比较只忽略 ASCII 大小写；
  短语要求各词在正文词序中连续，词间可有任意分隔符。
- 在所有满足整条查询的片段中，返回 UTF-8 字节长度最短者；同长取起点最早者。
- 无满足条件的片段时返回 `None`。

## 测试

```sh
python3 -m unittest discover -s tests -v
```

`tests/test_snippet.py` 为正确性测试（含与独立暴力解的随机对比）；
`tests/test_resources.py` 为规定规模（100 万词、64 叶子、32 组二选一）
下的 CPU 时间与新增峰值内存测试。

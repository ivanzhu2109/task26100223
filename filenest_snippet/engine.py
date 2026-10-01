"""命中摘要求值引擎。

每个子表达式的求值结果是一个“候选窗口前沿”：一组互不包含、
且都满足该子表达式的字节窗口。任意满足子表达式的窗口都包含
前沿中的某个窗口，因此前沿足以代表全部解。

窗口打包为单个 int：高 32 位为起始字节，低 32 位为结束字节，
因此打包值的大小序即 (start, end) 的字典序。
"""

from __future__ import annotations

from array import array
from typing import Optional, Tuple

SHIFT = 32
MASK = (1 << SHIFT) - 1


def pack(start: int, end: int) -> int:
    return (start << SHIFT) | end


_INF = 1 << 62


def _merge_filter(left: array, right: array) -> array:
    """归并两条按打包值升序的前沿，并只保留互不包含的窗口。

    从右向左扫描：若已保留窗口中存在起点 >= 当前起点且终点 <= 当前终点
    的窗口，则当前窗口被支配，丢弃。起点相同的窗口只留终点最小者。
    """
    i, j = len(left) - 1, len(right) - 1
    out = array("q")
    append = out.append
    min_end = _INF
    kept_start = -1
    while i >= 0 or j >= 0:
        if j < 0 or (i >= 0 and left[i] >= right[j]):
            p = left[i]
            i -= 1
        else:
            p = right[j]
            j -= 1
        start = p >> SHIFT
        end = p & MASK
        if start == kept_start:
            # 起点相同：逆序遍历时终点递减，用更小的终点替换已保留窗口
            out[-1] = p
            min_end = end
        elif end < min_end:
            append(p)
            min_end = end
            kept_start = start
    out.reverse()
    return out


def combine_or(left: array, right: array) -> array:
    """OR：两侧前沿合并后重新取互不包含的前沿。"""
    return _merge_filter(left, right)


def _candidates(here: array, there: array) -> array:
    """对 here 中每个窗口 x，找 there 中起点 >= x 起点的首个窗口 y，
    生成候选 [x.start, max(x.end, y.end)]。

    由于前沿中终点随起点递增，y 即 there 中该后缀内终点最小者；
    与 y 起点相同侧更靠左的配对所产生的窗口都被这些候选支配。
    """
    out = array("q")
    append = out.append
    j = 0
    n = len(there)
    for p in here:
        start = p >> SHIFT
        while j < n and (there[j] >> SHIFT) < start:
            j += 1
        if j == n:
            break
        end = p & MASK
        other_end = there[j] & MASK
        append((start << SHIFT) | (end if end > other_end else other_end))
    return out


def combine_and(left: array, right: array) -> array:
    """AND：两侧各取一个窗口，求覆盖两者的最小窗口前沿。"""
    return _merge_filter(_candidates(left, right), _candidates(right, left))


def best_window(frontier: array) -> Optional[Tuple[int, int]]:
    """从前沿中选出 (长度, 起点) 最小的窗口；空前沿返回 None。"""
    best = None
    best_key = None
    for p in frontier:
        start = p >> SHIFT
        end = p & MASK
        key = (end - start, start)
        if best_key is None or key < best_key:
            best_key = key
            best = (start, end)
    return best

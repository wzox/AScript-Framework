import time
import threading
import heapq
import inspect
import traceback
from typing import Callable, Dict, Optional, Sequence, Any
from dataclasses import dataclass, field

from .图文识别 import 截图一帧, 裁剪图片, 计算截图特征

@dataclass(order=True)
class 监测任务:
    """任务实体：按 下次执行时间 与 自增序号 参与最小堆排序，序号保证同刻任务按创建顺序稳定"""
    下次执行时间: float
    自增序号: int
    名称: str = field(compare=False)
    间隔秒数: float = field(compare=False)

    # 传统模式：到点直接执行
    执行函数: Optional[Callable] = field(default=None, compare=False)

    # 视觉帧差阻断模式：画面变化 → 识别条件(截屏) → 回调函数(识别结果)
    识别区域: Optional[Sequence[int]] = field(default=None, compare=False)
    识别条件: Optional[Callable] = field(default=None, compare=False)
    回调函数: Optional[Callable] = field(default=None, compare=False)

    需要截图: bool = field(default=False, compare=False)
    已启用: bool = field(default=True, compare=False)
    已取消: bool = field(default=False, compare=False)
    _上次特征: Any = field(default=None, compare=False)

    def 运行(self, 共享截图):
        """执行任务本体（添加任务已保证两模式互斥）：
        传统模式→到点直跑；视觉帧差模式→画面变化才识别，命中则回调"""
        if self.执行函数:
            if self.需要截图:
                self.执行函数(截屏=共享截图)
            else:
                self.执行函数()
            return

        目标图 = 裁剪图片(共享截图, self.识别区域) if self.识别区域 else 共享截图
        当前特征 = 计算截图特征(目标图)
        if 当前特征 == self._上次特征:
            return  # 画面未变化，跳过识别
        self._上次特征 = 当前特征
        识别结果 = self.识别条件(截屏=目标图)
        if 识别结果:
            self.回调函数(识别结果)

class 任务调度器:
    """调度器：最小堆(Min-Heap)排期 + 惰性删除，支持定时执行与帧差阻断两种任务模式"""

    def __init__(self):
        self._任务表: Dict[str, 监测任务] = {}
        self._任务堆 = []
        self._锁 = threading.RLock()
        self._后台轮询中 = False
        self._轮询线程 = None
        self._自增序号 = 0

    def 添加任务(self, 名称: str, 执行函数: Callable = None, 间隔秒数: float = 0.0, 自动启用: bool = True,
                 识别区域: Sequence[int] = None, 识别条件: Callable = None, 回调函数: Callable = None):
        """注册任务；同名任务会被新任务惰性替换（旧任务标记已取消）"""
        需要截图 = False
        if 执行函数:
            if 识别条件 or 回调函数:
                raise ValueError(f"任务[{名称}]的 '执行函数' 与 ('识别条件'/'回调函数') 互斥，不可同时提供")
            需要截图 = "截屏" in inspect.signature(执行函数).parameters
        elif 识别条件 and 回调函数:
            需要截图 = True
        else:
            raise ValueError(f"任务[{名称}]必须提供 '执行函数' 或 ('识别条件' 和 '回调函数')")

        with self._锁:
            if 名称 in self._任务表:
                self._任务表[名称].已取消 = True

            self._自增序号 += 1
            新任务 = 监测任务(
                下次执行时间=time.perf_counter() if 自动启用 else float('inf'),
                自增序号=self._自增序号,
                名称=名称,
                间隔秒数=间隔秒数,
                执行函数=执行函数,
                识别区域=识别区域,
                识别条件=识别条件,
                回调函数=回调函数,
                需要截图=需要截图,
                已启用=自动启用
            )

            self._任务表[名称] = 新任务
            if 自动启用:
                heapq.heappush(self._任务堆, 新任务)

    def 移除任务(self, 名称: str):
        """移除任务：惰性标记已取消，待从堆顶弹出时丢弃"""
        with self._锁:
            任务 = self._任务表.pop(名称, None)
            if 任务:
                任务.已取消 = True

    def 暂停任务(self, 名称: str):
        """暂停任务：惰性标记未启用，留在堆中但弹出即弃"""
        with self._锁:
            任务 = self._任务表.get(名称)
            if 任务 and not 任务.已取消:
                任务.已启用 = False

    def 恢复任务(self, 名称: str):
        """恢复任务：立即安排当前时刻执行，压回最小堆"""
        with self._锁:
            任务 = self._任务表.get(名称)
            if not 任务 or 任务.已取消 or 任务.已启用:
                return
            任务.已启用 = True
            任务.下次执行时间 = time.perf_counter()
            heapq.heappush(self._任务堆, 任务)

    def 执行一轮(self) -> bool:
        """推进一轮调度：取出全部到期任务并执行；返回本轮是否有任务执行
        节拍说明：重排以“完成时刻+间隔”起算，慢任务顺延不补跑，属有意的正向漂移"""
        当前时间 = time.perf_counter()

        # 1. 收集到期任务，惰性丢弃已取消/未启用的残留堆项
        本轮待执行 = []
        with self._锁:
            while self._任务堆 and self._任务堆[0].下次执行时间 <= 当前时间:
                任务 = heapq.heappop(self._任务堆)
                if 任务.已取消 or not 任务.已启用:
                    continue
                本轮待执行.append(任务)

        if not 本轮待执行:
            return False

        # 2. 本轮仅需一张共享截图，供所有需要画面的任务复用
        共享截图 = 截图一帧() if any(任务.需要截图 for 任务 in 本轮待执行) else None

        # 3. 逐个执行任务本体，异常隔离不影响其余任务
        # 4. 未取消且仍启用的任务，按间隔重新入堆
        for 任务 in 本轮待执行:
            try:
                任务.运行(共享截图)
            except Exception as e:
                print(f"！任务调度异常[{任务.名称}]: {e}\n{traceback.format_exc()}")
            finally:
                with self._锁:
                    if not 任务.已取消 and 任务.已启用:
                        任务.下次执行时间 = time.perf_counter() + 任务.间隔秒数
                        heapq.heappush(self._任务堆, 任务)

        return True

    def 启动后台调度(self, 轮询间隔: float = 0.1):
        """启动独立守护线程按固定间隔轮询执行一轮；重复调用无效"""
        if self._后台轮询中: return
        self._后台轮询中 = True
        self._轮询线程 = threading.Thread(target=self._轮询循环, args=(轮询间隔,), daemon=True)
        self._轮询线程.start()

    def 停止后台调度(self):
        self._后台轮询中 = False

    def _轮询循环(self, 轮询间隔: float):
        while self._后台轮询中:
            self.执行一轮()
            time.sleep(轮询间隔)

"""图文动作模块 - 设备动作原语与识别结果的链式交互 (支持 Android & iOS)"""
import random
import sys
import time
from typing import TYPE_CHECKING, Optional, Sequence, Tuple
from __future__ import annotations

# 仅供 IDE 静态分析使用，设备端运行时不导入，规避低版本 Python 缺失 Self
if TYPE_CHECKING: from typing import Self

from .配置参数 import 默认配置
from .图文识别 import 截图一帧, 计算截图特征, 查找文字, 模板匹配

if sys.platform == "linux":
    from ascript.android import action
else:
    from ascript.ios import action


# ==================== 设备动作原语 ====================

class 动作链:
    """基础动作的链式载体：方法返回自身，支持 点(...).等(...) 式续接。
    模块级 点/滑动/等 即本类单例的绑定方法，业务按普通函数调用即可。"""

    def 点(self, 坐标, y=None, 时长: Optional[int] = None, 抖动: bool = True) -> "动作链":
        """点击。坐标 可为 (x, y) 或 x+y；时长 语义为「中位数」，按 触点时长抖动比例 上下浮动以消除固定触点指纹。"""
        try:
            x, y_ = 坐标 if y is None else (坐标, y)
            if 抖动:
                x += random.randint(-默认配置.抖动半径, 默认配置.抖动半径)
                y_ += random.randint(-默认配置.抖动半径, 默认配置.抖动半径)
            if 时长 is None and 抖动:
                时长 = random.randint(默认配置.抖动时长最小值, 默认配置.抖动时长最大值)  # 拟人区间本身已随机，不再二次抖动
            else:
                基准时长 = 时长 if 时长 is not None else 默认配置.点击时长
                比例 = 默认配置.触点时长抖动比例
                if 比例 > 0 and 基准时长 > 1:
                    基准时长 = max(1, round(基准时长 * random.uniform(1 - 比例, 1 + 比例)))
                时长 = 基准时长
            action.click(int(x), int(y_), int(时长))
        except Exception as e:
            print(f"× 点击执行失败: {e}")
        return self

    def 滑动(self, x1: int, y1: int, x2: int, y2: int, 时长: int = 默认配置.滑动时长) -> "动作链":
        try:
            action.slide(int(x1), int(y1), int(x2), int(y2), 时长)
        except Exception as e:
            print(f"× 滑动执行失败: {e}")
        return self

    def 等(self, 秒数: float = 默认配置.等待秒数) -> "动作链":
        time.sleep(秒数)
        return self


_动作链 = 动作链()
点, 滑动, 等 = _动作链.点, _动作链.滑动, _动作链.等


# ==================== 画面稳态判据内核 ====================

class 等消结果:
    """等消 判据的返回值：真值即「目标曾出现且现已消失」。"""

    def __init__(self, 已消失: bool):
        self.已消失 = 已消失

    def __bool__(self) -> bool:
        return self.已消失

    def 等(self, 秒数: float = 默认配置.等待秒数) -> "等消结果":
        """等待指定秒数，仅在成功消失时执行。"""
        if self:
            等(秒数)
        return self


def _区域特征(区域: Optional[Sequence[int]]) -> Optional[int]:
    """区域直采算哈希做帧差检测：仅采样目标区域像素，比「全屏截图+裁剪」大幅降低序列化与哈希开销。"""
    return 计算截图特征(截图一帧(区域))


def _帧门控(区域: Optional[Sequence[int]]) -> Tuple[Optional[int], object]:
    """等显 轮询门控，返回 (门控特征, 可复用全屏帧)：整屏门控时一帧两用，省掉一次全屏截图；带区域时只做廉价直采。"""
    if 区域:
        return _区域特征(区域), None
    全屏帧 = 截图一帧()
    return 计算截图特征(全屏帧), 全屏帧


def _初始特征(区域: Optional[Sequence[int]], 结果, 截屏=None) -> Optional[int]:
    """命中即留下帧差基线。调用方传入外部帧（常为裁剪局部图）时与实时画面不同源、不可比，故置 None 交由 等消 现采基线，顺带省掉一次无谓截图。"""
    if not 结果 or 截屏 is not None:
        return None
    return _区域特征(区域)


# ==================== 识别结果链式动作 ====================

class _基础查找链:
    """图片链与文字链的基础抽象类，运用模板方法模式抹平行为差异：子类只供 坐标/摘要/存在检查/建新链 四个钩子。"""
    _结果: Optional[object] = None
    _命中特征: Optional[int] = None
    区域: Optional[Sequence[int]] = None
    _默认节拍: Tuple[float, float] = (0.0, 0.0)  # (等显默认超时, 识别频率上限)
    _日志标签 = ""

    def __bool__(self):
        return self._结果 is not None

    def _获取坐标(self) -> Tuple[int, int]: raise NotImplementedError
    def _目标摘要(self) -> str: raise NotImplementedError
    def _检查存在(self, 帧): raise NotImplementedError
    def _创建新链(self, 结果) -> Self: raise NotImplementedError

    @property
    def 命中坐标(self) -> Optional[Tuple[int, int]]:
        """命中目标坐标：文字链为全屏绝对中心点，图片链为识别所用帧的局部坐标（需自行叠加 区域 偏移）。"""
        return self._获取坐标() if self._结果 else None

    # ---- 原子动作 ----

    def 等显(self, 超时: Optional[float] = None, 识别频率: Optional[float] = None) -> Self:
        """等待目标出现，最长等待 超时。构造期已命中则直接返回，不做重复识别。"""
        if self._结果:
            return self
        默认超时, 上限频率 = self._默认节拍
        超时 = 默认超时 if 超时 is None else 超时
        上限频率 = 上限频率 if 识别频率 is None else 识别频率
        当前频率 = min(0.05, 上限频率)  # 初始极速探测
        结束时间 = time.monotonic() + 超时
        上一帧特征 = None
        while True:
            当前特征, 复用帧 = _帧门控(self.区域)
            画面未变 = 当前特征 is not None and 当前特征 == 上一帧特征
            上一帧特征 = 当前特征
            if not 画面未变:  # 帧差门控廉价，仅在画面变化时才做重度 OCR（全屏帧供绝对点击坐标）
                if 结果 := self._检查存在(复用帧 if 复用帧 is not None else 截图一帧()):
                    新链 = self._创建新链(结果)
                    新链._命中特征 = 当前特征
                    return 新链
            剩余时间 = 结束时间 - time.monotonic()
            if 剩余时间 <= 0:
                return self._创建新链(None)
            等(min(当前频率, 剩余时间))
            当前频率 = min(上限频率, 当前频率 * 1.3)  # 指数退避算法

    def 点(self, 坐标=None, y=None, 抖动: bool = True, 时长: Optional[int] = None) -> Self:
        """点击命中坐标；无坐标时安全跳过。可传入新坐标覆盖默认命中坐标。命中后统一先做点前缓冲再点击，点击后再做点后缓冲。"""
        if not self._结果:
            return self
        等(默认配置.点前等待)  # 点前缓冲：给界面渲染留时间，降低卡顿下点击落空（所有经此方法的点击统一生效）
        if 坐标 is not None:
            点(坐标, y, 时长=时长, 抖动=抖动)
        else:
            点(*self.命中坐标, 时长=时长, 抖动=抖动)
        等(默认配置.点后等待)  # 点后缓冲：给点击响应/界面转场留时间
        self._点击后处理(坐标 is not None)
        return self

    def 滑动(self, x或x1: int, y或y1: int, x2: Optional[int] = None, y2: Optional[int] = None, 时长: int = 默认配置.滑动时长) -> Self:
        """滑动：支持原方法滑动或从命中坐标滑动。"""
        if not self._结果:
            return self
        if x2 is None and y2 is None:
            滑动(*self.命中坐标, x或x1, y或y1, 时长=时长)
        else:
            滑动(x或x1, y或y1, x2, y2, 时长=时长)
        return self

    def 等(self, 秒数: float = 默认配置.等待秒数) -> Self:
        """等待指定秒数，仅在命中时执行。"""
        if self._结果:
            等(秒数)
        return self

    def _点击后处理(self, 自定义坐标: bool):
        """仅点击命中目标时留痕：自定义坐标点击不属识别结果，打印反而误导日志。"""
        if not 自定义坐标:
            print(f"√ {self._日志标签}：{self._目标摘要()}")

    # ---- 消失/落定判据 ----

    def 等消(self, 变化超时: Optional[float] = None) -> 等消结果:
        """等待目标消失。点击后目标消失可能因转场延时而滞后，故在 变化超时 观察窗口内轮询定论：
        帧差只捕捉「画面动过、又刚归于静止」这一瞬间触发一次区域识别（空档静止期与持续抖动期均零 OCR 开销），
        该时刻画面最稳、最宜采样；目标一旦识别不到立即判消失并早停，窗口耗尽仍识别得到才判未消失→交上层重试。
        判据恒为目标识别（有身份维度）：纯像素比对分不清「页面跳转(文字真没了)」与「按钮按压/选中变色(文字仍在)」，会把按压动画误判为消失。"""
        目标 = self if self._结果 else self.等显()
        if not 目标._结果:
            return 等消结果(False)  # 从未命中过，无“消失”可言
        区域 = 目标.区域
        截止 = time.monotonic() + (默认配置.变化超时 if 变化超时 is None else 变化超时)
        上帧, 动过 = _区域特征(区域), False
        while time.monotonic() < 截止:
            等(默认配置.变化探测间隔)
            帧 = _区域特征(区域)
            if 帧 is not None and 帧 != 上帧:
                动过 = True                             # 画面在变（按压/转场启动），暂不采样，等它停下
            elif 动过:                                   # 动过之后归于静止 → 此刻画面最稳，OCR 定论一次
                动过 = False
                if not 目标._检查存在(截图一帧()):
                    return 等消结果(True)                # 目标已消失 → 立即早停，最快返回
            上帧 = 帧
        消失 = not 目标._检查存在(截图一帧())             # 终局补采：防转场末帧恰好未被「归稳沿」捕捉到
        if not 消失:
            print(f"× 未消失：{目标._目标摘要()}")
        return 等消结果(消失)

    # ---- 复合动作 ----

    def 等点(self, 坐标=None, y=None, 超时: Optional[float] = None, 抖动: bool = True, 时长: Optional[int] = None) -> Self:
        """复合动作：等显 -> 点击（点前缓冲已下沉至 点()）。"""
        return self.等显(超时).点(坐标=坐标, y=y, 抖动=抖动, 时长=时长)

    def 点消(self, 坐标=None, y=None, 抖动: bool = True, 变化超时: Optional[float] = None) -> Self:
        """复合动作：点击目标 -> 在观察窗口内等其消失(帧差捕捉「动过又归稳」时 OCR 定论、消失即早停)。未消失则重试点一次；仍未消失则链死亡。返回链对象，支持 if 及链式续接。"""
        if not self._结果:
            return self
        for _ in range(2):  # 首次点击 + 未消失重试点一次
            self.点(坐标=坐标, y=y, 抖动=抖动)  # 点内含点前/点后缓冲，转场时间由 点后等待 统一承担
            if self.等消(变化超时):
                return self  # 已消失，链存活
        self._结果 = None  # 链死亡，后续 if 为 False、链式操作自动跳过
        return self

    def 等点消(self, 坐标=None, y=None, 超时: Optional[float] = None, 抖动: bool = True, 变化超时: Optional[float] = None) -> Self:
        """复合动作：等显 -> 点消。返回链对象，支持 if 及链式续接。"""
        return self.等显(超时).点消(坐标=坐标, y=y, 抖动=抖动, 变化超时=变化超时)

    def 点变(self, 坐标=None, y=None, 抖动: bool = True, 判据区: Optional[Sequence[int]] = None, 变化超时: Optional[float] = None) -> Self:
        """复合动作：点击目标 -> 在 变化超时 窗口内寻找「归稳(连续两帧相同) 且 稳定终态 ≠ 点击前基准」的落定态，
        抓到即判点击生效并早停；窗口耗尽画面始终没能稳定在「异于基准」的终态(按压回弹复原/被吞/未跳转)则重试点一次，仍未落定则链死亡。
        为何是「归稳 且 ≠基准」双条件：游戏点击必带按压动画，画面会「常态→按压→回弹常态」先出现一个 ==基准 的假性静止点，
        若一见归稳就定论会误判未生效、并错过其后的延时跳转；故回弹到基准不算数，须继续观察直到稳定在与基准不同的终态。
        迟迟不归稳(常驻动画/超长转场)时，以「窗口末帧 ≠ 基准」放行——画面结束时仍停在偏离基准处即视为已响应。
        与 点消 同族同守「归稳后定论」：点消 用 OCR 判目标消失(身份判据)，点变 用像素判区域终态迁移(差异判据)。
        判据区 传 [x1,y1,x2,y2]，缺省为命中元素区域（区域小且静态，终态比对最干净）。返回 self，支持 if 判真及链式续接。"""
        if not self._结果:
            return self
        判据区 = self.区域 if 判据区 is None else 判据区  # 默认盯命中元素所在区域：区域小且静态，终态比对最干净
        超时 = 默认配置.变化超时 if 变化超时 is None else 变化超时
        for _ in range(2):  # 首次点击 + 未落定到异态重试点击一次
            基准 = _区域特征(判据区)  # 本次点击前画面特征
            self.点(坐标=坐标, y=y, 抖动=抖动)
            截止 = time.monotonic() + 超时
            上帧 = 基准
            while time.monotonic() < 截止:
                等(默认配置.变化探测间隔)
                帧 = _区域特征(判据区)
                # 归稳且落在「不同于基准」的终态才是真跳转；回弹到基准(帧==基准)不算，继续等后续延时跳转
                if 帧 is not None and 帧 == 上帧 and 帧 != 基准:
                    return self  # 稳定在与基准不同的终态，生效
                上帧 = 帧
            if 上帧 is not None and 上帧 != 基准:
                return self  # 窗口末画面仍偏离基准(转场未静止)→视为已响应
        print(f"× 点击后画面未变化：{self._目标摘要()}")
        self._结果 = None  # 链死亡，后续 if 为 False、链式操作自动跳过
        return self

    def 等点变(self, 坐标=None, y=None, 超时: Optional[float] = None, 抖动: bool = True, 判据区: Optional[Sequence[int]] = None, 变化超时: Optional[float] = None) -> Self:
        """复合动作：等显 -> 点变。返回链对象，支持 if 及链式续接。"""
        return self.等显(超时).点变(坐标=坐标, y=y, 抖动=抖动, 判据区=判据区, 变化超时=变化超时)


class 图片链(_基础查找链):
    """图片查找的链式操作上下文。识别由 找图 完成，本类只承载结果与后续动作。"""
    _默认节拍 = (默认配置.图片等待时间, 默认配置.图片识别频率)
    _日志标签 = "图片点击"

    def __init__(self, 模板, 区域=None, 置信度=默认配置.图像置信度, 缩放范围=默认配置.区域缩放范围, 结果=None, 特征=None):
        self.模板, self.区域, self.置信度, self.缩放范围 = 模板, 区域, 置信度, 缩放范围
        self._结果, self._命中特征 = 结果, 特征

    def _获取坐标(self) -> Tuple[int, int]:
        return self._结果  # 模板匹配 直接返回 (x, y) 元组

    def _目标摘要(self) -> str:
        路径 = str(self.模板)
        return 路径[路径.find("res/"):] if "res/" in 路径 else 路径

    def _检查存在(self, 帧):
        return 模板匹配(self.模板, self.区域, self.置信度, self.缩放范围, 帧)

    def _创建新链(self, 结果) -> "图片链":
        self._结果 = 结果  # 无字符串不变性约束，原地更新结果即可，省去重建实例开销
        return self


class 文字链(_基础查找链, str):
    """文字查找的链式操作上下文（继承自 str，可直接作为字符串使用）。"""
    _默认节拍 = (默认配置.文字等待时间, 默认配置.文字识别频率)
    _日志标签 = "文字点击"

    def __new__(cls, 文本: str, 区域=None, 置信度=默认配置.文字识别阈值, 结果=None, 特征=None):
        实例 = str.__new__(cls, 结果.get("text", "") if 结果 else "")
        实例.文本, 实例.区域, 实例.置信度 = 文本, 区域, 置信度
        实例._结果, 实例._命中特征 = 结果, 特征
        return 实例

    def _获取坐标(self) -> Tuple[int, int]:
        return int(self._结果["center_x"]), int(self._结果["center_y"])

    def _目标摘要(self) -> str:
        return self.文本

    def _检查存在(self, 帧):
        return 查找文字(self.文本, self.区域, self.置信度, 帧)

    def _创建新链(self, 结果) -> "文字链":
        """继承 str，字符串值在 __new__ 时定型，命中新文本必须重建实例。"""
        return 文字链(self.文本, self.区域, self.置信度, 结果)

    def 取数(self) -> Optional[int]:
        """从识别结果中提取纯数字；无结果或无数字返回 None。"""
        if not self._结果:
            return None
        数字 = "".join(filter(str.isdigit, self._结果.get("text", "")))
        return int(数字) if 数字 else None


# ==================== 链式识别入口 ====================

def 找图(模板, 区域=None, 置信度=默认配置.图像置信度, 缩放范围=默认配置.区域缩放范围, 截屏=None) -> 图片链:
    """链式入口：识别一次图片，返回图片链。截屏 需为全屏帧，与 区域 配合按绝对坐标识别。"""
    帧 = 截屏 if 截屏 is not None else 截图一帧()
    结果 = 模板匹配(模板, 区域, 置信度, 缩放范围, 帧)
    return 图片链(模板, 区域, 置信度, 缩放范围, 结果, _初始特征(区域, 结果, 截屏))


def 找字(文本_或_区域="", 区域=None, 置信度=默认配置.文字识别阈值, 截屏=None) -> 文字链:
    """链式入口：识别一次文字，返回文字链。首参也可直接传 区域（此时按全量识别）。截屏 需为全屏帧，与 区域 配合按绝对坐标识别。"""
    实际区域, 实际文本 = (文本_或_区域, "") if isinstance(文本_或_区域, (list, tuple)) else (区域, 文本_或_区域)
    帧 = 截屏 if 截屏 is not None else 截图一帧()
    结果 = 查找文字(实际文本, 实际区域, 置信度, 帧)
    return 文字链(实际文本, 实际区域, 置信度, 结果, _初始特征(实际区域, 结果, 截屏))

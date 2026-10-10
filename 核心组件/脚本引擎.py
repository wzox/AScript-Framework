import traceback
from .系统应用 import (
    退出脚本, 定时执行, 重启脚本, 数据缓存,
    打开应用, 停止应用,
)
from .系统设备 import (
    开启熄屏, 熄屏还原, 保持屏幕常亮, 取消屏幕常亮, 修改分辨率, 获取屏幕信息,
    隐藏悬浮球, 显示悬浮球,
)


class 引擎退出异常(SystemExit):
    """业务层主动触发引擎安全退出"""
    pass

class 引擎重启异常(SystemExit):
    """触发引擎重启（如修改分辨率），保持缓存不清理"""
    pass

def 退出引擎(提示="脚本执行结束"):
    """框架层退出接口，触发引擎统一收尾"""
    raise 引擎退出异常(提示)


class 自动化引擎:
    """自动化脚本生命周期：配置→启动（普通/定时）→异常捕获→统一收尾"""

    def __init__(self, 任务名称="自动化任务"):
        self.任务名称 = 任务名称
        self.任务函数 = None
        self.应用包名 = None
        self.定时执行 = False
        self.执行时间 = (0, 0)
        self.目标分辨率 = None      # 定时任务运行分辨率 (宽, 高, dpi)，未配置则不介入
        self.原始分辨率 = None      # 任务结束后还原的设备原生分辨率 (宽, 高, dpi)
        self.退出恢复悬浮球 = True  # 收尾是否恢复显示悬浮球，默认始终关闭
        self._退出待清理缓存键 = []  # 退出时统一清理的缓存键列表
        self._已熄屏 = False         # 物理熄屏是否已开启，决定收尾时是否还原
        self._已常亮 = False         # 定时环境是否已开启屏幕常亮，决定收尾时是否取消
        # 重启标记缓存键
        self.修改分辨率标记 = f"{任务名称}_因修改分辨率重启"
        self.已修改分辨率标记 = f"{任务名称}_已修改分辨率"
        self.更新重启标记 = f"{任务名称}_因更新重启"

    # ---- 1. 配置接口（链式调用） ----

    def 清除定时缓存(self, 是否清除=False):
        """按需清除已缓存的定时目标时间"""
        if 是否清除:
            数据缓存.清除数据(f"{self.任务名称}_定时目标时间戳")
        return self

    def 配置定时(self, 是否开启, 执行时间=(0, 0)):
        self.定时执行 = 是否开启
        self.执行时间 = 执行时间
        return self

    def 配置应用(self, 应用包名):
        self.应用包名 = 应用包名
        return self

    def 配置分辨率(self, 宽, 高, dpi=None, 原始=None):
        """配置定时任务运行分辨率；原始为任务结束后要还原的设备原生 (宽, 高, dpi)"""
        self.目标分辨率 = (宽, 高, dpi)
        self.原始分辨率 = 原始
        return self

    def 配置悬浮球(self, 退出恢复=False):
        """配置收尾是否恢复显示悬浮球；默认 False 即任务全程隐藏、退出不恢复（始终关）"""
        self.退出恢复悬浮球 = 退出恢复
        return self

    def 挂载任务(self, 任务函数):
        self.任务函数 = 任务函数
        return self

    # ---- 2. 外部启动入口 ----

    def 启动(self):
        """检查重启标记并按配置分发至定时或普通执行路径"""
        if self._从重启标记恢复(self.更新重启标记, "更新"):
            return
        if self._从重启标记恢复(self.修改分辨率标记, "修改分辨率", 强制定时=True):
            return
        if self.定时执行:
            self._定时循环()
        else:
            self._安全执行()

    def _从重启标记恢复(self, 标记: str, 说明: str, 强制定时: bool = False) -> bool:
        """检查重启标记，命中则清除标记并立即执行一轮任务；返回是否命中"""
        if 数据缓存.读取数据(标记) != "1":
            return False
        数据缓存.清除数据(标记)
        print(f"√ [{self.任务名称}] 检测到{说明}重启标记，跳过定时直接执行流程")
        if 强制定时:
            self.定时执行 = True
        if self.定时执行:
            self._退出待清理缓存键.append(f"{self.任务名称}_定时目标时间戳")
        self._定时循环(立即执行=True)
        return True

    def _定时循环(self, 立即执行: bool = False):
        """定时调度主循环：等待到点→执行任务→清理本轮缓存→继续下一轮"""
        while True:
            if 立即执行:
                立即执行 = False
            else:
                缓存键 = 定时执行(self.执行时间, self.任务名称)
                if not 缓存键:
                    continue  # 分段等待触发 reboot，不执行任务
                self._退出待清理缓存键.append(缓存键)
            try:
                self._实际执行入口()
            except 引擎重启异常:
                raise
            except 引擎退出异常 as e:
                self._统一退出(提示=str(e))
                return
            except BaseException as e:
                print(f"× 脚本运行出现异常: {e}\n{traceback.format_exc()}")
                self._统一退出(提示="脚本运行异常")
                return
            # 任务正常完成：清理本轮定时缓存，防止短耗时任务在窗口期内被反复拉起
            for 键名 in self._退出待清理缓存键:
                数据缓存.清除数据(键名)
            self._退出待清理缓存键.clear()

    def _安全执行(self):
        """非定时模式执行入口，捕获异常并统一收尾"""
        退出提示 = "任务执行结束"
        发生异常 = False
        try:
            self._实际执行入口()
        except 引擎退出异常 as e:
            退出提示 = str(e)
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise  # 尊重外部 sys.exit 调用，不走收尾
            print(f"× 脚本运行出现异常: {e}\n{traceback.format_exc()}")
            发生异常 = True
        self._统一退出(提示=退出提示, 清理缓存=not 发生异常)

    # ---- 3. 内部核心逻辑 ----

    def _实际执行入口(self):
        """按模式执行任务：定时模式负责准备/恢复设备环境，普通模式直接执行"""
        if not self.定时执行:
            self._打开应用并执行任务()
            return
        try:
            self._准备定时环境()
            self._打开应用并执行任务()
        except 引擎重启异常:
            raise  # 分辨率已修改即将重启，不恢复环境
        except BaseException:
            self._恢复定时环境()  # 任务异常时也须恢复，再向上传播
            raise
        self._恢复定时环境()

    def _打开应用并执行任务(self):
        """按需切回应用前台后执行业务任务，启动失败则终止任务"""
        if self.应用包名 and not 打开应用(self.应用包名):
            退出引擎("应用启动失败，终止任务")
        隐藏悬浮球()  # 悬浮球会遮挡点击并被截进识别画面，任务执行前隐藏
        if self.任务函数:
            self.任务函数()

    def _准备定时环境(self):
        """定时任务前准备设备环境：分辨率就绪→进入物理熄屏挂机。
        分辨率不匹配时抛重启异常。"""
        print(f"√ [{self.任务名称}] 开始准备定时环境")
        self._检查并设置分辨率()  # 不匹配时抛 引擎重启异常 触发脚本重启
        保持屏幕常亮()  # 防任务期间自动熄屏，收尾时成对取消
        self._已常亮 = True
        self._已熄屏 = 开启熄屏()
        print(f"√ [{self.任务名称}] 已成功准备定时环境")

    def _恢复定时环境(self):
        """按序恢复设备状态：停应用→恢复分辨率→取消屏幕常亮→熄屏还原（单步失败不中断后续）"""
        恢复项目 = [
            (self.应用包名, lambda: 停止应用(self.应用包名)),
            (数据缓存.读取数据(self.已修改分辨率标记) == "1", self._恢复分辨率),
            (self._已常亮, 取消屏幕常亮),
            (self._已熄屏, 熄屏还原),
        ]
        for 需要执行, 操作 in 恢复项目:
            if not 需要执行:
                continue
            try:
                操作()
            except BaseException as e:
                print(f"× 定时环境恢复失败: {e}")
        self._已熄屏 = False
        self._已常亮 = False

    def _恢复分辨率(self):
        """还原设备原生分辨率并清除重启标记"""
        if self.原始分辨率:
            修改分辨率(*self.原始分辨率)
        数据缓存.清除数据(self.修改分辨率标记)
        数据缓存.清除数据(self.已修改分辨率标记)

    # ---- 4. 分辨率管理 ----

    def _检查并设置分辨率(self):
        """检查分辨率是否匹配目标；不匹配则修改并抛 引擎重启异常 触发脚本重启；匹配时正常返回"""
        if not self.目标分辨率:
            return
        目标宽, 目标高, dpi = self.目标分辨率
        显示信息 = 获取屏幕信息()
        if not 显示信息:
            return
        当前宽 = 显示信息.widthPixels
        当前高 = 显示信息.heightPixels
        # 考虑横竖屏，判断当前分辨率是否已匹配目标
        已匹配 = (当前宽 == 目标宽 and 当前高 == 目标高) or \
                 (当前宽 == 目标高 and 当前高 == 目标宽)
        if 已匹配:
            return
        # 根据当前屏幕方向自适应调整目标宽高
        横屏 = 当前宽 > 当前高
        实标宽 = max(目标宽, 目标高) if 横屏 else min(目标宽, 目标高)
        实标高 = min(目标宽, 目标高) if 横屏 else max(目标宽, 目标高)
        print(f"当前屏幕分辨率: {当前宽}x{当前高}，设置分辨率为 {实标宽}x{实标高}")
        修改分辨率(实标宽, 实标高, dpi)
        数据缓存.保存数据(self.已修改分辨率标记, "1")
        数据缓存.保存数据(self.修改分辨率标记, "1")
        重启脚本(延迟毫秒=100)
        raise 引擎重启异常("因修改分辨率触发脚本重启")

    # ---- 5. 统一退出收尾 ----

    def _统一退出(self, 提示="任务执行结束", 清理缓存=True):
        """清理业务侧缓存键，然后退出脚本"""
        print(f"√ [{self.任务名称}] 引擎触发统一退出流程")
        if 清理缓存:
            for 键名 in self._退出待清理缓存键:
                数据缓存.清除数据(键名)
        print("√ 引擎统一退出流程完成")
        if self.退出恢复悬浮球:
            显示悬浮球()  # 按配置恢复悬浮球，便于退出后手动控制 APP
        退出脚本(提示)

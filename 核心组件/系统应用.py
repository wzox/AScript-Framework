"""应用控制、数据缓存、脚本生命周期及定时执行。"""
import datetime
import sys
import time
from typing import Optional, Any


""" 环境与依赖配置 """
平台 = sys.platform
if 平台 == "linux":
    print("√ 已加载 Android 系统操作模块")
    from ascript.android.system import Config, R, KeyValue
    import ascript.android.system as 系统
else:
    print("√ 已加载 iOS 系统操作模块")
    from ascript.ios.system import R
    import ascript.ios.system as 系统

from .配置参数 import 默认配置
from .图文动作 import 等


""" 基础资源与应用控制 """
def 获取资源(路径: str) -> Any:
    return R.img(路径)


def 获取工程名() -> str:
    """获取当前工程（项目）名称；Android 为属性，iOS 为方法"""
    if 平台 == "linux":
        print(f"√ 当前工程名称: {R.name}")
        return R.name
    return R.name()


def _获取当前应用() -> Optional[str]:
    """获取当前正在运行的APP包名，默认获取1分钟内打开的操作"""
    return 系统.get_foreground_app() if 平台 == "linux" else 系统.app_current()


def 打开应用(包名: str, 超时时间: int = 5) -> bool:
    """启动应用并轮询前台校验（0.5秒/次）；单轮超时未入前台则重新拉起，最多共试3次；返回是否成功，失败交由调用方决定收尾方式"""
    for 尝试次数 in range(1, 4):
        try:
            系统.open(包名) if 平台 == "linux" else 系统.app_start(包名)
        except Exception:
            print(f"× 未找到应用 {包名}")
            return False
        开始时间 = time.time()
        while time.time() - 开始时间 < 超时时间:
            前台 = _获取当前应用()
            if 前台 and 包名 in str(前台):
                print(f"√ 启动应用 {包名} 成功")
                return True
            等(0.5)
        if 尝试次数 < 3:
            print(f"！第 {尝试次数} 次启动应用 {包名} 超时未进入前台，重新拉起重试")
    print(f"× 启动应用 {包名} 失败")
    return False


def 停止应用(包名: str) -> None:
    """停止/关闭已打开的应用"""
    系统.shell(f"am force-stop {包名}") if 平台 == "linux" else 系统.app_stop(bundle_id=包名)
    print(f"√ 已停止应用: {包名}")


""" 数据与缓存管理 """
class 数据缓存:
    @staticmethod
    def 保存数据(键: str, 值) -> None:
        KeyValue.save(键, 值)

    @staticmethod
    def 读取数据(键: str, 默认值="") -> str:
        return KeyValue.get(键, 默认值)

    @staticmethod
    def 清除数据(键: str) -> None:
        KeyValue.remove(键)


""" 脚本生命周期控制 """
_脚本开始时间 = time.time()
_已退出标记 = False


def 退出脚本(提示: str = "脚本执行结束") -> None:
    global _已退出标记
    if not _已退出标记:
        总时长 = time.time() - _脚本开始时间
        小时, 余 = divmod(总时长, 3600)
        分钟, 秒 = divmod(余, 60)
        print(f"！结束提示：{提示}")
        print(f"！总运行时长:{int(小时)}小时 {int(分钟)}分钟 {int(秒)}秒")
        _已退出标记 = True
    系统.exit()


def 重启脚本(延迟毫秒: int = 3000) -> None:
    print(f"！脚本将在 {延迟毫秒} 毫秒后重启")
    系统.reboot(int(延迟毫秒))


def _计算最近目标(时间点列表: list, 当前时间: datetime.datetime) -> datetime.datetime:
    """取未来最近的下一个时间点（当天已过则顺延次日）"""
    候选项 = []
    for 时, 分 in 时间点列表:
        目标 = 当前时间.replace(hour=时, minute=分, second=0, microsecond=0)
        if 目标 <= 当前时间:
            目标 += datetime.timedelta(days=1)
        候选项.append(目标)
    return min(候选项)


def _恢复定时目标(缓存键: str, 时间点列表: list, 当前时间: datetime.datetime, 窗口秒: int = 1800) -> datetime.datetime:
    """恢复定时目标：缓存有效则沿用；目标刚过（执行窗口内30分钟）保留补执行；否则重算未来最近点"""
    已缓存 = 数据缓存.读取数据(缓存键)
    if 已缓存:
        try:
            目标时间 = datetime.datetime.fromtimestamp(float(已缓存))
            if 目标时间 > 当前时间 or (当前时间 - 目标时间).total_seconds() <= 窗口秒:
                return 目标时间
        except Exception:
            pass
    目标时间 = _计算最近目标(时间点列表, 当前时间)
    数据缓存.保存数据(缓存键, str(目标时间.timestamp()))
    return 目标时间


def _计算分段秒(剩余秒: int) -> int:
    """分段策略：>4h等4h，>2h等2h，>=30min等30min，<30min直接等到点"""
    if 剩余秒 > 14400:
        return 14400
    if 剩余秒 > 7200:
        return 7200
    if 剩余秒 > 1800:
        return 1800
    return 0


def _格式化时长(秒数: int) -> str:
    """将秒数格式化为 小时/分钟 描述，便于日志阅读"""
    符号 = "-" if 秒数 < 0 else ""
    绝对秒 = abs(int(秒数))
    小时, 余秒 = divmod(绝对秒, 3600)
    分钟 = 余秒 // 60
    描述 = f"{小时}小时" if 小时 else ""
    if 分钟:
        描述 += f"{分钟}分钟"
    return f"{符号}{描述}" if 描述 else f"{符号}{余秒}秒"


def 定时执行(执行时间, 任务标识: str) -> str:
    """定时执行（仅安卓）：设定时间点，到达后返回缓存键交由引擎执行任务。
    稳定性机制：分段 reboot + 本地等满整个分段双兜底 + 30 分钟执行窗口补执行 + 缓存恢复。
    执行时间 支持单个 (时, 分) 或多个 [(时, 分), ...]。
    """
    Config.set_auto_run(True)
    Config.set_stop_re_run(True)
    _底层防休眠加固()
    时间点列表 = [执行时间] if isinstance(执行时间, tuple) else 执行时间
    缓存键 = f"{任务标识}_定时目标时间戳"
    当前时间 = datetime.datetime.now()
    目标时间 = _恢复定时目标(缓存键, 时间点列表, 当前时间)
    剩余秒 = int((目标时间 - 当前时间).total_seconds())
    时分秒 = 目标时间.strftime("%H:%M:%S")
    print(f"√ 定时任务：下次执行 {目标时间.strftime('%Y-%m-%d %H:%M:%S')}，距现在 {_格式化时长(剩余秒)}")
    if _计算分段秒(剩余秒) == 0:
        if 剩余秒 > 0:
            等(剩余秒)
        print(f"√ [{时分秒}] 到达设定时间，准备交由引擎执行任务")
        return 缓存键
    分段秒 = _计算分段秒(剩余秒)
    print(f"！距目标 {_格式化时长(剩余秒)}，分段等待 {_格式化时长(分段秒)}")
    系统.reboot(分段秒 * 1000)
    等(分段秒)
    return ""


def 关闭定时自动重启() -> None:
    """任务完成后关闭异常自动重启，让脚本自然结束"""
    if 平台 == "linux":
        Config.set_stop_re_run(False)
        Config.set_auto_run(False)


def _底层防休眠加固(包名: str = 默认配置.AScript宿主包名) -> None:
    """通过底层Shell命令自动将应用加入系统Doze白名单，并允许后台运行及持有唤醒锁"""
    print(f"！正在执行底层防休眠加固，目标包名：{包名}")
    for 命令 in (
        f"dumpsys deviceidle whitelist +{包名}", f"am set-inactive {包名} false",
        f"cmd appops set {包名} RUN_IN_BACKGROUND allow",
        f"cmd appops set {包名} RUN_ANY_IN_BACKGROUND allow",
        f"cmd appops set {包名} WAKE_LOCK allow",
        f"cmd appops set {包名} START_FOREGROUND allow",
        f"pm grant {包名} android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS",
        "dumpsys deviceidle unforce", "dumpsys battery reset",
    ):
        try:
            系统.shell(命令)  # 仅需发送命令，无需归一化返回值，避免反向依赖系统设备形成循环导入
        except Exception as e:
            print(f"！加固命令失败: {命令} -> {e}")

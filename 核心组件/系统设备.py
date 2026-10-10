"""工具模块 - 统一系统操作及设备反馈 (支持 Android & iOS)"""
import base64
import functools
import sys
import time
from typing import Optional, Any

""" 屏幕状态与硬件模拟 """
平台 = sys.platform
# 平台差异在导入期一次性归一化：下方业务函数不再出现任何 if 平台 分支
if 平台 == "linux":
    from ascript.android import media
    from ascript.android.system import R, Device, Clipboard
    import ascript.android.system as 系统
    from ascript.android.ui import WebWindow, Dialog, FloatWindow
    原生剪贴板 = Clipboard.put
else:
    from ascript.ios import media
    import ascript.ios.system as 系统
    原生剪贴板 = 系统.set_clipboard

from .配置参数 import 默认配置
from .图文动作 import 等


def 仅安卓(默认值: Any = None, 警告: str = ""):
    """平台守卫装饰器：非安卓环境跳过执行并返回默认值，避免每个函数重复写平台判断"""
    def 装饰(函数):
        @functools.wraps(函数)
        def 包装(*位置参数, **关键字参数):
            if 平台 != "linux":
                if 警告:
                    print(警告)
                return 默认值
            return 函数(*位置参数, **关键字参数)
        return 包装
    return 装饰


@仅安卓(False)
def _检查屏幕是否点亮() -> bool:
    """检查屏幕是否处于点亮状态"""
    try:
        结果 = Device.is_screen_on()
        print(f"√ 检查屏幕是否点亮: {结果}")
        return 结果
    except Exception as e:
        print(f"× 检查屏幕是否点亮失败: {e}")
        return False


@仅安卓()
def 按电源键() -> None:
    """模拟按下电源键 (锁屏/亮屏)"""
    系统.shell("input keyevent 26")
    print("√ 按电源键成功")


@仅安卓()
def 唤醒屏幕() -> None:
    """唤醒/点亮设备屏幕"""
    Device.wake_up()
    print("√ 唤醒屏幕成功")


@仅安卓()
def 关闭屏幕() -> None:
    """检查如果屏幕点亮则关闭屏幕 (关屏)"""
    if not _检查屏幕是否点亮():
        return
    try:
        系统.shell("input keyevent 26")
        print("√ 关闭屏幕成功")
    except Exception as e:
        print(f"× 关闭屏幕失败: {e}")


""" 物理熄屏挂机（纯 Shell 命令版，等价 scrcpy -S / Extinguish，无需安装任何 APP）

来源与许可：内嵌 dex 为自研 turnoff 工具，源码见 测试/熄屏资源/Main.java（随插件源码以 MIT 分发）。
原理：反射调用公开 AOSP 接口 SurfaceControl.setDisplayPowerMode 物理断显，仅借鉴 scrcpy(Apache-2.0) 思路，未复制其代码。
分发：预编译 dex 以 base64 内嵌，运行时落地到 /data/local/tmp 执行，免装外部 APP。
权限：需 shell 身份（Shizuku 或 ADB）；无权限时 开启熄屏 返回 False，交由引擎优雅降级。
"""



熄屏Dex路径 = "/data/local/tmp/turnoff.dex"
熄屏Log路径 = "/data/local/tmp/turnoff.log"
熄屏主类 = "com.turnoff.Main"
熄屏DexBase64 = ("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U3VjaE1ldGhvZEV4Y2VwdGlvbjsAEkxqYXZhL2xhbmcvT2JqZWN0OwAcTGphdmEvbGFuZy9SdW50aW1lRXhjZXB0aW9uOwASTGphdmEvbGFuZy9TdHJpbmc7ABlMamF2YS9sYW5nL1N0cmluZ0J1aWxkZXI7ABJMamF2YS9sYW5nL1N5c3RlbTsAFUxqYXZhL2xhbmcvVGhyb3dhYmxlOwAaTGphdmEvbGFuZy9yZWZsZWN0L01ldGhvZDsAC01PREVfTk9STUFMAAhNT0RFX09GRgAJTWFpbi5qYXZhAARUWVBFAAFWAAJWTAABWgACWkwAAltKABJbTGphdmEvbGFuZy9DbGFzczsAE1tMamF2YS9sYW5nL09iamVjdDsAHltMamF2YS9sYW5nL1N0YWNrVHJhY2VFbGVtZW50OwATW0xqYXZhL2xhbmcvU3RyaW5nOwANYWRkU3VwcHJlc3NlZAASYW5kcm9pZC5vcy5JQmluZGVyABthbmRyb2lkLnZpZXcuU3VyZmFjZUNvbnRyb2wABmFwcGVuZAAFY2xvc2UAFWRpc3BsYXkgdG9rZW4gaXMgbnVsbAAGZXF1YWxzAAdmb3JOYW1lABFnZXRCdWlsdEluRGlzcGxheQAJZ2V0TWV0aG9kABVnZXRQaHlzaWNhbERpc3BsYXlJZHMAF2dldFBoeXNpY2FsRGlzcGxheVRva2VuAA1nZXRTdGFja1RyYWNlAAZpbnZva2UABG1haW4AAm9uAANvdXQAB3ByaW50bG4AE3NldERpc3BsYXlQb3dlck1vZGUACHRvU3RyaW5nAA90dXJub2ZmIGVycm9yOiAAEHR1cm5vZmYgb2sgbW9kZT0AB3ZhbHVlT2YABXdyaXRlAGh+fkQ4eyJiYWNrZW5kIjoiZGV4IiwiY29tcGlsYXRpb24tbW9kZSI6InJlbGVhc2UiLCJoYXMtY2hlY2tzdW1zIjpmYWxzZSwibWluLWFwaSI6MjEsInZlcnNpb24iOiI4LjMuMzcifQADAAIAABoBGgEaAIGABPwGAQmUBwIXAQQCAAAOAAAAAAAAAAEAAAAAAAAAAQAAAD8AAABwAAAAAgAAABcAAABsAQAAAwAAAA8AAADIAQAABAAAAAYAAAB8AgAABQAAABYAAACsAgAABgAAAAEAAABcAwAAASAAAAIAAAB8AwAAAyAAAAIAAADKBQAAARAAAAgAAADwBQAAAiAAAD8AAAAuBgAAACAAAAEAAAANCgAABSAAAAEAAAAhCgAAABAAAAEAAAAoCgAA")

def _取文本(结果) -> str:
    """归一化 shell 返回值为文本（兼容 str/列表/带 res 属性的对象，适配 AScript 不同版本返回值）"""
    if 结果 is None:
        return ""
    if isinstance(结果, str):
        return 结果
    内容 = getattr(结果, "res", None)
    if 内容 is None:
        return str(结果)
    if isinstance(内容, list):
        return "\n".join(str(行) for 行 in 内容)
    return str(内容)


def 熄屏Dex就绪() -> bool:
    """检查熄屏 dex 是否已就位（stat 字节数与内嵌 base64 解码后一致，旧版/损坏均判失败重推）"""
    try:
        结果 = 系统.shell(f"stat -c %s {熄屏Dex路径}")
        文本 = _取文本(结果).strip()
        预期大小 = len(base64.b64decode(熄屏DexBase64))
        return 文本.isdigit() and int(文本) == 预期大小
    except Exception:
        return False

def 推送熄屏Dex() -> bool:
    """推送熄屏工具：Python 写 sdcard（普通 APP 权限）→ shizuku cp 到 /data/local/tmp（shell 权限）"""
    原始数据 = base64.b64decode(熄屏DexBase64)
    try:
        from ascript.android.system import R
        临时路径 = R.sd("turnoff.dex")
    except Exception:
        临时路径 = "/sdcard/Download/turnoff.dex"
    try:
        with open(临时路径, "wb") as 文件:
            文件.write(原始数据)
        系统.shell(f"cp {临时路径} {熄屏Dex路径}")
        系统.shell(f"chmod 644 {熄屏Dex路径}")
    except Exception as e:
        print(f"× 推送熄屏工具失败: {e}")
        return False
    return 熄屏Dex就绪()

def 读结果日志() -> str:
    """轮询读取熄屏结果日志（app_process 启动 ART 需一点时间）"""
    for _ in range(10):
        结果 = 系统.shell(f"cat {熄屏Log路径}")
        输出 = _取文本(结果)
        if 输出.strip():
            return 输出.strip()
        time.sleep(0.5)
    return ""

def 执行熄屏指令(恢复: bool = False) -> bool:
    """以 shell 身份运行 app_process 执行物理断显(off) / 恢复显示(on)
    用 env 命令设置 CLASSPATH，规避 shizuku shell 不支持环境变量前缀；
    结果以 dex 写入的 turnoff.log 为准（app_process 的 stdout 可能进 logcat）"""
    参数 = "on" if 恢复 else "off"
    目标 = "turnoff ok mode=" + ("2" if 恢复 else "0")
    命令 = f"env CLASSPATH={熄屏Dex路径} app_process / {熄屏主类} {参数}"
    try:
        系统.shell(f"rm {熄屏Log路径}")
        系统.shell(命令)
        输出 = 读结果日志()
        return 目标 in 输出
    except Exception as e:
        print(f"× 熄屏指令失败: {e}")
        return False

@仅安卓(False)
def 开启熄屏() -> bool:
    """开启物理熄屏挂机：唤醒屏幕 → 确保熄屏工具就绪 → 发送物理断显指令
    熄屏后不锁屏、不加遮罩，画面渲染与图色识别照常运行，期间可正常执行挂机脚本
    注意：必须先唤醒屏幕，否则后续 shell 指令无法生效"""
    唤醒屏幕()
    if not 熄屏Dex就绪() and not 推送熄屏Dex():
        print("× 熄屏工具不可用，请检查 Shizuku 权限")
        return False
    if not 执行熄屏指令(恢复=False):
        return False
    print("√ 已开启熄屏（物理断显）")
    return True


@仅安卓()
def 熄屏还原() -> None:
    """还原物理熄屏挂机：恢复显示 → 按电源键彻底关屏"""
    执行熄屏指令(恢复=True)
    关闭屏幕()
    print("√ 熄屏已还原")


@仅安卓()
def 保持屏幕常亮() -> None:
    """保持屏幕常亮，防止自动熄屏；直到调用 取消屏幕常亮 恢复"""
    Device.keep_screen_on()
    print("√ 已设置屏幕常亮")


@仅安卓()
def 取消屏幕常亮() -> None:
    """取消 保持屏幕常亮 设置的屏幕常亮状态"""
    Device.keep_screen_off()
    print("√ 已取消屏幕常亮")


@仅安卓()
def 按主页键() -> None:
    """模拟按下主页(Home)键"""
    系统.shell("input keyevent 3")
    print("√ 按主页键成功")


@仅安卓()
def 按返回键() -> None:
    """模拟按下返回(Back)键"""
    系统.shell("input keyevent 4")
    print("√ 按返回键成功")


@仅安卓()
def 获取亮度() -> Optional[int]:
    """获取当前屏幕亮度"""
    try:
        结果 = media.get_brightness()
        print(f"√ 当前设备亮度: {结果}")
        return 结果
    except Exception as e:
        print(f"× 获取亮度失败: {e}")
        return None


@仅安卓()
def 设置亮度(亮度值: int) -> None:
    """设置屏幕亮度 (0-255)"""
    try:
        media.brightness(亮度值)
        print(f"√ 设置设备亮度为: {亮度值}")
    except Exception as e:
        print(f"× 设置亮度失败: {e}")


@仅安卓()
def 启动模拟息屏(透明度: float = 0.5) -> Any:
    """启动模拟息屏：显示黑色遮罩，返回 画板对象"""
    画板 = None
    等(1)
    try:
        if 透明度 > 0:
            # 使用 WebWindow 的 dim_amount 机制实现全屏变暗且不拦截点击
            画板 = WebWindow(html="<html></html>")
            画板.background("#00000000")
            画板.dim_amount(透明度)
            画板.drag(False)  # 默认会禁止用户拖动画板窗口
            # 窗口极小，不拦截点击。注意：在某些设备上，1x1 的悬浮窗会被系统判定为异常或恶意行为导致强杀
            画板.size(2, 2)  # 改为 2x2 像素可以绕过这个底层限制，且依然足够小不影响点击。
            画板.show()
            print("√ 启动模拟息屏成功")
    except Exception as e:
        print(f"× 息屏功能初始化失败: {e}")
    return 画板


@仅安卓()
def 取消模拟息屏(画板) -> None:
    """取消模拟息屏：关闭画板"""
    if not 画板:
        return
    try:
        画板.close()
        print("√ 取消模拟息屏成功")
    except Exception:
        pass


""" 系统悬浮球（AScript APP 常驻 overlay，会遮挡点击并被截进识别画面） """


@仅安卓()
def 隐藏悬浮球() -> None:
    """隐藏 AScript 系统悬浮球，避免其遮挡界面点击或被截进图色识别画面"""
    FloatWindow.hide()
    print("√ 已隐藏悬浮球")


@仅安卓()
def 显示悬浮球() -> None:
    """恢复显示 AScript 系统悬浮球"""
    FloatWindow.show()
    print("√ 已显示悬浮球")


def 获取音量(类型: int = 3) -> int:
    """获取音量百分比 (0-100)，类型：3=媒体, 5=通知, 4=警告, 2=铃声, 1=系统, 0=通话"""
    结果 = media.get_volume(类型)
    print(f"√ 当前音量类型[{类型}]: {结果}%")
    return 结果


def 设置音量(百分比: int, 类型: int = 3) -> None:
    """调节音量 (1-100)，类型：3=媒体, 5=通知, 4=警告, 2=铃声, 1=系统, 0=通话"""
    media.volume(百分比, 类型)
    print(f"√ 已设置音量类型[{类型}]为: {百分比}%")


@仅安卓(警告="！警告: 未检测到运行环境，无法执行Shell")
def 执行Shell(命令: str) -> Optional[str]:
    """执行 Shell 命令并归一化返回文本"""
    结果 = 系统.shell(命令)
    if isinstance(结果, str):
        return 结果
    if not 结果:
        return None
    内容 = getattr(结果, "res", None)
    return "\n".join(str(行) for 行 in 内容) if isinstance(内容, list) else str(内容)


def 剪切板写入文本(文本: str) -> None:
    """将文本写入系统剪贴板，作为无输入法环境的文字输入原语。"""
    try:
        原生剪贴板(文本)
    except Exception as e:
        print(f"× 剪贴板写入失败: {e}")


""" 分辨率与底层系统交互 """


@仅安卓()
def 获取屏幕信息() -> Any:
    """获取手机设备的屏幕分辨率与屏幕密度
    返回对象包含: widthPixels(宽), heightPixels(高), density(密度), rotation(旋转角度)
    """
    return Device.display()


@仅安卓(警告="！警告: 非安卓环境，跳过修改分辨率")
def 修改分辨率(宽: int, 高: int, dpi: int = None) -> None:
    """修改设备分辨率和DPI"""
    print(f"修改设备分辨率为 {宽}x{高}" + (f", DPI {dpi}" if dpi else ""))
    执行Shell(f"wm size {宽}x{高}")
    if dpi:
        执行Shell(f"wm density {dpi}")
    等(2)


""" 设备反馈 """


@仅安卓()
def _设备发声(消息: str, 次数: int) -> None:
    """调用系统 TTS 发声；模拟器常缺 TTS 引擎，失败即终止本轮"""
    for _ in range(次数):
        try:
            media.talk(消息)
        except Exception as e:
            print(f"× 播报语音失败（模拟器可能未安装TTS引擎）：{e}")
            break


def 播报语音(消息: str = 默认配置.设备播报默认消息, 次数: int = 默认配置.设备播报默认次数, 声音开关: bool = False) -> None:
    """打印播报文案；声音开关开启且处于安卓环境时同时发声"""
    print(f"！语音播报：{消息}")
    if 声音开关:
        _设备发声(消息, 次数)


""" 弹窗对话（Android 用原生 Dialog；iOS 用系统通知横幅） """
_弹窗不支持 = "！警告: 弹窗功能暂不支持当前平台，已跳过"


@仅安卓(警告=_弹窗不支持)
def 弹出吐司(消息: str, 时长毫秒: int = 3000, 引力: int = 1 | 16, x: float = 0, y: float = 0.2, 背景色: str = None, 字体色: str = None, 字体大小: int = 0) -> None:
    """展示一条可自动消失的吐司提示，默认停留3秒偏屏幕中心下方"""
    Dialog.toast(消息, 时长毫秒, 引力, x, y, 背景色, 字体色, 字体大小)
    print(f"！弹出吐司：{消息}")


def 弹出提示(消息: str, 确认文本: str = "确认") -> None:
    """弹出一个提示框：Android 原生确认框，iOS 以系统通知横幅呈现，确认后继续"""
    Dialog.alert(消息, 确认文本) if 平台 == "linux" else 系统.notify(消息, 确认文本)
    print(f"！弹出提示：{消息}")


@仅安卓(False, _弹窗不支持)
def 弹窗确认(消息: str, 标题: str = None, 确认文本: str = "确认", 取消文本: str = "取消") -> bool:
    """弹出一个带确认/取消按钮的选择框，返回用户是否点击确认"""
    结果 = Dialog.confirm(消息, 标题, 确认文本, 取消文本)
    print(f"！弹出确认框：{消息}，用户点击确认：{结果}")
    return 结果
    

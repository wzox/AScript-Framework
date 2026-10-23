'''通用打包脚本，用于合并代码并打包为 .as 或 .ias 文件'''

import sys
import os
import zipfile
import argparse
from pathlib import Path

# 直接运行本文件（而非作为包导入）时，把项目根目录加入 sys.path，使绝对导入 ascript_framework 生效
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from ascript_framework.打包发布.合并代码 import 合并代码

def 打包代码(入口文件名: str, 产出文件名: str = "__init__.py", 打包为iOS: bool=False, 混淆代码: bool=False, 是否移除注释: bool=True, 仅合并代码: bool=False):
    '''
    通用打包脚本，用于合并代码并打包为 .as 或 .ias 文件。

    :param 入口文件名: 入口 Python 文件的名称 (例如 "main.py")
    :param 产出文件名: 合并产物文件名 (默认 "__init__.py"；多入口批量出码时各自指定，避免互相覆盖)
    :param 打包为iOS: 是否默认为 iOS 打包
    :param 混淆代码: 是否启用混淆压缩（中文标识符→短名、删注释、压空白）
    :param 是否移除注释: 是否移除源码中的注释（默认 True 移除）
    '''
    # 添加项目根目录到 sys.path（加上当前至根目录3级）
    项目根目录 = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(项目根目录))

    当前文件夹 = Path(sys.argv[0]).parent # 获取主脚本的目录

    入口文件 = 当前文件夹 / 入口文件名
    输出文件 = 当前文件夹 / 产出文件名

    合并代码(
        入口路径=str(入口文件),
        输出路径=str(输出文件),
        是否移除注释=是否移除注释,
        项目根目录=str(项目根目录),
    )

    if 仅合并代码:
        print("仅合并代码模式完成")
        return

    if 混淆代码:
        import re, ascript_framework.打包发布.混淆压缩
        混淆 = ascript_framework.打包发布.混淆压缩.混淆
        merged = 输出文件.read_text(encoding="utf-8")
        merged = re.sub(r'__all__\s*=.*?\]', '', merged, count=1, flags=re.DOTALL)
        混淆后 = 混淆(merged)
        输出文件.write_text(混淆后, encoding="utf-8")
        print(f"混淆完成: 输出文件已压缩")

    # --- 新增打包为 .as 或 .ias 文件的逻辑 ---
    # 使用 argparse 解析命令行参数
    参数解析器 = argparse.ArgumentParser(description=f"{当前文件夹.name}打包脚本")
    参数解析器.add_argument("--ios", action="store_true", default=打包为iOS, help="是否打包为 iOS 版本 (.ias)")
    参数, _ = 参数解析器.parse_known_args()

    是否为iOS = 参数.ios
    扩展名 = ".ias" if 是否为iOS else ".as"

    输出文件路径 = 输出文件
    图片目录 = 当前文件夹 / "res" / "img"
    打包文件路径 = 当前文件夹 / f"{Path(入口文件名).stem}{扩展名}"

    # 清理旧文件
    if 打包文件路径.exists():
        打包文件路径.unlink()

    print(f"正在创建压缩包 ({扩展名} 格式)")
    # 注意：AScript 的 .as/.ias 文件本质上是 zip 格式，这里使用 Python 内置的 zipfile 库进行兼容打包
    with zipfile.ZipFile(打包文件路径, 'w', zipfile.ZIP_DEFLATED) as 压缩包:
        # 1. 添加合并产物到压缩包根目录（设备端契约固定为 __init__.py）
        if 输出文件路径.exists():
            压缩包.write(输出文件路径, arcname="__init__.py")
            print(f"已添加: {输出文件路径.name} → __init__.py")
        else:
            print(f"警告: 未找到输出文件 {输出文件路径}")
        
        # 2. 添加 res/img 及其内部所有文件
        if 图片目录.exists():
            目录计数: dict[str, int] = {}
            for 根目录, 子目录列表, 文件列表 in os.walk(图片目录):
                for 文件名 in 文件列表:
                    文件路径 = Path(根目录) / 文件名
                    压缩包内路径 = 文件路径.relative_to(当前文件夹)
                    压缩包.write(文件路径, arcname=压缩包内路径)
                    目录名 = str(压缩包内路径.parent)
                    目录计数[目录名] = 目录计数.get(目录名, 0) + 1
            for 目录名, 计数 in sorted(目录计数.items()):
                print(f"已添加: {目录名} 共 {计数} 个文件")
        else:
            print(f"警告: 未找到图片目录 {图片目录}")

    from datetime import datetime
    print(f"打包完成！已生成: {打包文件路径.name}  ({datetime.now().strftime('%H:%M:%S')})")


def _解析插件元数据(源文件: Path) -> dict:
    """从工具封装源码 AST 解析 插件名/插件版本 等模块级字符串常量（不导入框架，避免依赖设备端 ascript）。"""
    import ast
    元数据 = {}
    for 节点 in ast.parse(源文件.read_text("utf-8-sig")).body:
        if isinstance(节点, ast.Assign):
            for 目标 in 节点.targets:
                if isinstance(目标, ast.Name) and 目标.id.startswith("插件"):
                    if isinstance(节点.value, ast.Constant) and isinstance(节点.value.value, str):
                        元数据[目标.id] = 节点.value.value
    return 元数据


def 打包插件(插件入口名: str = "工具封装.py", 是否移除注释: bool = False, 混淆代码: bool = False):
    """将 ascript_framework 合并为单一可导入模块并打包为插件归档（.asplug），供 plug.load 加载。

    产物：ascript_framework/发布产物/__init__.py（合并完整模块） 与 ascript_framework/发布产物/插件名.asplug。
    他人加载：plug.load("插件名:版本") 后 from 插件名 import *。
    仅做 AST 文本合并，本地不执行、不导入设备端 ascript。
    """
    项目根目录 = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(项目根目录))
    框架目录 = 项目根目录 / "ascript_framework"
    入口文件 = 框架目录 / 插件入口名

    元数据 = _解析插件元数据(入口文件)
    插件名 = 元数据.get("插件名", 框架目录.name)
    插件版本 = 元数据.get("插件版本", "")

    # 1. 合并框架为单一模块（直接输出到 发布产物/__init__.py）
    发布目录 = 框架目录 / "发布产物"
    发布目录.mkdir(parents=True, exist_ok=True)
    输出文件 = 发布目录 / "__init__.py"
    合并代码(
        入口路径=str(入口文件),
        输出路径=str(输出文件),
        头部注释=f"# 插件：{插件名} v{插件版本}｜作者：{元数据.get('插件作者', '')}",
        是否移除注释=是否移除注释,
        项目根目录=str(项目根目录),
    )

    # 2. 可选混淆：去除 __all__ 后压缩
    if 混淆代码:
        import re
        from ascript_framework.打包发布.混淆压缩 import 混淆
        合并文本 = 输出文件.read_text(encoding="utf-8")
        合并文本 = re.sub(r'__all__\s*=.*?\]', '', 合并文本, count=1, flags=re.DOTALL)
        输出文件.write_text(混淆(合并文本), encoding="utf-8")
        print("√ 插件模块已混淆压缩")

    # 3. 打包为插件归档（.asplug 本质为 zip，含合并后的 __init__.py）
    归档路径 = 框架目录 / "发布产物" / f"{插件名}.asplug"
    if 归档路径.exists():
        归档路径.unlink()
    with zipfile.ZipFile(归档路径, "w", zipfile.ZIP_DEFLATED) as 压缩包:
        压缩包.write(输出文件, arcname="__init__.py")
    print(f"√ 插件打包完成：{归档路径}（版本 {插件版本}）")
    return 归档路径


# 直接运行本脚本即打包插件（产出 发布产物/插件名.asplug）；被其它模块导入时不触发
if sys.argv and Path(sys.argv[0]).name == "打包程序.py":
    打包插件()


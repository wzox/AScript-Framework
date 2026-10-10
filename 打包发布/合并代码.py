"""merge_ascript.py - 将 AScript 项目合并为单个 .py 文件

用法:
    python 合并代码.py 梦域巡航/游戏准备/_1_助战流程.py -o __init__.py
    python 合并代码.py 梦域巡航/游戏准备/_1_助战流程.py -o __init__.py --root d:/Me/Code/AScirpt
    python 合并代码.py 梦域巡航/游戏准备/_1_助战流程.py -o __init__.py --no-strip-comments

原理:
    1. AST 扫描入口文件，找到所有项目内部导入
    2. 通过项目根目录解析绝对导入对应的文件路径
    3. 递归解析依赖文件，构建有向无环图
    4. 拓扑排序确定拼接顺序
    5. 按序读取每个文件，删除包内导入行
    6. 外部导入（stdlib / 第三方）保留并去重
"""

import ast, sys, argparse
from pathlib import Path
from datetime import datetime
from collections import OrderedDict

def 获取待移除行号(源码: str) -> set[int]:
    """通过 AST 找出所有文档字符串和独立字符串表达式的行号。"""
    try: 语法树 = ast.parse(源码)
    except SyntaxError: return set()
    return {行号 for 节点 in ast.walk(语法树) if isinstance(节点, ast.Expr) and isinstance(节点.value, ast.Constant) and isinstance(节点.value.value, str) for 行号 in range(节点.lineno, 节点.end_lineno + 1)}

def 移除注释(源码: str) -> str:
    """去除 Python 源码中的 # 注释、文档字符串和独立分隔符字符串。"""
    待移除行 = 获取待移除行号(源码)
    行列表, 最终结果 = 源码.split("\n"), []
    
    for 索引, 行 in enumerate(行列表, 1):
        if 索引 in 待移除行 or (去除空白 := 行.strip()).startswith("#"): continue
        if "#" in 行:
            在字符串中, 引号, 字符索引 = False, None, 0
            while 字符索引 < len(行):
                字符 = 行[字符索引]
                if 在字符串中:
                    if 字符 == "\\": 字符索引 += 1
                    elif 字符 == 引号: 在字符串中 = False
                elif 字符 in "\"'":
                    引号 = 行[字符索引:字符索引+3] if 行[字符索引:字符索引+3] in ('"""', "'''") else 字符
                    在字符串中, 字符索引 = True, 字符索引 + len(引号) - 1
                elif 字符 == "#":
                    行 = 行[:字符索引].rstrip()
                    break
                字符索引 += 1
        if 行.strip() or (最终结果 and 最终结果[-1].strip()): 最终结果.append(行)
    
    while 最终结果 and not 最终结果[-1]: 最终结果.pop()
    结果 = []
    for 索引, 行 in enumerate(最终结果):
        if not 行.strip() and 索引 > 0 and 结果[-1].strip().startswith(("def ", "class ", "async def ")): continue
        结果.append(行)
    return "\n".join(结果)

def 构建模块索引(根目录: Path) -> dict[str, Path]:
    """构建项目模块索引：模块名 → 文件路径。"""
    索引字典 = {}
    排除目录 = {".venv", "venv", "env", ".git", "__pycache__", "node_modules"}
    for 路径 in 根目录.rglob("*.*"):
        if 路径.suffix not in (".py", ".pyi") or 路径.name == "__init__.py": continue
        if 排除目录 & set(路径.parts): continue
        模块名 = ".".join(路径.relative_to(根目录).with_suffix("").parts)
        if 模块名 not in 索引字典 or 路径.suffix == ".py": 索引字典[模块名] = 路径
    return 索引字典

def 解析模块路径(模块名: str, 根目录: Path, 索引字典: dict, 当前文件: Path = None) -> Path:
    """将模块名解析为文件路径（在整个项目中查找）。"""
    if not 模块名: return None
    if 模块名 in 索引字典: return 索引字典[模块名]
    
    部分 = 模块名.split(".")
    for 目录 in filter(None, [当前文件.parent if 当前文件 else None, 根目录]):
        for 索引, 节点 in enumerate(部分):
            if 索引 == len(部分) - 1:
                for 文件 in (目录/f"{节点}.py", 目录/f"{节点}.pyi", 目录/节点/"__init__.py"):
                    if 文件.exists(): return 文件
            目录 = 目录 / 节点
            if not 目录.is_dir(): break

    匹配项 = [路径 for 名, 路径 in 索引字典.items() if 名 == 模块名 or 名.split(".")[-len(部分):] == 部分]
    return 匹配项[0] if 匹配项 else None

def 检测项目根目录(入口文件: Path) -> Path:
    """自动检测项目根目录：入口文件向上找含 >= 2 个 Python 子项的最高目录。"""
    当前 = 最佳 = 入口文件.parent.resolve()
    while 当前.parent != 当前:
        try:
            if sum(1 for 目录 in 当前.iterdir() if 目录.name == "__pycache__" or (目录.is_dir() and (目录/"__init__.py").exists()) or 目录.suffix in (".py", ".pyi")) >= 2:
                最佳 = 当前
        except (OSError, PermissionError): pass
        当前 = 当前.parent
    return 最佳

def 遍历项目导入(文件路径: Path, 根目录: Path, 索引字典: dict, 源码: str = None) -> list[dict]:
    """解析项目内部导入（相对 + 指向项目内模块的绝对），返回列表。"""
    try: 语法树 = ast.parse(源码 or 文件路径.read_text("utf-8-sig"))
    except Exception: return []
    
    结果 = []
    for 节点 in ast.walk(语法树):
        if not isinstance(节点, ast.ImportFrom): continue
        if 节点.level > 0:
            if not 节点.module: continue
            目录 = 文件路径.parent
            for _ in range(节点.level - 1): 目录 = 目录.parent
            for 节点名 in 节点.module.split("."): 目录 = 目录 / 节点名
            for 文件 in (目录.with_suffix(".py"), 目录.with_suffix(".pyi"), 目录/"__init__.py"):
                if 文件.exists():
                    结果.append({"节点": 节点, "解析路径": 文件.resolve(), "层级": 节点.level, "目标包": 节点.module})
                    break
        elif 节点.module:
            if 文件 := 解析模块路径(节点.module, 根目录, 索引字典, 文件路径):
                结果.append({"节点": 节点, "解析路径": 文件.resolve(), "层级": 0, "目标包": 节点.module})
    return 结果

def 提取外部导入(节点, 索引字典, 外部导入字典):
    """辅助函数：提取外部导入"""
    if isinstance(节点, ast.Import):
        for 别名 in 节点.names:
            外部导入字典[f"import {别名.name}" + (f" as {别名.asname}" if 别名.asname else "")] = 节点.lineno
    elif isinstance(节点, ast.ImportFrom) and 节点.level == 0:
        模块 = 节点.module or ""
        if 模块 not in 索引字典 and not any(名.split(".")[-len(模块.split(".")):] == 模块.split(".") for 名 in 索引字典):
            for 别名 in 节点.names:
                外部导入字典[f"from {模块} import {别名.name}" + (f" as {别名.asname}" if 别名.asname else "")] = 节点.lineno

def 处理单文件依赖(文件路径: Path, 根目录: Path, 索引字典: dict, 是否移除注释: bool, 已访问: set, 排序字典: OrderedDict, 外部导入字典: OrderedDict):
    绝对路径 = str(文件路径.resolve())
    if 绝对路径 in 已访问: return
    已访问.add(绝对路径)

    源码 = 文件路径.read_text("utf-8-sig")
    内部导入 = 遍历项目导入(文件路径, 根目录, 索引字典, 源码)
    for 导入 in 内部导入: 处理单文件依赖(导入["解析路径"], 根目录, 索引字典, 是否移除注释, 已访问, 排序字典, 外部导入字典)

    if 是否移除注释: 源码 = 移除注释(源码)
    行列表 = 源码.split("\n")

    待移除行, 在移除块中 = set(), False
    for 索引, 行 in enumerate(行列表):
        清理行 = 行.strip()
        if "_ROOT = os.path.dirname" in 清理行: 在移除块中 = True; 待移除行.add(索引); continue
        if 在移除块中:
            if not 清理行 or 清理行.startswith(("if _ROOT", "sys.path.insert", "#")): 待移除行.add(索引)
            else: 在移除块中 = False

    try: 语法树 = ast.parse(源码)
    except SyntaxError: 语法树 = None

    if 语法树:
        内部节点集 = {(导入["节点"].lineno, 导入["节点"].col_offset) for 导入 in 内部导入}
        顶层节点集 = set(语法树.body)

        for 节点 in ast.walk(语法树):
            if isinstance(节点, (ast.Import, ast.ImportFrom)):
                是内部导入 = (节点.lineno, 节点.col_offset) in 内部节点集
                是顶层导入 = 节点 in 顶层节点集

                if 是内部导入 or 是顶层导入:
                    待移除行.update(range(节点.lineno - 1, 节点.end_lineno))

                if not 是内部导入 and 是顶层导入:
                    提取外部导入(节点, 索引字典, 外部导入字典)

    输出行 = [行 for 索引, 行 in enumerate(行列表) if 索引 not in 待移除行]
    结果, 上行为空 = [], False
    for 行 in 输出行:
        if not 行.strip():
            if not 上行为空 and 结果: 结果.append(""); 上行为空 = True
        else: 结果.append(行); 上行为空 = False
    while 结果 and not 结果[-1]: 结果.pop()
    
    if (最终源码 := "\n".join(结果).strip()): 排序字典[绝对路径] = 最终源码

def 构建依赖图(入口文件: Path, 根目录: Path, 索引字典: dict, 是否移除注释: bool = True):
    """递归构建依赖图。"""
    已访问, 排序字典, 外部导入字典 = set(), OrderedDict(), OrderedDict()
    处理单文件依赖(入口文件, 根目录, 索引字典, 是否移除注释, 已访问, 排序字典, 外部导入字典)
    return 排序字典, 外部导入字典

def 合并代码(入口路径: str, 输出路径: str, 头部注释: str = "", 是否移除注释: bool = True, 项目根目录: str = ""):
    入口 = Path(入口路径).resolve()
    if not 入口.exists(): return print(f"入口文件不存在: {入口}") or sys.exit(1)

    输出 = Path(输出路径)
    if 输出.parent == Path("."): 输出 = 入口.parent / 输出.name
    
    根目录 = Path(项目根目录).resolve() if 项目根目录 else 检测项目根目录(入口)
    print(f"项目根目录: {根目录}")

    索引字典 = 构建模块索引(根目录)
    print(f"模块索引: {len(索引字典)} 个文件")

    排序字典, 外部导入字典 = 构建依赖图(入口, 根目录, 索引字典, 是否移除注释)
    if not 排序字典: return print("未找到任何可合并的文件。") or sys.exit(1)

    行列表 = [头部注释] if 头部注释 else []
    行列表.insert(0, f"# 打包时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if 外部导入字典:
        第三方库 = {"ascript", "cv2", "numpy", "PIL", "requests", "pandas", "openpyxl", "schedule", "websocket", "pymysql"}
        标准库列表, 第三方库列表 = [], []
        for 导入 in 外部导入字典:
            (第三方库列表 if 导入.split()[1].split(".")[0] in 第三方库 else 标准库列表).append(导入)
        
        if 标准库列表: 行列表.extend(["# ─── 项目公共导入汇总 ───"] + sorted(标准库列表))
        if 第三方库列表: 行列表.extend(([""] if 标准库列表 else ["# ─── 项目公共导入汇总 ───"]) + sorted(第三方库列表))
        行列表.extend(["", ""])

    for 路径, 源码 in 排序字典.items():
        文件路径 = Path(路径)
        if 文件路径.name == "__init__.py":
            行列表.append(f"# ─── 入口模块: {文件路径.parent.name}/__init__.py ───")
        else:
            try: 标签 = 文件路径.relative_to(根目录).as_posix()
            except ValueError: 标签 = 文件路径.name
            行列表.append(f"# ─── 模块文件: {标签} ───")
        行列表.extend([源码, ""])

    输出.write_text("\n".join(行列表).rstrip() + "\n", encoding="utf-8")
    print(f"合并完成 → {输出}\n  {len(排序字典)} 个文件已合并\n  {len(外部导入字典)} 个外部导入已去重")

def 主函数():
    解析器 = argparse.ArgumentParser(description="合并 AScript 项目为单个 .py 文件")
    解析器.add_argument("entry", nargs="?", default="梦域巡航/游戏准备/_1_助战流程.py", help="入口文件，如 梦域巡航/__init__.py")
    解析器.add_argument("-o", "--output", default="__init__.py", help="输出文件路径（仅文件名时输出到入口同级目录）")
    解析器.add_argument("--header", default="", help="输出文件头部注释")
    解析器.add_argument("--no-strip-comments", action="store_true", help="保留 # 注释（默认去除）")
    解析器.add_argument("--root", default="", help="项目根目录（用于解析指向项目内模块的绝对导入），默认自动检测")
    参数 = 解析器.parse_args()
    合并代码(参数.entry, 参数.output, 参数.header, not 参数.no_strip_comments, 参数.root)

if sys.argv and Path(sys.argv[0]).name == "合并代码.py":
    主函数()

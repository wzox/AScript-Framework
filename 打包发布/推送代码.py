"""将本地合并产物一键推送到 AScript 网页编辑器的指定工程。

作为工具被各项目的 打包.py 调用：打包合并后按需覆盖编辑器工程的入口 __init__.py。
保存沿用网页编辑器 ctrl+s 的原生协议（POST /api/file/save: path + content），与手动保存完全等价。
纯本地运行，仅走 HTTP，不触碰设备端 ascript。
"""
import json
import urllib.request, urllib.parse
from pathlib import Path

默认服务地址 = "http://192.168.1.154:9096"


def _请求(地址: str, 数据: bytes = None) -> dict:
    with urllib.request.urlopen(urllib.request.Request(地址, data=数据), timeout=15) as 响应:
        return json.loads(响应.read().decode("utf-8"))


def _取入口路径(服务地址: str, 工程名: str) -> str:
    """向 /api/model/get 查该工程 __init__.py 在设备上的绝对路径（不写死，存储位置变更自适应）。"""
    编码名 = urllib.parse.quote(工程名)
    响应 = _请求(f"{服务地址}/api/model/get?name={编码名}")
    for 子 in 响应["data"]["childs"]:
        if 子.get("name") == "__init__.py":
            return 子["path"]
    raise RuntimeError(f"工程「{工程名}」未找到 __init__.py")


def 推送代码(源文件: Path, 目标工程: list[str], 服务地址: str = 默认服务地址) -> None:
    """把 源文件 内容覆盖推送到每个 目标工程 的入口 __init__.py；目标工程为空则跳过。"""
    if not 目标工程:
        return
    内容 = Path(源文件).read_text(encoding="utf-8")
    字符数 = len(内容)
    print(f"推送源：{源文件}（{字符数} 字符）")
    for 工程名 in 目标工程:
        路径 = _取入口路径(服务地址, 工程名)
        表单 = urllib.parse.urlencode({"path": 路径, "content": 内容}).encode()
        响应 = _请求(f"{服务地址}/api/file/save", 表单)
        if 响应.get("code") != 1:
            错误 = 响应.get("msg")
            raise RuntimeError(f"「{工程名}」保存失败：{错误}")
        print(f"√ 已推送 → {工程名}  ({路径})")

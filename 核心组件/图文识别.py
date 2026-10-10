"""图文识别模块 - 统一图像工具与 OCR (支持 Android & iOS)"""
import sys
from typing import List, Optional

from .配置参数 import 默认配置

平台 = sys.platform

# 平台差异在导入期一次性归一化：下方业务函数不再出现任何 if 平台 分支
if 平台 == "linux":
    print("√ 已加载 Android 图像操作模块")
    from ascript.android.screen import Ocr, FindImages, capture, CompareColors, bitmap_crop, bitmap_to_cvimage

    原生裁剪 = bitmap_crop

    def 原生截图(区域):
        return capture(*区域) if 区域 else capture()

    def 取图字节(截屏):
        return bitmap_to_cvimage(截屏).tobytes()
else:
    print("√ 已加载 iOS 图像操作模块")
    from ascript.ios.screen import Ocr, FindImages, capture, CompareColors, image_crop

    原生裁剪 = image_crop

    def 原生截图(区域):
        return capture(区域) if 区域 else capture()

    def 取图字节(截屏):
        return 截屏.tobytes()

Ocr.set_engine("paddle")


def 截图一帧(区域: Optional[List[int]] = None):
    """获取屏幕截图。可传入区域 [x1, y1, x2, y2] 进行局部截取以提升性能，无效区域静默降级为全屏。"""
    return 原生截图(区域 if 区域 and len(区域) == 4 else None)


def 裁剪图片(截屏, 区域: List[int]):
    """对已截取的图片进行局部裁剪，复用截图以提升性能。区域: [x1, y1, x2, y2]"""
    if not 截屏 or not 区域 or len(区域) != 4:
        return 截屏
    try:
        return 原生裁剪(截屏, 区域)
    except Exception:
        return 截屏  # 裁剪失败时原样返回，交由调用方重新截图


def 计算截图特征(截屏) -> Optional[int]:
    """计算图像字节哈希，极速判断画面变化。"""
    if not 截屏:
        return None
    try:
        return hash(取图字节(截屏))
    except Exception:
        return None


# --- 图文基础API封装 ---
def 比色(颜色特征: str, 相似度: float = 0.9, 截屏=None, 模式: int = 0, 超时毫秒: int = 0, 整体相似度: float = 1.0) -> bool:
    """多点比色，返回是否匹配成功。颜色特征写法"733,792,#493718|730,1148,#7B5E2C"是并且的关系"""
    return CompareColors.compare(颜色特征, diff=相似度, bitmap=截屏, mode=模式, until=超时毫秒, sim=整体相似度)


def 比色多组(颜色列表: list, 相似度: float = 0.9, 模式: int = 0, 整体相似度: float = 1.0) -> int:
    """多组比色，返回匹配的组索引（0-based），全部不匹配返回 -1。"""
    return CompareColors.compare_multi(颜色列表, diff=相似度, mode=模式, sim=整体相似度)


def 查找文字(文本: str = "", 区域: Optional[List[int]] = None, 置信度: float = 默认配置.文字识别阈值, 截屏=None):
    """单次OCR识别，返回结果字典或 None"""
    return Ocr.find(text=文本, rect=区域, confidence=置信度, image=截屏)


def 查找所有文字(区域: Optional[List[int]] = None, 置信度: float = 默认配置.文字识别阈值, 截屏=None) -> List[dict]:
    """全量OCR识别，返回包含多个文字字典结果的列表"""
    return Ocr.find_all(text=None, rect=区域, confidence=置信度, image=截屏) or []


def 模板匹配(模板, 区域: Optional[List[int]] = None, 置信度: float = 默认配置.图像置信度, 缩放范围: List[float] = 默认配置.区域缩放范围, 截屏=None):
    """单次模板匹配，返回 (x, y) 或 None"""
    命中 = FindImages.find_template(part_img=模板, confidence=置信度, rect=区域, scale_range=缩放范围, image=截屏)
    return tuple(命中.get("result", (0, 0))) if 命中 else None


def 识别图片多模板单结果(模板列表: List[dict], 区域: Optional[List[int]] = None, 置信度: float = 默认配置.图像置信度, 缩放范围: List[float] = 默认配置.区域缩放范围, 彩色: bool = True, 截屏=None) -> Optional[str]:
    """区域图像识别：一次性匹配所有模版。返回匹配的 名称 或 None。"""
    匹配结果 = FindImages.find_template([项["路径"] for 项 in 模板列表], rect=区域, confidence=置信度, rgb=彩色, scale_range=缩放范围, image=截屏)
    return 模板列表[匹配结果["index"]]["名称"] if 匹配结果 else None


def 识别图片多模板多结果(模板列表: List[dict], 区域: Optional[List[int]] = None, 置信度: float = 默认配置.图像置信度, 缩放范围: List[float] = 默认配置.区域缩放范围, 彩色: bool = True, 截屏=None) -> List[dict]:
    """查找所有匹配的模板：返回所有匹配结果列表，无匹配返回空列表。"""
    return FindImages.find_all_template(模板列表, rect=区域, confidence=置信度, rgb=彩色, scale_range=缩放范围, image=截屏) or []

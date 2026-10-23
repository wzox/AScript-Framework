# 混淆器：基于 python-minifier 实现 AST 级别深度压缩与混淆

import python_minifier
import python_minifier.expression_printer
import python_minifier.f_string
import ast


def 兼容旧版f字符串(自身, 节点):
    """强制 pep701=False：设备端 Python 3.8 不支持同引号嵌套的 f-string"""
    自身.printer.fstring(str(python_minifier.f_string.OuterFString(节点, pep701=False)))


python_minifier.expression_printer.ExpressionPrinter.visit_JoinedStr = 兼容旧版f字符串


class 属性重命名器(ast.NodeTransformer):
    def __init__(self):
        self.动态映射表 = {}
        self.动态映射计数 = 1

    def 需混淆(self, 名):
        return 名 and not 名.startswith('__') and any('\u4e00' <= c <= '\u9fa5' for c in 名)

    def visit_Attribute(self, node):
        self.generic_visit(node)
        if self.需混淆(node.attr):
            node.attr = self.自动映射(node.attr)
        return node

    def visit_FunctionDef(self, node):
        self.generic_visit(node)
        if self.需混淆(node.name):
            node.name = self.自动映射(node.name)
        return node

    def visit_Name(self, node):
        self.generic_visit(node)
        if self.需混淆(node.id):
            node.id = self.自动映射(node.id)
        return node

    def visit_arg(self, node):
        self.generic_visit(node)
        if self.需混淆(node.arg):
            node.arg = self.自动映射(node.arg)
        return node

    def visit_keyword(self, node):
        self.generic_visit(node)
        if self.需混淆(node.arg):
            node.arg = self.自动映射(node.arg)
        return node

    def visit_ClassDef(self, node):
        self.generic_visit(node)
        if self.需混淆(node.name):
            node.name = self.自动映射(node.name)
        return node

    def visit_alias(self, node):
        self.generic_visit(node)
        if self.需混淆(node.asname):
            node.asname = self.自动映射(node.asname)
        return node

    def visit_Global(self, node):
        self.generic_visit(node)
        node.names = [self.自动映射(n) if self.需混淆(n) else n for n in node.names]
        return node

    def visit_Nonlocal(self, node):
        self.generic_visit(node)
        node.names = [self.自动映射(n) if self.需混淆(n) else n for n in node.names]
        return node

    def 自动映射(self, 中文名):
        if 中文名 not in self.动态映射表:
            新名 = f"_v{self.动态映射计数}"
            self.动态映射计数 += 1
            self.动态映射表[中文名] = 新名
        return self.动态映射表[中文名]


def 混淆(源码: str) -> str:
    """AST 级深度压缩 + 混淆"""
    try:
        # 1. AST 预处理：替换 python-minifier 无法安全处理的动态属性/中文名
        语法树 = ast.parse(源码)
        语法树 = 属性重命名器().visit(语法树)
        ast.fix_missing_locations(语法树)
        源码 = ast.unparse(语法树)

        # 2. python-minifier 混淆压缩
        压缩后 = python_minifier.minify(
            源码,
            filename=None,                        # 源文件名（无关可略）
            remove_annotations=True,              # 删类型注解（函数返回值/变量/参数注解全删）
            remove_pass=True,                     # 删无用的 pass 语句
            remove_literal_statements=True,       # 删纯字面量语句（包括模块/函数/类 docstring）
            combine_imports=True,                 # 合并相邻 import 语句
            hoist_literals=False,                 # 不提升字符串到模块级变量（提升虽减体积但语义跳转，混淆后不利查错）
            rename_locals=True,                   # 缩短局部变量名（a/b/c...）
            preserve_locals=None,                 # 保留的局部变量（None = 全改）
            rename_globals=True,                  # 缩短全局/内置名（如 print→_p），需保证不被其他模块 import
            preserve_globals=None,                # 保留的全局名（None 指无白名单，全部可改）
            remove_object_base=True,              # 删类定义中多余的 (object)
            convert_posargs_to_args=True,         # 将斜杠 / 前的仅位置参数转为普通参数（缩短函数头）
            preserve_shebang=False,               # 删 #!/usr/bin/env python 等 shebang（设备端不依赖）
            remove_asserts=True,                 # 保留 assert（开发/测试阶段保诊断，发布可开 True
            remove_debug=True,                   # 保留 __debug__ 条件块（发布可开 True）
            remove_explicit_return_none=True,     # return None → return
            remove_builtin_exception_brackets=True,  # raise Exception() → raise Exception
            constant_folding=True,                # 常量折叠（如 1+2 → 3，'a'+'b' → 'ab'）
            prefer_single_line=True,              # 多用分号合并短行为一行，进一步减行数
        )
        return 压缩后
    except Exception as e:
        print(f"代码压缩/混淆过程出现异常: {e}")
        return 源码

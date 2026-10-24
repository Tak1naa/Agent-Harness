"""Constrained pytest harnesses: model chooses inputs, trusted code owns oracles.

This AST policy is a correctness boundary, NOT an OS sandbox. Target code still
requires a rootless, offline container. Restricting the grammar also prevents
generated tests from reading the fixed version or fabricating result files.
"""
import ast

# 测试语法白名单只限制模型生成的测试；不能替代操作系统级隔离。
# 被测代码本身仍必须在无网络、受资源限制的rootless容器内执行。
STRATEGIES = {"sampled_from", "text", "just", "one_of", "integers", "lists",
              "tuples", "binary", "characters"}
ALLOWED = (
    ast.Module, ast.ImportFrom, ast.alias, ast.FunctionDef, ast.arguments, ast.arg,
    ast.Expr, ast.Call, ast.Name, ast.Load, ast.Attribute, ast.Constant,
    ast.List, ast.Tuple, ast.Dict, ast.keyword, ast.UnaryOp, ast.USub,
)


def validate_harness(source: str) -> None:
    if len(source.encode()) > 20_000:
        raise ValueError("Harness exceeds 20 KB")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        raise ValueError("Harness syntax error") from e
    # 第一层检查模块结构：只允许指定导入和普通测试函数，禁止顶层执行语句。
    tests = 0
    for top in tree.body:
        if isinstance(top, ast.ImportFrom):
            if top.module != "hypothesis" or top.level:
                raise ValueError("Only hypothesis imports are permitted")
            for item in top.names:
                if (item.name, item.asname) not in {
                    ("given", None), ("example", None), ("strategies", "st")}:
                    raise ValueError("Unsupported import")
        elif isinstance(top, ast.FunctionDef):
            tests += 1
            if not top.name.startswith("test_") or top.returns or top.args.defaults or top.args.kw_defaults:
                raise ValueError("Only plain test functions are permitted")
            args = [a.arg for a in top.args.args]
            if not args or args[0] != "probe" or len(args) > 2 or any(
                a in {"st", "given", "example"} or a.startswith("_") for a in args
            ):
                raise ValueError("Test must accept probe and optionally one generated input")
            if top.args.vararg or top.args.kwarg or top.args.kwonlyargs or top.args.posonlyargs:
                raise ValueError("Unsupported test parameters")
            # 测试正文只能调用probe.check，模型不能自行写断言、伪造证据或读文件。
            for stmt in top.body:
                if not (isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call)
                        and isinstance(stmt.value.func, ast.Attribute)
                        and isinstance(stmt.value.func.value, ast.Name)
                        and stmt.value.func.value.id == "probe" and stmt.value.func.attr == "check"
                        and len(stmt.value.args) == 1 and not stmt.value.keywords):
                    raise ValueError("Test bodies may only call probe.check(input)")
            for dec in top.decorator_list:
                if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Name) or dec.func.id not in {"given", "example"}:
                    raise ValueError("Only given/example decorators permitted")
        else:
            raise ValueError("No executable module-level statements")
    if not 1 <= tests <= 20:
        raise ValueError("Expected 1 to 20 tests")
    # 第二层遍历所有子节点，堵住参数表达式、属性访问等位置的越界语法。
    # 通过检查不代表输入类型或目标行为一定正确，运行错误仍需单独分类。
    for node in ast.walk(tree):
        if not isinstance(node, ALLOWED):
            raise ValueError(f"Unsupported syntax: {type(node).__name__}")
        if isinstance(node, ast.Attribute):
            if not isinstance(node.value, ast.Name) or not (
                (node.value.id == "probe" and node.attr == "check")
                or (node.value.id == "st" and node.attr in STRATEGIES)
            ):
                raise ValueError("Unsupported attribute")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id not in {"given", "example"}:
            raise ValueError("Unsupported function call")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("Private names are forbidden")
        if isinstance(node, ast.arg) and node.annotation:
            raise ValueError("Annotations not permitted")

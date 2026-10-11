import ast
import re
import builtins
from typing import List, Dict, Any, Set, Optional, Tuple
from app.services.static_analyzer.models import (
    StaticAnalysisResult,
    StaticIssue,
    LoopAnalysis,
    ConditionalAnalysis,
    ComplexityEvidenceData,
)

PYTHON_BUILTIN_NAMES = set(dir(builtins)) | {
    "__name__", "__doc__", "__file__", "True", "False", "None",
    "range", "len", "print", "int", "str", "float", "list", "dict", "set", "tuple",
    "bool", "max", "min", "sum", "any", "all", "enumerate", "zip", "map", "filter",
    "sorted", "reversed", "abs", "round", "isinstance", "issubclass", "type", "open",
    "iter", "next", "super", "id", "hash", "input", "format", "dir", "vars", "repr",
    "Exception", "ValueError", "TypeError", "KeyError", "IndexError", "AttributeError",
    "ZeroDivisionError", "FileNotFoundError", "RuntimeError", "StopIteration",
}


def _try_parse(code: str) -> Tuple[Optional[ast.AST], str, Optional[SyntaxError]]:
    """
    Attempt to parse Python source code into an AST.
    Returns (tree, parse_status, syntax_error_if_any).
    """
    syntax_err = None

    # 1. Direct parse attempt
    try:
        tree = ast.parse(code)
        return tree, "success", None
    except SyntaxError as e:
        syntax_err = e

    # 2. Try adding pass to incomplete block headers (for, while, if, def, class, try, with)
    lines = code.splitlines()
    if lines:
        stripped_last = lines[-1].strip()
        if stripped_last.endswith(":"):
            try:
                fixed_code = code + "\n    pass"
                tree = ast.parse(fixed_code)
                return tree, "partial", None
            except SyntaxError:
                pass

    # 3. Try closing unclosed parentheses or brackets if applicable
    open_parens = code.count("(") - code.count(")")
    open_brackets = code.count("[") - code.count("]")
    open_braces = code.count("{") - code.count("}")
    if open_parens > 0 or open_brackets > 0 or open_braces > 0:
        patch = (")" * open_parens) + ("]" * open_brackets) + ("}" * open_braces)
        try:
            tree = ast.parse(code + patch)
            return tree, "partial", None
        except SyntaxError:
            pass

    # 4. Incomplete snippet fallback
    return None, "unavailable", syntax_err


def _extract_variables(tree: ast.AST) -> List[str]:
    """Collect assigned variable names in order of appearance."""
    variables: List[str] = []
    seen: Set[str] = set()

    for node in ast.walk(tree):
        # Regular assignment: x = ...
        if isinstance(node, ast.Assign):
            for target in node.targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Store):
                        if sub.id not in seen:
                            seen.add(sub.id)
                            variables.append(sub.id)
        # Annotated assignment: x: int = ...
        elif isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id not in seen:
                    seen.add(node.target.id)
                    variables.append(node.target.id)
        # Augmented assignment: x += ...
        elif isinstance(node, ast.AugAssign):
            if isinstance(node.target, ast.Name):
                if node.target.id not in seen:
                    seen.add(node.target.id)
                    variables.append(node.target.id)
        # Named expression (walrus operator): (x := ...)
        elif isinstance(node, getattr(ast, "NamedExpr", ())):
            if isinstance(node.target, ast.Name):
                if node.target.id not in seen:
                    seen.add(node.target.id)
                    variables.append(node.target.id)
        # For loop variable: for i in ...
        elif isinstance(node, (ast.For, getattr(ast, "AsyncFor", ()))):
            for sub in ast.walk(node.target):
                if isinstance(sub, ast.Name):
                    if sub.id not in seen:
                        seen.add(sub.id)
                        variables.append(sub.id)
        # Comprehension target: [x for x in ...]
        elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
            for gen in node.generators:
                for sub in ast.walk(gen.target):
                    if isinstance(sub, ast.Name):
                        if sub.id not in seen:
                            seen.add(sub.id)
                            variables.append(sub.id)

    return variables


def _extract_functions(tree: ast.AST) -> List[Dict[str, Any]]:
    """Extract functions, their parameters, and return statement info."""
    functions: List[Dict[str, Any]] = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, getattr(ast, "AsyncFunctionDef", ()))):
            params = []
            for arg in node.args.args:
                if arg.arg not in ("self", "cls"):
                    params.append(arg.arg)
            for arg in node.args.kwonlyargs:
                params.append(arg.arg)
            if node.args.vararg:
                params.append(f"*{node.args.vararg.arg}")
            if node.args.kwarg:
                params.append(f"**{node.args.kwarg.arg}")

            # Check for return statements
            returns = [
                n for n in ast.walk(node)
                if isinstance(n, ast.Return) and n.value is not None
            ]

            functions.append({
                "name": node.name,
                "parameters": params,
                "has_return": len(returns) > 0,
                "node": node,
            })

    return functions


def _extract_classes(tree: ast.AST) -> List[str]:
    """Extract declared class names."""
    return [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]


def _extract_imports(tree: ast.AST) -> List[str]:
    """Extract imported modules and symbols."""
    imports: List[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(f"{mod}.{alias.name}" if mod else alias.name)
    return imports


def _analyze_loops(tree: ast.AST) -> Tuple[LoopAnalysis, bool]:
    """
    Analyze loops for count and nesting.
    Returns (LoopAnalysis, has_nested_loops).
    """
    loop_nodes = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.For, ast.While, getattr(ast, "AsyncFor", ())))
    ]
    count = len(loop_nodes)
    if count == 0:
        return LoopAnalysis(count=0, nested=False, sequential_count=0), False

    has_nested = False
    for loop in loop_nodes:
        # Check if any child of this loop (excluding loop itself) is also a loop
        for child in ast.walk(loop):
            if child is not loop and isinstance(child, (ast.For, ast.While, getattr(ast, "AsyncFor", ()))):
                has_nested = True
                break
        if has_nested:
            break

    sequential = count > 1 and not has_nested
    return LoopAnalysis(
        count=count,
        nested=has_nested,
        sequential_count=count if sequential else (1 if count > 0 else 0),
        loop_types=["for" if isinstance(n, (ast.For, getattr(ast, "AsyncFor", ()))) else "while" for n in loop_nodes],
    ), has_nested


def _analyze_conditionals(tree: ast.AST) -> ConditionalAnalysis:
    """Analyze if/elif/else and ternary conditional statements."""
    count = 0
    has_else = False
    has_elif = False

    for node in ast.walk(tree):
        if isinstance(node, ast.If):
            count += 1
            if node.orelse:
                if len(node.orelse) == 1 and isinstance(node.orelse[0], ast.If):
                    has_elif = True
                else:
                    has_else = True
        elif isinstance(node, ast.IfExp):
            count += 1
            has_else = True
        elif isinstance(node, getattr(ast, "Match", ())):
            count += 1

    return ConditionalAnalysis(
        count=count,
        has_else=has_else,
        has_elif=has_elif,
    )


def _check_recursion(functions: List[Dict[str, Any]]) -> bool:
    """Check if any function contains a call to itself."""
    for fn_data in functions:
        fn_name = fn_data["name"]
        fn_node = fn_data.get("node")
        if not fn_node:
            continue

        for child in ast.walk(fn_node):
            if isinstance(child, ast.Call):
                # Direct call: fn_name(...)
                if isinstance(child.func, ast.Name) and child.func.id == fn_name:
                    return True
                # Method call on self: self.fn_name(...)
                elif isinstance(child.func, ast.Attribute) and child.func.attr == fn_name:
                    if isinstance(child.func.value, ast.Name) and child.func.value.id in ("self", "cls"):
                        return True
    return False


def _detect_sorting_searching(tree: ast.AST) -> Tuple[bool, bool]:
    """Detect sorting and searching calls or operations."""
    sorting_detected = False
    searching_detected = False

    for node in ast.walk(tree):
        # Calls
        if isinstance(node, ast.Call):
            # sorted(...)
            if isinstance(node.func, ast.Name) and node.func.id == "sorted":
                sorting_detected = True
            # .sort(...)
            elif isinstance(node.func, ast.Attribute) and node.func.attr == "sort":
                sorting_detected = True
            # Searching methods
            elif isinstance(node.func, ast.Attribute) and node.func.attr in ("index", "find", "rfind"):
                searching_detected = True
            elif isinstance(node.func, ast.Name) and node.func.id in ("bisect", "binary_search"):
                searching_detected = True

        # In-operator searching: x in collection
        elif isinstance(node, ast.Compare):
            for op in node.ops:
                if isinstance(op, (ast.In, ast.NotIn)):
                    searching_detected = True

    return sorting_detected, searching_detected


def _detect_issues(tree: ast.AST, functions: List[Dict[str, Any]], variables: List[str], imports: List[str]) -> List[StaticIssue]:
    """Detect deterministic issues (unreachable code, empty except, assert tuple, infinite loops, etc.)."""
    issues: List[StaticIssue] = []

    # 1. Unreachable code after return, break, continue, raise in the same block
    for node in ast.walk(tree):
        for attr in ("body", "orelse", "finalbody"):
            stmts = getattr(node, attr, None)
            if isinstance(stmts, list) and len(stmts) > 1:
                terminating_idx = -1
                terminating_name = ""
                terminating_line = 0
                for idx, stmt in enumerate(stmts):
                    if isinstance(stmt, (ast.Return, ast.Break, ast.Continue, ast.Raise)):
                        terminating_idx = idx
                        terminating_name = stmt.__class__.__name__.lower()
                        terminating_line = getattr(stmt, "lineno", 0)
                        break
                if terminating_idx != -1 and terminating_idx < len(stmts) - 1:
                    issues.append(StaticIssue(
                        type="definite",
                        severity="high",
                        description=f"Unreachable code detected after '{terminating_name}' statement on line {terminating_line}.",
                        line=terminating_line,
                    ))

    # 2. Empty exception handlers: except ...: pass
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for handler in node.handlers:
                # Check if body consists solely of pass or ...
                is_empty = False
                if len(handler.body) == 1:
                    first = handler.body[0]
                    if isinstance(first, ast.Pass):
                        is_empty = True
                    elif isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and first.value.value is Ellipsis:
                        is_empty = True
                if is_empty:
                    line_no = getattr(handler, "lineno", None)
                    issues.append(StaticIssue(
                        type="definite",
                        severity="medium",
                        description=f"Empty exception handler catches exception and silently suppresses it with 'pass'.",
                        line=line_no,
                    ))

    # 3. Assert with tuple: assert (cond, "msg")
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            if isinstance(node.test, ast.Tuple) and len(node.test.elts) > 0:
                line_no = getattr(node, "lineno", None)
                issues.append(StaticIssue(
                    type="definite",
                    severity="high",
                    description="Asserting a tuple 'assert (condition, msg)' always evaluates to True. Use 'assert condition, msg'.",
                    line=line_no,
                ))

    # 4. Suspicious infinite loop: while True / while 1 without break, return, raise
    for node in ast.walk(tree):
        if isinstance(node, ast.While):
            is_always_true = isinstance(node.test, ast.Constant) and (node.test.value is True or node.test.value == 1)

            if is_always_true:
                has_exit = False
                for child in ast.walk(node):
                    if isinstance(child, (ast.Break, ast.Return, ast.Raise)):
                        has_exit = True
                        break
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Attribute) and child.func.attr == "exit":
                        has_exit = True
                        break
                if not has_exit:
                    line_no = getattr(node, "lineno", None)
                    issues.append(StaticIssue(
                        type="possible",
                        severity="medium",
                        description="Suspicious infinite loop: 'while True' contains no break, return, or exit condition.",
                        line=line_no,
                    ))

    # 5. Mutable default argument: def f(x=[])
    for fn in functions:
        fn_node = fn.get("node")
        if fn_node and isinstance(fn_node, ast.FunctionDef):
            for default in fn_node.args.defaults + fn_node.args.kw_defaults:
                if default and isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    kind = default.__class__.__name__.lower()
                    line_no = getattr(fn_node, "lineno", None)
                    issues.append(StaticIssue(
                        type="possible",
                        severity="medium",
                        description=f"Mutable default argument ({kind}) in function '{fn_node.name}'. Default values are instantiated once and shared across all calls.",
                        line=line_no,
                    ))

    # 6. Undefined variable references in complete functions
    defined_names = set(PYTHON_BUILTIN_NAMES) | set(variables) | set(imports)
    for fn in functions:
        defined_names.add(fn["name"])
        defined_names.update(fn["parameters"])

    for fn in functions:
        fn_node = fn.get("node")
        if fn_node:
            local_defined = set(defined_names)
            for child in ast.walk(fn_node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                    local_defined.add(child.id)
            for child in ast.walk(fn_node):
                if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                    if child.id not in local_defined:
                        issues.append(StaticIssue(
                            type="possible",
                            severity="medium",
                            description=f"Possible undefined variable reference '{child.id}' inside function '{fn['name']}'.",
                            line=getattr(child, "lineno", None),
                        ))
                        break  # report first one per function

    return issues


def _fallback_regex_python(code: str, first_err: Optional[SyntaxError] = None) -> StaticAnalysisResult:
    """Fallback extraction using regular expressions when AST parsing fails completely."""
    issues = []
    if first_err:
        issues.append(StaticIssue(
            type="definite",
            severity="high",
            description=f"Syntax error on line {first_err.lineno}: {first_err.msg}",
            line=first_err.lineno,
        ))

    # Extract functions
    func_matches = re.findall(r"\bdef\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)", code)
    functions = [{"name": m[0], "parameters": [p.strip() for p in m[1].split(",") if p.strip()]} for m in func_matches]

    # Extract variables
    var_matches = re.findall(r"\b([a-zA-Z_]\w*)\s*=\s*[^=]", code)
    seen = set()
    variables = []
    for v in var_matches:
        if v not in seen and v not in PYTHON_BUILTIN_NAMES and not any(v == f["name"] for f in functions):
            seen.add(v)
            variables.append(v)

    # Loops
    for_loops = len(re.findall(r"\bfor\s+[a-zA-Z_]\w*\s+in\s+", code))
    while_loops = len(re.findall(r"\bwhile\s+", code))
    loop_count = for_loops + while_loops

    # Conditionals
    if_count = len(re.findall(r"\b(?:if|elif)\s+", code))

    # Recursion
    recursion = False
    for f in functions:
        if re.search(r"\b" + re.escape(f["name"]) + r"\s*\(", code):
            recursion = True
            break

    # Imports
    imports = re.findall(r"\b(?:import\s+([a-zA-Z_]\w*)|from\s+([a-zA-Z_]\w*)\s+import)", code)
    flat_imports = [m[0] or m[1] for m in imports]

    return StaticAnalysisResult(
        language="Python",
        parse_status="partial" if (functions or variables or loop_count > 0) else "unavailable",
        variables=variables,
        functions=functions,
        parameters=[p for f in functions for p in f.get("parameters", [])],
        loops=LoopAnalysis(count=loop_count, nested=False, sequential_count=loop_count),
        conditionals=ConditionalAnalysis(count=if_count),
        recursion_detected=recursion,
        imports=flat_imports,
        complexity_evidence=ComplexityEvidenceData(
            loops=loop_count,
            nested_loops=False,
            recursion_detected=recursion,
            sorting_detected=bool(re.search(r"\.sort\(|\bsorted\(", code)),
            searching_detected=bool(re.search(r"\bin\b|\.find\(|\.index\(", code)),
            sequential_loops=loop_count > 1,
        ),
        issues=issues,
    )


def analyze_python(code: str) -> StaticAnalysisResult:
    """Analyze Python code using AST and deterministic static checks."""
    tree, parse_status, first_err = _try_parse(code)
    if not tree:
        return _fallback_regex_python(code, first_err)

    variables = _extract_variables(tree)
    functions = _extract_functions(tree)
    classes = _extract_classes(tree)
    imports = _extract_imports(tree)
    loop_info, has_nested = _analyze_loops(tree)
    cond_info = _analyze_conditionals(tree)
    recursion = _check_recursion(functions)
    sorting, searching = _detect_sorting_searching(tree)
    issues = _detect_issues(tree, functions, variables, imports)

    parameters = [p for f in functions for p in f.get("parameters", [])]

    # Clean function dicts (remove AST node reference)
    clean_functions = [
        {
            "name": f["name"],
            "parameters": f["parameters"],
            "has_return": f.get("has_return", False),
        }
        for f in functions
    ]

    complexity_evidence = ComplexityEvidenceData(
        loops=loop_info.count,
        nested_loops=has_nested,
        recursion_detected=recursion,
        sorting_detected=sorting,
        searching_detected=searching,
        sequential_loops=loop_info.count > 1 and not has_nested,
    )

    return StaticAnalysisResult(
        language="Python",
        parse_status=parse_status,
        variables=variables,
        functions=clean_functions,
        parameters=parameters,
        loops=loop_info,
        conditionals=cond_info,
        recursion_detected=recursion,
        imports=imports,
        classes=classes,
        complexity_evidence=complexity_evidence,
        issues=issues,
    )

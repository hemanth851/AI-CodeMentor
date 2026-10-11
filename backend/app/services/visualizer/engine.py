"""
Safe, deterministic AST-based execution tracer for Step 7A Algorithm Visualization.

CRITICAL SAFETY DESIGN:
- Arbitrary code execution (exec, eval, compile) is strictly forbidden.
- Executes AST directly using an explicit allowlist of supported nodes.
- Memory, step, loop iteration, recursion depth, and execution time are strictly bounded.
- No access to filesystem, networking, processes, or reflection.
"""

import ast
import copy
import time
from typing import Any, Dict, List, Optional, Tuple, Set

from app.models.visualize import TraceEvent, VisualizeResponse

# Execution limits
MAX_STEPS = 500
MAX_LOOP_ITERATIONS = 200
MAX_RECURSION_DEPTH = 25
MAX_EXECUTION_TIME_SECONDS = 2.0

# Supported AST Node Types (Allowlist)
ALLOWED_NODE_TYPES = (
    ast.Module,
    ast.FunctionDef,
    ast.arguments,
    ast.arg,
    ast.Return,
    ast.Assign,
    ast.AugAssign,
    ast.If,
    ast.For,
    ast.While,
    ast.Break,
    ast.Continue,
    ast.Pass,
    ast.Expr,
    ast.Name,
    ast.Constant,
    ast.List,
    ast.Tuple,
    ast.Subscript,
    getattr(ast, "Index", ast.AST),
    ast.Slice,
    ast.BinOp,
    ast.UnaryOp,
    ast.Compare,
    ast.BoolOp,
    ast.Call,
    # Binary / Unary / Comparison / Boolean Operators
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow,
    ast.USub, ast.UAdd, ast.Not,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn,
    ast.And, ast.Or,
    # Contexts
    ast.Load, ast.Store,
)

# Supported Builtin Functions
ALLOWED_BUILTINS: Set[str] = {
    "range",
    "len",
    "print",
    "min",
    "max",
    "abs",
    "int",
    "str",
    "float",
    "bool",
    "list",
}

# Forbidden Identifiers & Attributes
FORBIDDEN_NAMES: Set[str] = {
    "exec", "eval", "compile", "open", "file", "input", "raw_input",
    "globals", "locals", "vars", "dir", "getattr", "setattr", "delattr",
    "hasattr", "importlib", "__import__", "breakpoint", "help", "exit",
    "quit", "memoryview", "bytearray", "bytes", "classmethod", "staticmethod",
    "property", "super", "type", "object", "isinstance", "issubclass",
}


class VisualizerError(Exception):
    """Base exception for visualizer errors."""
    def __init__(self, message: str, termination_reason: str):
        super().__init__(message)
        self.message = message
        self.termination_reason = termination_reason


class UnsupportedConstructError(VisualizerError):
    """Raised when unsupported or forbidden syntax/constructs are encountered."""
    def __init__(self, message: str):
        super().__init__(message, "unsupported_construct")


class LimitExceededError(VisualizerError):
    """Raised when execution limits (steps, loops, recursion, time) are exceeded."""
    def __init__(self, termination_reason: str, message: str):
        super().__init__(message, termination_reason)


class TraceRuntimeError(VisualizerError):
    """Raised when runtime errors occur during interpretation (e.g. division by zero, index error)."""
    def __init__(self, message: str):
        super().__init__(message, "runtime_error")


class ReturnException(Exception):
    """Flow control signal for function return."""
    def __init__(self, value: Any):
        self.value = value


class BreakException(Exception):
    """Flow control signal for loop break."""
    pass


class ContinueException(Exception):
    """Flow control signal for loop continue."""
    pass


def format_value_preview(val: Any) -> str:
    """Format a Python value cleanly for educational visualization."""
    if isinstance(val, str):
        return f"'{val}'"
    if isinstance(val, (int, float, bool)):
        return str(val)
    if isinstance(val, list):
        if len(val) > 10:
            preview = ", ".join(format_value_preview(x) for x in val[:10])
            return f"[{preview}, ... ({len(val)} items)]"
        return f"[{', '.join(format_value_preview(x) for x in val)}]"
    if isinstance(val, tuple):
        return f"({', '.join(format_value_preview(x) for x in val)})"
    if val is None:
        return "None"
    return repr(val)


def validate_python_ast(tree: ast.AST) -> None:
    """
    Validate that the parsed AST only contains allowlisted nodes and safe constructs.
    
    Raises:
        UnsupportedConstructError: If any forbidden node or construct is detected.
    """
    for node in ast.walk(tree):
        # 1. Allowlist node type check
        if not isinstance(node, ALLOWED_NODE_TYPES):
            node_name = node.__class__.__name__
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                raise UnsupportedConstructError(
                    "Import statements ('import', 'from ... import') are not permitted in algorithm visualization."
                )
            if isinstance(node, ast.ClassDef):
                raise UnsupportedConstructError(
                    "Class definitions are not supported in the Step 7A algorithm visualization subset."
                )
            if isinstance(node, (ast.With, getattr(ast, "AsyncWith", ast.AST))):
                raise UnsupportedConstructError(
                    "Context managers ('with' statements) are not supported in algorithm visualization."
                )
            if isinstance(node, (ast.Try, getattr(ast, "TryStar", ast.AST), ast.Raise)):
                raise UnsupportedConstructError(
                    "Exception handling ('try', 'raise') is not supported in the Step 7A visualization subset."
                )
            if isinstance(node, ast.Attribute):
                raise UnsupportedConstructError(
                    f"Attribute access (e.g. '.{getattr(node, 'attr', '')}') is not permitted for security."
                )
            if isinstance(node, (ast.Global, ast.Nonlocal)):
                raise UnsupportedConstructError(
                    "Global/nonlocal statements are not supported in Step 7A."
                )
            if isinstance(node, (ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
                raise UnsupportedConstructError(
                    f"Comprehensions and lambda expressions are not supported in Step 7A."
                )
            raise UnsupportedConstructError(
                f"The construct '{node_name}' is not supported in Step 7A algorithm visualization."
            )

        # 2. Check identifier names
        if isinstance(node, ast.Name):
            name = node.id
            if name.startswith("__") or name in FORBIDDEN_NAMES:
                raise UnsupportedConstructError(
                    f"The identifier '{name}' is restricted or forbidden in algorithm visualization."
                )

        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("__") or node.name in FORBIDDEN_NAMES:
                raise UnsupportedConstructError(
                    f"The function name '{node.name}' is restricted or forbidden."
                )

        if isinstance(node, ast.arg):
            if node.arg.startswith("__") or node.arg in FORBIDDEN_NAMES:
                raise UnsupportedConstructError(
                    f"The parameter name '{node.arg}' is restricted or forbidden."
                )

        # 3. Check function calls
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name):
                raise UnsupportedConstructError(
                    "Dynamic or attribute function calls are not supported. Only simple named calls are allowed."
                )
            func_id = node.func.id
            if func_id.startswith("__") or func_id in FORBIDDEN_NAMES:
                raise UnsupportedConstructError(
                    f"Calling '{func_id}()' is forbidden for security."
                )


class SafeTraceInterpreter:
    """
    Direct AST interpreter that traces execution step-by-step and produces serializable snapshots.
    """
    def __init__(self, code: str):
        self.code = code
        self.code_lines = code.splitlines()
        self.globals: Dict[str, Any] = {}
        self.functions: Dict[str, ast.FunctionDef] = {}
        self.frames: List[Dict[str, Any]] = []  # Stack of local frames
        self.trace: List[TraceEvent] = []
        self.step_counter = 0
        self.output_buffer: List[str] = []
        self.start_time = 0.0
        self.termination_reason = "completed"

    def _get_active_vars(self) -> Dict[str, Any]:
        """Return combined dictionary of current in-scope variables."""
        scope: Dict[str, Any] = {}
        # Globals
        for k, v in self.globals.items():
            if k not in self.functions:
                scope[k] = self._sanitize_for_json(v)
        # Current local frame (overrides globals if inside function)
        if self.frames:
            for k, v in self.frames[-1].items():
                scope[k] = self._sanitize_for_json(v)
        return scope

    def _get_list_state(self) -> Dict[str, List[Any]]:
        """Extract dedicated snapshot of lists in scope."""
        list_state: Dict[str, List[Any]] = {}
        active = self._get_active_vars()
        for k, v in active.items():
            if isinstance(v, list):
                list_state[k] = copy.deepcopy(v)
        return list_state

    def _sanitize_for_json(self, val: Any) -> Any:
        """Deep copy and ensure value is JSON-serializable with bounded size."""
        if isinstance(val, (int, float, bool)) or val is None:
            return val
        if isinstance(val, str):
            if len(val) > 200:
                return val[:200] + f"... [truncated, length {len(val)}]"
            return val
        if isinstance(val, list):
            if len(val) > 100:
                sanitized = [self._sanitize_for_json(x) for x in val[:100]]
                sanitized.append(f"... [{len(val) - 100} more items]")
                return sanitized
            return [self._sanitize_for_json(x) for x in val]
        if isinstance(val, tuple):
            if len(val) > 100:
                sanitized = [self._sanitize_for_json(x) for x in val[:100]]
                sanitized.append(f"... [{len(val) - 100} more items]")
                return tuple(sanitized)
            return tuple(self._sanitize_for_json(x) for x in val)
        return str(val)

    def _check_limits(self):
        """Enforce step count and execution duration limits."""
        if time.time() - self.start_time > MAX_EXECUTION_TIME_SECONDS:
            raise LimitExceededError(
                "time_limit_exceeded",
                f"Execution time limit exceeded ({MAX_EXECUTION_TIME_SECONDS}s)."
            )
        if self.step_counter >= MAX_STEPS:
            raise LimitExceededError(
                "step_limit_exceeded",
                f"Execution step limit exceeded ({MAX_STEPS} steps). Stopped tracing."
            )

    def record_step(
        self,
        event_type: str,
        line_number: Optional[int],
        description: str,
        condition_result: Optional[bool] = None,
        loop_iteration: Optional[int] = None,
        force: bool = False,
    ):
        """Record an execution step snapshot."""
        if not force:
            self._check_limits()
        self.step_counter += 1

        current_func = None
        if self.frames and hasattr(self, "_current_func_name"):
            current_func = getattr(self, "_current_func_name", None)

        output_str = "".join(self.output_buffer) if self.output_buffer else None

        event = TraceEvent(
            step_number=self.step_counter,
            event_type=event_type,
            line_number=line_number,
            description=description,
            variable_state=self._get_active_vars(),
            list_state=self._get_list_state(),
            current_function=current_func,
            condition_result=condition_result,
            loop_iteration=loop_iteration,
            output=output_str,
        )
        self.trace.append(event)

    def lookup_var(self, name: str) -> Any:
        """Lookup variable in current local scope or globals."""
        if self.frames and name in self.frames[-1]:
            return self.frames[-1][name]
        if name in self.globals:
            return self.globals[name]
        raise TraceRuntimeError(f"Variable '{name}' is referenced before assignment.")

    def set_var(self, name: str, value: Any):
        """Set variable in current local frame or globals."""
        if self.frames:
            self.frames[-1][name] = value
        else:
            self.globals[name] = value

    def eval_expr(self, node: ast.AST) -> Any:
        """Evaluate an AST expression safely."""
        self._check_limits()

        if isinstance(node, ast.Constant):
            return node.value

        if isinstance(node, ast.Name):
            return self.lookup_var(node.id)

        if isinstance(node, ast.List):
            if len(node.elts) > 500:
                raise LimitExceededError("step_limit_exceeded", "List literal exceeds maximum permitted size of 500 elements.")
            return [self.eval_expr(elt) for elt in node.elts]

        if isinstance(node, ast.Tuple):
            if len(node.elts) > 500:
                raise LimitExceededError("step_limit_exceeded", "Tuple literal exceeds maximum permitted size of 500 elements.")
            return tuple(self.eval_expr(elt) for elt in node.elts)

        if isinstance(node, ast.BinOp):
            left = self.eval_expr(node.left)
            right = self.eval_expr(node.right)
            op = node.op

            try:
                res = None
                if isinstance(op, ast.Add):
                    res = left + right
                elif isinstance(op, ast.Sub):
                    res = left - right
                elif isinstance(op, ast.Mult):
                    if isinstance(left, (list, tuple, str)) and isinstance(right, int):
                        if len(left) * max(0, right) > 1000:
                            raise LimitExceededError("step_limit_exceeded", "Sequence multiplication exceeds maximum size of 1000 items.")
                    elif isinstance(right, (list, tuple, str)) and isinstance(left, int):
                        if len(right) * max(0, left) > 1000:
                            raise LimitExceededError("step_limit_exceeded", "Sequence multiplication exceeds maximum size of 1000 items.")
                    res = left * right
                elif isinstance(op, ast.Div):
                    if right == 0:
                        raise TraceRuntimeError("Division by zero.")
                    res = left / right
                elif isinstance(op, ast.FloorDiv):
                    if right == 0:
                        raise TraceRuntimeError("Integer division by zero.")
                    res = left // right
                elif isinstance(op, ast.Mod):
                    if right == 0:
                        raise TraceRuntimeError("Modulo by zero.")
                    res = left % right
                elif isinstance(op, ast.Pow):
                    if isinstance(right, (int, float)):
                        if right > 100:
                            raise LimitExceededError("step_limit_exceeded", "Exponent too large to evaluate safely (maximum is 100).")
                        if right < -100:
                            raise LimitExceededError("step_limit_exceeded", "Negative exponent too small to evaluate safely.")
                    if isinstance(left, int) and isinstance(right, int) and right > 0:
                        if left.bit_length() * right > 2048:
                            raise LimitExceededError("step_limit_exceeded", "Exponentiation result exceeds safe integer limit.")
                    if left == 0 and right < 0:
                        raise TraceRuntimeError("ZeroDivisionError: 0.0 cannot be raised to a negative power.")
                    res = left ** right
                else:
                    raise UnsupportedConstructError(f"Unsupported binary operator: {op.__class__.__name__}")

                if isinstance(res, int) and res.bit_length() > 2048:
                    raise LimitExceededError("step_limit_exceeded", "Integer value grew too large to compute safely (exceeded 2048 bits).")

                return res
            except TypeError as te:
                raise TraceRuntimeError(f"Type error in arithmetic operation: {te}")

        if isinstance(node, ast.UnaryOp):
            operand = self.eval_expr(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.Not):
                return not operand
            raise UnsupportedConstructError(f"Unsupported unary operator: {node.op.__class__.__name__}")

        if isinstance(node, ast.Compare):
            left = self.eval_expr(node.left)
            for op, comparator in zip(node.ops, node.comparators):
                right = self.eval_expr(comparator)
                result = False
                if isinstance(op, ast.Eq):
                    result = (left == right)
                elif isinstance(op, ast.NotEq):
                    result = (left != right)
                elif isinstance(op, ast.Lt):
                    result = (left < right)
                elif isinstance(op, ast.LtE):
                    result = (left <= right)
                elif isinstance(op, ast.Gt):
                    result = (left > right)
                elif isinstance(op, ast.GtE):
                    result = (left >= right)
                elif isinstance(op, ast.In):
                    result = (left in right)
                elif isinstance(op, ast.NotIn):
                    result = (left not in right)
                else:
                    raise UnsupportedConstructError(f"Unsupported comparison operator: {op.__class__.__name__}")

                if not result:
                    return False
                left = right
            return True

        if isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                val = True
                for val_node in node.values:
                    val = self.eval_expr(val_node)
                    if not val:
                        return val
                return val
            if isinstance(node.op, ast.Or):
                val = False
                for val_node in node.values:
                    val = self.eval_expr(val_node)
                    if val:
                        return val
                return val
            raise UnsupportedConstructError(f"Unsupported boolean operator: {node.op.__class__.__name__}")

        if isinstance(node, ast.Subscript):
            target = self.eval_expr(node.value)
            idx_node = node.slice
            # Handle ast.Index in older Python ASTs
            if hasattr(ast, "Index") and isinstance(idx_node, ast.Index):
                idx_node = idx_node.value

            if isinstance(idx_node, ast.Slice):
                lower = self.eval_expr(idx_node.lower) if idx_node.lower else None
                upper = self.eval_expr(idx_node.upper) if idx_node.upper else None
                step = self.eval_expr(idx_node.step) if idx_node.step else None
                return target[slice(lower, upper, step)]

            idx = self.eval_expr(idx_node)
            try:
                return target[idx]
            except IndexError:
                raise TraceRuntimeError(f"IndexError: index {idx} out of range for sequence of length {len(target)}.")
            except TypeError as te:
                raise TraceRuntimeError(f"TypeError accessing subscript: {te}")

        if isinstance(node, ast.Call):
            return self.execute_call(node)

        raise UnsupportedConstructError(f"Unsupported expression node: {node.__class__.__name__}")

    def execute_call(self, node: ast.Call) -> Any:
        """Execute a call to an allowlisted builtin or user function."""
        func_name = node.func.id
        evaluated_args = [self.eval_expr(arg) for arg in node.args]

        # 1. Builtin functions
        if func_name in ALLOWED_BUILTINS:
            if func_name == "print":
                msg = " ".join(str(a) for a in evaluated_args) + "\n"
                self.output_buffer.append(msg)
                self.record_step(
                    event_type="output",
                    line_number=node.lineno,
                    description=f"Printed output: {repr(msg.strip())}",
                )
                return None
            if func_name == "range":
                if not (1 <= len(evaluated_args) <= 3):
                    raise TraceRuntimeError("range() expects 1 to 3 arguments.")
                if not all(isinstance(a, int) for a in evaluated_args):
                    raise TraceRuntimeError("range() arguments must be integers.")
                if len(evaluated_args) == 3 and evaluated_args[2] == 0:
                    raise TraceRuntimeError("range() arg 3 must not be zero.")
                try:
                    r = range(*evaluated_args)
                except Exception as e:
                    raise TraceRuntimeError(f"Invalid arguments to range(): {e}")

                if len(r) > 1000:
                    raise LimitExceededError(
                        "loop_limit_exceeded",
                        f"range() length of {len(r)} exceeds maximum permitted limit of 1000 elements for visualization."
                    )
                return list(r)
            if func_name == "len":
                if len(evaluated_args) != 1:
                    raise TraceRuntimeError("len() takes exactly one argument.")
                return len(evaluated_args[0])
            if func_name == "min":
                if not evaluated_args:
                    raise TraceRuntimeError("min() expects at least 1 argument.")
                if len(evaluated_args) == 1:
                    return min(evaluated_args[0])
                return min(*evaluated_args)
            if func_name == "max":
                if not evaluated_args:
                    raise TraceRuntimeError("max() expects at least 1 argument.")
                if len(evaluated_args) == 1:
                    return max(evaluated_args[0])
                return max(*evaluated_args)
            if func_name == "abs":
                if len(evaluated_args) != 1:
                    raise TraceRuntimeError("abs() takes exactly one argument.")
                return abs(evaluated_args[0])
            if func_name == "int":
                return int(evaluated_args[0]) if evaluated_args else 0
            if func_name == "float":
                return float(evaluated_args[0]) if evaluated_args else 0.0
            if func_name == "str":
                return str(evaluated_args[0]) if evaluated_args else ""
            if func_name == "bool":
                return bool(evaluated_args[0]) if evaluated_args else False
            if func_name == "list":
                return list(evaluated_args[0]) if evaluated_args else []

        # 2. User-defined functions
        if func_name in self.functions:
            func_def = self.functions[func_name]

            if len(self.frames) >= MAX_RECURSION_DEPTH:
                raise LimitExceededError(
                    "recursion_limit_exceeded",
                    f"Maximum recursion depth of {MAX_RECURSION_DEPTH} exceeded."
                )

            param_names = [arg.arg for arg in func_def.args.args]
            if len(param_names) != len(evaluated_args):
                raise TraceRuntimeError(
                    f"Function '{func_name}' expects {len(param_names)} arguments, got {len(evaluated_args)}."
                )

            # Create local frame
            frame: Dict[str, Any] = dict(zip(param_names, evaluated_args))
            self.frames.append(frame)
            prev_func_name = getattr(self, "_current_func_name", None)
            self._current_func_name = func_name

            args_desc = ", ".join(f"{k}={format_value_preview(v)}" for k, v in frame.items())
            self.record_step(
                event_type="function_call",
                line_number=func_def.lineno,
                description=f"Calling function '{func_name}({args_desc})'",
            )

            ret_val = None
            try:
                for stmt in func_def.body:
                    self.execute_stmt(stmt)
            except ReturnException as ret_sig:
                ret_val = ret_sig.value
            finally:
                self.frames.pop()
                self._current_func_name = prev_func_name

            return ret_val

        raise UnsupportedConstructError(
            f"Call to unknown or unsupported function '{func_name}()'."
        )

    def execute_stmt(self, stmt: ast.AST):
        """Execute a single AST statement node."""
        self._check_limits()

        if isinstance(stmt, ast.FunctionDef):
            self.functions[stmt.name] = stmt
            self.record_step(
                event_type="initialization",
                line_number=stmt.lineno,
                description=f"Defined function '{stmt.name}' with parameters ({', '.join(a.arg for a in stmt.args.args)})",
            )
            return

        if isinstance(stmt, ast.Assign):
            val = self.eval_expr(stmt.value)
            for target in stmt.targets:
                if isinstance(target, ast.Name):
                    var_name = target.id
                    self.set_var(var_name, val)
                    self.record_step(
                        event_type="assignment",
                        line_number=stmt.lineno,
                        description=f"Assigned variable '{var_name}' = {format_value_preview(val)}",
                    )
                elif isinstance(target, ast.Subscript):
                    seq = self.eval_expr(target.value)
                    idx_node = target.slice
                    if hasattr(ast, "Index") and isinstance(idx_node, ast.Index):
                        idx_node = idx_node.value
                    idx = self.eval_expr(idx_node)
                    try:
                        seq[idx] = val
                        seq_name = target.value.id if isinstance(target.value, ast.Name) else "list"
                        self.record_step(
                            event_type="assignment",
                            line_number=stmt.lineno,
                            description=f"Updated element {seq_name}[{idx}] = {format_value_preview(val)}",
                        )
                    except IndexError:
                        raise TraceRuntimeError(f"IndexError updating element at index {idx}.")
                else:
                    raise UnsupportedConstructError("Unsupported assignment target.")
            return

        if isinstance(stmt, ast.AugAssign):
            rhs = self.eval_expr(stmt.value)
            op = stmt.op

            is_name = isinstance(stmt.target, ast.Name)
            is_subscript = isinstance(stmt.target, ast.Subscript)

            if not is_name and not is_subscript:
                raise UnsupportedConstructError("Augmented assignment only supported on variables and list elements.")

            if is_name:
                var_name = stmt.target.id
                curr_val = self.lookup_var(var_name)
            else:
                seq = self.eval_expr(stmt.target.value)
                idx_node = stmt.target.slice
                if hasattr(ast, "Index") and isinstance(idx_node, ast.Index):
                    idx_node = idx_node.value
                idx = self.eval_expr(idx_node)
                try:
                    curr_val = seq[idx]
                except IndexError:
                    raise TraceRuntimeError(f"IndexError updating element at index {idx}.")
                seq_name = stmt.target.value.id if isinstance(stmt.target.value, ast.Name) else "seq"
                var_name = f"{seq_name}[{idx}]"

            try:
                if isinstance(op, ast.Add):
                    new_val = curr_val + rhs
                elif isinstance(op, ast.Sub):
                    new_val = curr_val - rhs
                elif isinstance(op, ast.Mult):
                    if isinstance(curr_val, (list, tuple, str)) and isinstance(rhs, int):
                        if len(curr_val) * max(0, rhs) > 1000:
                            raise LimitExceededError("step_limit_exceeded", "Sequence multiplication exceeds maximum size of 1000 items.")
                    new_val = curr_val * rhs
                elif isinstance(op, ast.Div):
                    if rhs == 0:
                        raise TraceRuntimeError("Division by zero.")
                    new_val = curr_val / rhs
                elif isinstance(op, ast.FloorDiv):
                    if rhs == 0:
                        raise TraceRuntimeError("Integer division by zero.")
                    new_val = curr_val // rhs
                elif isinstance(op, ast.Mod):
                    if rhs == 0:
                        raise TraceRuntimeError("Modulo by zero.")
                    new_val = curr_val % rhs
                else:
                    raise UnsupportedConstructError(f"Unsupported augmented assignment operator: {op.__class__.__name__}")

                if isinstance(new_val, int) and new_val.bit_length() > 2048:
                    raise LimitExceededError("step_limit_exceeded", "Integer value grew too large to compute safely.")

            except TypeError as te:
                raise TraceRuntimeError(f"Type error in augmented assignment: {te}")

            if is_name:
                self.set_var(stmt.target.id, new_val)
                self.record_step(
                    event_type="assignment",
                    line_number=stmt.lineno,
                    description=f"Updated '{stmt.target.id}' from {format_value_preview(curr_val)} to {format_value_preview(new_val)}",
                )
            else:
                seq[idx] = new_val
                self.record_step(
                    event_type="assignment",
                    line_number=stmt.lineno,
                    description=f"Updated {var_name} from {format_value_preview(curr_val)} to {format_value_preview(new_val)}",
                )
            return

        if isinstance(stmt, ast.If):
            cond_val = bool(self.eval_expr(stmt.test))
            if cond_val:
                self.record_step(
                    event_type="condition_true",
                    line_number=stmt.lineno,
                    description="Condition evaluated to True; entering 'if' branch",
                    condition_result=True,
                )
                for s in stmt.body:
                    self.execute_stmt(s)
            else:
                self.record_step(
                    event_type="condition_false",
                    line_number=stmt.lineno,
                    description="Condition evaluated to False; taking 'else' branch" if stmt.orelse else "Condition evaluated to False; skipping branch",
                    condition_result=False,
                )
                for s in stmt.orelse:
                    self.execute_stmt(s)
            return

        if isinstance(stmt, ast.For):
            iter_val = self.eval_expr(stmt.iter)
            if not isinstance(iter_val, (list, tuple, range)):
                raise TraceRuntimeError(f"TypeError: '{type(iter_val).__name__}' object is not iterable.")

            target_name = stmt.target.id if isinstance(stmt.target, ast.Name) else "item"
            self.record_step(
                event_type="loop_start",
                line_number=stmt.lineno,
                description=f"Starting 'for' loop over {format_value_preview(iter_val)}",
                loop_iteration=0,
            )

            iteration = 0
            for item in iter_val:
                iteration += 1
                if iteration > MAX_LOOP_ITERATIONS:
                    raise LimitExceededError(
                        "loop_limit_exceeded",
                        f"Loop iteration limit of {MAX_LOOP_ITERATIONS} exceeded."
                    )

                self.set_var(target_name, item)
                self.record_step(
                    event_type="loop_iteration",
                    line_number=stmt.lineno,
                    description=f"Loop iteration {iteration}: set '{target_name}' = {format_value_preview(item)}",
                    loop_iteration=iteration,
                )

                try:
                    for s in stmt.body:
                        self.execute_stmt(s)
                except BreakException:
                    break
                except ContinueException:
                    continue
            return

        if isinstance(stmt, ast.While):
            self.record_step(
                event_type="loop_start",
                line_number=stmt.lineno,
                description="Starting 'while' loop",
                loop_iteration=0,
            )

            iteration = 0
            while True:
                cond = bool(self.eval_expr(stmt.test))
                if not cond:
                    self.record_step(
                        event_type="condition_false",
                        line_number=stmt.lineno,
                        description="While condition evaluated to False; exiting loop",
                        condition_result=False,
                        loop_iteration=iteration,
                    )
                    break

                iteration += 1
                if iteration > MAX_LOOP_ITERATIONS:
                    raise LimitExceededError(
                        "loop_limit_exceeded",
                        f"While loop exceeded maximum limit of {MAX_LOOP_ITERATIONS} iterations."
                    )

                self.record_step(
                    event_type="condition_true",
                    line_number=stmt.lineno,
                    description=f"While condition evaluated to True (iteration {iteration})",
                    condition_result=True,
                    loop_iteration=iteration,
                )

                try:
                    for s in stmt.body:
                        self.execute_stmt(s)
                except BreakException:
                    break
                except ContinueException:
                    continue
            return

        if isinstance(stmt, ast.Return):
            ret_val = self.eval_expr(stmt.value) if stmt.value else None
            func_name = getattr(self, "_current_func_name", "function")
            self.record_step(
                event_type="return",
                line_number=stmt.lineno,
                description=f"Function '{func_name}' returned {format_value_preview(ret_val)}",
            )
            raise ReturnException(ret_val)

        if isinstance(stmt, ast.Break):
            raise BreakException()

        if isinstance(stmt, ast.Continue):
            raise ContinueException()

        if isinstance(stmt, ast.Pass):
            return

        if isinstance(stmt, ast.Expr):
            self.eval_expr(stmt.value)
            return

        raise UnsupportedConstructError(f"Unsupported statement: {stmt.__class__.__name__}")

    def run(self) -> VisualizeResponse:
        """
        Parse, validate, and execute the Python code deterministically.
        """
        self.start_time = time.time()

        # 1. Parse AST
        try:
            tree = ast.parse(self.code)
        except SyntaxError as syn_err:
            # Check if this syntax error is caused by non-Python code (e.g. Java, C++, JS)
            from app.services.detector import detect_language
            detection = detect_language(self.code)
            if detection.language != "Python" and detection.confidence in ("high", "moderate"):
                return VisualizeResponse(
                    status="unsupported",
                    supported=False,
                    trace=[],
                    total_steps=0,
                    final_state={},
                    termination_reason="unsupported_language",
                    error="Interactive visualization is currently available only for Python.",
                )

            # Heuristic check for non-Python keywords/constructs in code
            lower_code = self.code.lower()
            non_python_markers = (
                "public class", "public static void", "system.out.",
                "console.log", "int main(", "#include <", "fn main()",
                "package main", "func ", "fmt.println",
            )
            if any(marker in lower_code for marker in non_python_markers):
                return VisualizeResponse(
                    status="unsupported",
                    supported=False,
                    trace=[],
                    total_steps=0,
                    final_state={},
                    termination_reason="unsupported_language",
                    error="Interactive visualization is currently available only for Python.",
                )

            return VisualizeResponse(
                status="error",
                supported=True,
                trace=[],
                total_steps=0,
                final_state={},
                termination_reason="syntax_error",
                error=f"Python syntax error at line {syn_err.lineno}: {syn_err.msg}",
            )

        # 2. Strict AST Allowlist Validation
        try:
            validate_python_ast(tree)
        except UnsupportedConstructError as unc_err:
            return VisualizeResponse(
                status="unsupported",
                supported=False,
                trace=[],
                total_steps=0,
                final_state={},
                termination_reason=unc_err.termination_reason,
                error=unc_err.message,
            )

        # 3. Check for defined functions to validate allowed function calls
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                self.functions[node.name] = node

        # Verify all function calls target either ALLOWED_BUILTINS or defined user functions
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                func_id = node.func.id
                if func_id not in ALLOWED_BUILTINS and func_id not in self.functions:
                    return VisualizeResponse(
                        status="unsupported",
                        supported=False,
                        trace=[],
                        total_steps=0,
                        final_state={},
                        termination_reason="unsupported_construct",
                        error=f"Function '{func_id}()' is not supported in Step 7A visualization. Supported functions: {', '.join(sorted(ALLOWED_BUILTINS))} or user functions defined in your code.",
                    )

        # 4. Deterministic Tracing Execution
        try:
            for stmt in tree.body:
                self.execute_stmt(stmt)

            # Record final completed event
            final_vars = self._get_active_vars()
            self.record_step(
                event_type="completed",
                line_number=len(self.code_lines) if self.code_lines else 1,
                description="Algorithm execution finished successfully.",
            )

            return VisualizeResponse(
                status="success",
                supported=True,
                trace=self.trace,
                total_steps=len(self.trace),
                final_state=final_vars,
                termination_reason="completed",
                error=None,
            )

        except LimitExceededError as lim_err:
            # Capture partial trace up to the limit and report termination reason
            final_vars = self._get_active_vars()
            self.record_step(
                event_type="limit_exceeded",
                line_number=self.trace[-1].line_number if self.trace else 1,
                description=f"Execution stopped: {lim_err.message}",
                force=True,
            )
            return VisualizeResponse(
                status="success",
                supported=True,
                trace=self.trace,
                total_steps=len(self.trace),
                final_state=final_vars,
                termination_reason=lim_err.termination_reason,
                error=lim_err.message,
            )

        except TraceRuntimeError as rt_err:
            final_vars = self._get_active_vars()
            return VisualizeResponse(
                status="error",
                supported=True,
                trace=self.trace,
                total_steps=len(self.trace),
                final_state=final_vars,
                termination_reason="runtime_error",
                error=rt_err.message,
            )

        except UnsupportedConstructError as unc_err:
            return VisualizeResponse(
                status="unsupported",
                supported=False,
                trace=self.trace,
                total_steps=len(self.trace),
                final_state=self._get_active_vars(),
                termination_reason=unc_err.termination_reason,
                error=unc_err.message,
            )

        except Exception as e:
            # Safe generic catch without leaking internal stack trace
            return VisualizeResponse(
                status="error",
                supported=True,
                trace=self.trace,
                total_steps=len(self.trace),
                final_state=self._get_active_vars(),
                termination_reason="runtime_error",
                error="An unexpected error occurred during execution tracing.",
            )


def trace_python_code(code: str) -> VisualizeResponse:
    """Entrypoint to deterministically trace a Python snippet."""
    interpreter = SafeTraceInterpreter(code)
    return interpreter.run()

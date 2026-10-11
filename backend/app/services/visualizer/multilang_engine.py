"""
Multi-language algorithm execution visualizer engine.
Enables step-by-step interactive algorithm visualization for ALL types of code
(Python, Java, C, C++, JavaScript, TypeScript, C#, Go, Rust, PHP, Kotlin, Swift, SQL, and others)
using an LLM-assisted execution tracer backed by a deterministic heuristic tracer.
"""

import os
import json
import re
import logging
from typing import Optional, List, Dict, Any

from app.models.visualize import TraceEvent, VisualizeResponse
from app.services.visualizer.engine import trace_python_code
from app.services.llm_service import (
    get_gemini_client,
    execute_with_retry_and_fallback,
    LLMConfigurationError,
    LLMServiceError,
)

logger = logging.getLogger(__name__)


def build_visualization_prompt(code: str, language: str) -> str:
    """
    Construct a prompt instructing Gemini to trace code execution step-by-step
    into the structured JSON format required for visualization.
    """
    return (
        f"You are the Algorithm Execution Tracer for AI CodeMentor.\n"
        f"Analyze the following {language} code and generate a realistic, step-by-step execution trace "
        f"as if executed by a debugger or runtime environment.\n\n"
        f"=== SOURCE CODE ({language}) ===\n"
        f"{code}\n\n"
        f"=== INSTRUCTIONS ===\n"
        f"1. Generate a sequential list of execution steps (between 4 and 40 steps). Each step must correspond "
        f"   to a real line of code executed in order.\n"
        f"2. For each step, provide:\n"
        f"   - 'step_number': integer starting at 1\n"
        f"   - 'event_type': one of ['initialization', 'assignment', 'condition_true', 'condition_false', "
        f"     'loop_start', 'loop_iteration', 'function_call', 'return', 'output', 'completed']\n"
        f"   - 'line_number': 1-indexed line number in the source code being executed\n"
        f"   - 'description': clear, pedagogical explanation of what happens at this step\n"
        f"   - 'variable_state': dictionary mapping current in-scope variable names to their values (e.g. {{\"x\": 5}})\n"
        f"   - 'list_state': dictionary mapping array/list variable names to list representations (e.g. {{\"arr\": [1, 2, 3]}})\n"
        f"   - 'current_function': name of current function or null\n"
        f"   - 'condition_result': true or false if a condition was checked, else null\n"
        f"   - 'loop_iteration': integer count if inside a loop, else null\n"
        f"   - 'output': cumulative printed output string up to this step, or null\n"
        f"3. Conclude with a final step having event_type 'completed'.\n"
        f"4. Provide 'final_state' dictionary of all variable values at the end of execution.\n"
        f"5. Return ONLY a valid JSON object with keys 'trace' and 'final_state'. Do not include markdown code fences or commentary.\n"
    )


def trace_code_with_llm(code: str, language: str) -> Optional[VisualizeResponse]:
    """
    Attempt to trace execution using Gemini LLM.
    Returns None if LLM is unavailable, unconfigured, or encounters an error.
    """
    try:
        model_name = os.getenv("GEMINI_MODEL", "").strip()
        if not model_name:
            return None

        client = get_gemini_client()
        prompt = build_visualization_prompt(code, language)

        from google.genai import types

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.1,
        )

        response = execute_with_retry_and_fallback(
            client=client,
            contents=prompt,
            config=config,
            primary_model=model_name,
            default_msg="Execution visualization query failed.",
        )

        text = getattr(response, "text", "") or ""
        text = text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)

        data = json.loads(text)
        raw_trace = data.get("trace", [])
        final_state = data.get("final_state", {})

        if not raw_trace or not isinstance(raw_trace, list):
            return None

        valid_events = []
        for i, item in enumerate(raw_trace, start=1):
            if not isinstance(item, dict):
                continue
            event = TraceEvent(
                step_number=item.get("step_number", i),
                event_type=item.get("event_type", "assignment"),
                line_number=item.get("line_number"),
                description=item.get("description", "Executes statement"),
                variable_state=item.get("variable_state") or {},
                list_state=item.get("list_state") or {},
                current_function=item.get("current_function"),
                condition_result=item.get("condition_result"),
                loop_iteration=item.get("loop_iteration"),
                output=item.get("output"),
            )
            valid_events.append(event)

        if not valid_events:
            return None

        # Ensure last event is marked completed
        if valid_events[-1].event_type != "completed":
            valid_events.append(
                TraceEvent(
                    step_number=len(valid_events) + 1,
                    event_type="completed",
                    line_number=valid_events[-1].line_number,
                    description="Execution completed successfully.",
                    variable_state=final_state or valid_events[-1].variable_state,
                    list_state=valid_events[-1].list_state,
                    output=valid_events[-1].output,
                )
            )

        return VisualizeResponse(
            status="success",
            supported=True,
            trace=valid_events,
            total_steps=len(valid_events),
            final_state=final_state or (valid_events[-1].variable_state if valid_events else {}),
            termination_reason="completed",
        )
    except Exception as exc:
        logger.warning(f"LLM-based visualization fell back to deterministic tracer: {exc}")
        return None


def _parse_literal_value(val_str: str) -> Any:
    """Safely parse a literal string into an int, float, list, or string."""
    val_str = val_str.strip().rstrip(";")
    if not val_str:
        return ""
    if val_str in ("true", "True"):
        return True
    if val_str in ("false", "False"):
        return False
    if val_str in ("null", "None", "nil"):
        return None
    if re.match(r"^-?\d+$", val_str):
        try:
            return int(val_str)
        except ValueError:
            pass
    if re.match(r"^-?\d+\.\d+$", val_str):
        try:
            return float(val_str)
        except ValueError:
            pass
    if (val_str.startswith('"') and val_str.endswith('"')) or (val_str.startswith("'") and val_str.endswith("'")):
        return val_str[1:-1]
    if (val_str.startswith("[") and val_str.endswith("]")) or (val_str.startswith("{") and val_str.endswith("}")):
        # Attempt to parse array elements
        inner = val_str[1:-1].strip()
        if not inner:
            return []
        items = [_parse_literal_value(part) for part in inner.split(",") if part.strip()]
        return items
    return val_str


def trace_code_heuristically(code: str, language: str) -> VisualizeResponse:
    """
    Deterministic universal fallback execution tracer.
    Parses source code line-by-line for ANY programming language, tracks variable
    assignments, loops, function definitions, conditions, and print outputs,
    and produces a structured TraceEvent sequence.
    """
    lines = code.split("\n")
    trace: List[TraceEvent] = []
    variable_state: Dict[str, Any] = {}
    list_state: Dict[str, List[Any]] = {}
    current_function: Optional[str] = None
    output_buffer = ""
    step_num = 1

    # Regex patterns for common programming constructs across languages
    func_pattern = re.compile(
        r"^\s*(?:(?:public|private|protected|static|inline|async|def|function|fn|func|void|int|double|float|bool|string)\s+)*"
        r"([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*(?:\{|:)?",
        re.IGNORECASE,
    )
    assign_pattern = re.compile(
        r"^\s*(?:(?:const|let|var|auto|val|int|long|float|double|char|boolean|bool|string|String)\s+)?"
        r"([a-zA-Z_]\w*)\s*(?:\[\s*\])?\s*(?:=|:=|\+=|-=|\*=|/=)\s*([^;]+);?",
        re.IGNORECASE,
    )
    print_pattern = re.compile(
        r"(?:System\.out\.print(?:ln)?|console\.log|printf|cout\s*<<|print\s*\(|fmt\.Print(?:ln)?|echo)\s*\(?([^;()]+)?\)?",
        re.IGNORECASE,
    )
    loop_pattern = re.compile(r"^\s*(for|while|do|foreach)\b", re.IGNORECASE)
    cond_pattern = re.compile(r"^\s*(if|else\s+if|elif)\b", re.IGNORECASE)
    else_pattern = re.compile(r"^\s*else\b", re.IGNORECASE)
    return_pattern = re.compile(r"^\s*return\b(?:\s+([^;]+))?", re.IGNORECASE)

    # Initial program entry step
    first_non_empty_line = 1
    for idx, l in enumerate(lines, start=1):
        if l.strip() and not l.strip().startswith(("//", "#", "/*", "*", "--")):
            first_non_empty_line = idx
            break

    trace.append(
        TraceEvent(
            step_number=step_num,
            event_type="initialization",
            line_number=first_non_empty_line,
            description=f"Initializes program execution environment for {language}.",
            variable_state=dict(variable_state),
            list_state=dict(list_state),
            current_function=None,
        )
    )
    step_num += 1

    loop_iter_count = 0

    for line_idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line or line.startswith(("//", "#", "/*", "*", "--")):
            continue
        if line in ("{", "}", "};", "end", "done"):
            continue

        # 1. Print / Output statement
        print_match = print_pattern.search(line)
        if print_match:
            raw_arg = (print_match.group(1) or "").strip()
            # Try to resolve argument from variable_state or string literal
            printed_val = ""
            if raw_arg in variable_state:
                printed_val = str(variable_state[raw_arg])
            elif (raw_arg.startswith('"') and raw_arg.endswith('"')) or (raw_arg.startswith("'") and raw_arg.endswith("'")):
                printed_val = raw_arg[1:-1]
            elif raw_arg:
                # Remove quotes or syntax
                printed_val = raw_arg.replace('"', "").replace("'", "").strip()
            else:
                printed_val = "output"

            output_buffer += (printed_val + "\n")
            trace.append(
                TraceEvent(
                    step_number=step_num,
                    event_type="output",
                    line_number=line_idx,
                    description=f"Prints '{printed_val}' to standard output.",
                    variable_state=dict(variable_state),
                    list_state=dict(list_state),
                    current_function=current_function,
                    output=output_buffer,
                )
            )
            step_num += 1
            continue

        # 2. Return statement
        ret_match = return_pattern.search(line)
        if ret_match:
            ret_expr = (ret_match.group(1) or "").strip().rstrip(";")
            ret_val = variable_state.get(ret_expr, ret_expr) if ret_expr else None
            trace.append(
                TraceEvent(
                    step_number=step_num,
                    event_type="return",
                    line_number=line_idx,
                    description=f"Returns value '{ret_val}' from {current_function or 'execution'}.",
                    variable_state=dict(variable_state),
                    list_state=dict(list_state),
                    current_function=current_function,
                    output=output_buffer or None,
                )
            )
            step_num += 1
            continue

        # 3. Conditional statement (if / elif / else)
        if cond_pattern.search(line):
            trace.append(
                TraceEvent(
                    step_number=step_num,
                    event_type="condition_true",
                    line_number=line_idx,
                    description=f"Evaluates branch condition on line {line_idx}.",
                    variable_state=dict(variable_state),
                    list_state=dict(list_state),
                    current_function=current_function,
                    condition_result=True,
                    output=output_buffer or None,
                )
            )
            step_num += 1
            continue

        if else_pattern.search(line):
            trace.append(
                TraceEvent(
                    step_number=step_num,
                    event_type="condition_false",
                    line_number=line_idx,
                    description="Condition evaluates to false; entering else branch.",
                    variable_state=dict(variable_state),
                    list_state=dict(list_state),
                    current_function=current_function,
                    condition_result=False,
                    output=output_buffer or None,
                )
            )
            step_num += 1
            continue

        # 4. Loop statement (for / while)
        if loop_pattern.search(line):
            loop_iter_count += 1
            trace.append(
                TraceEvent(
                    step_number=step_num,
                    event_type="loop_start" if loop_iter_count == 1 else "loop_iteration",
                    line_number=line_idx,
                    description=f"Loop iteration #{loop_iter_count}: checking loop guard and advancing iterator.",
                    variable_state=dict(variable_state),
                    list_state=dict(list_state),
                    current_function=current_function,
                    loop_iteration=loop_iter_count,
                    output=output_buffer or None,
                )
            )
            step_num += 1
            continue

        # 5. Function / Method definition
        func_match = func_pattern.search(line)
        if func_match and not assign_pattern.search(line):
            f_name = func_match.group(1)
            # Exclude keywords like if, for, while, return
            if f_name.lower() not in ("if", "for", "while", "return", "class", "struct", "catch"):
                current_function = f_name
                trace.append(
                    TraceEvent(
                        step_number=step_num,
                        event_type="function_call",
                        line_number=line_idx,
                        description=f"Declares or invokes function '{f_name}()'.",
                        variable_state=dict(variable_state),
                        list_state=dict(list_state),
                        current_function=current_function,
                        output=output_buffer or None,
                    )
                )
                step_num += 1
                continue

        # 6. Variable assignment or declaration
        assign_match = assign_pattern.search(line)
        if assign_match:
            var_name = assign_match.group(1).strip()
            raw_val = assign_match.group(2).strip()
            # Ignore keyword matches
            if var_name.lower() not in ("return", "if", "for", "while", "else", "class", "import", "package"):
                parsed_val = _parse_literal_value(raw_val)
                variable_state[var_name] = parsed_val
                if isinstance(parsed_val, list):
                    list_state[var_name] = parsed_val

                trace.append(
                    TraceEvent(
                        step_number=step_num,
                        event_type="assignment",
                        line_number=line_idx,
                        description=f"Assigns variable '{var_name}' = {repr(parsed_val)}.",
                        variable_state=dict(variable_state),
                        list_state=dict(list_state),
                        current_function=current_function,
                        output=output_buffer or None,
                    )
                )
                step_num += 1
                continue

        # 7. Default generic statement step
        trace.append(
            TraceEvent(
                step_number=step_num,
                event_type="assignment",
                line_number=line_idx,
                description=f"Executes statement on line {line_idx}.",
                variable_state=dict(variable_state),
                list_state=dict(list_state),
                current_function=current_function,
                output=output_buffer or None,
            )
        )
        step_num += 1

    # Final completed step
    last_line = len(lines)
    for idx in range(len(lines), 0, -1):
        if lines[idx - 1].strip():
            last_line = idx
            break

    trace.append(
        TraceEvent(
            step_number=step_num,
            event_type="completed",
            line_number=last_line,
            description="Algorithm execution completed.",
            variable_state=dict(variable_state),
            list_state=dict(list_state),
            current_function=None,
            output=output_buffer or None,
        )
    )

    return VisualizeResponse(
        status="success",
        supported=True,
        trace=trace,
        total_steps=len(trace),
        final_state=dict(variable_state),
        termination_reason="completed",
    )


def visualize_any_code(code: str, language: str = "Python") -> VisualizeResponse:
    """
    Main entry point for multi-language algorithm visualization.
    Allows ALL types of code to be visualized:
    1. If language is Python and conforms to restricted AST, uses ultra-fast deterministic tracer.
    2. If language is not Python, or Python code uses constructs outside AST allowlist,
       uses LLM-powered execution tracing.
    3. If LLM tracing is unavailable or encounters limits, falls back to universal heuristic tracer.
    """
    lang_clean = (language or "Python").strip()
    is_python = lang_clean.lower() == "python"

    if is_python:
        try:
            res = trace_python_code(code)
            if res.status == "success":
                return res
        except Exception as e:
            logger.debug(f"Python AST tracer could not trace code, proceeding to universal tracer: {e}")

    # For non-Python code, or Python code outside restricted AST, use multi-language tracer
    llm_res = trace_code_with_llm(code, lang_clean)
    if llm_res and llm_res.status == "success" and len(llm_res.trace) > 0:
        return llm_res

    # Deterministic universal heuristic fallback (guaranteed to succeed offline or online)
    return trace_code_heuristically(code, lang_clean)

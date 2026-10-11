import re
from typing import List, Dict, Any, Tuple, Optional, Set
from app.services.static_analyzer.models import (
    StaticAnalysisResult,
    StaticIssue,
    LoopAnalysis,
    ConditionalAnalysis,
    ComplexityEvidenceData,
)

GENERIC_KEYWORDS = {
    "if", "else", "for", "while", "do", "switch", "case", "default", "break",
    "continue", "return", "try", "catch", "finally", "throw", "throws", "new",
    "class", "struct", "interface", "enum", "public", "private", "protected",
    "static", "final", "const", "let", "var", "val", "fn", "fun", "func",
    "function", "import", "package", "namespace", "using", "include", "use",
    "void", "int", "float", "double", "char", "bool", "boolean", "string",
    "String", "auto", "select", "from", "where", "group", "by", "order",
}


def _strip_comments_and_strings(code: str, language: str) -> str:
    """
    Replace strings and comments with spaces to preserve character positions
    while preventing keywords inside strings/comments from being detected.
    """
    chars = list(code)
    n = len(chars)
    i = 0

    while i < n:
        # Single-line comment: // or # (PHP) or -- (SQL)
        if (i + 1 < n and chars[i] == "/" and chars[i + 1] == "/") or \
           (language.lower() == "sql" and i + 1 < n and chars[i] == "-" and chars[i + 1] == "-") or \
           (language.lower() == "php" and chars[i] == "#"):
            while i < n and chars[i] != "\n":
                chars[i] = " "
                i += 1
            continue

        # Multi-line comment: /* ... */
        if i + 1 < n and chars[i] == "/" and chars[i + 1] == "*":
            chars[i] = " "
            chars[i + 1] = " "
            i += 2
            while i + 1 < n and not (chars[i] == "*" and chars[i + 1] == "/"):
                if chars[i] != "\n":
                    chars[i] = " "
                i += 1
            if i + 1 < n:
                chars[i] = " "
                chars[i + 1] = " "
                i += 2
            continue

        # String literals: "...", '...', `...`
        if chars[i] in ('"', "'", "`"):
            quote = chars[i]
            chars[i] = " "
            i += 1
            while i < n and chars[i] != quote:
                if chars[i] == "\\" and i + 1 < n:
                    chars[i] = " "
                    chars[i + 1] = " "
                    i += 2
                else:
                    if chars[i] != "\n":
                        chars[i] = " "
                    i += 1
            if i < n:
                chars[i] = " "
                i += 1
            continue

        i += 1

    return "".join(chars)


def _find_brace_body(code: str, start_pos: int) -> Tuple[int, int, str]:
    """
    Find opening brace and matching closing brace starting from start_pos.
    Returns (open_pos, close_pos, body_content).
    """
    if start_pos < 0 or start_pos >= len(code):
        return -1, -1, ""

    if code[start_pos] == "{":
        open_brace = start_pos
    else:
        open_brace = code.find("{", start_pos)

    if open_brace == -1:
        # Check for single-statement body ending at semicolon
        semi = code.find(";", start_pos)
        if semi != -1:
            return start_pos, semi + 1, code[start_pos:semi + 1]
        return -1, -1, ""

    depth = 1
    pos = open_brace + 1
    n = len(code)
    while pos < n and depth > 0:
        if code[pos] == "{":
            depth += 1
        elif code[pos] == "}":
            depth -= 1
        pos += 1

    close_pos = pos if depth == 0 else n
    return open_brace, close_pos, code[open_brace:close_pos]


def _extract_loops(code: str, clean_code: str, language: str) -> Tuple[LoopAnalysis, List[Tuple[int, int]]]:
    """Find loops, their spans, count, and nesting."""
    loop_spans: List[Tuple[int, int]] = []
    loop_types: List[str] = []

    # Patterns for loops across C-family, Go, Rust, Kotlin, Swift, PHP, SQL
    loop_patterns = [
        (r"\bfor\s*\(", "for"),
        (r"\bfor\s+[a-zA-Z_]\w*\s+(?:in|of)\s+", "for"),
        (r"\bfor\s+[a-zA-Z_]\w*\s*:=", "for"),
        (r"\bfor\s*\{", "for"),
        (r"\bloop\s*\{", "loop"),
        (r"\bwhile\s*\(", "while"),
        (r"\bwhile\s+[^{;]+", "while"),
        (r"\bdo\s*\{", "do-while"),
    ]

    if language.lower() == "sql":
        loop_patterns = [(r"\bWHILE\s+", "while")]

    seen_starts: Set[int] = set()

    for pattern, l_type in loop_patterns:
        for m in re.finditer(pattern, clean_code, re.IGNORECASE):
            start = m.start()
            if start in seen_starts:
                continue
            seen_starts.add(start)

            # Find body
            search_start = m.end() - 1 if m.group(0).endswith("{") else m.end()
            open_pos, close_pos, _ = _find_brace_body(clean_code, search_start)
            if open_pos != -1:
                loop_spans.append((start, close_pos))
                loop_types.append(l_type)

    loop_spans.sort(key=lambda s: s[0])
    count = len(loop_spans)

    # Check nesting: A loop is nested if its start is inside another loop's span
    has_nested = False
    for i, span_a in enumerate(loop_spans):
        for j, span_b in enumerate(loop_spans):
            if i != j and span_b[0] > span_a[0] and span_b[1] <= span_a[1]:
                has_nested = True
                break
        if has_nested:
            break

    sequential = count > 1 and not has_nested

    return LoopAnalysis(
        count=count,
        nested=has_nested,
        sequential_count=count if sequential else (1 if count > 0 else 0),
        loop_types=loop_types,
    ), loop_spans


def _extract_functions(code: str, clean_code: str, language: str) -> List[Dict[str, Any]]:
    """Extract functions across the 12 non-Python supported languages."""
    functions: List[Dict[str, Any]] = []
    seen_names: Set[str] = set()

    patterns = []
    lang_lower = language.lower()

    if lang_lower in ("javascript", "typescript"):
        patterns = [
            # function foo(a, b)
            r"\bfunction\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)",
            # const foo = (a, b) =>
            r"(?:const|let|var)\s+([a-zA-Z_]\w*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>",
            # foo(a, b) {
            r"\b([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*\{",
        ]
    elif lang_lower == "go":
        patterns = [
            r"\bfunc\s+(?:\([^)]*\)\s+)?([a-zA-Z_]\w*)\s*\(([^)]*)\)",
        ]
    elif lang_lower == "rust":
        patterns = [
            r"\bfn\s+([a-zA-Z_]\w*)\s*(?:<[^>]+>)?\s*\(([^)]*)\)",
        ]
    elif lang_lower == "kotlin":
        patterns = [
            r"\bfun\s+([a-zA-Z_]\w*)\s*(?:<[^>]+>)?\s*\(([^)]*)\)",
        ]
    elif lang_lower == "swift":
        patterns = [
            r"\bfunc\s+([a-zA-Z_]\w*)\s*(?:<[^>]+>)?\s*\(([^)]*)\)",
        ]
    elif lang_lower == "php":
        patterns = [
            r"\bfunction\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)",
        ]
    elif lang_lower in ("c", "c++", "java", "c#"):
        patterns = [
            r"\b(?:[a-zA-Z_]\w*(?:<[^>]+>)?(?:\[\])?)\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)\s*(?:const)?\s*(?:throws\s+[a-zA-Z0-9_,\s]+)?\s*\{",
        ]
    elif lang_lower == "sql":
        patterns = [
            r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+([a-zA-Z_]\w*)\s*\(([^)]*)\)",
        ]

    for pat in patterns:
        for m in re.finditer(pat, clean_code):
            name = m.group(1).strip()
            if not name or name in GENERIC_KEYWORDS or name in seen_names:
                continue

            raw_params = m.group(2) if len(m.groups()) >= 2 else ""
            params = [p.strip() for p in raw_params.split(",") if p.strip()]

            # Find function body span
            search_start = m.end() - 1 if m.group(0).endswith("{") else m.end()
            open_pos, close_pos, body = _find_brace_body(clean_code, search_start)

            seen_names.add(name)
            functions.append({
                "name": name,
                "parameters": params,
                "has_return": bool(re.search(r"\breturn\b", body)) if body else False,
                "body": body,
                "span": (m.start(), close_pos),
            })

    return functions


def _extract_variables(clean_code: str, language: str) -> List[str]:
    """Extract variable declarations across languages."""
    variables: List[str] = []
    seen: Set[str] = set()

    lang_lower = language.lower()
    patterns = []

    if lang_lower in ("javascript", "typescript"):
        patterns = [r"\b(?:let|const|var)\s+([a-zA-Z_]\w*)"]
    elif lang_lower == "rust":
        patterns = [r"\blet\s+(?:mut\s+)?([a-zA-Z_]\w*)"]
    elif lang_lower == "go":
        patterns = [r"\b([a-zA-Z_]\w*)\s*:=", r"\bvar\s+([a-zA-Z_]\w*)"]
    elif lang_lower in ("kotlin", "swift"):
        patterns = [r"\b(?:val|var|let)\s+([a-zA-Z_]\w*)"]
    elif lang_lower == "php":
        patterns = [r"\$([a-zA-Z_]\w*)"]
    elif lang_lower in ("c", "c++", "java", "c#"):
        patterns = [
            r"\b(?:int|long|short|float|double|char|bool|boolean|byte|auto|String|string|var|std::string|size_t|uint32_t|int32_t|int64_t)\s+([a-zA-Z_]\w*)\s*(?:=|[;,])",
        ]
    elif lang_lower == "sql":
        patterns = [r"\bDECLARE\s+([a-zA-Z_@]\w*)"]

    for pat in patterns:
        for m in re.finditer(pat, clean_code):
            name = m.group(1).strip()
            if name and name not in GENERIC_KEYWORDS and name not in seen:
                seen.add(name)
                variables.append(name)

    return variables


def _extract_conditionals(clean_code: str, language: str) -> ConditionalAnalysis:
    """Extract conditional statements (if, else if, else, switch)."""
    count = 0
    has_else = False
    has_elif = False

    if language.lower() == "sql":
        count = len(re.findall(r"\bCASE\b|\bIF\b", clean_code, re.IGNORECASE))
        return ConditionalAnalysis(count=count)

    ifs = len(re.findall(r"\bif\s*\(|\bif\s+", clean_code))
    elifs = len(re.findall(r"\belse\s+if\b|\belif\b", clean_code))
    elses = len(re.findall(r"\belse\b", clean_code)) - elifs
    switches = len(re.findall(r"\bswitch\s*\(|\bswitch\s+|\bwhen\s*\{", clean_code))

    total = ifs + switches
    if total > 0:
        has_elif = elifs > 0
        has_else = elses > 0

    return ConditionalAnalysis(
        count=total,
        has_else=has_else,
        has_elif=has_elif,
    )


def _check_recursion(functions: List[Dict[str, Any]]) -> bool:
    """Check if any function calls itself within its body."""
    for fn in functions:
        name = fn["name"]
        body = fn.get("body", "")
        if body and re.search(r"\b" + re.escape(name) + r"\s*\(", body):
            return True
    return False


def _extract_imports(clean_code: str, language: str) -> List[str]:
    """Extract imported packages or included headers."""
    imports: List[str] = []
    lang_lower = language.lower()

    if lang_lower in ("c", "c++"):
        matches = re.findall(r'#include\s*([<"][^>"]+[>"])', clean_code)
        imports.extend(matches)
    elif lang_lower in ("java", "kotlin"):
        matches = re.findall(r"\bimport\s+([a-zA-Z0-9_.*]+);?", clean_code)
        imports.extend(matches)
    elif lang_lower == "c#":
        matches = re.findall(r"\busing\s+([a-zA-Z0-9_.]+);", clean_code)
        imports.extend(matches)
    elif lang_lower == "go":
        matches = re.findall(r'\bimport\s+(?:\(([^)]*)\)|"([^"]+)")', clean_code)
        for m in matches:
            if m[0]:
                for line in m[0].splitlines():
                    clean_line = line.strip().strip('"')
                    if clean_line:
                        imports.append(clean_line)
            elif m[1]:
                imports.append(m[1])
    elif lang_lower in ("rust", "php"):
        matches = re.findall(r"\buse\s+([a-zA-Z0-9_\\:]+);", clean_code)
        imports.extend(matches)
    elif lang_lower in ("javascript", "typescript"):
        matches = re.findall(r'\bimport\s+.*?from\s+[\'"]([^\'"]+)[\'"]|\brequire\s*\([\'"]([^\'"]+)[\'"]\)', clean_code)
        for m in matches:
            imports.append(m[0] or m[1])
    elif lang_lower == "swift":
        matches = re.findall(r"\bimport\s+([a-zA-Z0-9_]+)", clean_code)
        imports.extend(matches)

    return imports


def _extract_classes(clean_code: str) -> List[str]:
    """Extract classes, structs, or interfaces."""
    matches = re.findall(r"\b(?:class|struct|interface|record|enum)\s+([a-zA-Z_]\w*)", clean_code)
    return [m for m in matches if m not in GENERIC_KEYWORDS]


def _detect_sorting_searching(clean_code: str, language: str) -> Tuple[bool, bool]:
    """Detect sorting and searching calls across languages."""
    sort_pattern = r"\.sort\(|\bsort\(|Arrays\.sort|Collections\.sort|std::sort|sort\.Slice|ORDER\s+BY"
    search_pattern = r"\.indexOf\(|\.includes\(|\.contains\(|\.find\(|binary_search|bsearch|std::binary_search|WHERE\b"

    sorting = bool(re.search(sort_pattern, clean_code, re.IGNORECASE))
    searching = bool(re.search(search_pattern, clean_code, re.IGNORECASE))
    return sorting, searching


def _detect_issues(code: str, clean_code: str, language: str, functions: List[Dict[str, Any]]) -> List[StaticIssue]:
    """Detect deterministic issues (assignment in conditional, empty catch, infinite loops, unreachable code)."""
    issues: List[StaticIssue] = []
    lang_lower = language.lower()

    # 1. Assignment in condition: if (x = 5)
    if lang_lower in ("c", "c++", "java", "c#", "javascript", "typescript", "php"):
        assign_in_if = re.search(r"\bif\s*\(\s*([a-zA-Z_]\w*)\s*=\s*([^=][^)]*)\)", clean_code)
        if assign_in_if:
            issues.append(StaticIssue(
                type="definite",
                severity="high",
                description=f"Assignment operator '=' used in conditional statement instead of equality operator '=='.",
            ))

    # 2. Empty catch block: catch (...) {}
    empty_catch = re.search(r"\bcatch\s*(?:\([^)]*\))?\s*\{\s*\}", clean_code)
    if empty_catch:
        issues.append(StaticIssue(
            type="definite",
            severity="medium",
            description="Empty catch block: catches exceptions and silently suppresses them.",
        ))

    # 3. Unreachable code after return / break / continue
    unreachable = re.search(r"\b(?:return(?:\s+[^;]*)?|break|continue)\s*;\s*([a-zA-Z_]\w*[^;]*;)", clean_code)
    if unreachable:
        issues.append(StaticIssue(
            type="definite",
            severity="high",
            description=f"Unreachable code detected after terminating statement.",
        ))

    # 4. Suspicious infinite loop: while(true) {} or for(;;) {} without break or return
    inf_loop_matches = re.finditer(r"\b(?:while\s*\(\s*(?:true|1)\s*\)|for\s*\(\s*;\s*;\s*\))\s*\{", clean_code, re.IGNORECASE)
    for m in inf_loop_matches:
        open_pos, close_pos, body = _find_brace_body(clean_code, m.end() - 1)
        if body and not re.search(r"\b(?:break|return|exit|goto)\b", body):
            issues.append(StaticIssue(
                type="possible",
                severity="medium",
                description="Suspicious infinite loop: loop condition is always true with no break or return statement.",
            ))
            break

    # 5. Unbalanced braces or parentheses (only for multi-line snippets)
    lines = code.strip().splitlines()
    if len(lines) > 2:
        open_braces = clean_code.count("{") - clean_code.count("}")
        open_parens = clean_code.count("(") - clean_code.count(")")
        if open_braces > 0:
            issues.append(StaticIssue(
                type="possible",
                severity="medium",
                description=f"Unclosed curly brace detected ({open_braces} unmatched '{{').",
            ))
        elif open_parens > 0:
            issues.append(StaticIssue(
                type="possible",
                severity="medium",
                description=f"Unclosed parenthesis detected ({open_parens} unmatched '(').",
            ))

    return issues


def analyze_generic(code: str, language: str) -> StaticAnalysisResult:
    """Analyze non-Python code using deterministic structural analysis."""
    clean_code = _strip_comments_and_strings(code, language)

    functions = _extract_functions(code, clean_code, language)
    variables = _extract_variables(clean_code, language)
    classes = _extract_classes(clean_code)
    imports = _extract_imports(clean_code, language)
    loop_info, loop_spans = _extract_loops(code, clean_code, language)
    cond_info = _extract_conditionals(clean_code, language)
    recursion = _check_recursion(functions)
    sorting, searching = _detect_sorting_searching(clean_code, language)
    issues = _detect_issues(code, clean_code, language, functions)

    # Determine parse status
    # If the snippet has functions/classes or main, or valid partial statements
    has_structure = bool(functions or variables or loop_info.count > 0 or cond_info.count > 0 or imports)
    has_enclosing = bool(functions or classes or re.search(r"\bmain\s*\(", clean_code))

    if has_enclosing:
        parse_status = "success"
    elif has_structure:
        parse_status = "partial"
    else:
        parse_status = "unavailable"

    parameters = [p for f in functions for p in f.get("parameters", [])]

    # Clean function objects
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
        nested_loops=loop_info.nested,
        recursion_detected=recursion,
        sorting_detected=sorting,
        searching_detected=searching,
        sequential_loops=loop_info.count > 1 and not loop_info.nested,
    )

    return StaticAnalysisResult(
        language=language,
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

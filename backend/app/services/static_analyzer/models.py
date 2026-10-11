from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from app.models.analysis import StaticAnalysisData, StructureSummary, ComplexityEvidence


@dataclass
class StaticIssue:
    """Internal representation of a statically identified bug or issue."""
    type: str  # "definite" or "possible"
    severity: str  # "high", "medium", or "low"
    description: str
    line: Optional[int] = None


@dataclass
class LoopAnalysis:
    """Internal loop structure information."""
    count: int = 0
    nested: bool = False
    sequential_count: int = 0
    loop_types: List[str] = field(default_factory=list)


@dataclass
class ConditionalAnalysis:
    """Internal conditional statement information."""
    count: int = 0
    has_else: bool = False
    has_elif: bool = False


@dataclass
class ComplexityEvidenceData:
    """Internal complexity indicators."""
    loops: int = 0
    nested_loops: bool = False
    recursion_detected: bool = False
    sorting_detected: bool = False
    searching_detected: bool = False
    sequential_loops: bool = False


@dataclass
class StaticAnalysisResult:
    """Comprehensive static code analysis result."""
    language: str
    parse_status: str = "success"  # "success", "partial", "unavailable"
    variables: List[str] = field(default_factory=list)
    functions: List[Dict[str, Any]] = field(default_factory=list)
    parameters: List[str] = field(default_factory=list)
    return_statements: List[str] = field(default_factory=list)
    loops: LoopAnalysis = field(default_factory=LoopAnalysis)
    conditionals: ConditionalAnalysis = field(default_factory=ConditionalAnalysis)
    recursion_detected: bool = False
    imports: List[str] = field(default_factory=list)
    classes: List[str] = field(default_factory=list)
    data_structures: List[str] = field(default_factory=list)
    complexity_evidence: ComplexityEvidenceData = field(default_factory=ComplexityEvidenceData)
    issues: List[StaticIssue] = field(default_factory=list)

    def to_prompt_summary(self) -> str:
        """Format a clear, concise bulleted summary of deterministic facts for the Gemini prompt."""
        if self.parse_status == "unavailable":
            return "Static analysis was unavailable for this snippet. Analyze structure and complexity directly from source code."

        summary_lines = []
        status_note = " (partial snippet)" if self.parse_status == "partial" else ""
        summary_lines.append(f"- Status: Parse {self.parse_status}{status_note}")

        # Functions & Variables
        func_count = len(self.functions)
        func_names = [f["name"] for f in self.functions if "name" in f]
        if func_count > 0:
            summary_lines.append(f"- Functions ({func_count}): {', '.join(func_names)}")
        else:
            summary_lines.append("- Functions: 0 detected")

        var_count = len(self.variables)
        if var_count > 0:
            # show up to 6 variable names
            display_vars = self.variables[:6]
            if len(self.variables) > 6:
                display_vars.append(f"...+{len(self.variables) - 6} more")
            summary_lines.append(f"- Variables ({var_count}): {', '.join(display_vars)}")
        else:
            summary_lines.append("- Variables: 0 detected")

        # Loops & Nesting
        if self.loops.count > 0:
            nesting_str = "yes (nested loops present)" if self.loops.nested else "no nesting (single/sequential)"
            summary_lines.append(f"- Loops ({self.loops.count}): nested={nesting_str}")
        else:
            summary_lines.append("- Loops: 0 detected")

        # Conditionals
        if self.conditionals.count > 0:
            summary_lines.append(f"- Conditionals: {self.conditionals.count} detected")
        else:
            summary_lines.append("- Conditionals: 0 detected")

        # Recursion
        if self.recursion_detected:
            summary_lines.append("- Recursion: YES (recursive call detected)")
        else:
            summary_lines.append("- Recursion: no recursive calls detected")

        # Complexity indicators
        evidence = self.complexity_evidence
        comp_details = []
        if evidence.loops > 0:
            comp_details.append(f"{evidence.loops} loop(s)")
        if evidence.nested_loops:
            comp_details.append("nested loops")
        if evidence.sequential_loops:
            comp_details.append("sequential loops")
        if evidence.recursion_detected:
            comp_details.append("recursion")
        if evidence.sorting_detected:
            comp_details.append("sorting call detected (e.g. O(n log n))")
        if evidence.searching_detected:
            comp_details.append("searching operation detected")

        if comp_details:
            summary_lines.append(f"- Complexity evidence: {', '.join(comp_details)}")
        else:
            summary_lines.append("- Complexity evidence: No loops, recursion, or heavy operations detected. Insufficient for algorithmic complexity.")

        # Classes & Imports
        if self.classes:
            summary_lines.append(f"- Classes ({len(self.classes)}): {', '.join(self.classes)}")
        if self.imports:
            summary_lines.append(f"- Imports/Includes: {len(self.imports)} detected")

        # Issues
        if self.issues:
            issue_strs = [f"[{issue.type.upper()}] {issue.description}" for issue in self.issues]
            summary_lines.append(f"- Static issue checks: {'; '.join(issue_strs)}")
        else:
            summary_lines.append("- Static issue checks: No definite syntax/structural issues detected")

        return "\n".join(summary_lines)

    def to_api_response(self) -> StaticAnalysisData:
        """Map to public Pydantic API response model."""
        if self.parse_status == "unavailable":
            return StaticAnalysisData(parse_status="unavailable")

        return StaticAnalysisData(
            parse_status=self.parse_status,
            structure=StructureSummary(
                variables=len(self.variables),
                functions=len(self.functions),
                loops=self.loops.count,
                conditionals=self.conditionals.count,
                recursion=self.recursion_detected,
                classes=len(self.classes) if self.classes else 0,
                imports=len(self.imports) if self.imports else 0,
            ),
            complexity_evidence=ComplexityEvidence(
                loops=self.complexity_evidence.loops,
                nested_loops=self.complexity_evidence.nested_loops,
                recursion_detected=self.complexity_evidence.recursion_detected,
                sorting_detected=self.complexity_evidence.sorting_detected,
                searching_detected=self.complexity_evidence.searching_detected,
                sequential_loops=self.complexity_evidence.sequential_loops,
            ),
        )

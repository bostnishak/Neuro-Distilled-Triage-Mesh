from typing import Dict, Optional
from compiler.ast_nodes import (
    ASTNode,
    LiteralNode,
    VariableNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
    IfThenElseNode,
)
from core.exceptions import RuleCompilationError

# Standard schema symbol table for NDTM rule environments
STANDARD_ENV: Dict[str, str] = {
    "urgency": "STRING",
    "category": "STRING",
    "modality": "STRING",
    "triage_confidence": "FLOAT",
    "divergence_score": "FLOAT",
    "optical_blur_score": "FLOAT",
    "hawkes_intensity": "FLOAT",
    "incident_count": "INT",
    "burnout_index": "FLOAT",
    "criticality": "FLOAT",
    "failure_probability": "FLOAT",
    "is_night_shift": "BOOL",
    "latitude": "FLOAT",
    "longitude": "FLOAT",
}


class TypeChecker:
    """Performs static type analysis and semantic invariant checks on AST."""

    def __init__(self, symbol_table: Optional[Dict[str, str]] = None):
        self.symbols = dict(STANDARD_ENV)
        if symbol_table:
            self.symbols.update(symbol_table)

    def check(self, node: ASTNode) -> str:
        """Type-checks an AST node recursively and returns its inferred type."""
        if isinstance(node, LiteralNode):
            return node.type_name

        elif isinstance(node, VariableNode):
            var_type = self.symbols.get(node.name)
            if var_type is None:
                # Default unknown variable to STRING or ANY if not declared
                return "STRING"
            return var_type

        elif isinstance(node, UnaryOpNode):
            operand_type = self.check(node.operand)
            if node.op == "NOT":
                if operand_type != "BOOL":
                    raise RuleCompilationError(f"Unary NOT expects BOOL, got {operand_type}", 0, 0)
                return "BOOL"
            elif node.op == "-":
                if operand_type not in ("INT", "FLOAT"):
                    raise RuleCompilationError(f"Unary '-' expects INT or FLOAT, got {operand_type}", 0, 0)
                return operand_type
            raise RuleCompilationError(f"Unsupported unary operator: {node.op}", 0, 0)

        elif isinstance(node, BinaryOpNode):
            left_type = self.check(node.left)
            right_type = self.check(node.right)

            # Arithmetic (+, -, *, /)
            if node.op in ("+", "-", "*", "/"):
                if left_type not in ("INT", "FLOAT") or right_type not in ("INT", "FLOAT"):
                    if node.op == "+" and (left_type == "STRING" or right_type == "STRING"):
                        return "STRING"  # string concatenation
                    raise RuleCompilationError(
                        f"Arithmetic '{node.op}' incompatible with {left_type} and {right_type}", 0, 0
                    )
                return "FLOAT" if "FLOAT" in (left_type, right_type) else "INT"

            # Equality (==, !=)
            if node.op in ("==", "!="):
                return "BOOL"

            # Relational (<, <=, >, >=)
            if node.op in ("<", "<=", ">", ">="):
                if left_type not in ("INT", "FLOAT") or right_type not in ("INT", "FLOAT"):
                    raise RuleCompilationError(
                        f"Relational '{node.op}' requires numeric types, got {left_type} and {right_type}", 0, 0
                    )
                return "BOOL"

            # Logical (AND, OR)
            if node.op in ("AND", "OR"):
                if left_type != "BOOL" or right_type != "BOOL":
                    raise RuleCompilationError(
                        f"Logical '{node.op}' requires BOOL operands, got {left_type} and {right_type}", 0, 0
                    )
                return "BOOL"

            raise RuleCompilationError(f"Unknown binary operator '{node.op}'", 0, 0)

        elif isinstance(node, FunctionCallNode):
            if node.func_name == "WITHIN_METERS":
                if len(node.args) != 3:
                    raise RuleCompilationError(f"WITHIN_METERS requires 3 args, got {len(node.args)}", 0, 0)
                return "BOOL"
            elif node.func_name == "HAVERSINE":
                return "FLOAT"
            return "BOOL"

        elif isinstance(node, IfThenElseNode):
            cond_type = self.check(node.condition)
            if cond_type != "BOOL":
                raise RuleCompilationError(f"IF condition must be BOOL, got {cond_type}", 0, 0)
            then_type = self.check(node.then_branch)
            if node.else_branch:
                else_type = self.check(node.else_branch)
                if then_type != else_type:
                    raise RuleCompilationError(
                        f"IF branches type mismatch: {then_type} vs {else_type}", 0, 0
                    )
            return then_type

        raise RuleCompilationError(f"Unknown AST node type: {type(node).__name__}", 0, 0)

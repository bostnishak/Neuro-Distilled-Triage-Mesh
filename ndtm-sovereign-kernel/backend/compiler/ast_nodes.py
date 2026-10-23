from dataclasses import dataclass
from typing import Any, List, Optional


@dataclass
class ASTNode:
    """Base class for all NDTM-RuleLang AST nodes."""
    pass


@dataclass
class LiteralNode(ASTNode):
    value: Any
    type_name: str  # "INT", "FLOAT", "STRING", "BOOL"


@dataclass
class VariableNode(ASTNode):
    name: str


@dataclass
class BinaryOpNode(ASTNode):
    left: ASTNode
    op: str  # "+", "-", "*", "/", "==", "!=", "<", "<=", ">", ">=", "AND", "OR"
    right: ASTNode


@dataclass
class UnaryOpNode(ASTNode):
    op: str  # "-", "NOT"
    operand: ASTNode


@dataclass
class FunctionCallNode(ASTNode):
    func_name: str  # e.g., "WITHIN_METERS", "HAVERSINE", "GET_URGENCY"
    args: List[ASTNode]


@dataclass
class IfThenElseNode(ASTNode):
    condition: ASTNode
    then_branch: ASTNode
    else_branch: Optional[ASTNode] = None

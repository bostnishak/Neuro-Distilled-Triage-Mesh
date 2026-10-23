from typing import Any, Dict, List, Tuple
from compiler.ast_nodes import (
    ASTNode,
    LiteralNode,
    VariableNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
)


class SQLCodeGen:
    """Compiles NDTM-RuleLang AST into parameterized PostgreSQL/PostGIS WHERE clauses."""

    def __init__(self):
        self.params: Dict[str, Any] = {}
        self._param_counter = 0

    def _next_param_name(self) -> str:
        self._param_counter += 1
        return f"p_{self._param_counter}"

    def compile(self, node: ASTNode) -> Tuple[str, Dict[str, Any]]:
        self.params.clear()
        self._param_counter = 0
        sql = self._compile_node(node)
        return sql, dict(self.params)

    def _compile_node(self, node: ASTNode) -> str:
        if isinstance(node, LiteralNode):
            p_name = self._next_param_name()
            self.params[p_name] = node.value
            return f":{p_name}"

        elif isinstance(node, VariableNode):
            # Map rule variables to column names in incidents table
            col_map = {
                "urgency": "incidents.urgency",
                "category": "incidents.category",
                "modality": "incidents.modality",
                "triage_confidence": "incidents.triage_confidence",
                "divergence_score": "incidents.divergence_score",
                "optical_blur_score": "incidents.optical_blur_score",
                "created_at": "incidents.created_at",
            }
            return col_map.get(node.name, f"incidents.{node.name}")

        elif isinstance(node, UnaryOpNode):
            sub = self._compile_node(node.operand)
            if node.op == "NOT":
                return f"(NOT {sub})"
            elif node.op == "-":
                return f"(-{sub})"

        elif isinstance(node, BinaryOpNode):
            left_sql = self._compile_node(node.left)
            right_sql = self._compile_node(node.right)

            op_map = {
                "==": "=",
                "!=": "!=",
                "<": "<",
                "<=": "<=",
                ">": ">",
                ">=": ">=",
                "+": "+",
                "-": "-",
                "*": "*",
                "/": "/",
                "AND": "AND",
                "OR": "OR",
            }
            sql_op = op_map.get(node.op, node.op)
            return f"({left_sql} {sql_op} {right_sql})"

        elif isinstance(node, FunctionCallNode):
            if node.func_name == "WITHIN_METERS":
                # WITHIN_METERS(location, target_point, radius_meters)
                point_a = self._compile_node(node.args[0])
                point_b = self._compile_node(node.args[1])
                dist = self._compile_node(node.args[2])
                return f"ST_DWithin({point_a}, {point_b}, {dist}, true)"

        raise ValueError(f"Unsupported AST node for SQL codegen: {type(node).__name__}")

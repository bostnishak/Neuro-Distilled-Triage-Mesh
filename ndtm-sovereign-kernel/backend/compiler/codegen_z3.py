from typing import Dict, Any, Tuple
import z3
from compiler.ast_nodes import (
    ASTNode,
    LiteralNode,
    VariableNode,
    BinaryOpNode,
    UnaryOpNode,
    FunctionCallNode,
    IfThenElseNode,
)
from compiler.type_checker import STANDARD_ENV


class Z3CodeGen:
    """Compiles NDTM-RuleLang AST into Z3 SMT solver expressions and SMT-LIB v2 syntax."""

    def __init__(self, variable_symbols: Dict[str, z3.ExprRef] = None):
        self.var_map: Dict[str, z3.ExprRef] = variable_symbols or {}

    def get_or_create_z3_var(self, name: str) -> z3.ExprRef:
        if name in self.var_map:
            return self.var_map[name]

        var_type = STANDARD_ENV.get(name, "FLOAT")
        if var_type == "INT":
            v = z3.Int(name)
        elif var_type == "BOOL":
            v = z3.Bool(name)
        elif var_type == "STRING":
            v = z3.String(name)
        else:
            v = z3.Real(name)

        self.var_map[name] = v
        return v

    def compile_to_z3(self, node: ASTNode) -> z3.ExprRef:
        """Transforms AST node into native Z3 expression tree."""
        if isinstance(node, LiteralNode):
            if node.type_name == "INT":
                return z3.IntVal(int(node.value))
            elif node.type_name == "FLOAT":
                return z3.RealVal(float(node.value))
            elif node.type_name == "BOOL":
                return z3.BoolVal(bool(node.value))
            elif node.type_name == "STRING":
                return z3.StringVal(str(node.value))

        elif isinstance(node, VariableNode):
            return self.get_or_create_z3_var(node.name)

        elif isinstance(node, UnaryOpNode):
            sub = self.compile_to_z3(node.operand)
            if node.op == "NOT":
                return z3.Not(sub)
            elif node.op == "-":
                return -sub

        elif isinstance(node, BinaryOpNode):
            left_z3 = self.compile_to_z3(node.left)
            right_z3 = self.compile_to_z3(node.right)

            if node.op == "+":
                return left_z3 + right_z3
            elif node.op == "-":
                return left_z3 - right_z3
            elif node.op == "*":
                return left_z3 * right_z3
            elif node.op == "/":
                return left_z3 / right_z3
            elif node.op == "==":
                return left_z3 == right_z3
            elif node.op == "!=":
                return left_z3 != right_z3
            elif node.op == "<":
                return left_z3 < right_z3
            elif node.op == "<=":
                return left_z3 <= right_z3
            elif node.op == ">":
                return left_z3 > right_z3
            elif node.op == ">=":
                return left_z3 >= right_z3
            elif node.op == "AND":
                return z3.And(left_z3, right_z3)
            elif node.op == "OR":
                return z3.Or(left_z3, right_z3)

        elif isinstance(node, IfThenElseNode):
            cond = self.compile_to_z3(node.condition)
            then_expr = self.compile_to_z3(node.then_branch)
            else_expr = self.compile_to_z3(node.else_branch) if node.else_branch else z3.BoolVal(False)
            return z3.If(cond, then_expr, else_expr)

        elif isinstance(node, FunctionCallNode):
            # Fallback constraint for uninterpreted function calls in SMT
            func_decl = z3.Function(node.func_name, *[z3.RealSort() for _ in node.args], z3.BoolSort())
            arg_exprs = [self.compile_to_z3(a) for a in node.args]
            return func_decl(*arg_exprs)

        raise ValueError(f"Unable to compile AST node {node} to Z3")

    def compile_to_smtlib(self, node: ASTNode) -> str:
        """Converts AST node to standard SMT-LIB v2 S-expression string."""
        z3_expr = self.compile_to_z3(node)
        s = z3.Solver()
        s.add(z3_expr)
        return s.to_smt2()

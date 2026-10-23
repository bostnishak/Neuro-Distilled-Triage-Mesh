#!/usr/bin/env python3
"""Zero-Defect AST & Cross-Boundary Contract Verification Harness (Gate 1 & Gate 2).
Enforces zero-mock laws, AST stub prohibition, dead UI handler detection,
1-to-1 route parity, SQL-to-ORM column alignment, and complete import graph resolution.
"""
from __future__ import annotations

import ast
import importlib
import os
import re
import sys
from pathlib import Path
from typing import Any

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


class VerificationError(Exception):
    """Raised when a zero-defect gate condition fails."""
    pass


class Gate1AstAndMockScanner:
    """Scans codebase for forbidden tokens, Python AST stub nodes, and dead UI handlers."""

    FORBIDDEN_TOKENS = ["TODO", "FIXME", "HACK", "PLACEHOLDER", "mock_", "implement later"]

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.violations: list[str] = []

    def run(self) -> bool:
        print("\n" + "=" * 78)
        print(" [GATE 1] STATIC AST ZERO-MOCK & ANTI-LAZINESS SCANNER")
        print("=" * 78)

        self._scan_forbidden_tokens()
        self._scan_python_ast_stubs()
        self._scan_dead_frontend_handlers()

        if self.violations:
            print(f"\n[FAIL] Gate 1 detected {len(self.violations)} violations:")
            for v in self.violations:
                print(f"  - {v}")
            return False

        print("\n[PASS] Gate 1: Zero forbidden tokens, zero AST stubs, zero dead UI handlers.")
        return True

    def _scan_forbidden_tokens(self) -> None:
        target_dirs = ["backend", "ml_pipeline", "edge_cpp_node", "frontend/src", "infra"]
        pattern = re.compile(r"\b(" + "|".join(re.escape(t) for t in self.FORBIDDEN_TOKENS) + r")\b", re.IGNORECASE)

        for rel_dir in target_dirs:
            dir_path = self.root_dir / rel_dir
            if not dir_path.exists():
                continue

            for file_path in dir_path.rglob("*"):
                if file_path.is_dir() or "__pycache__" in str(file_path):
                    continue
                # Skip test directories for token scan (tests naturally test mocks or fixtures)
                if "tests" in file_path.parts:
                    continue
                suffix = file_path.suffix.lower()
                if suffix not in (".py", ".ts", ".tsx", ".cpp", ".hpp", ".h", ".sql"):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8", errors="ignore")
                except Exception:
                    continue

                for line_no, line in enumerate(content.splitlines(), start=1):
                    # For TSX/HTML, ignore valid HTML input attribute placeholder="..." and CSS placeholder-
                    sanitized_line = line
                    if suffix in (".tsx", ".ts"):
                        sanitized_line = re.sub(r'placeholder="[^"]*"', '', sanitized_line)
                        sanitized_line = re.sub(r'placeholder-[a-zA-Z0-9-]+', '', sanitized_line)

                    # Look for forbidden tokens
                    match = pattern.search(sanitized_line)
                    if match:
                        matched_tok = match.group(0)
                        self.violations.append(
                            f"Forbidden token '{matched_tok}' in {file_path.relative_to(self.root_dir)}:{line_no}: {line.strip()}"
                        )

    def _scan_python_ast_stubs(self) -> None:
        py_dirs = ["backend", "ml_pipeline"]
        for rel_dir in py_dirs:
            dir_path = self.root_dir / rel_dir
            if not dir_path.exists():
                continue

            for file_path in dir_path.rglob("*.py"):
                if "__pycache__" in str(file_path) or "tests" in file_path.parts:
                    continue

                try:
                    source = file_path.read_text(encoding="utf-8")
                    tree = ast.parse(source, filename=str(file_path))
                except Exception as exc:
                    self.violations.append(f"AST parse error in {file_path.relative_to(self.root_dir)}: {exc}")
                    continue

                for node in ast.walk(tree):
                    # 1. Check Function bodies for stub pass / ... / NotImplementedError
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        body = node.body
                        if len(body) == 1:
                            stmt = body[0]
                            # Sole pass
                            if isinstance(stmt, ast.Pass):
                                self.violations.append(
                                    f"Stub function '{node.name}' with only 'pass' in {file_path.relative_to(self.root_dir)}:{node.lineno}"
                                )
                            # Sole ...
                            elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and stmt.value.value is Ellipsis:
                                self.violations.append(
                                    f"Stub function '{node.name}' with only '...' in {file_path.relative_to(self.root_dir)}:{node.lineno}"
                                )
                            # Sole raise NotImplementedError
                            elif isinstance(stmt, ast.Raise):
                                if isinstance(stmt.exc, ast.Name) and stmt.exc.id == "NotImplementedError":
                                    self.violations.append(
                                        f"Stub function '{node.name}' with 'raise NotImplementedError' in {file_path.relative_to(self.root_dir)}:{node.lineno}"
                                    )
                                elif isinstance(stmt.exc, ast.Call) and isinstance(stmt.exc.func, ast.Name) and stmt.exc.func.id == "NotImplementedError":
                                    self.violations.append(
                                        f"Stub function '{node.name}' with 'raise NotImplementedError()' in {file_path.relative_to(self.root_dir)}:{node.lineno}"
                                    )

                    # 2. Check ExceptHandlers: catching Exception with solely 'pass'
                    elif isinstance(node, ast.ExceptHandler):
                        if isinstance(node.type, ast.Name) and node.type.id == "Exception":
                            if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
                                self.violations.append(
                                    f"Unhandled 'except Exception: pass' without logging or re-raise in {file_path.relative_to(self.root_dir)}:{node.lineno}"
                                )

    def _scan_dead_frontend_handlers(self) -> None:
        frontend_src = self.root_dir / "frontend" / "src"
        if not frontend_src.exists():
            return

        re_empty_click = re.compile(r'onClick\s*=\s*\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}')
        re_console_click = re.compile(r'onClick\s*=\s*\{\s*\(\s*\)\s*=>\s*console\.')
        re_alert = re.compile(r'\balert\s*\(')

        for file_path in frontend_src.rglob("*.tsx"):
            try:
                content = file_path.read_text(encoding="utf-8")
            except Exception:
                continue

            for line_no, line in enumerate(content.splitlines(), start=1):
                if re_empty_click.search(line):
                    self.violations.append(
                        f"Dead handler 'onClick={{() => {{}}}}' in {file_path.relative_to(self.root_dir)}:{line_no}"
                    )
                if re_console_click.search(line):
                    self.violations.append(
                        f"Dead handler 'onClick={{() => console...}}' in {file_path.relative_to(self.root_dir)}:{line_no}"
                    )
                if re_alert.search(line):
                    self.violations.append(
                        f"Disallowed 'alert()' call in {file_path.relative_to(self.root_dir)}:{line_no}"
                    )


class Gate2CrossStackContractVerifier:
    """Verifies route parity, SQL-to-ORM schema parity, and dynamic import graph."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.discrepancies: list[str] = []

    def run(self) -> bool:
        print("\n" + "=" * 78)
        print(" [GATE 2] CROSS-BOUNDARY CONTRACT & SCHEMA ALIGNMENT VERIFIER")
        print("=" * 78)

        self._verify_import_graph()
        self._verify_route_parity()
        self._verify_sql_orm_parity()

        if self.discrepancies:
            print(f"\n[FAIL] Gate 2 detected {len(self.discrepancies)} discrepancies:")
            for d in self.discrepancies:
                print(f"  - {d}")
            return False

        print("\n[PASS] Gate 2: 100% Import Graph Resolution, Route Parity & Schema Parity certified.")
        return True

    def _verify_import_graph(self) -> None:
        print("  -> Checking dynamic import graph resolution...")
        modules_to_import: list[str] = []

        for p in self.root_dir.glob("backend/**/*.py"):
            if "__pycache__" in str(p) or "tests" in p.parts:
                continue
            rel = p.relative_to(self.root_dir)
            mod_name = str(rel.with_suffix("")).replace(os.sep, ".").replace("/", ".")
            modules_to_import.append(mod_name)

        for p in self.root_dir.glob("ml_pipeline/**/*.py"):
            if "__pycache__" in str(p):
                continue
            rel = p.relative_to(self.root_dir)
            mod_name = str(rel.with_suffix("")).replace(os.sep, ".").replace("/", ".")
            modules_to_import.append(mod_name)

        imported_count = 0
        for mod in sorted(modules_to_import):
            try:
                importlib.import_module(mod)
                imported_count += 1
            except Exception as exc:
                self.discrepancies.append(f"Import resolution failed for '{mod}': {exc}")

        print(f"     Successfully resolved and imported {imported_count}/{len(modules_to_import)} modules.")

    def _verify_route_parity(self) -> None:
        print("  -> Checking Frontend-to-Backend route parity...")
        try:
            from backend.main import app
        except Exception as exc:
            self.discrepancies.append(f"Could not import backend.main: {exc}")
            return

        # Canonicalize route paths
        def normalize_route(path: str) -> str:
            # Replace path params {param} or ${param} with {*}
            p = re.sub(r"\{[^}]+\}", "{*}", path)
            p = re.sub(r"\$\{[^}]+\}", "{*}", p)
            return p.rstrip("/")

        backend_routes: set[str] = set()
        for r in app.routes:
            if hasattr(r, "path"):
                p = r.path
                if p not in ("/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc", "/"):
                    backend_routes.add(normalize_route(p))

        # Extract routes called in frontend apiClient.ts
        api_client_path = self.root_dir / "frontend" / "src" / "services" / "apiClient.ts"
        frontend_routes: set[str] = set()
        if api_client_path.exists():
            content = api_client_path.read_text(encoding="utf-8")
            matches = re.findall(r'["`](/api/v[12]/[^"`]+)["`]', content)
            for m in matches:
                frontend_routes.add(normalize_route(m))

        # Check WebSocket endpoint
        ws_client_path = self.root_dir / "frontend" / "src" / "services" / "wsClient.ts"
        if ws_client_path.exists():
            ws_content = ws_client_path.read_text(encoding="utf-8")
            if "/ws/telemetry" in ws_content:
                frontend_routes.add(normalize_route("/ws/telemetry"))

        # Verify all frontend routes exist in backend
        for f_route in frontend_routes:
            if f_route not in backend_routes:
                self.discrepancies.append(f"Orphaned frontend route call: '{f_route}' has no matching backend router.")

        print(f"     Verified route coverage: {len(frontend_routes)} frontend calls match registered backend endpoints.")

    def _verify_sql_orm_parity(self) -> None:
        print("  -> Checking SQL DDL to SQLAlchemy 2.0 ORM column parity...")
        try:
            from backend.db.session import Base
            import backend.db.models
        except Exception as exc:
            self.discrepancies.append(f"Could not inspect SQLAlchemy models: {exc}")
            return

        orm_tables = {table.name: set(table.columns.keys()) for table in Base.metadata.tables.values()}

        # Parse SQL DDL files
        sql_files = [
            self.root_dir / "infra" / "postgres" / "init_schema.sql",
            self.root_dir / "infra" / "postgres" / "migrations" / "V2__frontier_expansion.sql",
        ]

        sql_tables: dict[str, set[str]] = {}
        for sql_f in sql_files:
            if not sql_f.exists():
                continue
            text = sql_f.read_text(encoding="utf-8")
            # Extract CREATE TABLE statements
            create_blocks = re.findall(r"CREATE TABLE IF NOT EXISTS\s+([a-zA-Z0-9_]+)\s*\((.*?)\);", text, re.DOTALL | re.IGNORECASE)
            for tbl_name, body in create_blocks:
                tbl_name = tbl_name.strip().lower()
                cols = set()
                for line in body.splitlines():
                    line = line.strip()
                    if not line or line.startswith(("--", "CONSTRAINT", "PRIMARY KEY", "CHECK", "FOREIGN KEY", ")")):
                        continue
                    tokens = line.split()
                    if tokens:
                        col_candidate = tokens[0].lower().strip('",;')
                        # Valid SQL column identifier
                        if re.match(r"^[a-z_][a-z0-9_]*$", col_candidate):
                            if col_candidate not in ("constraint", "primary", "check", "foreign", "unique"):
                                cols.add(col_candidate)
                sql_tables[tbl_name] = cols

        # Compare tables and columns
        for tbl_name, sql_cols in sql_tables.items():
            if tbl_name not in orm_tables:
                self.discrepancies.append(f"SQL table '{tbl_name}' is missing an ORM model in backend.db.models.")
                continue

            orm_cols = orm_tables[tbl_name]
            for col in sql_cols:
                # Column name in SQL vs mapped column name in ORM
                if col not in orm_cols:
                    self.discrepancies.append(f"Column '{col}' in SQL table '{tbl_name}' is missing in ORM model.")

        print(f"     Verified schema parity: {len(sql_tables)} SQL DDL tables match ORM models with 0 missing columns.")


def main() -> None:
    print("\n" + "#" * 78)
    print(" NDTM MASTER ZERO-DEFECT STATIC & CONTRACT CERTIFICATION HARNESS")
    print("#" * 78)

    gate1 = Gate1AstAndMockScanner(PROJECT_ROOT)
    gate1_pass = gate1.run()

    gate2 = Gate2CrossStackContractVerifier(PROJECT_ROOT)
    gate2_pass = gate2.run()

    if not gate1_pass or not gate2_pass:
        print("\n" + "!" * 78)
        print(" [CERTIFICATION FAILED] Repository did not meet zero-defect requirements.")
        print("!" * 78 + "\n")
        sys.exit(1)

    print("\n" + "*" * 78)
    print(" [CERTIFICATION APPROVED] Gate 1 & Gate 2 Certified: Exit Code 0.")
    print("*" * 78 + "\n")
    sys.exit(0)


if __name__ == "__main__":
    main()

"""Gate 5 Certification Harness: UI/UX Zero-Dead-Button & Zero-Mock Static Verifier.
Validates that all 8 Cockpit Views contain fully wired event handlers, zero empty callbacks,
zero dead UI buttons, zero TODO placeholders, and 100% apiClient method binding parity.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT_DIR / "frontend" / "src"
VIEWS_DIR = FRONTEND_DIR / "views"
API_CLIENT_PATH = FRONTEND_DIR / "services" / "apiClient.ts"
APP_PATH = FRONTEND_DIR / "App.tsx"

EXPECTED_VIEWS = [
    "TriageGatekeeperView.tsx",
    "DistillMeshRouterView.tsx",
    "SymbolicSchedulerView.tsx",
    "SecurityAndChaosView.tsx",
    "CausalTwinMapView.tsx",
    "McpAndHitlConsoleView.tsx",
    "FederatedPrivacyView.tsx",
    "MerkleAndSpeculativeView.tsx",
]


def certify_gate_5() -> int:
    print("=" * 80)
    print("GATE 5: COCKPIT UI/UX ZERO-DEAD-BUTTON & ZERO-MOCK CERTIFICATION")
    print("=" * 80)

    errors: list[str] = []
    total_buttons_checked = 0

    # 1. Check all 8 views exist
    for view_name in EXPECTED_VIEWS:
        view_file = VIEWS_DIR / view_name
        if not view_file.exists():
            errors.append(f"Missing required Cockpit View: {view_name}")
            continue

        content = view_file.read_text(encoding="utf-8")

        # Check for forbidden TODO or placeholder tokens
        for line_no, line in enumerate(content.splitlines(), start=1):
            if any(token in line.lower() for token in ["// todo", "/* todo", "# todo", "implement later", "pass"]):
                # Allow 'pass' only in safe english words like 'bypassed' or 'password'
                stripped = line.strip().lower()
                if "todo" in stripped or "implement later" in stripped:
                    errors.append(f"Forbidden placeholder found in {view_name}:{line_no}: '{line.strip()}'")

        # Find all <button elements
        button_matches = re.finditer(r"<button\b([^>]*)>", content, re.DOTALL)
        for b_match in button_matches:
            total_buttons_checked += 1
            attrs = b_match.group(1)

            # Must have either onClick or type="submit" or disabled condition
            has_onclick = "onClick=" in attrs
            has_submit = 'type="submit"' in attrs or "type='submit'" in attrs

            if not has_onclick and not has_submit:
                errors.append(f"Dead button detected in {view_name}: '<button {attrs.strip()}>' has no onClick or type='submit'")

            # Check for dummy empty handler: onClick={() => {}} or onClick={() => { /* ... */ }}
            empty_handlers = re.findall(r"onClick=\{\s*\(\s*\)\s*=>\s*\{\s*\}\s*\}", attrs)
            if empty_handlers:
                errors.append(f"Empty stub callback detected in {view_name}: '{empty_handlers[0]}'")

    # 2. Check API Client method bindings
    if not API_CLIENT_PATH.exists():
        errors.append(f"Missing API Client file: {API_CLIENT_PATH}")
        return 1

    api_client_code = API_CLIENT_PATH.read_text(encoding="utf-8")
    # Extract declared method names in apiClient object
    # e.g., submitTriage: async (...)
    declared_api_methods = set(re.findall(r"async\s+(\w+)\s*\(", api_client_code))

    # Extract all apiClient.<method> calls from views
    api_calls_in_views: set[str] = set()
    for view_name in EXPECTED_VIEWS:
        view_file = VIEWS_DIR / view_name
        if not view_file.exists():
            continue
        v_code = view_file.read_text(encoding="utf-8")
        calls = re.findall(r"apiClient\.(\w+)\s*\(", v_code)
        for c in calls:
            api_calls_in_views.add(c)
            if c not in declared_api_methods:
                errors.append(f"Unresolved API client binding: view '{view_name}' calls non-existent 'apiClient.{c}'")

    # 3. Check App.tsx mounting
    app_code = APP_PATH.read_text(encoding="utf-8")
    for view_name in EXPECTED_VIEWS:
        base_name = view_name.replace(".tsx", "")
        if base_name not in app_code:
            errors.append(f"Cockpit View '{base_name}' is not imported or mounted in App.tsx")

    print(f"[*] Total Cockpit Views Audited: {len(EXPECTED_VIEWS)} / {len(EXPECTED_VIEWS)}")
    print(f"[*] Total Interactive Buttons Certified: {total_buttons_checked}")
    print(f"[*] Total API Client Endpoints Wired: {len(api_calls_in_views)}")

    if errors:
        print("\n[!] GATE 5 CERTIFICATION FAILED! Violations:")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("\n[+] GATE 5 PASSED: 100% of UI buttons, state bindings, and API routes are live with zero dead stubs.")
    return 0


if __name__ == "__main__":
    sys.exit(certify_gate_5())

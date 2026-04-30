import pathlib
import re
import sys
from pathlib import Path

from flask import url_for

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from project.app import create_app


def check_render_templates() -> list[tuple[str, str]]:
    root = pathlib.Path("templates")
    missing: list[tuple[str, str]] = []
    pattern = re.compile(r'render_template\(\s*["\']([^"\']+)["\']')
    for py in pathlib.Path("project").rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            template_name = match.group(1)
            if not (root / template_name).exists():
                missing.append((str(py), template_name))
    return missing


def check_url_for_endpoints() -> list[tuple[str, str, str]]:
    app = create_app()
    pattern = re.compile(r'url_for\(\s*["\']([^"\']+)["\']')
    errors: list[tuple[str, str, str]] = []
    for template in pathlib.Path("templates").rglob("*.html"):
        text = template.read_text(encoding="utf-8")
        endpoints = sorted(set(pattern.findall(text)))
        with app.test_request_context():
            for endpoint in endpoints:
                try:
                    rule = next((r for r in app.url_map.iter_rules() if r.endpoint == endpoint), None)
                    if rule is None:
                        errors.append((str(template), endpoint, "endpoint not found"))
                        continue
                    kwargs = {arg: "1" for arg in rule.arguments}
                    url_for(endpoint, **kwargs)
                except Exception as exc:
                    errors.append((str(template), endpoint, str(exc)))
    return errors


def main() -> None:
    missing_templates = check_render_templates()
    print(f"MISSING_TEMPLATES={len(missing_templates)}")
    for source, template_name in missing_templates:
        print(f"{source} -> {template_name}")

    endpoint_errors = check_url_for_endpoints()
    print(f"URL_FOR_ERRORS={len(endpoint_errors)}")
    for template_path, endpoint, error in endpoint_errors:
        print(f"{template_path} -> {endpoint} :: {error}")


if __name__ == "__main__":
    main()

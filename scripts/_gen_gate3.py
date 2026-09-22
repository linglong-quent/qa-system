"""提取越域import违规列表"""
import re, os

root = r'D:\WB\linglong'
config = {
    "import_exempt": [
        "access.data.adapters", "access.decision.engines",
        "cognition.data.adapters", "cognition.data.orchestrator",
        "cognition.data.service", "data.cognition.engines",
        "data.decision.engines", "data.factor.engines",
        "data.risk.engines", "decision.cognition.engines",
        "decision.data.collectors", "decision.data.orchestrator",
        "decision.data.time_segment", "decision.factor.engines",
        "decision.risk.engines", "factor.data.service",
    ]
}
import_exempt = set(config.get("import_exempt", []))

violations = set()
domain_dir = os.path.join(root, 'domain')
for r, dirs, files in os.walk(domain_dir):
    for f in files:
        if not f.endswith('.py') or f == '__init__.py':
            continue
        fpath = os.path.join(r, f)
        with open(fpath, 'r', encoding='utf-8') as fh:
            content = fh.read()
        domain_imports = re.findall(r'from\s+domain\.(\w+)\.(?!api)(\w+)', content)
        current_domain = os.path.relpath(r, domain_dir).split(os.sep)[0]
        for imported_domain, imported_mod in domain_imports:
            if imported_domain != current_domain:
                exempt_key = f"{current_domain}.{imported_domain}.{imported_mod}"
                if exempt_key not in import_exempt:
                    rel_path = os.path.relpath(fpath, root)
                    violations.add(f"- \"{exempt_key}\"  # {rel_path} → domain.{imported_domain}.{imported_mod}")

for v in sorted(violations):
    print(v)
print(f'\nTotal violations: {len(violations)}')

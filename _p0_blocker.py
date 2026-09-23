import pathlib
p = pathlib.Path(".ai/config/review-rules.yaml")
t = p.read_text(encoding='utf-8')

# P0: WARN -> BLOCKER
changes = [
    ("solid_check:\n  enabled: true  # QA-System 自身不参与 SOLID 门禁（存量违规整改完成后可开启）\n  scan_dirs:\n  - scripts/\n  severity: WARN",
     "solid_check:\n  enabled: true\n  scan_dirs:\n  - scripts/\n  severity: BLOCKER"),
    ("fusedetect_check:\n  enabled: true\n  severity: WARN",
     "fusedetect_check:\n  enabled: true\n  severity: BLOCKER"),
    ("docconsistency_check:\n  enabled: true\n  severity: WARN",
     "docconsistency_check:\n  enabled: true\n  severity: BLOCKER"),
    ("runtime_drift_check:\n  enabled: true\n  severity: WARN",
     "runtime_drift_check:\n  enabled: true\n  severity: BLOCKER"),
    ("vcs_governance_check:\n  enabled: true\n  severity: WARN",
     "vcs_governance_check:\n  enabled: true\n  severity: BLOCKER"),
]

for old, new in changes:
    if old in t:
        t = t.replace(old, new)
        print(f"OK: {old.split(chr(10))[0][:40]}...")
    else:
        print(f"SKIP: not found: {old.split(chr(10))[0][:40]}...")

p.write_text(t, encoding='utf-8')
print("P0 done: 5 WARN -> BLOCKER")

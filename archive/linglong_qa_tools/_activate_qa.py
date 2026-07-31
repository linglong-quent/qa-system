"""激活全部19个checker + 全部Gate"""

file_path = r"E:\WB\linglong\.ai\config\review-rules.yaml"

with open(file_path, "r", encoding="utf-8") as f:
    content = f.read()

old_block = '''# Profile
profiles:
  full:
    checkers_on: ["inplace_check", "lookahead_check", "secret_check", "cyclic_check"]
  quick:
    checkers_on: []

# Gate5 跳过（基线期）
gate5:
  skip: true

# Gate8 跳过（非生产）
gate8:
  skip: true

# Gate9 跳过（基线期）
gate9:
  skip: true'''

new_block = '''# Profile
profiles:
  full:
    checkers_on: [
      "inplace_check", "lookahead_check", "secret_check",
      "deadcode_check", "cyclic_check", "code_ban",
      "import_boundary", "config_audit", "quality_gates",
      "claude_validation", "codestyle", "governance",
      "securityplus", "documentation", "zeroprint",
      "customrules", "fusedetect", "docconsistency",
      "production"
    ]
  quick:
    checkers_on: ["inplace_check", "secret_check", "code_ban"]
  ci:
    checkers_on: [
      "inplace_check", "lookahead_check", "secret_check",
      "cyclic_check", "code_ban", "import_boundary",
      "quality_gates", "zeroprint"
    ]

# Gate5 开启
gate5:
  skip: false

# Gate8 开启
gate8:
  skip: false

# Gate9 开启
gate9:
  skip: false'''

if old_block in content:
    content = content.replace(old_block, new_block)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
    print("✓ 全部19个checker + Gate5/8/9 已激活")
else:
    print("✗ 未找到旧配置块，内容可能不同")
    print(content[-600:])

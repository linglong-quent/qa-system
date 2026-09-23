import pathlib

p = pathlib.Path("scripts/chk_healthscorer.py")
t = p.read_text(encoding='utf-8')

old = '''            # [M51-① 2026-09-14 by m-qa] quality_gates 的结果必须落进**同一个产物**。
            # 原实现只在上面 save_report(staged=True) 存过一次盘（那次在 quality_gates
            # **运行之前**，为的是让它能读到报告），之后仅更新内存并 return ——
            # 于是**磁盘上的报告永远不含 quality_gates**。
            # 下游 qa_gate `missing = (CODE_CHECKERS|META_CHECKERS) - ran` 因此永不为空
            # ⇒ **Gate5 恒 FAIL**，阻断恒真、判据失去分辨力（"恒红"是"恒绿"的镜像；
            # 实测三份报告 legacy/run/fxproj 全部缺失 quality_gates）。
            # 这里补一次存盘，使产物与内存一致。'''

new = '''            # 补存盘：使磁盘报告与内存一致（否则 Gate5 恒 FAIL）。'''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("shortened: 8 lines -> 1 line")

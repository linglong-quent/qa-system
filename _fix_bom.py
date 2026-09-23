import pathlib, os

count = 0
for root in ['D:/WB/TDX', 'D:/WB/NEWSFORGE', 'D:/WB/factor_forge']:
    for dirpath, dirs, files in os.walk(root):
        # 跳过开源库
        if 'open_source_systems' in dirpath:
            continue
        for f in files:
            if not f.endswith('.py'):
                continue
            fp = pathlib.Path(dirpath) / f
            try:
                raw = fp.read_bytes()
                if raw.startswith(b'\xef\xbb\xbf'):
                    fp.write_bytes(raw[3:])
                    count += 1
            except Exception:
                pass

print(f'removed BOM from {count} files')

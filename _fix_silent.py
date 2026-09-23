import pathlib

# 修 TDX 静默降级
p = pathlib.Path('D:/WB/TDX/tools/auction_signal_study.py')
t = p.read_text(encoding='utf-8')
old = '''    except Exception as exc:
        _p(f"   ⚠ CH 补源失败（忽略）: {type(exc).__name__}: {exc}")
        return pd.DataFrame(columns=COLS)'''
new = '''    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("CH 补源失败: %s: %s", type(exc).__name__, exc)
        return pd.DataFrame(columns=COLS)'''
assert old in t, 'old not found'
t = t.replace(old, new)
p.write_text(t, encoding='utf-8')
print('fixed TDX')

# 修 factor_forge 静默降级 3 个
files = [
    ('D:/WB/factor_forge/scripts/event_factor.py', 401),
    ('D:/WB/factor_forge/scripts/game_pool_selector.py', 225),
    ('D:/WB/factor_forge/src/factors/linglong_domain/factor/engines/hidden_theme/linkage_cluster.py', 183),
]

for fpath, lineno in files:
    p = pathlib.Path(fpath)
    if not p.exists():
        print(f'skip: {fpath} not found')
        continue
    lines = p.read_text(encoding='utf-8').split('\n')
    # 在 except 分支后加 log.error
    # 找 lineno 附近的 except 行
    for i in range(lineno-1, min(lineno+3, len(lines))):
        if 'except' in lines[i] and ('return' in lines[i+1] or 'except' in lines[i]):
            # 在 except 行后插入 log.error
            indent = '        '
            lines.insert(i+1, f'{indent}import logging; logging.getLogger(__name__).error("异常: %s", e)')
            print(f'fixed: {fpath}:{lineno}')
            break
    p.write_text('\n'.join(lines), encoding='utf-8')

print('done')

import pathlib

p = pathlib.Path('D:/WB/factor_forge/src/factors/linglong_domain/factor/engines/hidden_theme/linkage_cluster.py')
lines = p.read_text(encoding='utf-8').split('\n')

# line 183 (0-indexed): except 行
# line 184 (0-indexed): log.error 行（缩进错了）
lines[182] = '        except (ValueError, RuntimeWarning) as e:  # pragma: no cover'
lines[183] = '            import logging; logging.getLogger(__name__).error("corr计算异常: %s", e)'

p.write_text('\n'.join(lines), encoding='utf-8')
print('fixed linkage_cluster.py')

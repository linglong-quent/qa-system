import os, re, yaml
import logging
logger = logging.getLogger(__name__)
ROOT = 'E:/WB/linglong'
CFG = 'E:/WB/QA-System/.ai/projects/linglong_local.yaml'
with open(CFG, 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)
import_exempt = set(cfg.get('import_exempt', []))
issues = []
domain_root = os.path.join(ROOT, 'domain')
for (root, dirs, files) in os.walk(domain_root):
    for f in files:
        if not f.endswith('.py') or f == '__init__.py':
            continue
        fpath = os.path.join(root, f)
        try:
            content = open(fpath, 'r', encoding='utf-8').read()
        except Exception as e:
            logger.debug('except Exception: %s', e)
            logger.debug('except Exception: %s', e)
            continue
        domain_imports = re.findall('from\\s+domain\\.(\\w+)\\.(?!api)(\\w+)', content)
        current_domain = os.path.relpath(root, domain_root).split(os.sep)[0]
        for (imported_domain, imported_mod) in domain_imports:
            if imported_domain != current_domain:
                exempt_key = current_domain + '.' + imported_domain + '.' + imported_mod
                if exempt_key in import_exempt:
                    continue
                rel_path = os.path.relpath(fpath, ROOT)
                issues.append(rel_path + ' -> domain.' + imported_domain + '.' + imported_mod + ' (key=' + exempt_key + ')')
print('Unexempted cross-domain imports: ' + str(len(issues)))
for i in issues:
    print('  ' + i)

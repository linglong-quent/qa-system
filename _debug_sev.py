import json, yaml

r = json.load(open('.ai/logs/qa-report.json', encoding='utf-8'))
config = yaml.safe_load(open('.ai/config/review-rules.yaml', encoding='utf-8'))

print("=== Checkers with errors ===")
for cid, cdata in r.get('checkers', {}).items():
    errs = cdata.get('errors', 0)
    if errs > 0:
        # 找 severity
        cfg_key = cid if cid.endswith('_check') else cid + '_check'
        sev = config.get(cid, {}).get('severity', config.get(cfg_key, {}).get('severity', '?'))
        print(f"  {cid}: errors={errs} severity={sev}")

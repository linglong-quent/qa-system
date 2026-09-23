import json
r = json.load(open('.ai/logs/qa-report.json', encoding='utf-8'))
for cid, cdata in r.get('checkers', {}).items():
    errs = cdata.get('errors', 0)
    if errs > 0:
        print(f"{cid}: errors={errs}")
        for note in cdata.get('notes', [])[:3]:
            print(f"  {note}")

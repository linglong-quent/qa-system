import urllib.request, json, os

pubkey = open(os.path.expanduser("~/.ssh/gh_linglong.pub")).read().strip()
print(f"Key length: {len(pubkey)}")
print(f"Key starts: {pubkey[:30]}")

token = os.environ.get("GITHUB_TOKEN", "")
req = urllib.request.Request(
    "https://api.github.com/user/keys",
    data=json.dumps({"title": "linglong-quent-pc", "key": pubkey}).encode(),
    headers={
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json"
    },
    method="POST"
)
try:
    resp = urllib.request.urlopen(req)
    result = json.loads(resp.read())
    print(f"Success! ID: {result['id']}, title: {result['title']}")
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, "read"):
        print(e.read().decode())

import pathlib

p = pathlib.Path("D:/WB/linglong/docker/docker-compose.yml")
t = p.read_text(encoding='utf-8')

# 在 scheduler 的 logging 后面加 deploy.resources
old = '''    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"

  # ==================== 数据写入层 ===================='''

new = '''    logging:
      driver: "json-file"
      options:
        max-size: "50m"
        max-file: "5"
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 4G
        reservations:
          cpus: "0.5"
          memory: 512M

  # ==================== 数据写入层 ===================='''

assert old in t, "old not found"
t = t.replace(old, new)

p.write_text(t, encoding='utf-8')
print("added deploy.resources to scheduler")

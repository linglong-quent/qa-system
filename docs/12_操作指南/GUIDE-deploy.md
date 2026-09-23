# QA System 部署 SOP

## 发布流程

1. 创建发布分支 `release/vX.Y.Z`
2. 更新 CHANGELOG.md
3. 创建 PR → CI 通过 → Squash Merge
4. 打 Git Tag: `git tag vX.Y.Z && git push --tags`
5. 确认 main 分支 CI 通过

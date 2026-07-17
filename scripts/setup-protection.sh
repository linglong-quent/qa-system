#!/usr/bin/env bash
# GitHub 分支保护设置脚本
# 用法: bash setup-protection.sh
# 需要: gh 已登录, 有管理员权限

set -e

ORG="linglong-quent"
QA_REPO="qa-system"
PROJ_REPO="linglong"

echo "=== 设置 MAIN 分支保护 ==="

# QA 系统仓库
echo ""
echo "1. QA System ($ORG/$QA_REPO)"
gh api repos/$ORG/$QA_REPO/branches/main/protection -X PUT \
  -f required_status_checks='{"strict":true,"checks":[
    {"context":"qa-self-test"}
  ]}' \
  -f enforce_admins=true \
  -f required_pull_request_reviews='{"required_approving_review_count":1}' \
  -f allow_force_pushes=false \
  -f allow_deletions=false

gh repo edit $ORG/$QA_REPO \
  --default-branch main \
  --delete-branch-on-merge

echo "   ✅ QA System MAIN 保护已启用"

# 量化项目
echo ""
echo "2. 量化项目 ($ORG/$PROJ_REPO)"
gh api repos/$ORG/$PROJ_REPO/branches/main/protection -X PUT \
  -f required_status_checks='{"strict":true,"checks":[
    {"context":"lint"},
    {"context":"preflight-gate"},
    {"context":"test"}
  ]}' \
  -f enforce_admins=true \
  -f required_pull_request_reviews='{"required_approving_review_count":1}' \
  -f allow_force_pushes=false \
  -f allow_deletions=false \
  -f restrictions='{}'

gh repo edit $ORG/$PROJ_REPO \
  --default-branch main \
  --delete-branch-on-merge

echo "   ✅ 量化项目 MAIN 保护已启用"

echo ""
echo "=== 保护规则 ==="
echo "  Org: $ORG"
echo "  Repos: $QA_REPO, $PROJ_REPO"
echo "  Checks: lint + preflight-gate + test"
echo "  Reviews: 1 required"
echo "  Force push: disallowed"
echo "  Branch delete: auto on merge"
echo "  MAIN: protected, only CI+PR can merge"

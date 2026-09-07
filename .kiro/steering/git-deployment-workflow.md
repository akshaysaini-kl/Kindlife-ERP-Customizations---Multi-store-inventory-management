---
title: Git Deployment Workflow
description: Standard workflow for committing and pushing code changes to Git repository
keywords: git, deployment, push, commit, branch, workflow
inclusion: manual
created: 2026-05-07
status: active
---

# Git Deployment Workflow

## CRITICAL RULES

### 1. NEVER Push to Protected Branches
FORBIDDEN:
- git push origin main
- git push origin master
- git push origin develop
- git push origin production

ALLOWED:
- git push origin feature-branch-name
- Always push to the SAME branch you are working on

### 2. Only Push When Explicitly Asked
DO NOT push automatically after completing tasks

ONLY push when user says:
- push to git
- push changes
- commit and push

### 3. Always Use Current Branch
- Check current branch first
- Push to that exact branch
- Never switch branches before pushing

## Standard Workflow

### Step 1: Check Current Status
git branch --show-current
git status

### Step 2: Configure Git User (First Time)
git config --global user.name "username"
git config --global user.email "email@example.com"

Example:
git config --global user.name "akshaysaini-kl"
git config --global user.email "akshay.saini@kindlife.in"

### Step 3: Stage Changes
git add path/to/file1.py
git add path/to/file2.js
git status

### Step 4: Commit Changes
git commit -m "feat: Brief description

- Detail 1
- Detail 2

Tested: What was tested
Status: Production ready"

### Step 5: Push to Remote
git push origin $(git branch --show-current)

OR first time:
git push -u origin $(git branch --show-current)

### Step 6: Create Pull Request
Go to GitHub/GitLab and create PR from feature branch to develop

## Complete Command Sequence

git branch --show-current
git status
git add file1.py file2.js
git status
git commit -m "feat: Description"
git push origin $(git branch --show-current)

## Common Mistakes

WRONG: git push origin develop
RIGHT: git push origin feature-branch

WRONG: Pushing without user request
RIGHT: Wait for user to say "push to git"

## Verification Checklist

- Current branch is feature branch (NOT main/develop/production)
- User explicitly asked to push
- Git user is configured
- Changes are staged and committed
- Pushing to SAME branch you are working on
- Not including .kiro/ files

Last Updated: May 7, 2026
Version: 1.0.0

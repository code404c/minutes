# Task Plan

## Goal
根据 `docs/code-review-2026-03-12.md` 高质量修复 Minutes 仓库的高优先级问题，补齐自动检查与开发规范，并把全量测试跑到通过；若环境允许，再完成真实模型下载与音频 smoke。

## Phases
- [x] 读取任务文档、现有计划文件与 `../convbox/CLAUDE.md`
- [x] 审查高优先级代码路径与现有测试基线
- [x] 修复 P0 运行时与安全问题
- [x] 修复可安全落地的 P1 数据层/基础设施问题
- [x] 补充自动化测试与开发规范文件
- [ ] 执行全量测试、锁文件/模型准备与 smoke 验证

## Decisions
- 优先修复 `P0`，并顺带落地不会扩大风险的 `P1`
- 保持 `Dramatiq + Redis` 架构，不引入额外基础设施重构
- 若调整 repository 事务边界，必须同步补齐调用方 `commit/rollback`
- 自动检查优先采用仓库内脚本 + `CLAUDE.md` 规范，不依赖外部 CI
- 真实音频测试路径按 Windows 提示映射为 `/mnt/c/temp/meetings`

## Errors Encountered
- `ruff` 的 `B008` 与 FastAPI `Depends/File/Form` 约定冲突；通过 `per-file-ignores` 仅对 router 文件豁免
- `make check` 首轮因新增测试文件 import 顺序失败；已用 `ruff --fix` 修复
- `docker compose config` 首轮因缺少本地 `.env` 失败；已临时从 `.env.example` 生成本地 `.env` 后复验

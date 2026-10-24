# 第一阶段执行记录（2026-10-24）

起始主线 `e226222d95684ef86afc0b33f51dec0e44792313`；PR 起点 `1a8c7d33b98ba2618d3ac1cf3264a02b1451db99`。
实现提交 `bff0f75`；本记录与实现分主题提交；结束提交以 PR head 和 Git 历史为准，不在提交内容内循环嵌入自身哈希。
Python 3.12.14、Node v24.19.0；复用现有 `.venv` 和锁定依赖，无框架升级。
未发现适用 AGENTS.md。已读取任务单、README 和任务单要求的五份技术/发布文档。

## 审计矩阵与实际改动

| 项目 | 起始状态 | 本轮结果 |
|---|---|---|
| Provider、预检、超时、错误脱敏 | 已有 | 复用；补空响应/无效 JSON 回归；每轮显式最多 5 次调用，逐步记录请求模型名 |
| 重试 | 不自动重试 | 保留零重试，防止重复计费；失败走脱敏回退，未实现可配置重试 |
| 引用定位 | 已有、仅字符串存在 | 加请求内消息 ID、user 角色；新增独立可替换三态语义规则接口 |
| 状态语义 | 缺失 | 四类状态逐字段记录来源/三态/当前历史；不支持的情绪和意图撤销为 unknown，提示需要澄清 |
| 当前意愿 | 整段正则 | 加引述、双重否定、假设、反讽、历史表述的保守 unknown；支持本轮显式纠错及跨轮当前意愿优先 |
| 策略选择 | 确定性函数 | 加可注入接口并保留规则基线，版本更新为 0.3；未训练排序器 |
| 生成校验、取消、安全路径 | 已有 | 保留规则检查、一次重写、模型检查、断连取消及独立危险关键词保护 |
| 多条件评测 | 仅本地规则诊断 | 新增七条件 CLI、总调用预算、匿名盲评 CSV、条件映射、失败分母和人工标注汇总 |
| 数据契约 | 旧开发用例 | 新增九条手写虚构开发用例、FamilyStressBench JSON schema、标注指南；无独立测试集 |
| 隐私与隔离 | 已有认证、删除、内存对话和导出 | 增加双账号删除/导出隔离测试；原取消、清空、认证、导出测试重跑 |
| 真实模型及专家效果 | 未验证 | 未验证，配置及授权预算缺失；没有付费模型调用 |

## 实际运行结果

- 基线：`scripts/check_ccare.py` 59/59 通过（2.725 秒）；前端两文件在完整运行环境中展开为 15/15 通过。
- 新增后：后端 71/71 通过（3.181 秒），前端 15/15 通过；无跳过。后端测试脚本禁止 httpx 外部传输，mock 覆盖所有七条件执行。
- 新 CLI：9 × 7 = 63 条 dry-run，全部明确标记 dry_run；模型调用 0，费用 null，所有人工指标 unavailable。没有模型优劣或共情效果统计。
- 原 20 条规则诊断完整保留；`dev14`（否定自杀）、`dev15`（课程转述）仍与开发暂定标签不符。这是独立保守安全规则的已知误报，未因语义不支持而关闭安全路径。
- 现有 8 对/16 条配对诊断于提交后运行，具体输出见 PR 更新；不作为独立效果实验。
- `check_model.py` 零调用预检返回缺少新密钥、模型名、接口地址、服务商与隐私说明，退出码 2，真实连通未验证。
- 初次受限运行中 Git 代理连接失败、后端 API 测试停滞；在环境权限更新后成功检出分支、完成测试；没有因此修改应用权限。

## 可复制命令

```bash
.venv/bin/python -m pip install -r backend/requirements-ccare.lock.txt
.venv/bin/python scripts/check_ccare.py
node --test tests/web-session.test.mjs tests/web-stream.test.mjs
.venv/bin/python scripts/benchmark_ccare.py --output /tmp/kinvoice-benchmark-new
.venv/bin/python scripts/summarize_benchmark.py /tmp/kinvoice-benchmark-new/results.jsonl
.venv/bin/python scripts/evaluate_ccare.py
.venv/bin/python scripts/evaluate_policy_pairs.py
.venv/bin/python scripts/check_model.py
.venv/bin/python backend/start.py --mode demo --port 8768
```

开发中旧诊断可显式 `--allow-dirty`，清洁提交后默认记录 commit。评测输出目录必须不存在，避免覆盖。
模型评测仅提供入口：配置 `KINVOICE_` 新凭据后，**取得明确预算授权**才使用 `benchmark_ccare.py --live --call-budget N --output ...`；本轮未执行。
预算是整个运行的实际 provider 调用总上限，耗尽后每个剩余样本仍记录失败。无隐式重试；超时/失败的 usage 与费用未知。
多步基线实际三步（分析、回应、修订），与 C-CARE 相同信息、模型、每步 token 上限、五调用上限和总超时；单轮/历史 NVC 为一次。实际调用/token 均另报，未声称严格等 token 消耗。

## 局限与未完成项

规则只覆盖狭窄词形，不能完整处理中文否定、说话人归属、反讽或时态；不把 supported 称为概率或可靠蕴含。整句不确定性也可能过度撤销状态。风险/家庭状态不因语义 uncertain 被自动清除，因此仍会误报；未做专业安全审阅。
字段 schema 可表示 explicit/confirmed/inferred/unknown 和 supersedes，但当前实现不提供持久状态、用户确认流程或历史安全线索撤销。消息 ID 仅在单个请求内稳定，不能用作跨会话身份。

意愿、家庭消融只移除策略层约束；生成提示和输出安全检查继续保留。证据消融只在 CLI 暂时跳过状态证据校验，本地安全保护保留。这是局部机制消融，不是全部移除安全机制，不能直接声称完成正式消融研究。
盲评汇总支持真实成功结果和具名评价者的 0/1/2 评分，不给失败补分，不产生显著性/胜率；未实现评价者一致性、正式统计协议或生产数据采集。

Provider 现有实现使用 trust_env=False，真实连接还需核验与部署代理的兼容性。本轮未更改网络配置或凭据，不声称真实服务可用。新增评测无额外 HTTP 客户端，复用原 provider。
专业标注、校准、独立冻结测试集、NLI/学习排序、正式预算对齐实验和真人研究均未完成，属于后续阶段。当前需要人工处理的是新凭据与调用预算授权；正式研究还需要专业合作者及审查。

提交前检查 diff、语法、凭证模式和文件白名单；不提交环境文件、数据库、私钥、原始运行目录或真人内容。不部署、不合并 main。

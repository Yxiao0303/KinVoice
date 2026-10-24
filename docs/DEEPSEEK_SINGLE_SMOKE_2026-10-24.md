# 一次最小真实连通：2026-10-24 UTC

> 后续核心流程烟测新增3次，累计预留8.401408元；发现输出复活撤销情绪并作离线修复，详见 [核心烟测记录](CORE_SMOKE_2026-10-24.md)。本页金额和单次状态为此前阶段快照。

沿用 `codex/ccare-implementation-20261024` 和草稿 PR #1，起点 `69a63d3`。
旧任务生成请求 0，本接续任务此前生成请求 0；本次新增且仅新增 1 次。
没有重试、批量实验、真人数据、部署或 main 合并。

## 配置证据及限制

本实例 ID：`ccarenv_b64_Y2NhcmVudl8zZWNhODMwZDIzOTg4MTkxOTE4ZDMwMjRlNTBjNGIzOA`。
有效网络策略允许 `api.deepseek.com`；继承平台代理和 CA、TLS 校验开启、重定向禁用。
已有 `DEEPSEEK_API_KEY` 绑定通过官方 `/models` 认证检查，HTTP 200，列出 deepseek-flash。
未读取或打印真实 secret、未更改网络配置或新建凭据。

当前工具未暴露 source_config_version_id/network secret readiness 元数据查询。
预期版本为 `6b7f8514-37b6-4a24-830d-c109b93d1cb9~cecfgver_6adc470f905081a0bdd6134b1f17bec9`，
**精确版本未独立核验**。成功认证与生成是功能证据，不冒充版本元数据。
父线程明确确认可据此继续既有授权，版本不可读仅作为溯源限制。

## 固定请求及统一账本

复用 `scripts/check_model.py --live`、RemoteProvider 和 CNYLedger，
仅发送固定提示，要求返回 `{"ok":true,"case":"synthetic"}`。
固定官方 endpoint、deepseek-flash、thinking disabled、JSON 模式、max_tokens 400；
无工具、无自动重试。默认预检仍零调用，批量入口继续阻塞。

授权 ID：`kinvoice-deepseek-first-10cny-20261024`，累计上限人民币 10 元。
规范账本：`backend/data/deepseek_first_run_budget.db`（本地持久且 Git 忽略）。
发送前 BEGIN IMMEDIATE 原子预留并领取唯一操作 `authorized-single-json-20261024`。
同一操作成功、失败或在途后均不能再次领取；重开 CLI 不会再发一次。
失败、未知用量、取消均保留预留并停发；进程中断由既有租期机制恢复为 unknown。

2026-10-24 再核验官方公开契约：
- [人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：峰值每百万输入 2 元、输出 8 元。
- [参数](https://api-docs.deepseek.com/api/create-chat-completion/)：max_tokens 限制生成 token，输入和生成受上下文限制；显式关闭默认开启的 thinking。
- [模型元数据契约](https://api-docs.deepseek.com/api/list-models/)：上下文 1048576 token。

按全上下文输入加400输出预留：`(1048576×2+400×8)/1000000 = 2.100352` 元。
`provider_bound_verified=true` **仅表示上述公开费率/token 契约已核验**，
不表示供应商账户支出锁或账单绝对保证。原默认离线 policy 不变；若已有账本 policy 不同则拒绝，不覆盖。
价格有效至2026-10-25 00:00 UTC。推理 token 如报告，是 completion 的细分，不重复计费。

## 实际结果

| 项目 | 结果 |
|---|---|
| HTTP | 200 |
| 请求/返回模型 | deepseek-flash / deepseek-flash（未返回更细版本标识） |
| JSON | 解析成功，固定对象匹配 |
| 输入/输出/合计 token | 49 / 10 / 59 |
| 缓存命中/未命中 | 0 / 49 |
| 推理细分 | 未报告；请求显式 disabled，不虚构计数 |
| 峰值人民币估算 | 0.000178 元，非实际账单 |
| 累计完整预留 | 2.100352 元，成功不退款 |
| 剩余可预留 | 7.899648 元，不代表允许继续调用 |
| actual_billed_cny | unknown |
| 后续自动请求 | 0，固定操作已完成 |

真实账本记录必须保留。换实例/丢失账本时不得按新任务重置为10元或重跑；
必须先恢复该统一账本及上述已发生的预留。本次结果不是心理支持有效性证据。

## 验证

`.venv/bin/python scripts/check_ccare.py`：119/119 通过，HTTP 传输在测试中被禁止。
新增 mock 覆盖发送前预留、完整参数、成功后跨实例重开拒绝重复领取、429不重试、缺失usage停发、无效JSON保留已知用量。
命令 `.venv/bin/python scripts/check_model.py --live` 已真实执行一次、退出0；不要为复核再次运行。
实际 head 和 CI 结果见原 PR；账本未提交，不含密钥或对话原文。

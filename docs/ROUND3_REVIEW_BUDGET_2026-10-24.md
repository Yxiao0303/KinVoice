# 本页确认闭环与离线预算升级：执行记录

日期：2026-10-24（北京时间）；本轮起点 `b47a1f47fd6c993733a5d3e986c4a871878cf62d`，与远端一致、工作树干净。沿用原任务、原分支和 PR #1。未发现 AGENTS.md 或额外 .agents 指令。读取原任务单及历史执行记录；继续使用云环境运行技能，无新增凭据、部署或真实模型请求。

## 核心能力实际状态

| 目标 | 本轮交付 | 验证与剩余限制 |
|---|---|---|
| 确认/纠正/撤销 | 页面“确认或更正本轮理解”提供情绪、支持意愿、风险与家庭线索操作；随下一次请求应用 | 来源校验、最高修订号、重复幂等、冲突拒绝、撤销墓碑、更新意愿优先；仅本页与随请求重放，不是持久记忆 |
| 撤销向后续决策传播 | reviews.apply_reviews 在规则和远程估计后应用，旧模型判断不能重新激活已撤销字段，清理撤回的活动证据 | 旧状态覆盖、相同文字新消息、跨用户隔离测试；当前明确拒绝优先，独立危险/家庭约束不能被撤销清除 |
| 来源与状态版本 | user 消息稳定 ID + 文本摘要 + 字段 + 修订号；同一 ID 在上下文中不得重复 | 新版网站始终携带 ID。兼容旧客户端无 ID 时退为摘要定位，相同文本身份区分较弱；不提供跨设备/恶意客户端的持久防回滚保证 |
| 调用与预算对齐 | 每个条件统一 5 调用上限、累计 96000 输入 UTF-8 字节、2000 请求输出 token 配额；全局预算单独限制 | 单轮分配 1×2000；多步/C-CARE/消融为最多 5×400。失败、取消不返还预留；不同条件实际消耗可以不同 |
| 强多步基线 | 同一用户信息、分析→生成→独立 JSON 检查→可选重写和再检查，最多五步 | 拒绝、重写、超时/取消、预算耗尽均留分母；不是以增加调用数宣称创新 |
| 实例隔离消融 | 移除全局 patch；仅评测脚本的 EvaluationEngine 同时去除指定模块的策略、生成规则、对应输出检查和检查器指令；证据消融仅在实例跳过来源/语义校验 | 并发完整/消融互不影响，输入不改写；所有消融保留独立急性保护和通用防伤害/隐私规则，网站无消融参数 |
| 真实模型与费用 | 复用 DeepSeek adapter；新增推理 token 明细、失败返回已知 usage 保留、USD/CNY 估算与真实 CLI 阻塞 | 未调用；10 元人民币预算获授权，但未可靠硬控，详见下文，不以 token/调用上限冒充人民币费用上限 |

当前能力已从“schema 可表达确认”推进为本页可操作闭环。仍是规则与 mock 的工程验证；未证明模型更合适、算法创新成立或心理支持效果。独立专家数据、专业审阅、校准、真实模型对照及真人研究仍未完成。

## 隐私和操作语义

- 仅允许引用请求中的用户消息，不能以助手文字或缺失来源写入确认；非法来源/冲突修订通过 API 返回脱敏 422。
- 用户操作只放在 Conversation 实例的内存 Map。清空、退出、账号删除和 pagehide 清理；上下文过期后不再传递该来源的操作。暂停或过期结果不能覆盖新版操作。
- “撤销判断”让字段变为 unknown（布尔字段撤销模型断言为 false），并保留需要澄清标记；不删除原对话，也不表示安全无风险。独立 local_state 每次重新扫描原用户历史和当前消息并保留保护。
- 风险保护未设计为可随意撤销；历史急性线索仍需专业流程决定何时失效。本轮没有将其改成用户点一下即可清除。
- 后端不保存操作或状态，不写入家庭数据。技术导出白名单排除 review source/摘要/纠正内容；用户主动的“导出本页对话”仍可能含私人内容，保留原确认提示。
- 旧服务未宣告 review_protocol 时，网站去除新字段，保留原对话兼容行为。

## 预算口径与可复现命令

```bash
.venv/bin/python scripts/check_ccare.py
node --test tests/web-session.test.mjs tests/web-stream.test.mjs
.venv/bin/python scripts/benchmark_ccare.py --output /tmp/kinvoice-new-dry
.venv/bin/python scripts/benchmark_ccare.py --mock --output /tmp/kinvoice-new-mock
.venv/bin/python scripts/benchmark_ccare.py --mock --call-budget 1 --output /tmp/kinvoice-new-exhausted
.venv/bin/python scripts/summarize_benchmark.py /tmp/kinvoice-new-mock/results.jsonl
.venv/bin/python scripts/evaluate_ccare.py
.venv/bin/python scripts/evaluate_policy_pairs.py
.venv/bin/python scripts/check_model.py
```

同一输入（原消息、历史、UI 目标及本页操作）进入所有条件；各流水线的派生状态不同是实验变量。资源严格对齐的是**相同上限与输出预留池**，不声称实际 token 使用相等，也不把输入字节当成服务商 token。通用 tokenizer 与服务端额外开销未核验，严格“总输入+输出 token”相等的研究条件仍未冻结。

记录每次请求模型、返回模型、实际 usage/推理细分、输入字节、预留输出 token、耗时和失败类别。取消会保存当前取消项及后续 skipped 行，退出 130；预算耗尽继续记录失败。没有 usage 时保持 null，未知费用不填 0。mock 结果标记 mock/mock_failed，不能进入真实模型盲评分母；人工指标保持 unavailable。CI 新增完整 mock 执行。

## DeepSeek 接入准备与 10 元边界

用户已批准：官方 DeepSeek、deepseek-flash、首轮累计不超过人民币 10 元、仅虚构情境。此授权保留，不重复请求预算；用户随后已确认保存安全配置，但当前运行实例尚未获得绑定，本轮不真实执行。

2026-10-24 只读核验官方文档：

- https://api-docs.deepseek.com/quick_start/pricing/ ：官方 OpenAI 格式 base 为 https://api.deepseek.com，deepseek-flash 支持 JSON；thinking 默认开启，存在峰谷价格。
- https://api-docs.deepseek.com/api/create-chat-completion/ ：thinking.type=disabled 可关闭；JSON 使用 response_format.type=json_object 且提示应明确 JSON；max_tokens、finish_reason 与 usage 的字段有独立契约。

沿用适配器显式 disabled，不发送未使用的 reasoning_effort、tools 或惩罚参数；无自动重试。DeepSeek 非 stop 输出拒绝，输出截断仍保留已报告 usage；仅保留数字推理 token 明细，不返回私有推理内容。兼容性目前只有官方文档核对和 httpx MockTransport 测试，真实连通未验证。

billing.py 保存公开峰值价快照用于离线记账：每百万 token USD 0.006（命中）、0.3（未命中）、1.2（输出），版本 deepseek-flash-2026-10-24-peak-usd。缺少或不一致 usage 时估算为 null。reasoning_tokens 是 completion 的细分，不重复累加。另核验官方中文版 https://api-docs.deepseek.com/zh-cn/quick_start/pricing/ ，峰值人民币单价分别为每百万 0.04/2/8 元，增加直接 CNY 用量估算，无需虚构汇率。估算不是账单或实际已花费用。

**人民币 10 元硬费用保护未成立。**目前没有实现并验证请求前完整可计费 token 上界与跨脚本累计费用预留；人民币单价已查到，但服务端开销和失败请求也必须纳入保守预留；价格也可能调整，失败或超时可能已计费。因此 `check_model.py --live` 和 `benchmark_ccare.py --live` 均在构建远程客户端前明确 blocked、退出 2，不用模拟结果替代真实成功。网站原 remote 模式仍是独立手动流程，不宣称受该 10 元研究预算保护，本轮未启动它。

准备计划在 configs/deepseek_first_run.json：先 1 条内置虚构连通案例、最多 5 调用；核对输出/用量后，最多 10 条已有虚构开发情境、先只做强单轮与完整 C-CARE，最多 60 调用。须累计包括连通、全部候选/检查/重写、失败及任何后续重试；不得将 10 元分开重复授权给每个脚本。当前 live_enabled=false，不执行该计划或七条件真实批量实验。

预期配置名：DEEPSEEK_API_KEY（兼容 KINVOICE_API_KEY）、KINVOICE_PROVIDER_KIND、KINVOICE_API_BASE、KINVOICE_MODEL、KINVOICE_PROVIDER_LABEL、KINVOICE_PROVIDER_PRIVACY_URL。本轮预检仅输出配置存在布尔值，六项均未就绪；进程中 DEEPSEEK_API_KEY/KINVOICE_API_KEY 均不存在。环境状态 observations_current=true，secrets=[]、runtime_variables=[]，网络状态 unknown，策略快照未列 api.deepseek.com；HTTP_PROXY/HTTPS_PROXY 存在，仅表示代理变量已配置，不能证明该 API 可达。没有读取旧历史密钥、搜索聊天密钥或写入新凭据。下一步需确认已保存的 secret 绑定到当前选中云环境及目标域名 api.deepseek.com，在保留原任务/工作区的前提下刷新或重启执行环境，然后仅复查存在性和就绪状态；还需实现并验证人民币累计预留/计费口径。若二者不满足，真实调用持续阻塞。

## 运行结果

- 本轮基线后端 74/74、前端 15/15；修改后后端 97/97（3.569 秒）、前端 19/19（96 ms）；最终 head 的 CI 单独核实并写入 PR。
- 七条件 × 九虚构开发例：63 条 dry-run，外部调用 0；63 条 mock 成功、129 次本地桩调用、外部调用 0，所有专家指标 unavailable。
- 全局预算设为 1 的 mock：总计 1 次本地调用，9 条 mock/54 条 mock_failed，全部 63 条保留。部分急性样本走零调用安全路径，所以不会因外部调用配额耗尽而变成失败。
- 取消测试另有 1 次桩请求中断，后续样本标记 skipped；输出为测试专用临时目录，不冒充正常 mock 运行结果。
- 原 20 条和 8 对开发诊断于清洁提交后运行；结果见 PR，不是独立测试集。
- 真实调用、真实费用、独立效果和专业审阅均未验证；无真实心理数据、无新密钥、无部署、无 main 合并。

本轮主题提交：`af82811`（本页确认/纠正/撤销闭环与独立安全）、`461eadc`（资源上限、实例消融、费用记账准备与 live 阻塞）。文档提交及最终 head 由 Git 历史/PR 提供，不循环嵌入自身哈希。用户已保存配置，但当前实例尚无绑定；不要求重新发送密钥，也未更改其安全设置。


人民币累计预留机制后续已补充离线实现，早前“尚未实现预留”为历史状态；最新账本能力、供应商假设、环境版本和刷新建议见 [人民币账本与环境复核](CNY_LEDGER_RUNTIME_2026-10-24.md)。真实入口仍阻塞。

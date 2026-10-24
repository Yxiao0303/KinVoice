# 人民币累计预留账本与环境复核

> 接续更新：单次真实 JSON 连通已完成，累计预留2.100352元；见 [实际调用与配置证据](DEEPSEEK_SINGLE_SMOKE_2026-10-24.md)。下文为历史过程，零真实调用和访问阻塞不再代表最新状态。

本轮起点 `e7680e631817db136c563d9fa14fcb8a39fa95aa`，沿用原分支和 PR #1。仅离线实现、虚构桩测试及只读环境元数据检查；没有真实模型调用、部署或 main 合并。

## 已补齐的客户端预留机制

`backend/app/ccare/cny_ledger.py` 实现 SQLite 持久账本，货币采用整数纳元和 Decimal 向上取整，不用浮点数作钱款比较。固定授权 ID 为 `kinvoice-deepseek-first-10cny-20261024`。未来真实执行必须由全部协作入口共享 `backend/data/deepseek_first_run_budget.db`（忽略路径）；本轮只在临时目录及离线 CI 产物目录创建测试账本，不创建真实消费账本。

- `BEGIN IMMEDIATE` + FULL 同步写入，在发送前原子占额，独立进程也不能同时突破总额。
- 操作 ID、请求摘要及输出上限固定；重复预留幂等，但只能一次从 reserved 领取为 dispatched，不能借幂等键重复发送。重试必须新尝试 ID，继续占同一授权余额；没有自动重试。
- 各运行重开同一文件后累计已有记录，不自动清空或重建。价格、上下文上界、币种、汇率或授权额度改变时拒绝沿用账本，不悄悄增加额度；损坏、符号链接及无法读写时阻塞。
- 只在尚未领取发送时允许取消并释放；发送后即使成功且用量很少，仍保留完整最坏预留，**不按回包退款**。这是保守的可发额度，不是实际消费。
- 失败、取消、缺失/非法 usage、超过上下文/输出上界时全额保留并永久 halt 后续发送；没有自动解锁、归零或猜测零费用。有效但超界的数字用量保留为假设被破坏的证据。
- 已领取的操作设置派发租期，进程中断后过期记录恢复为 unknown 并冻结账本；并发中的其他进程不能借恢复重发旧请求。未过期的在途请求已经占额，也不能冲破累计预留。
- 日志只保存受限操作 ID、摘要、政策版本、状态、数字用量和数字费用估算，不保存消息、密钥、原始错误或模型私有推理。已知失败 usage 可审计，但不返还预留或允许重试。

## 金额、推理与价格假设

采用公开中文峰值价快照：deepseek-flash 每百万 token 缓存未命中输入 2 元、输出 8 元。预留时所有输入按未命中价，不依赖缓存折扣；保守把整个已公开 1M 上下文（1048576 token）当作每次输入上界，再另加最多 400 输出 token。输出上限包括 reasoning token；推理细分不重复加钱。

每次最坏预留为 `(1048576×2 + 400×8)/1000000 = 2.100352 元`。10 元累计授权在这些假设下只能接纳 4 次，预留 8.401408 元，剩余可预留金额 1.598592 元，不足以再发第 5 个同上界请求。成功回包也不释放差额。部分已知用量的估算与全部已发请求的完整账单是不同字段；unknown 后可用额度为 0，并另列未分配账面金额。

直接用公开人民币价格，无需假装知道实时汇率。USD 政策的备用路径则必须同时提供审计来源、保守人民币/美元上界、明确验证状态及有效期，缺少或过期立即拒绝；测试中的 10 元/美元仅是虚构报价，不代表已核验的真实汇率。政策 JSON 固化所有费率、币种、上界、引用来源和时间，重开账本逐字校验。价格快照日期为 2026-10-24 UTC，2026-10-25 UTC 起不再准许新派发；过期后仍可读取旧账本作审计。离线 CLI 使用明确标记的冻结模拟时钟，避免把过期价格复用为真实执行许可。

公开来源：

- https://api-docs.deepseek.com/zh-cn/quick_start/pricing/
- https://api-docs.deepseek.com/api/create-chat-completion/

**仍不承诺服务商账单绝对硬上限，真实入口保持阻塞。**尚未验证具体账户的币种/费率、服务端所有可计费 token 是否受该上下文与 max_tokens 约束，也没有供应商侧的账户支出锁；别的客户端、价格即时改变、文件被人为替换或服务商违反声明不能由本地 SQLite 阻止。账本上限依赖单一规范路径、协作入口、未被篡改存储、有效峰值价及 token 上界假设。`provider_bound_verified=false`；`OfflineMonetaryProvider` 仅接纳声明为离线 fixture 的桩，拒绝真实 provider。`check_model.py --live`、`benchmark_ccare.py --live` 和新 CLI 的 --live 都在网络前阻塞。未将此机制偷偷接到普通网站收费路径，也不宣称网站受 10 元限制。

最小连通计划调整为单条虚构 JSON 请求、最多 1 次、400 输出 token；后续最多 3 次同预留规格烟测，所有运行、失败和重试共享同一个 10 元授权。之前的“5 调用连通 + 60 调用批量”是历史方案，不能在这套保守预留下执行。configs/deepseek_first_run.json 已同步，live_enabled=false；不重复索要已批准预算。

## 只读环境观测与刷新建议

2026-10-24 本轮 environment_status 返回：

- environment_id：`ccarenv_b64_Y2NhcmVudl8zZTQ1YzM4ZGFmYTg4MTkxOTIxOTY1MzI4ODZmNTIyMw`
- source_config_id：`6b7f8514-37b6-4a24-830d-c109b93d1cb9~cecfg_6adbad30a27881a0a929009fbeeb12c7`
- source_config_version_id：`6b7f8514-37b6-4a24-830d-c109b93d1cb9~cecfgver_6adbae2670ac81a0b7dc1cf7c0c59c7f`
- spec_revision=18，observed_spec_revision=18，observations_current=true；运行中。
- 网络为 restricted/enforced，effective_allowed_hosts 未列 api.deepseek.com。
- 此观测未报告就绪 secret、runtime variable 或 outbound identity；相应数组为空。
- 元数据不提供 environment_name/configuration_name，故无法确认界面里的友好名称。仓库名 KinVoice 不等于云环境名，不能凭猜测宣称它们一致。

普通环境变量存在性与代理注入凭据是两类证据。`os.environ` 的 DEEPSEEK_API_KEY/KINVOICE_API_KEY 均为 false 只说明当前进程没有这两个变量，**不能单独证明 Network Secret/代理注入不可用**；代理 placeholder 也不能被视为失效或要求泄露真实值。需要当前的、匹配所选环境的运行就绪观测及目标域名策略。已将 `RemoteProvider` 改为保留继承的代理与 CA 设置（trust_env=true），保持 TLS 校验和禁止重定向；mock 测试客户端显式与真实代理隔离，没有真实探测服务商。

当前可用云工具只有状态与诊断读取，未暴露应用配置、热刷新或重启能力，也未返回运行时刷新 capability；本轮未读取可能包含秘密的诊断日志，未编辑网络策略、代理或路由。技能明确环境配置变化须使用平台配置工作流；启动时 `/etc/codex/network-policy.json` 不是最新应用状态的替代品。

父对话可将截图中的环境/配置与以上 ID、版本对应，确认 Network Secret 指向 api.deepseek.com 且配置属于当前附着环境。若界面提供受支持的“应用到当前环境”或重启流程，应在保存提交后使用该流程，再在**原任务**读取 environment_status，要求观测当前、修订匹配、目标策略 enforced 且对应凭据 ready。不要只刷新浏览器就假定执行实例已重启，不创建替代任务、不要求发送密钥。若 UI 只显示友好名而无 ID，需由平台确认配置与附着实例的关联；不能用“环境变量不存在”替代这一核验。本轮代码已提交后再由用户决定是否进行可能影响状态的刷新，代理凭据就绪也仍不能解除费用假设阻塞。

## 离线命令与结果

```bash
.venv/bin/python scripts/check_ccare.py
node --test tests/web-session.test.mjs tests/web-stream.test.mjs
.venv/bin/python scripts/check_cny_budget.py
.venv/bin/python scripts/check_cny_budget.py --mock --ledger /tmp/kinvoice-offline-fees.db --attempts 6
.venv/bin/python scripts/check_cny_budget.py --mock --ledger /tmp/kinvoice-offline-fees.db --attempts 2
```

首次 6 次尝试：4 次本地桩调用、2 次预算拒绝；再次运行同一账本：0 次桩调用、2 次预算拒绝，预留仍为 8.401408 元。费用只是虚构用量估算，actual_billed_cny=null，真实外部调用均为 0。CI 重复运行同一测试账本，验证跨运行累计。

本轮后端基线 97 项通过；新增跨进程并发、重复领取、恢复、中断、未知用量、上界破坏、过期价格/FX、元数据变更、损坏存储和代理保留等离线回归，最终计数见 PR。前端原有 19 项重跑；不新增真人数据或声称模型效果。

### 用户要求“再试一次”后的最新复查

运行元数据随后更新为 spec_revision=19、observed_spec_revision=19、observations_current=true，source_config_id/version_id 与上表相同。网络仍为 restricted/enforced，目标域名未列入生效列表，未报告对应就绪 secret。这表明运行**已能观测到新的修订**，不能笼统把原因归为“完全没有刷新”；需要将界面截图的配置关联到同一个 source_config_id/version，并核对已发布修订 19 的 secret 与域名内容。当前工具仍不提供友好名称或重启/热刷新操作，未擅自重启实例。普通进程变量缺失仅是补充信息。费用与访问门禁都未被绕过，真实调用持续为 0。

最终离线验收：115/115 后端测试通过（3.364 秒），前端 19/19 通过；12 个独立进程竞争仅 4 个成功预留，其余预算拒绝；前后两次 CLI 证明跨运行不归零。价格/FX 到期、模糊或冲突结算、存储错误、中断恢复和推理细分均覆盖。实际提交和最终 head 的 CI 另记原 PR，旧 head 成功不冒充本轮成功。

## 配置版本差异的最终定位与预算复核

父侧 `list_environments` 报告 KinVoice 最新已保存版本为：
`6b7f8514-37b6-4a24-830d-c109b93d1cb9~cecfgver_6adc40ba32a081a0a08031af599c2838`。
本任务直接 `environment_status` 的最新观测是 spec_revision=observed_spec_revision=20、observations_current=true，但 source_config_version_id 仍为：
`6b7f8514-37b6-4a24-830d-c109b93d1cb9~cecfgver_6adbae2670ac81a0b7dc1cf7c0c59c7f`。
环境 ID、source_config_id 不变；网络 restricted/enforced 未允许 api.deepseek.com，未报告对应就绪凭据。前者为父侧提供的最新配置元数据，后者为本任务直接观测，两种来源不混同。

因此精确阻碍是**当前运行实例尚未使用已保存的新配置版本**，而不是已证实用户填错密钥，也不是仅凭进程变量推断代理 secret 不存在。运行修订 20 并不表示 source_config_version_id 已切到最新版本。

已穷尽本任务可用环境工具：状态读取、诊断读取，以及仅用于 starting 状态的等待；没有配置应用、实例重绑、热刷新或重启调用。wait_for_environment 不能把运行中的实例升级到另一个配置版本。技能也明确运行上下文工具不是配置变更工作流。本轮没有调用未文档化管理接口、改代理/策略文件、创建新任务或猜测界面按钮。

唯一下一步是由平台支持的原任务配置应用流程，将上述**新版本**关联并应用到当前实例，再复查 source_config_version_id、对应凭据 ready 和域名策略 enforced。当前工具无法验证哪个具体 UI 按钮能执行这一动作，不能把“刷新浏览器”“重复保存”或“重启某个进程”冒充已验证的操作。父侧可依所掌握的环境配置能力处理该版本关联；需要新的安全确认时由平台界面完成。成果已提交推送，不应通过新建替代任务来解决。

官方文档本轮再次核对：peak 输入 2 元/百万、输出 8 元/百万，1M 上下文，max_tokens 限制生成 completion；thinking 默认开，应显式 disabled，JSON 要明确 response_format 及 JSON 指令。现有 2.100352 元预留按完整上下文收费而非短输入，且成功不退款，确实保守，会限制后续样本量；它不是要求再次扩展账本或提高授权的理由。人民币直接定价无需额外虚构汇率。现有单次预留按公开契约低于 10 元，不应将“获得服务商账单绝对保证”无限加码成单次小额烟测的前置条件；应明确公开费率/token 上界假设，并对本任务请求保守累计。

当前网络与凭据前置条件尚未满足，故没有解锁离线专用适配器或绕过 live 门禁来发送请求，也不把此状态称为连通失败（没有尝试 HTTP 模型调用）。配置生效后才核验当时价格/有效期、同一规范账本剩余预留和单次限制，执行用户已授权的一条虚构 JSON 请求；不做额外付费重试。本轮新增源码为 0，不再扩大账本工程。既有后端115/115、前端19/19及原 head CI 成功记录保持；文档 head CI 单独在 PR 核对。真实模型请求累计仍为0，10元授权未动用。

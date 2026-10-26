# 同模型批量评测准备状态

**真实批量尚未执行：预算不足；独立专业评分未获得。** 本目录不是优势证明，不能称临床或独立专家结果。

- PROTOCOL.md + freeze.json：方法/代码/数据/rubric先冻结；不改旧真实探索结果。
- COST_REVIEW.md：官方费率复核与无法证明更紧短输入上界的原因。
- development-rule-diagnostics.json：仅24开发例的原本地状态/策略，不评分、不预测36候选。
- mock-development：72条计划输出（24×三臂）的显式fixture结果、汇总与空白盲评导出；168次本地fixture调用，0外部调用。model=offline-fixture，无真实HTTP/usage。mock前缀与mode明确标识，不能用于效果比较。

## 离线发现与验证

发现两个D07开发例的当前威胁措辞，原本地risk均为unknown，未走急性安全模板；第1例allowed仅listen，第2例允许四类。这是规则覆盖缺口，**没有证明线上能安全处理这些情况**。真实模型可能识别也可能失败，本轮未验证。保留原输入/标签/诊断，不以更换标签掩盖缺陷；方法若修复，需新版本冻结再评价，不能反复用候选结果调参。

流程初测因mock配置缺少remote必填项失败。已仅在明确注入MockTransport时用本地disabled设置构造并切换执行模式；live仍走原配置验证与安全代理。记录HTTP实际尝试与派发前失败的区别，未知usage不作0token。所有实时日志先落盘再dispatch，崩溃不续发。

回归涵盖：完整三臂分母、盲评/密钥分离、候选mock拒绝、预算不足的原子回滚、已预留槽位不重用、故障后停止留行、真实路径预留拒绝不触达transport、已有急性模板共享且0调用。当前生产算法未改；工程验证不等于效果评分。

## 复现与审核

```sh
.venv/bin/python scripts/batch_evaluation.py --mode mock --split development --output /tmp/kinvoice-new-development-run
.venv/bin/python scripts/check_ccare.py
```

输出目录必须新建；全量run保留prepared/dispatch日志、plan、outputs、summary、reviewer与custodian。只给评分者reviewer目录，custodian单独保管；本公开mock包同时展示两者只为流程复现，不是假称已盲评。未来真实评分必须由独立保管者分发。

不提供跳过资金检查入口。真实启动还需用户批准足够的累计授权、审计迁移并重新冻结、有效价格快照；任何未知费用/usage故障均保留预留，不自动重试、不退款。当前阻塞不是平台拒绝收费动作，而是预算可行性审计主动阻断；实际没有发起新请求。

需刘老师或独立合适评阅者确认标签与安全边界、给出盲评与争议裁决。自动问号/规则诊断不冒充专业评分。当前可信结论仅为：流程可离线复现，但方法优势与实际安全质量仍未证实。

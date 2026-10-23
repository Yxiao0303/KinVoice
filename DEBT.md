# 技术债务清单

> 更新日期：2026-07-06（上次：2026-07-04）
> 用于追踪项目中已知的冗余代码、设计问题和待优化项，统一管理，分批清理。

---

## ⚡ 常见运行时错误排查

> 新增于 2026-07-05。这类报错已多次出现，统一记录在此避免重复踩坑。

---

### E1. `Cannot find module '../../helper/apis/xxx'`

**症状**：`Uncaught Error: Cannot find module '../../helper/apis/xxx'` 在快应用运行时报错

**原因**：
- 某个 `.ux` 页面 import 了 `src/helper/apis/` 下不存在或已删除的 JS 文件
- 通常发生在以下场景：
  1. 后端重构后某个 API 模块被删除/重命名，但前端 import 没有同步更新
  2. 新增页面时写了 import 但忘了创建对应的 API 文件
  3. 合并代码时遗漏了某个文件的删除

**排查方法**：
```bash
# 在 src/helper/apis/ 目录下列出所有实存文件
ls src/helper/apis/*.js

# 搜索所有引用 helper/apis 的 import
grep -rn "helper/apis/" src/pages/
```

然后逐一比对：引用的文件名是否在实存列表中？文件名拼写是否一致？

**历史上的实例**：

| 日期 | 文件 | 错误 import | 根因 | 修复 |
|------|------|-----------|------|------|
| 2026-07-05 | `src/pages/Companion/index.ux:194` | `import profileAI from '../../helper/apis/profile_ai'` | profile_ai.js 模块已删除，Companion 页面未清除 import | 删除该 import 行 |
| (更早) | `src/helper/apis/index.js` | 遗漏 profile_ai 导出 | 当时 index.js 没有导出 profile_ai | 已在清理时删除 |

**当前 `src/helper/apis/` 实存文件**（2026-07-06）：

| 文件 | 说明 |
|------|------|
| `.backend-url.js` | 后端 URL 配置（辅助文件） |
| `auth.js` | 用户认证（注册/登录） |
| `cards.js` | 传承笔记 CRUD + 文件夹 |
| `chat.js` | 陪伴对话（会话持久化 + 历史管理） |
| `chatroom.js` | 家庭聊天室 |
| `config.js` | API 配置 |
| `example.js` | 新增接口模板 |
| `family.js` | 家庭组管理 |
| `index.js` | 统一导出（13 个模块） |
| `nvc.js` | NVC 非暴力沟通转换 |
| `profile_ai.js` | AI 档案编写 |
| `profiles.js` | 家庭成员档案 |
| `replica.js` | 音色克隆 |
| `tts.js` | TTS 文本转语音 |

**所有页面 import 验证**（2026-07-06）：

| 页面 | 引用的 API 模块 | 状态 |
|------|---------------|------|
| BreakIce | family, chatroom | ✅ |
| ChatRoom | chatroom, nvc | ✅ |
| Companion | chat, family, tts, profile_ai | ✅ |
| CustomVoice | replica | ✅ |
| Family | auth, family | ✅ |
| FamilyJoin | auth, family | ✅ |
| Profile | auth, family, profile_ai | ✅ |
| ProfileDetail | profiles | ✅ |
| VoiceSelect | tts, replica | ✅ |

**预防规则**：
- 删除/重命名任何 `helper/apis/xxx.js` 时，必须同步检查并更新所有引用该模块的 `.ux` 文件
- 提交前运行 `grep -rn "helper/apis/" src/` 确认所有引用模块都存在
- `index.js` 中的导出列表也必须与实际文件保持一致

---

## 🔴 高优先级（影响功能正确性 / 运行成本）

### 1. ~~Companion.onHide() 触发两次 LLM 调用~~ ✅ 已修复（2026-07-06）

**位置**：`src/pages/Companion/index.ux` → `onHide()` → `triggerProfileUpdate()`

**原问题**：离开 Companion 页面时调用 `profileAI.updateDynamic()`。

**修复内容**：
- 删除了 `triggerProfileUpdate()` 方法及其 import
- 后端 `chat.py` 已在对话中自动做 fire-and-forget 后台提取（每 3 条消息更新档案，每 5 条提取卡片），前端无需额外调用
- Companion.onHide() 现在只设置 `isActive = false`

---

### 2. Card 模型三种语义混在一张表（上帝表）

**状态**：✅ **已解决**（2026-07-06）

**位置**：`backend/app/models/card.py` → `Card` 类

**变更内容**：
- Card 模型已精简为统一的"文件夹 + Markdown 笔记"模式
- 字段：`id / title / content(Markdown) / author / folder_id / family_id / created_at / updated_at`
- 不再有 `type` 字段，不再承载 NVC / chat_message / chat_conversation 三种语义
- ORM 与 Pydantic Schema 字段已对齐
- Memory 页面同步逻辑已重写

---

### 3. ~~POST /cards/favorite 后端完整但前端未接入~~

**状态**：✅ **已废弃**（功能随 Card 模型重构移除）

**变更内容**：
- `memory.py` 完全重写，不再有 `/cards/favorite` 端点
- `cards.js` 前端也已重写，仅保留文件夹/笔记 CRUD
- 错误码 3036/3037/3038（favorite 相关）在 errorCodes.js 中可能仍残留

---

## 🟡 中优先级（死代码 / 未使用）

### 4. Conversation.is_favorited / ChatMessage.is_favorited 死字段

**位置**：`backend/app/models/card.py` → `Conversation.is_favorited`（L21）、`ChatMessage.is_favorited`（L39）

**问题**：
- 两个 `is_favorited` 字段定义了但**全项目没有任何代码将其设为 True**
- 原 DEBT #4 是关于 `Card.type = "chat_conversation"`（已随 Card 重构移除），但 Conversation/ChatMessage 的收藏字段仍然存在且从未使用
- `Conversation.type` 现在用于区分 ai/private/group（聊天室功能），不再涉及收藏语义

**建议方案**：如果收藏功能不再计划实现，删除这两个字段。

---

### 5. ~~llm_service 中未使用的函数~~ ✅ 已修复（2026-07-06）

**位置**：`backend/app/services/llm_service.py`

**修复内容**：
- 删除了 `chat()` 函数（无人调用，chat.py 和 nvc.py 都直接调 `call_llm`）
- 删除了 `chat_with_system()` 函数（si 兼容分支已随 chat.py 重写移除）
- 删除了 `SYSTEM_PROMPT_CHAT` 常量（仅 chat_with_system 使用）
- 保留了 `chat_completion()`（nvc_service.py 在用）
- 保留了 `call_llm()`（chat.py, nvc.py 在用）

**当前 llm_service.py 导出**：`call_llm`、`chat_completion`（两个函数，职责清晰）

---

### 6. ~~Demo / DemoDetail 框架模板页面~~ ✅ 已删除（2026-07-06）

**位置**：`src/pages/Demo/index.ux`，`src/pages/DemoDetail/index.ux`

**修复内容**：
- 删除了 `src/pages/Demo/` 和 `src/pages/DemoDetail/` 目录
- 从 `manifest.json` 的 `router.pages` 和 `display.pages` 中移除了对应条目

---

### 7. ~~apis/index.js 遗漏 profile_ai 导出~~ ✅ 已删除（profile_ai 模块已恢复并正确导出）

**位置**：`src/helper/apis/index.js`

**状态**：profile_ai 模块已恢复并正确在 index.js 中导出。本条作废。

---

### 8. ~~POST /chat 的 si 兼容分支~~

**状态**：✅ **已废弃**（chat.py 完全重写 + chat_with_system 已删除）

**变更内容**：
- `chat.py` 已完全重写为 Cloudie 主 Agent，统一走会话持久化模式
- 不再有 si 兼容分支（`chat_with_system` 调用）
- `chat_with_system()` 和 `SYSTEM_PROMPT_CHAT` 已从 llm_service.py 中删除（见 #5）

---

## 🟢 低优先级（优化建议）

### 9. ~~sync_cards 硬编码 type="nvc"~~

**状态**：✅ **已废弃**（sync_cards 已随 memory.py 重写移除）

---

### 10. cloudie_prompt.py 与 llm_service.py 两套系统提示词

**位置**：`backend/app/services/cloudie_prompt.py`（CLOUDIE_SYSTEM_PROMPT），`backend/app/services/llm_service.py`（SYSTEM_PROMPT_CHAT）

**当前状态**：同一问题已扩散至更多文件：

| 文件 | 提示词变量 | 用途 |
|------|-----------|------|
| `cloudie_prompt.py` | `CLOUDIE_SYSTEM_PROMPT` | Cloudie 陪伴对话（主 prompt，~70 行） |
| `api/nvc.py` | `NVC_SYSTEM_PROMPT` | NVC 转换（~67 行，含 JSON 输出指令） |
| `services/nvc_service.py` | `NVC_SYSTEM_PROMPT` | NVC 破冰（~23 行，旧版） |
| `nvc_service.py`（根目录） | `NVC_SYSTEM_PROMPT` | NVC 破冰（~25 行，另一版本） |

**问题**：
- `SYSTEM_PROMPT_CHAT` 已随 `chat_with_system()` 删除（见 #5）✅
- 存在 3 份不同的 NVC 提示词（nvc.py / nvc_service.py / root nvc_service.py），内容不同
- 根目录 `nvc_service.py` 的定位不明确 — 它是后端的副本还是在别处使用的？
- 建议：统一管理所有 prompt 到一个文件（如 `prompts.py`），各 API 按需引用

---

### 11. family_members 表命名冲突

**位置**：`backend/app/models/profile.py` → `FamilyMember`，`backend/app/models/family.py` → `FamilyMembership`

**问题**：现有 `family_members` 表是"家庭成员档案"（父亲/母亲的名字、生日），新增的 `family_memberships` 表是"家庭组成员关系"。两者概念不同但命名容易混淆。

**当前状态**：`family.py` 模型文件中已有注释说明两者区别。无需紧急处理。

**建议方案**：将现有 `family_members` 重命名为 `family_member_profiles`。

---

## 🆕 新增问题（2026-07-06）

### 12. ~~前端 profile_ai 端点与后端不匹配~~ ✅ 已修复（2026-07-06）

**位置**：
- 前端：`src/helper/apis/profile_ai.js` → `POST /profile/ai/update-dynamic`、`POST /profile/ai/update-stable`
- 后端：`backend/app/api/profile_ai.py`

**修复内容**：
- 后端新增 `POST /profile/ai/update-dynamic` 端点：自动从 DB 读取用户最近 60 条对话消息 → 调用 `update_dynamic_profile()`
- 后端新增 `POST /profile/ai/update-stable` 端点：自动从 DB 读取用户最近 200 条对话消息 → 调用 `update_stable_profile()`
- 已有 `POST /profile/ai/extract`（手动传入 messages）和 `GET /profile/ai/read` 保持不变
- 同时删除了 Companion.onHide() 中的冗余 `triggerProfileUpdate()` 调用（见 #1）
- Profile 页面手动调用 `updateStable()` 现在可用

---

### 13. 🟡 根目录 nvc_service.py 与 backend 内版本重复

**位置**：
- `nvc_service.py`（项目根目录）
- `backend/app/services/nvc_service.py`
- `backend/app/api/nvc.py`（内联 NVC prompt）

**问题**：
- 根目录的 `nvc_service.py` 导入 `from app.services.llm_service import chat_completion`，说明它是后端代码，但放在项目根目录而非 `backend/app/services/`
- 根目录版本与 `backend/app/services/nvc_service.py` 内容相似但提示词不同（根目录版 prompt 更详细）
- `backend/app/api/nvc.py` 又内联了第三份 NVC prompt（最详细版本，~67 行）
- 实际生效的是 `api/nvc.py` 内联的版本（因为 nvc.py 路由直接调用 `call_llm`，不走 nvc_service）

**建议方案**：确定一个 canonical 版本，删除其余两份。推荐保留 `api/nvc.py` 的 prompt（功能最完整），将其提取到 `services/nvc_service.py` 中统一管理。

---

### 14. 🟢 Conversation/ChatMessage 收藏字段从未写入

**位置**：`backend/app/models/card.py` → `Conversation.is_favorited`、`ChatMessage.is_favorited`

**问题**：两个 Boolean 字段定义了但全项目无任何代码将其设为 `True`。无 favorite API 端点。

**建议方案**：确认是否计划实现收藏功能。不需要则删除字段。

---

### 15. 🟢 helper/apis/example.js 未注册

**位置**：`src/helper/apis/example.js`

**问题**：文件存在但 `index.js` 没有导入/导出它。似乎是意图保留的接口模板。

**建议方案**：如果确认是模板文件，在 index.js 中加注释说明；或者移到 `scripts/` 目录。

---

## 📋 清理计划

| 批次 | 条目 | 预计工作量 | 状态 |
|------|------|-----------|------|
| ~~第一批~~ | ~~#12 修复 profile_ai 前后端端点不匹配~~ | 小 | ✅ 已完成 |
| ~~第一批~~ | ~~#1 删除 Companion.onHide() 冗余调用~~ | 小 | ✅ 已完成 |
| ~~第一批~~ | ~~#5 删除 llm_service 未用函数~~ | 小 | ✅ 已完成 |
| ~~第一批~~ | ~~#6 删除 Demo 页面~~ | 小 | ✅ 已完成 |
| 第二批 | #4 清理 is_favorited 死字段 | 小 | |
| 第二批 | #14 清理收藏残留 | 小 | |
| 第三批 | #10 统一系统提示词管理 | 中 | |
| 第三批 | #13 合并 nvc_service.py 重复 | 小 | |
| 第四批 | #11 family_members 重命名 | 中 | |
| 第四批 | #15 example.js 归类 | 小 | |

**已完成**：
- ✅ #1 Companion.onHide() 冗余调用删除（2026-07-06）
- ✅ #2 Card 模型拆分（God table → 统一笔记模型）
- ✅ #3 favorite 接口清理（随 memory.py 重写移除）
- ✅ #5 llm_service 未用函数删除（chat, chat_with_system, SYSTEM_PROMPT_CHAT）
- ✅ #6 Demo/DemoDetail 页面删除（2026-07-06）
- ✅ #7 profile_ai 导出（index.js 已正确导出）
- ✅ #8 si 兼容分支（chat.py 完全重写 + chat_with_system 删除）
- ✅ #9 sync_cards 重构（随 memory.py 重写移除）
- ✅ #12 前后端 profile_ai 端点不匹配（后端补充 update-dynamic/update-stable）

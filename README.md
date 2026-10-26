# KinVoice · C-CARE 个人情绪支持原型

当前版本 **v0.5** 提供本地网站，聚焦因亲子冲突产生情绪困扰的 18–25 岁大学生。C-CARE 根据用户原话、当前意愿和家庭安全线索限制支持策略，再生成与检查回应。

已实现登录、对话、支持方式选择、暂停、清空、账号删除、技术讲解与记录导出。网站可以显示后端处理阶段；检测到断连后取消本地任务，停止启动后续步骤。服务商已收到的请求仍可能继续处理或计费。

当前使用虚构案例进行内部演示。固定示例不调用模型；远程接口已实现并通过模拟测试，真实连通、模型效果、专业审阅与真人研究尚未完成。

本轮已增加本页确认/纠正/撤销、统一资源上限和七条件完整 mock 评测；真实 CLI 在人民币费用保护及安全配置就绪前保持阻塞。详见[本轮执行与边界](docs/ROUND3_REVIEW_BUDGET_2026-10-24.md)。

人民币累计预留账本及代理凭据/环境版本复核见[本轮补充记录](docs/CNY_LEDGER_RUNTIME_2026-10-24.md)；仅离线验证，未启用真实收费请求。

## 当前研究优先级

研究导向的方法定义、规则/LLM边界、差距矩阵与冻结强对照协议见[研究审计](docs/RESEARCH_METHOD_AUDIT_2026-10-24.md)。后续开发优先验证证据与意愿约束的增量价值；真实连通与网页演示已在后续任务完成，前文及早期文档的“未连通”是历史状态，不能当作当前结论。真实效果对照、专业审核和算法优势仍未证实。

本轮[选择性判断实验](research/selective-v1/RESULTS.md)已冻结方法后构造新合成探索集：实际比较NB、线性分类器和拒判机制，报告覆盖率、错误与澄清负担；低覆盖率结果不构成算法优势。

用户选择“先倾听、少追问”后的[动作层小实验](research/listen-first-v1/RESULTS.md)将unknown与必须追问解耦，保留必要安全询问；固定模板诊断仍有否定与转述错误，尚未接入默认网页。

2026-10-26已完成[一个新虚构案例的真实三臂探索](research/three-arm-v1/RESULTS.md)：七次API调用全部完成，强单步/通用多步/C-CARE输出相近；没有证明方法优势，并记录了C-CARE允许策略集合过宽的失败线索。

后续[当前意愿约束修复](docs/CURRENT_INTENT_MASK_FIX_2026-10-26.md)已完成离线开发回归：明确当前倾听意愿限制允许动作，保留修改意愿、unknown 与独立安全处理；原真实探索输出和负面结论保持不变。

新增[60例合成评测包与评分标准](research/evaluation-pack-v1/README.md)：24开发/36候选留出，按30个情境家族分组，附五维量表、空白盲评表与冻结哈希。全部AI合成、未专业审阅；同一作者见过全包，不称独立测试，本轮没有运行候选案例的算法预测或评分。

[批量对照协议与成本审计](research/batch-evaluation-v1/PROTOCOL.md)提供整批预算准入、失败保留与盲评导出流程。当前仅开发集mock验证；候选集无预测、真实批量运行因预算不足未启动，未产生新的效果结论。

[D07离线修复与批量方法v2](research/batch-evaluation-v2/README.md)补充当前威胁作用域规则；原mock保留，列出仍存在的引语/时序漏报与旧规则误报。候选未运行，提额未批准。

[引语/时间作用域v3](research/batch-evaluation-v3/README.md)处理施害者引语、后置时间与明确解除的第三方引语；保留跨轮解除失败与后续语义接口方案，未运行候选集。

[跨消息事件绑定v4](research/batch-evaluation-v4/README.md)复用来源与修订机制，关闭明确同主体跨轮解除误报；歧义保留事件并必要澄清，未运行候选或真实批次。

[24例真实开发三臂结果](research/batch-evaluation-v5/RESULTS.md)已完成：保留全部72输出、152次调用、共享安全模板及校验回退。没有证明C-CARE优势，明确记录必要澄清遗漏与无依据措辞；专业评分尚缺，36候选未运行。

## 在本机运行新版网站

建议 Python 3.12。在仓库根目录运行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend/requirements-ccare.lock.txt
.\.venv\Scripts\python.exe backend/start.py --mode demo --port 8768
```

打开 <http://127.0.0.1:8768/>，创建只供演示的本地账号。依赖安装后也可用 `scripts/Start-Demo.ps1 -Port 8768` 启动。macOS/Linux 用 `python3` 创建环境，再使用 `.venv/bin/python` 执行同样的安装和启动步骤。

模型模式的配置示例在 `backend/.env.deepseek.example`。复制为本机 `backend/.env.local` 后填写新密钥；不要提交这个文件，也不要使用旧历史中暴露过的凭证。配置预检和真实连通检查见 [模型接入说明](docs/MODEL_CONNECTION_2026-10-23.md)。

## 演示与技术材料

- [最新版答辩 PPT、讲稿与现场演示流程](docs/presentation/README.md)：12 页，10 页主讲、2 页备答，含 90 秒固定案例流程。
- [v0.5 功能与工程验证](docs/STREAMING_DEMO_UPGRADE_2026-10-23.md)：阶段事件、取消任务、技术记录和隐私边界。
- [C-CARE 技术与创新边界](docs/CCARE_V2_TECHNICAL_POSITION.md)：已实现机制、待验证假设、强基线与消融设计。
- [工程验证记录](docs/verification/2026-10-23-streaming/README.md)：59 项后端离线测试、15 项前端测试通过；这些数字不代表模型准确率或心理支持效果。
- [开发与运行说明](docs/CCARE_DEVELOPMENT.md)：早期原型说明；v0.5 阶段进度与取消行为以本页和升级说明为准。
- [上传范围与历史敏感文件说明](docs/PUBLICATION_2026-10-24.md)。

离线检查可运行 `.venv/Scripts/python.exe scripts/check_ccare.py` 和 `node --test tests/web-session.test.mjs tests/web-stream.test.mjs`。后端测试禁止外部 HTTP 传输，不消耗模型调用。

## 数据与使用范围

新入口只开放认证、个人支持和账号删除。对话不存入账号数据库，也不进入家庭卡片；页面对话和令牌仅在当前页内存。技术记录导出排除原始对话、原话引用、生成回复、账号和密钥。模型模式仍需用户同意向服务商发送处理所需内容，清空或暂停不能撤回已外发数据。

旧快应用源码保留，尚未适配新认证与接口。旧入口 `app.legacy_main` 已阻断启动，不应部署。下方内容保留为历史说明，不代表新版网站当前开放的功能。

## 代码来源与快照

项目在 [qiyuxi24/KinVoice](https://github.com/qiyuxi24/KinVoice) 的旧源码基础上增加 C-CARE 与本地网站。当前仓库保存清理后的 v0.5 快照和新增答辩材料；未复制来源仓库含敏感文件的提交历史。旧源码说明保留在下方，本仓库不额外授予第三方代码的开源许可。具体范围见 [上传版本说明](docs/PUBLICATION_2026-10-24.md)。

## 历史项目说明

> 前端：快应用（Quick App） | 后端：FastAPI + SQLite | AI：LLM 大模型  
> 通过 AI 陪伴对话、家庭组、传承笔记、语音合成，促进家庭成员间的沟通与记忆传承。

---

## 一、项目结构

```
KinVoice/
├── src/                         # ★ 快应用前端源码
│   ├── app.ux                   # 入口：全局注入 $utils/$apis/$user，触发身份初始化
│   ├── manifest.json            # 应用配置 + 路由表
│   ├── assets/
│   │   └── styles/              # variables.less, mixins.less, style.less
│   ├── pages/
│   │   ├── Main/                # 单页容器（if 指令切换 4 个 Tab 组件）
│   │   ├── ProfileDetail/       # 用户档案详情（Markdown 阅读/编辑）
│   │   ├── Family/              # 家庭组管理（创建/加入/成员列表）
│   │   ├── FamilyJoin/          # 加入家庭组（输入 ID + 密码）
│   │   ├── ChatRoom/            # 家庭聊天室（私聊/群聊，轮询消息）
│   │   ├── BreakIce/            # 破冰页（独立页，家庭聊天入口）
│   │   └── About/               # 关于页面
│   ├── components/
│   │   ├── CompanionTab/        # Tab 1：Cloudie AI 陪伴对话
│   │   ├── BreakIceTab/         # Tab 2：破冰页入口
│   │   ├── MemoryTab/           # Tab 3：传承笔记（文件夹 + 笔记 CRUD）
│   │   ├── ProfileTab/          # Tab 4：我的（头像/昵称/菜单）
│   │   └── Tabbar/              # 底部 TabBar（事件驱动切换）
│   ├── helper/
│   │   ├── ajax.js              # 网络层：Promise 封装 @system.fetch（超时 20s）
│   │   ├── userIdentity.js      # 用户身份：设备 UUID + 昵称（storage 持久化）
│   │   ├── utils.js             # 工具方法（showToast, queryString 等）
│   │   ├── navigate.js          # 路由封装（safePush/safeBack）
│   │   ├── errorCodes.js        # 错误码体系
│   │   └── apis/                # 业务接口层
│   │       ├── config.js        # baseUrl 配置
│   │       ├── chat.js          # /chat 对话
│   │       ├── cards.js         # /folders, /cards 笔记
│   │       ├── profiles.js      # /profiles 档案
│   │       ├── family.js        # /family 家庭组
│   │       ├── chatroom.js      # /chatroom 聊天室
│   │       └── index.js         # 聚合导出到 $apis
│   └── CardDemo/                # 快应用卡片示例（厂商专属）
│
├── backend/                     # ★ FastAPI 后端
│   ├── start.py                 # 一键启动脚本
│   ├── init_db.py               # 建表 + 迁移脚本
│   ├── .env / .env.example      # LLM_API_KEY 等环境变量
│   ├── data/kinvoice.db         # SQLite 数据库
│   └── app/
│       ├── main.py              # FastAPI 入口（11 个路由 + CORS + 异常处理）
│       ├── config.py            # Pydantic Settings 配置管理
│       ├── api/                 # 路由层
│       │   ├── chat.py          # POST /chat — Cloudie 陪伴对话（核心）
│       │   ├── memory.py        # CRUD /folders, /cards — 传承笔记
│       │   ├── summarize.py     # POST /chat/summarize — 对话总结
│       │   ├── profile.py       # CRUD /profiles — 用户档案
│       │   ├── profile_ai.py    # /profile/ai — AI 档案编写
│       │   ├── cards_ai.py      # /cards/ai — AI 卡片提取
│       │   ├── family.py        # /family — 家庭组管理
│       │   ├── chatroom.py      # /chatroom — 家庭聊天室
│       │   ├── tts.py           # /tts — 文本转语音
│       │   └── replica.py       # /replica — 音色克隆
│       ├── services/            # 业务逻辑层
│       │   ├── llm_service.py   # LLM 调用封装（兼容 OpenAI 接口）
│       │   ├── cloudie_prompt.py # Cloudie 系统提示词工程
│       │   ├── profile_writer.py # AI 档案编写服务
│       │   ├── card_summarizer.py # 对话→传承笔记提取
│       │   ├── search_service.py  # FTS5 全文检索
│       │   ├── family_service.py  # 家庭组业务逻辑
│       │   ├── tts_service.py     # TTS 语音合成
│       │   └── replica_service.py # 音色克隆服务
│       ├── models/              # ORM 数据模型
│       │   ├── card.py          # Conversation + ChatMessage + Card + Folder
│       │   └── profile.py       # FamilyMember（用户档案）
│       ├── schemas/             # Pydantic 请求/响应模型
│       ├── middleware/
│       │   └── user_identity.py # X-User-Id 提取中间件
│       ├── db/
│       │   └── session.py       # 异步 SQLAlchemy 引擎 + Session
│       └── utils/
│           └── logger.py        # loguru 日志配置
│
├── scripts/                     # 前端辅助脚本
├── DEBT.md                      # 技术债务 + 常见错误排查
├── env-requirement.md           # 环境要求
└── package.json                 # 前端依赖
```

---

## 二、核心功能

### 2.1 Cloudie AI 陪伴对话

主 Tab，AI 温暖陪伴者。后端 chat.py 自动编排：
- 每次对话注入用户档案 + FTS5 全文检索上下文
- 对话结束后 fire-and-forget 后台提取档案更新 + 传承卡片
- 支持主动标记 `<!--PROFILE-->` / `<!--CARD-->` 触发即时保存

```
用户输入 → POST /chat → 注入档案 + 检索上下文 → LLM 回复
                                    └→ 后台：更新档案 / 提取卡片
```

### 2.2 家庭组

创建/加入家庭组（8 位 ID + 6 位密码），成员管理。

| 接口 | 功能 |
|------|------|
| POST `/family/create` | 创建家庭组 |
| POST `/family/join` | 加入家庭组 |
| GET `/family/my-group` | 查询我的家庭组 |
| POST `/family/leave` | 退出家庭组 |

### 2.3 家庭聊天室

私聊 + 群聊，轮询增量拉取消息。

| 接口 | 功能 |
|------|------|
| POST `/chatroom/send` | 发送消息 |
| GET `/chatroom/messages` | 增量拉取（after_id 轮询） |
| GET `/chatroom/conversations` | 聊天列表 |

### 2.4 传承笔记

文件夹 + Markdown 笔记 CRUD，支持长按移动、编辑、删除。

| 接口 | 功能 |
|------|------|
| CRUD `/folders` | 文件夹管理 |
| CRUD `/cards` | 笔记增删改查 |
| POST `/chat/summarize` | AI 从对话中自动总结笔记 |

### 2.5 用户档案

每用户一份 Markdown 档案，阅读/编辑双模式。  
Cloudie 对话中可自然语言更新档案（后台 AI 提取）。

| 接口 | 功能 |
|------|------|
| GET `/profiles/mine` | 获取我的档案 |
| POST/PUT/DELETE `/profiles` | 创建/更新/删除 |
| POST `/profile/ai/extract` | AI 从对话更新档案 |

### 2.6 TTS 语音 + 音色克隆

文本转语音（8 种系统音色 + 自定义音色），支持声音复刻。

| 接口 | 功能 |
|------|------|
| POST `/tts` | 文本→WAV 音频 |
| GET `/tts/voices` | 可用音色列表 |
| POST `/replica/create` | 上传录音创建音色 |
| GET `/replica/list` | 自定义音色列表 |

---

## 三、前端架构

### 3.1 单页容器 + Tab 组件

4 个 Tab 通过 MainPage 容器 + `if` 指令切换，Tabbar 用 `$dispatch('tabchange')` 事件驱动。  
每个 Tab 组件通过 `if` 指令控制创建/销毁，`onInit` 时重置数据 + 加载。

```
MainPage
  ├─ if tab === 'companion' → CompanionTab
  ├─ if tab === 'breakice'   → BreakIceTab
  ├─ if tab === 'memory'     → MemoryTab
  └─ if tab === 'profile'    → ProfileTab
```

### 3.2 通信架构

```
页面/组件
  → $apis.xxx.method()          # 业务接口层
    → $ajax.get/post/put/delete()  # 网络封装层
      → @system.fetch               # 快应用原生
        → HTTP → FastAPI 后端
```

### 3.3 用户身份

`userIdentity.js` 管理设备 UUID + 昵称：
- 模块加载时生成 `eagerUuid`，确保 `getUserId()` 永远有值
- `app.ux onCreate()` 触发 `init()` → 从 storage 恢复 UUID + 昵称
- 所有 API 请求自动注入 `X-User-Id` Header
- 未注册用户点击头像即可设置昵称完成登录

### 3.4 前端 API 接口

| 调用方式 | HTTP | 说明 |
|---------|------|------|
| `$apis.chat.sendMessage({message, history})` | POST `/chat` | 陪伴对话 |
| `$apis.cards.list({folder_id?, limit?})` | GET `/cards` | 笔记列表 |
| `$apis.cards.create({title, content, folder_id?})` | POST `/cards` | 创建笔记 |
| `$apis.cards.update(id, data)` | PUT `/cards/{id}` | 更新笔记 |
| `$apis.cards.remove(id)` | DELETE `/cards/{id}` | 删除笔记 |
| `$apis.folders.list()` | GET `/folders` | 文件夹列表 |
| `$apis.folders.create({name})` | POST `/folders` | 创建文件夹 |
| `$apis.profiles.mine()` | GET `/profiles/mine` | 获取我的档案 |
| `$apis.profiles.create({content_md})` | POST `/profiles` | 创建档案 |
| `$apis.profiles.update(id, data)` | PUT `/profiles/{id}` | 更新档案 |
| `$apis.family.create({nickname})` | POST `/family/create` | 创建家庭组 |
| `$apis.family.join({family_id, password})` | POST `/family/join` | 加入家庭组 |
| `$apis.family.getMyGroup()` | GET `/family/my-group` | 查询家庭组 |
| `$apis.chatroom.send({conversation_id, message})` | POST `/chatroom/send` | 发送消息 |
| `$apis.chatroom.getMessages({conversation_id, after_id})` | GET `/chatroom/messages` | 拉取消息 |

---

## 四、后端架构

### 4.1 技术栈

| 组件 | 用途 |
|------|------|
| FastAPI 0.115 | Web 框架 |
| SQLAlchemy 2.0（异步） | ORM |
| aiosqlite | SQLite 异步驱动 |
| httpx | LLM API 调用 |
| Pydantic 2.7 | 数据校验 |
| loguru | 日志 |

### 4.2 数据模型

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│  family_members  │     │   conversations   │     │     cards       │
│─────────────────│     │──────────────────│     │─────────────────│
│ id (PK)         │     │ id (PK)           │     │ id (PK)         │
│ user_id         │     │ title             │     │ title           │
│ name            │     │ user_id           │     │ content (MD)    │
│ content_md      │     │ family_id         │     │ author          │
│ relation        │     │ type (ai/private  │     │ folder_id (FK)  │
│ birth_date      │     │        /group)     │     │ family_id       │
│ created_at      │     │ created_at        │     │ created_at      │
│ updated_at      │     └───────┬──────────┘     │ updated_at      │
└─────────────────┘             │                 └────────┬────────┘
                                │ 1:N                      │ N:1
                                ▼                          ▼
                    ┌──────────────────┐     ┌─────────────────┐
                    │  chat_messages    │     │    folders      │
                    │──────────────────│     │─────────────────│
                    │ id (PK)          │     │ id (PK)         │
                    │ conversation_id  │     │ name            │
                    │ role / sender_id │     │ family_id       │
                    │ content          │     │ created_at      │
                    │ created_at       │     └─────────────────┘
                    └──────────────────┘
```

### 4.3 路由注册（main.py）

```
/               → 健康检查
/chat           → Cloudie 陪伴对话
/chat/summarize → 对话总结
/folders        → 文件夹 CRUD
/cards          → 笔记 CRUD
/cards/ai       → AI 卡片提取
/profiles       → 用户档案 CRUD
/profile/ai     → AI 档案编写
/family         → 家庭组管理
/chatroom       → 聊天室
/tts            → 文本转语音
/replica        → 音色克隆
```

---

## 五、环境变量

后端 `.env` 配置：

| 变量 | 说明 | 必填 |
|------|------|------|
| `LLM_API_KEY` | LLM 接口密钥 | 是 |
| `LLM_API_BASE` | LLM 接口地址 | 是 |
| `LLM_MODEL` | 模型名称 | 否（默认 qwen-plus） |
| `DATABASE_URL` | 数据库连接 | 否（默认 SQLite） |
| `LOG_LEVEL` | 日志级别 | 否（默认 INFO） |
| `TTS_APP_ID` | vivo TTS App ID | 否 |
| `TTS_APP_KEY` | vivo TTS App Key | 否 |

前端 `src/helper/apis/config.js`：`baseUrl` 指向后端地址。

---

## 六、启动

### 后端

```bash
cd backend
cp .env.example .env        # 编辑填入 LLM_API_KEY
python init_db.py           # 初始化数据库
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
npm install                 # 安装依赖
npm run start               # hap server --watch（模拟器预览）
npm run build               # 编译 rpk 包
```

模拟器预览时前端默认请求 `http://localhost:8000`。真机调试需将 `config.js` 中的 `baseUrl` 改为电脑局域网 IP。

---

## 七、设计原则

- **单页容器**：4 个 Tab 共用 MainPage，避免页面频繁销毁重建
- **解耦优先**：AI 服务（Cloudie / Profile / Cards）各有独立 prompt + API，chat.py 统一编排
- **身份透明**：设备 UUID 自动管理，用户无感知；昵称即登录
- **渐进增强**：前端离线降级，后端 Mock 兜底，不阻塞核心体验
- **组件化**：Tab 组件通过 `data:` + `if` 指令控制生命周期

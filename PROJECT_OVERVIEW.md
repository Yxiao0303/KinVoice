# KinVoice 项目总览

> **KinVoice** = 「亲子破冰 · NVC 非暴力沟通智能助手」  
> 前端：快应用（Quick App） | 后端：FastAPI + SQLite | AI：LLM（vivo 大模型）  
> 核心价值：将用户冲动/攻击性话语 → 温和 NVC 表达，促进家庭和谐沟通

---

## 一、顶层目录结构

```
KinVoice/
├── README.md                  # 快应用模板说明（非项目专属）
├── env-requirement.md         # 空文件
├── 通信API.md                 # ★ 前端通信层完整 API 文档
├── package.json               # 前端 npm 依赖 & 脚本
├── .env / .env.example        # 后端环境变量
│
├── src/                       # ★ 快应用前端源码
│   ├── app.ux                 # 入口：全局注入 $utils + $apis
│   ├── manifest.json          # 应用配置 + 路由表
│   ├── sitemap.json           # 全页面启用
│   ├── assets/
│   │   ├── images/            # logo.png, 云朵精灵.png
│   │   └── styles/            # style.less, variables.less, mixins.less
│   ├── helper/
│   │   ├── ajax.js            # 第一层：Promise 封装 @system.fetch
│   │   ├── utils.js           # showToast, queryString
│   │   └── apis/              # 第二层：业务接口模块
│   │       ├── index.js       # 自动扫描注册所有 API 到 $apis
│   │       ├── config.js      # baseUrl = http://localhost:8000
│   │       ├── chat.js        # POST /chat
│   │       ├── convert.js     # POST /convert
│   │       ├── cards.js       # GET/POST/DELETE /cards
│   │       ├── errorCodes.js  # 错误码表 + classifyError()
│   │       └── example.js     # 新增接口模板
│   ├── pages/
│   │   ├── Companion/         # 陪伴页（首页入口）
│   │   ├── BreakIce/          # 破冰页（NVC 转换）
│   │   ├── Memory/            # 传承页（经验卡片 CRUD）
│   │   └── Profile/           # 我的页（占位）
│   └── CardDemo/              # 快应用卡片示例（vivo 厂商专属）
│
├── backend/                   # ★ FastAPI 后端
│   ├── .env / .env.example    # LLM_API_KEY 等环境变量
│   ├── requirements.txt       # Python 依赖
│   ├── init_db.py             # 数据库建表脚本
│   ├── data/kinvoice.db       # SQLite 数据库文件
│   └── app/
│       ├── main.py            # FastAPI 入口 + CORS + 路由注册
│       ├── config.py          # Pydantic Settings 读取 .env
│       ├── api/               # ★ 路由层
│       │   ├── convert.py     # POST /convert → 破冰转换
│       │   ├── chat.py        # POST /chat → 陪伴对话（占位）
│       │   └── memory.py      # CRUD /cards → 经验卡片
│       ├── services/          # ★ 业务逻辑层
│       │   ├── llm_service.py # LLM 调用封装（call_llm, chat）
│       │   ├── nvc_service.py # NVC prompt 工程（convert_text）
│       │   └── tts_service.py # TTS 语音合成（占位）
│       ├── models/
│       │   └── card.py        # Card ORM 模型
│       ├── schemas/           # Pydantic 请求/响应模型
│       │   ├── convert.py     # ConvertRequest / ConvertResponse
│       │   ├── chat.py        # ChatRequest / ChatResponse
│       │   └── memory.py      # CardCreate / CardUpdate / CardOut / CardListOut
│       ├── db/
│       │   └── session.py     # 异步引擎 + AsyncSession + Base
│       └── utils/
│           └── logger.py      # logging 日志配置
│
└── scripts/                   # 前端辅助脚本
    ├── gen/index.js           # yarn gen PageName 生成新页面
    ├── gen/template.ux        # 页面模板
    └── selfCloseInputTag.js   # 自动修复 input 标签闭合
```

---

## 二、前端架构（快应用）

### 2.1 框架特征

| 项目 | 说明 |
|------|------|
| **平台** | 快应用（Quick App），基于 `hap-toolkit` 构建 |
| **包名** | `cn.nekohackers.kinvoice` |
| **最低平台版本** | 1070 |
| **UI 库** | apex-ui |
| **样式方案** | Less 预编译（dart sass 方案） |
| **格式化** | Prettier + prettier-plugin-ux |
| **入口文件** | `app.ux` → 全局注入 `$utils` 和 `$apis` |
| **路由** | `manifest.json` 的 `router.pages` |
| **文件类型** | `.ux`（模板+脚本+样式 单文件）、`.js`、`.less` |

### 2.2 全局注入机制（app.ux）

```
app.ux 启动时：
  1. require('./helper/utils') → 挂载到 global.$utils
  2. require('./helper/apis') → 挂载到 global.$apis
  → 所有页面无需 import，直接使用 $utils / $apis
```

### 2.3 三层通信架构

```
┌──────────────────────────────────────────┐
│  页面层 (pages/*.ux)                      │
│  直接调用 $apis.xxx.method()              │
├──────────────────────────────────────────┤
│  第二层：业务接口 (helper/apis/*.js)       │
│  每个后端接口一个文件                      │
│  调用 $ajax.post/get/delete()             │
├──────────────────────────────────────────┤
│  第一层：网络封装 (helper/ajax.js)         │
│  Promise 封装 @system.fetch               │
│  超时 20s，JSON 解析 + 二次兜底           │
│  兼容模拟器 code=0                         │
├──────────────────────────────────────────┤
│  HTTP → FastAPI 后端                      │
└──────────────────────────────────────────┘
```

### 2.4 四个页面

| 页面 | 路由 | 功能 | 后端接口 | 状态 |
|------|------|------|---------|------|
| **Companion** | `/pages/Companion` (entry) | AI 陪伴对话，Cloudie 精灵互动 | `POST /chat` | 占位（本地兜底回复） |
| **BreakIce** | `/pages/BreakIce` | NVC 破冰转换 | `POST /convert` | ✅ 已打通 |
| **Memory** | `/pages/Memory` | 经验卡片 CRUD（4 分类） | `GET/POST/DELETE /cards` | 在线+本地双写 |
| **Profile** | `/pages/Profile` | 设置/关于/帮助（占位） | 无 | 占位 |

**页面间通过底部 TabBar + `router.replace()` 切换。**

### 2.5 前端 API 接口一览

| 调用方式 | HTTP | 路径 | 说明 |
|---------|------|------|------|
| `$apis.chat.sendMessage({message, history?, emotionState?})` | POST | `/chat` | 陪伴对话 |
| `$apis.convert.transform({rawText})` | POST | `/convert` | 破冰转换 |
| `$apis.cards.list({category?, limit?, offset?})` | GET | `/cards` | 卡片列表 |
| `$apis.cards.create({category, emotion, observation, feeling, need, request?})` | POST | `/cards` | 创建卡片 |
| `$apis.cards.remove(cardId)` | DELETE | `/cards/{id}` | 删除卡片 |

### 2.6 错误码体系（errorCodes.js）

```
1xxx 网络    → 1001 后端未启动, 1002 DNS 失败
2xxx 超时    → 2001 请求超时(>20s)
3xxx 客户端  → 3001 400, 3002 401, 3003 404, 3004 422, 3005 429
4xxx 服务端  → 4001 500, 4002 LLM 失败, 4003 503
5xxx 数据    → 5001 解析失败, 5002 空响应, 5003 缺少字段
9999 通用    → 未知错误
```

---

## 三、后端架构（FastAPI）

### 3.1 技术栈

| 组件 | 版本 | 用途 |
|------|------|------|
| FastAPI | 0.115 | Web 框架 |
| Uvicorn | 0.30 | ASGI 服务器 |
| SQLAlchemy | 2.0.30 | ORM（异步模式） |
| aiosqlite | 0.19 | SQLite 异步驱动 |
| httpx | 0.27 | 异步 HTTP 客户端（调 LLM） |
| Pydantic | 2.7 | 数据校验 |
| loguru | 0.7.2 | 日志（实际代码用的是标准 logging） |

### 3.2 入口文件 main.py

```python
# 创建 FastAPI 应用 → 配置 CORS（allow_origins=["*"]）
# 注册路由：include_router(convert_router)
# 健康检查：GET /ping → {"status": "ok"}
```

**⚠️ 注意**：当前 `main.py` 只注册了 `convert_router`，`chat` 和 `cards` 路由**未被注册**！  
这意味着 `POST /chat` 和 `CRUD /cards` 在后端实际不可用。

### 3.3 路由层 (api/)

#### convert.py — POST /convert ✅ 已注册

```
用户请求: { raw_text: "你们从来都不理解我！" }
   ↓
convert_text(raw_text)  → nvc_service.py
   ↓
chat(prompt=raw_text, system_prompt=NVC_SYSTEM_PROMPT) → llm_service.py
   ↓
call_llm(messages) → httpx → vivo LLM API
   ↓
返回: { original, converted, tokens_used, processing_time }
```

#### chat.py — POST /chat ⚠️ 未注册

```
用户请求: { message, history?, emotion_state? }
   ↓
chat(prompt=message) → llm_service.py → call_llm()
   ↓
返回: { reply, emotion?, need_hint? }
```

#### memory.py — CRUD /cards ⚠️ 未注册

```
GET    /cards?category=&limit=20&offset=0  → 分页列表
POST   /cards                                → 创建卡片
DELETE /cards/{card_id}                      → 删除卡片（204）
```

### 3.4 服务层 (services/)

#### llm_service.py — LLM 调用核心

```
call_llm(messages: list[dict]) → str
  ├── Mock 模式：API Key 含 "your-key" 时用本地规则回复
  └── 真实调用：POST {llm_api_base}/chat/completions
       ├── Headers: Authorization: Bearer {llm_api_key}
       ├── Body: { model, messages, temperature:0.7, max_tokens:1024 }
       ├── vivo 模型特殊处理：query 参数加 request_id
       ├── 超时：10 秒
       └── 失败降级：返回 "我暂时无法回答，请稍后再试"

chat(prompt, system_prompt=None) → str
  ├── 构建 messages：[{system}, {user}]
  ├── 调用 call_llm()
  └── 超时/异常降级
```

**vivo 模型列表**：`qwen3.5-plus`, `Volc-DeepSeek-V3.2`, `Doubao-Seed-2.0-mini/lite/pro`

#### nvc_service.py — NVC Prompt 工程

```
NVC_SYSTEM_PROMPT（核心提示词）:
  "你是 NVC 语言转换专家，把攻击性话语转为温和表达
   规则：观察-感受-需要-请求四步法、保留原意、不添加内容、不评判用户、直接返回转换文本"

convert_text(original_text) → str
  → chat(prompt=original_text, system_prompt=NVC_SYSTEM_PROMPT)
```

#### tts_service.py — TTS 占位

```
synthesize_speech(text, voice) → 当前返回 None
预留 Azure TTS 集成（azure_speech_key/region 已在 config 中定义）
```

### 3.5 数据模型层

#### ORM 模型 (models/card.py)

```python
class Card(Base):
    __tablename__ = "cards"
    id            Integer PK autoincrement
    title         String(200)   NOT NULL
    content       Text          NOT NULL
    original_text Text          nullable
    family_id     Integer       default=1
    created_at    DateTime      server_default=now()
```

#### Pydantic Schema (schemas/memory.py)

```python
CardCreate:   category, emotion, observation, feeling, need, request?
CardUpdate:   同上但全字段可选
CardOut:      id, category, emotion, observation, feeling, need, request?, created_at, updated_at
CardListOut:  cards: list[CardOut], total: int
```

**⚠️ 严重不匹配**：ORM 模型字段（`title`, `content`, `original_text`, `family_id`）与 Schema 字段（`category`, `emotion`, `observation`, `feeling`, `need`, `request`）**完全不同**！当前 CRUD 接口会因字段不匹配而失败。

### 3.6 数据库层 (db/session.py)

```python
DATABASE_PATH = backend/data/kinvoice.db
DATABASE_URL  = sqlite+aiosqlite:///{DATABASE_PATH}

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = DeclarativeBase  ← 所有 ORM 模型继承此基类
```

`get_session` 依赖注入 → 自动创建/提交/回滚/关闭 AsyncSession。

### 3.7 配置管理 (config.py)

```python
Settings(BaseSettings):
    APP_NAME             = "KinVoice"
    DEBUG                = True
    ALLOWED_ORIGINS      = "http://localhost:3000,..."
    llm_api_key           # 必填，含 "your-key" 则走 Mock
    llm_api_base          # LLM 接口地址
    llm_model             # 默认 Volc-DeepSeek-V3.2
    database_url          # sqlite+aiosqlite:///./data/kinvoice.db
    LOG_LEVEL             # INFO
    azure_speech_key/region  # TTS 预留
```

---

## 四、前后端调用流程

### 4.1 破冰转换（完整链路）

```
用户输入 "你们从来都不理解我！"
  │
  ▼ 前端 BreakIce/index.ux
transformText() → $apis.convert.transform({ rawText })
  │
  ▼ helper/apis/convert.js
$ajax.post('http://localhost:8000/convert', { raw_text })
  │
  ▼ helper/ajax.js
@system.fetch → HTTP POST /convert
  │
  ▼ 后端 api/convert.py
POST /convert → convert_text(request.raw_text)
  │
  ▼ services/nvc_service.py
chat(prompt, system_prompt=NVC_SYSTEM_PROMPT)
  │
  ▼ services/llm_service.py
call_llm([{system: NVC_PROMPT}, {user: raw_text}])
  │
  ▼ httpx → vivo LLM API
返回转换后文本
  │
  ◄ 逐层返回 → 前端显示 "温柔表达"
```

### 4.2 陪伴对话

```
用户输入 → Companion/index.ux
  → $apis.chat.sendMessage({ message })
    → $ajax.post('/chat', { message, history, emotion_state })
      → 后端 POST /chat（⚠️ 未注册路由）
        → chat(prompt) → call_llm()
          ← { reply, emotion?, need_hint? }
      失败时 → 前端本地 getFallbackReply() 兜底
```

### 4.3 经验卡片（在线+本地双写）

```
Memory/index.ux:

加载流程（在线优先 + 离线兜底）：
  loadCards()
    → $apis.cards.list({ limit: 100 })
      成功 → 合并后端数据 → saveCardsToLocal() → 显示
      失败 → loadCardsFromLocal()（从 storage 读取）

保存流程（本地即时 + 后台同步）：
  saveCard()
    → this.cards[key].unshift(newCard)     ← 本地即时生效
    → saveCardsToLocal()                   ← 持久化到 storage
    → $apis.cards.create(cardToBackend())  ← 后台非阻塞同步
      失败不影响本地数据
```

---

## 五、已知问题

| # | 问题 | 影响 | 严重程度 | 状态 |
|---|------|------|---------|------|
| 1 | **main.py 只注册了 convert_router**，chat 和 cards 路由未注册 | `POST /chat` 和 `CRUD /cards` 不可用 | 🔴 高 | ✅ 已修复 |
| 2 | **ORM 模型 (Card) 字段与 Pydantic Schema 不匹配** | cards CRUD 即使注册路由也会报错 | 🔴 高 | ✅ 已修复 |
| 3 | Memory 页面的 `cardFromBackend()` 使用 `b.observation`/`b.feeling` 等字段，与 ORM 实际字段不匹配 | 后端数据无法正确映射到前端 | 🟡 中 | ✅ 已修复 |
| 4 | `schemas/memory.py` 的 `CardOut` 包含 `updated_at`，但 ORM 模型 `Card` 没有此字段 | 查询卡片列表会因字段缺失报错 | 🟡 中 | ✅ 已修复 |
| 5 | Companion 页 `chat.js` 的 `emotionState` → `emotion_state` 映射在 API 文件中做了，但后端 `ChatResponse` 未实际使用 LLM 分析情绪 | 陪伴对话缺少情绪识别 | 🟢 低 | 待处理 |
| 6 | TTS 功能占位 | 语音合成不可用 | 🟢 低 | 待处理 |
| 7 | Profile 页纯占位 | 无实际功能 | 🟢 低 | 待处理 |

---

## 六、构建与运行

### 前端

```bash
# 安装依赖
npm install   # 或 yarn

# 开发（模拟器预览）
yarn start    # hap server --watch

# 构建
yarn build    # hap build → 生成 rpk 包

# 新增页面
yarn gen PageName

# 代码格式化
yarn prettier
```

### 后端

```bash
cd backend

# 安装依赖
pip install -r requirements.txt

# 配置环境变量
copy .env.example .env
# 编辑 .env 填入 LLM_API_KEY 等

# 初始化数据库
python init_db.py

# 启动服务（默认 8000 端口）
uvicorn app.main:app --reload --port 8000
```

### 前端 baseUrl 配置

`src/helper/apis/config.js`：
- 模拟器预览：`http://localhost:8000`
- USB 真机调试：改为电脑局域网 IP，如 `http://192.168.1.8:8000`
- 生产环境：改为实际 API 域名

---

## 七、核心数据流图

```
┌────────────────────────────────────────────────────────────┐
│                      快应用前端 (src/)                       │
│                                                            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │Companion │  │ BreakIce │  │  Memory  │  │ Profile  │  │
│  │ 陪伴对话  │  │ NVC转换  │  │ 经验卡片  │  │  我的    │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┘  │
│       │              │              │                      │
│       ▼              ▼              ▼                      │
│  $apis.chat    $apis.convert   $apis.cards                 │
│       │              │              │                      │
│       └──────────────┼──────────────┘                      │
│                      ▼                                     │
│               $ajax (helper/ajax.js)                       │
│               @system.fetch Promise 封装                    │
│               超时 20s / JSON 解析 / 错误分类               │
└──────────────────────┬─────────────────────────────────────┘
                       │ HTTP
                       ▼
┌────────────────────────────────────────────────────────────┐
│                    FastAPI 后端 (backend/)                   │
│                                                            │
│  POST /convert  ✅   POST /chat  ✅   CRUD /cards  ✅     │
│       │                    │                 │             │
│       ▼                    ▼                 ▼             │
│  nvc_service.py      llm_service.py    memory.py           │
│  (NVC prompt)         (call_llm)       (SQLAlchemy)        │
│       │                    │                 │             │
│       └────────────────────┼─────────────────┘             │
│                            ▼                               │
│                     llm_service.py                         │
│                     httpx → LLM API                        │
│                     (vivo 大模型)                           │
│                            │                               │
│                     ┌──────┴──────┐                        │
│                     │  SQLite DB  │                        │
│                     │ kinvoice.db │                        │
│                     └─────────────┘                        │
└────────────────────────────────────────────────────────────┘
```

# KinVoice 后端

## 项目简介

亲子破冰 · NVC 非暴力沟通智能助手后端 API。

## 技术栈

- **框架**: FastAPI + Uvicorn
- **数据库**: SQLite（异步，aiosqlite + SQLAlchemy 2.0）
- **大模型**: 统一 OpenAI 兼容接口（支持蓝心/阿里千问等）

## 快速开始

```bash
cd backend

# 1. 创建虚拟环境
python -m venv venv
.\venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS/Linux

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
copy .env.example .env
# 编辑 .env 填写真实的 LLM_API_KEY

# 4. 初始化数据库
python init_db.py

# 5. 启动服务
uvicorn app.main:app --reload --port 8000
```

## API 文档

启动后访问：

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## 接口列表

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/convert` | 破冰转换 — 原始文本 → NVC 四要素 |
| POST | `/chat` | 陪伴对话 — NVC 风格 AI 回应 |
| GET | `/cards` | 获取经验卡片列表 |
| POST | `/cards` | 创建经验卡片 |
| DELETE | `/cards/{id}` | 删除经验卡片 |

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 入口
│   ├── config.py            # 配置管理
│   ├── api/                 # 路由层
│   │   ├── convert.py       # POST /convert
│   │   ├── chat.py          # POST /chat
│   │   └── memory.py        # CRUD /cards
│   ├── services/            # 业务逻辑
│   │   ├── llm_service.py   # 大模型调用
│   │   ├── nvc_service.py   # NVC prompt 工程
│   │   └── tts_service.py   # 语音合成（占位）
│   ├── models/              # ORM 模型
│   │   └── card.py
│   ├── schemas/             # Pydantic 模型
│   │   ├── convert.py
│   │   ├── chat.py
│   │   └── memory.py
│   ├── db/                  # 数据库
│   │   └── session.py
│   └── utils/               # 工具
│       └── logger.py
├── requirements.txt
├── .env.example
├── init_db.py
└── README.md
```

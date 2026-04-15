# Atlas Agentic RAG Copilot

本仓库用于实现基于设计文档推进的 Atlas Agentic RAG Copilot，目前已完成基础骨架与高质量 RAG 主链路。

## 目录说明

- `backend/`：FastAPI 后端、数据库模型、迁移、解析链路
- `frontend/`：React + TypeScript 前端骨架
- `notes/`：阶段推进记录
- `agentic_rag_design_docs/`：设计文档
- `atlas_agentic_rag_testset_v1/`：最小 RAG 测试集
- `agentic_rag_sample_files/`：PDF / DOCX / PPTX 解析样例

## 本地启动

### 1. 创建虚拟环境并安装依赖

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -e .\backend[dev]
cd frontend
npm install
```

### 2. 清理并初始化数据库

```powershell
$env:ATLAS_DATABASE_URL="postgresql+psycopg://<db_user>:<db_password>@127.0.0.1:5432/rag_lab"
.venv\Scripts\python .\backend\app\scripts\reset_local_db.py
.venv\Scripts\python -m alembic -c .\backend\alembic.ini upgrade head
```

### 3. 启动后端

```powershell
$env:ATLAS_DATABASE_URL="postgresql+psycopg://<db_user>:<db_password>@127.0.0.1:5432/rag_lab"
$env:ATLAS_DASHSCOPE_API_KEY="你的百炼APIKey"
.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir .\backend
```

### 4. 启动前端

```powershell
cd frontend
npm run dev
```

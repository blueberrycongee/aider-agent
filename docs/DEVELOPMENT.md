# Aider Agent 开发文档

## 项目概述

Aider Agent 是一个开源贡献自动化系统，能够批量自动修复 GitHub 项目的 Issue。

### 核心价值
- **自动化**：一键处理多个仓库的 Issue
- **智能筛选**：AI 评估 Issue 难度，优先处理简单任务
- **可视化**：实时追踪进度，无需盯着终端

---

## 技术架构

```
┌─────────────────────────────────────────────────────────────┐
│                      Web UI (Flask)                          │
│                   端口 5000 / WebSocket                       │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Task Runner (调度器)                       │
│              管理任务队列、并发控制、状态追踪                    │
└─────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              ▼               ▼               ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  GitHub Client  │ │  Aider Wrapper  │ │  Issue Selector │
│   API 操作      │ │   AI 代码修改    │ │   难度评估       │
└─────────────────┘ └─────────────────┘ └─────────────────┘
```

### 技术栈
| 组件 | 技术 |
|------|------|
| 后端 | Python 3.11+, Flask, Flask-SocketIO |
| AI 引擎 | Aider (CLI 调用) |
| GitHub API | PyGithub |
| 前端 | 原生 HTML/CSS/JS, Socket.IO |
| 数据存储 | 本地 JSON 文件 (MVP), SQLite (后续) |

---

## 模块说明

### 1. agent_core/github_client.py
GitHub API 封装，负责：
- 获取仓库信息
- 爬取 Issue 列表
- Fork 仓库
- 创建 Pull Request

### 2. agent_core/aider_wrapper.py
Aider CLI 封装，负责：
- 启动 Aider 进程
- 发送指令（审查代码、修复 Issue）
- 实时捕获输出
- 异步执行支持

### 3. agent_core/task_runner.py
任务调度器，负责：
- 管理任务生命周期
- 克隆仓库
- 协调 GitHub + Aider 操作
- 并发控制

### 4. agent_core/issue_selector.py (待开发)
Issue 筛选器，负责：
- 难度评估（LLM 评分）
- 优先级排序
- 过滤不适合的 Issue

### 5. agent_ui/app.py
Web 界面后端，负责：
- RESTful API
- WebSocket 实时推送
- 前端资源服务

---

## API 设计

### RESTful Endpoints

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/repos` | 获取所有仓库任务 |
| POST | `/api/repos` | 添加新仓库 |
| DELETE | `/api/repos/<id>` | 删除仓库 |
| POST | `/api/repos/<id>/start` | 启动任务（克隆+审查） |
| GET | `/api/repos/<id>/issues` | 获取仓库 Issues |
| POST | `/api/repos/<id>/issues/<num>/fix` | 修复指定 Issue |

### WebSocket Events

| 事件 | 方向 | 说明 |
|------|------|------|
| `status_update` | Server → Client | 任务状态变更 |
| `aider_output` | Server → Client | Aider 实时输出 |
| `issue_found` | Server → Client | 发现新 Issue |

---

## 配置项

### 环境变量 (.env)

```bash
# 必须
GITHUB_TOKEN=xxx          # GitHub Personal Access Token
OPENAI_API_KEY=xxx        # 或 ANTHROPIC_API_KEY

# 可选
AIDER_MODEL=gpt-4         # 使用的模型
MAX_CONCURRENT=5          # 最大并发任务数
CLONE_DIR=./data/repos    # 仓库克隆目录
```

---

## 开发规范

### 代码风格
- Python: PEP 8, 使用 Black 格式化
- 类型注解: 必须添加
- 文档字符串: Google 风格

### Git 提交规范
```
feat: 新功能
fix: Bug 修复
docs: 文档更新
refactor: 重构
test: 测试
chore: 构建/工具
```

### 测试
```bash
# 运行所有测试
pytest tests/

# 运行单个测试
pytest tests/test_github_client.py -v
```

---

## 本地开发

### 环境搭建
```bash
# 1. 克隆项目
git clone https://github.com/blueberrycongee/aider-agent.git
cd aider-agent

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env 填入你的 API Keys

# 5. 启动开发服务器
cd agent_ui
python app.py
```

### 调试技巧
- 使用 `--debug` 参数启动 Flask
- Aider 输出会实时显示在控制台
- WebSocket 消息可在浏览器 DevTools Network 面板查看

---

## 部署 (后续)

### Docker
```bash
docker build -t aider-agent .
docker run -p 5000:5000 --env-file .env aider-agent
```

### 生产环境注意
- 使用 Gunicorn + eventlet
- 配置 HTTPS
- 设置 SECRET_KEY
- 限制 GitHub Token 权限

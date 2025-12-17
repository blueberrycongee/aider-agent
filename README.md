# Aider Agent

🤖 开源贡献自动化 Agent 系统 - 批量自动修复 GitHub Issue

## 功能

- 📦 批量管理 GitHub 仓库
- 🔍 自动爬取和筛选 Issue
- 🛠️ 使用 Aider AI 自动修复简单 Issue
- 🚀 自动创建 Pull Request

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置 GitHub Token

```bash
# Windows
set GITHUB_TOKEN=your_token_here

# Linux/Mac
export GITHUB_TOKEN=your_token_here
```

### 3. 启动界面

```bash
cd agent_ui
python app.py
```

访问 http://localhost:5000

## 项目结构

```
aider-agent/
├── agent_ui/           # Web 界面
├── agent_core/         # 核心逻辑
│   ├── github_client.py
│   ├── issue_selector.py
│   ├── task_runner.py
│   └── aider_wrapper.py
├── config/             # 配置文件
└── data/               # 数据存储
```

## 技术栈

- **AI 引擎**: [Aider](https://github.com/paul-gauthier/aider)
- **后端**: Flask + Flask-SocketIO
- **GitHub API**: PyGithub

## License

MIT

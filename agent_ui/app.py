"""
Agent UI - 仓库管理和任务调度 Web 界面
"""
import os
import sys
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, str(Path(__file__).parent.parent))

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from dotenv import load_dotenv

from agent_core.task_runner import TaskRunner, TaskStatus

# 加载环境变量
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'aider-agent-secret')
socketio = SocketIO(app, cors_allowed_origins="*")

# 任务调度器
runner = TaskRunner()


def on_status_update(task_id: str, status: TaskStatus, message: str):
    """状态更新回调"""
    socketio.emit('status_update', {
        'id': task_id,
        'status': status.value,
        'message': message
    })


def on_output(task_id: str, line: str):
    """Aider 输出回调"""
    socketio.emit('aider_output', {
        'id': task_id,
        'line': line
    })


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/repos', methods=['GET'])
def get_repos():
    """获取所有仓库任务"""
    tasks = runner.get_all_tasks()
    return jsonify([{
        'id': t.id,
        'url': t.repo_url,
        'name': t.repo_name,
        'status': t.status.value,
        'message': t.message,
        'output': t.output
    } for t in tasks])


@app.route('/api/repos', methods=['POST'])
def add_repo():
    """添加新仓库"""
    data = request.json
    url = data.get('url', '').strip()
    
    if not url:
        return jsonify({'error': '请输入仓库地址'}), 400
    
    task = runner.create_task(url)
    
    return jsonify({
        'id': task.id,
        'url': task.repo_url,
        'name': task.repo_name,
        'status': task.status.value,
        'message': task.message
    })


@app.route('/api/repos/<task_id>/start', methods=['POST'])
def start_task(task_id):
    """启动任务"""
    task = runner.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    if task.status in [TaskStatus.CLONING, TaskStatus.REVIEWING]:
        return jsonify({'error': '任务正在进行中'}), 400
    
    # 异步启动任务
    runner.run_full_task_async(task_id, on_status_update, on_output)
    
    return jsonify({'message': '任务已启动'})


@app.route('/api/repos/<task_id>', methods=['DELETE'])
def delete_repo(task_id):
    """删除任务"""
    runner.delete_task(task_id)
    return jsonify({'message': '已删除'})


if __name__ == '__main__':
    print("=" * 50)
    print("🤖 Aider Agent UI 启动中...")
    print(f"📁 工作目录: {runner.work_dir}")
    print("🌐 打开浏览器访问: http://localhost:5000")
    print("=" * 50)
    socketio.run(app, debug=True, port=5000)

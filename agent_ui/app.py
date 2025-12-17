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
from agent_core.github_client import GitHubClient
from agent_core.issue_selector import IssueSelector

# 加载环境变量
load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'aider-agent-secret')
socketio = SocketIO(app, cors_allowed_origins="*")

# 任务调度器
runner = TaskRunner()

# GitHub 客户端 (延迟初始化)
github_client = None
issue_selector = IssueSelector()


def get_github_client():
    """获取 GitHub 客户端（延迟初始化）"""
    global github_client
    if github_client is None:
        token = os.getenv('GITHUB_TOKEN')
        if token:
            try:
                github_client = GitHubClient(token)
            except Exception as e:
                print(f"GitHub 客户端初始化失败: {e}")
                return None
    return github_client


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


@app.route('/api/repos/<task_id>/issues', methods=['GET'])
def get_repo_issues(task_id):
    """获取仓库的 Issues"""
    task = runner.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    client = get_github_client()
    if not client:
        return jsonify({'error': '未配置 GITHUB_TOKEN'}), 400
    
    try:
        # 从 URL 解析 owner 和 repo
        parts = task.repo_url.rstrip('/').rstrip('.git').split('/')
        owner, repo_name = parts[-2], parts[-1]
        
        # 获取 Issues
        issues = client.get_issues(owner, repo_name, limit=30)
        
        # 筛选和评分
        best_issues = issue_selector.get_best_issues(issues, limit=20)
        
        return jsonify({
            'total': len(issues),
            'issues': [issue.to_dict() for issue in best_issues]
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/repos/<task_id>/issues/<int:issue_number>/fix', methods=['POST'])
def fix_issue(task_id, issue_number):
    """修复指定的 Issue"""
    task = runner.get_task(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404
    
    if not task.local_path:
        return jsonify({'error': '仓库未克隆'}), 400
    
    client = get_github_client()
    if not client:
        return jsonify({'error': '未配置 GITHUB_TOKEN'}), 400
    
    try:
        # 获取 Issue 详情
        parts = task.repo_url.rstrip('/').rstrip('.git').split('/')
        owner, repo_name = parts[-2], parts[-1]
        
        issues = client.get_issues(owner, repo_name, limit=100)
        issue = next((i for i in issues if i['number'] == issue_number), None)
        
        if not issue:
            return jsonify({'error': 'Issue 不存在'}), 404
        
        # 更新状态
        task.status = TaskStatus.FIXING
        task.message = f'正在修复 Issue #{issue_number}...'
        on_status_update(task_id, task.status, task.message)
        
        # 异步调用 Aider 修复
        from agent_core.aider_wrapper import AiderWrapper
        import threading
        
        def do_fix():
            try:
                wrapper = AiderWrapper(task.local_path)
                
                def _on_output(line):
                    task.output += line + '\n'
                    on_output(task_id, line)
                
                code, output = wrapper.fix_issue(
                    issue['title'],
                    issue['body'],
                    on_output=_on_output
                )
                
                if code == 0:
                    task.status = TaskStatus.COMPLETED
                    task.message = f'Issue #{issue_number} 修复完成！'
                else:
                    task.status = TaskStatus.ERROR
                    task.message = f'修复失败'
                
                on_status_update(task_id, task.status, task.message)
                
            except Exception as e:
                task.status = TaskStatus.ERROR
                task.message = f'修复出错: {str(e)}'
                on_status_update(task_id, task.status, task.message)
        
        thread = threading.Thread(target=do_fix, daemon=True)
        thread.start()
        
        return jsonify({'message': f'开始修复 Issue #{issue_number}'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/status', methods=['GET'])
def get_status():
    """获取系统状态"""
    client = get_github_client()
    
    status = {
        'github_connected': False,
        'github_user': None,
        'work_dir': str(runner.work_dir),
        'task_count': len(runner.tasks),
    }
    
    if client:
        try:
            status['github_connected'] = True
            status['github_user'] = client.user.login
        except:
            pass
    
    return jsonify(status)


if __name__ == '__main__':
    print("=" * 50)
    print("Aider Agent UI 启动中...")
    print(f"工作目录: {runner.work_dir}")
    print("打开浏览器访问: http://localhost:5000")
    print("=" * 50)
    socketio.run(app, debug=True, port=5000)

"""
任务调度器 - 管理仓库克隆和 Aider 任务执行
"""
import subprocess
import threading
import os
from pathlib import Path
from typing import Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from .aider_wrapper import AiderWrapper


class TaskStatus(Enum):
    PENDING = 'pending'
    CLONING = 'cloning'
    CLONED = 'cloned'
    REVIEWING = 'reviewing'
    FIXING = 'fixing'
    COMPLETED = 'completed'
    ERROR = 'error'


@dataclass
class Task:
    id: str
    repo_url: str
    repo_name: str
    status: TaskStatus = TaskStatus.PENDING
    local_path: str = None
    message: str = ''
    output: str = ''
    error: str = ''


class TaskRunner:
    def __init__(self, work_dir: str = None):
        """
        初始化任务调度器
        
        Args:
            work_dir: 工作目录，用于存放克隆的仓库
        """
        if work_dir:
            self.work_dir = Path(work_dir)
        else:
            self.work_dir = Path(__file__).parent.parent / 'data' / 'repos'
        
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.tasks: Dict[str, Task] = {}
        self._task_counter = 0
        self._lock = threading.Lock()
    
    def _get_repo_name(self, url: str) -> str:
        """从 URL 提取仓库名"""
        return url.rstrip('/').rstrip('.git').split('/')[-1]
    
    def _parse_repo_url(self, url: str) -> tuple[str, str]:
        """解析仓库 URL，返回 (owner, repo_name)"""
        # https://github.com/owner/repo.git
        parts = url.rstrip('/').rstrip('.git').split('/')
        return parts[-2], parts[-1]
    
    def create_task(self, repo_url: str) -> Task:
        """创建新任务"""
        with self._lock:
            self._task_counter += 1
            task_id = str(self._task_counter)
            
            task = Task(
                id=task_id,
                repo_url=repo_url,
                repo_name=self._get_repo_name(repo_url)
            )
            self.tasks[task_id] = task
            return task
    
    def get_task(self, task_id: str) -> Task:
        """获取任务"""
        return self.tasks.get(task_id)
    
    def get_all_tasks(self) -> list[Task]:
        """获取所有任务"""
        return list(self.tasks.values())
    
    def clone_repo(self, task_id: str, 
                   on_status: Callable[[str, TaskStatus, str], None] = None) -> bool:
        """
        克隆仓库
        
        Args:
            task_id: 任务 ID
            on_status: 状态回调 (task_id, status, message)
        
        Returns:
            是否成功
        """
        task = self.get_task(task_id)
        if not task:
            return False
        
        repo_path = self.work_dir / task.repo_name
        task.local_path = str(repo_path)
        
        # 更新状态
        task.status = TaskStatus.CLONING
        task.message = f'正在克隆 {task.repo_url}...'
        if on_status:
            on_status(task_id, task.status, task.message)
        
        try:
            if repo_path.exists():
                # 仓库已存在，拉取最新
                task.message = '仓库已存在，拉取最新代码...'
                if on_status:
                    on_status(task_id, task.status, task.message)
                
                result = subprocess.run(
                    ['git', 'pull'],
                    cwd=str(repo_path),
                    capture_output=True,
                    text=True
                )
            else:
                # 克隆新仓库
                result = subprocess.run(
                    ['git', 'clone', task.repo_url, str(repo_path)],
                    capture_output=True,
                    text=True
                )
            
            if result.returncode == 0:
                task.status = TaskStatus.CLONED
                task.message = '克隆完成！'
                if on_status:
                    on_status(task_id, task.status, task.message)
                return True
            else:
                task.status = TaskStatus.ERROR
                task.error = result.stderr
                task.message = f'克隆失败: {result.stderr}'
                if on_status:
                    on_status(task_id, task.status, task.message)
                return False
                
        except Exception as e:
            task.status = TaskStatus.ERROR
            task.error = str(e)
            task.message = f'错误: {str(e)}'
            if on_status:
                on_status(task_id, task.status, task.message)
            return False
    
    def review_repo(self, task_id: str,
                    on_status: Callable[[str, TaskStatus, str], None] = None,
                    on_output: Callable[[str, str], None] = None) -> bool:
        """
        使用 Aider 审查仓库代码
        
        Args:
            task_id: 任务 ID
            on_status: 状态回调
            on_output: 输出回调 (task_id, line)
        """
        task = self.get_task(task_id)
        if not task or not task.local_path:
            return False
        
        task.status = TaskStatus.REVIEWING
        task.message = '正在启动 Aider 审查代码...'
        if on_status:
            on_status(task_id, task.status, task.message)
        
        try:
            wrapper = AiderWrapper(task.local_path)
            
            def _on_output(line: str):
                task.output += line + '\n'
                if on_output:
                    on_output(task_id, line)
            
            code, output = wrapper.review_code(on_output=_on_output)
            
            if code == 0:
                task.status = TaskStatus.COMPLETED
                task.message = '审查完成！'
            else:
                task.status = TaskStatus.ERROR
                task.message = f'审查失败，返回码: {code}'
            
            if on_status:
                on_status(task_id, task.status, task.message)
            
            return code == 0
            
        except Exception as e:
            task.status = TaskStatus.ERROR
            task.error = str(e)
            task.message = f'Aider 错误: {str(e)}'
            if on_status:
                on_status(task_id, task.status, task.message)
            return False
    
    def run_full_task(self, task_id: str,
                      on_status: Callable[[str, TaskStatus, str], None] = None,
                      on_output: Callable[[str, str], None] = None):
        """
        运行完整任务流程：克隆 + 审查
        """
        success = self.clone_repo(task_id, on_status)
        if success:
            self.review_repo(task_id, on_status, on_output)
    
    def run_full_task_async(self, task_id: str,
                            on_status: Callable[[str, TaskStatus, str], None] = None,
                            on_output: Callable[[str, str], None] = None) -> threading.Thread:
        """异步运行完整任务"""
        thread = threading.Thread(
            target=self.run_full_task,
            args=(task_id, on_status, on_output),
            daemon=True
        )
        thread.start()
        return thread
    
    def delete_task(self, task_id: str):
        """删除任务"""
        if task_id in self.tasks:
            del self.tasks[task_id]

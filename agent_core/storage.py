"""
数据持久化 - JSON 文件存储
"""
import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import threading


class Storage:
    """JSON 文件存储"""
    
    def __init__(self, data_dir: str = None):
        """
        初始化存储
        
        Args:
            data_dir: 数据目录路径
        """
        if data_dir:
            self.data_dir = Path(data_dir)
        else:
            self.data_dir = Path(__file__).parent.parent / 'data'
        
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
    
    def _get_file_path(self, name: str) -> Path:
        """获取数据文件路径"""
        return self.data_dir / f"{name}.json"
    
    def save(self, name: str, data: Any) -> bool:
        """
        保存数据到 JSON 文件
        
        Args:
            name: 数据名称（不含扩展名）
            data: 要保存的数据
        
        Returns:
            是否成功
        """
        file_path = self._get_file_path(name)
        
        with self._lock:
            try:
                # 先写入临时文件，再重命名（原子操作）
                temp_path = file_path.with_suffix('.tmp')
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2, default=str)
                
                # 替换原文件
                if file_path.exists():
                    file_path.unlink()
                temp_path.rename(file_path)
                
                return True
            except Exception as e:
                print(f"保存数据失败 [{name}]: {e}")
                return False
    
    def load(self, name: str, default: Any = None) -> Any:
        """
        从 JSON 文件加载数据
        
        Args:
            name: 数据名称
            default: 默认值（文件不存在时返回）
        
        Returns:
            加载的数据
        """
        file_path = self._get_file_path(name)
        
        with self._lock:
            try:
                if not file_path.exists():
                    return default
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"加载数据失败 [{name}]: {e}")
                return default
    
    def delete(self, name: str) -> bool:
        """删除数据文件"""
        file_path = self._get_file_path(name)
        
        with self._lock:
            try:
                if file_path.exists():
                    file_path.unlink()
                return True
            except Exception as e:
                print(f"删除数据失败 [{name}]: {e}")
                return False
    
    def exists(self, name: str) -> bool:
        """检查数据是否存在"""
        return self._get_file_path(name).exists()
    
    def list_all(self) -> list:
        """列出所有数据文件"""
        return [f.stem for f in self.data_dir.glob('*.json')]


class TaskStorage:
    """任务数据持久化"""
    
    def __init__(self, storage: Storage = None):
        self.storage = storage or Storage()
        self._data_name = 'tasks'
    
    def save_tasks(self, tasks: Dict[str, Any]) -> bool:
        """
        保存任务列表
        
        Args:
            tasks: 任务字典 {task_id: task_data}
        """
        # 转换为可序列化格式
        data = {
            'updated_at': datetime.now().isoformat(),
            'tasks': {}
        }
        
        for task_id, task in tasks.items():
            # 如果是 Task 对象，转换为字典
            if hasattr(task, '__dict__'):
                task_dict = {
                    'id': task.id,
                    'repo_url': task.repo_url,
                    'repo_name': task.repo_name,
                    'status': task.status.value if hasattr(task.status, 'value') else str(task.status),
                    'local_path': task.local_path,
                    'message': task.message,
                    'output': task.output[:10000] if task.output else '',  # 限制输出长度
                    'error': task.error if hasattr(task, 'error') else '',
                }
            else:
                task_dict = task
            
            data['tasks'][task_id] = task_dict
        
        return self.storage.save(self._data_name, data)
    
    def load_tasks(self) -> Dict[str, dict]:
        """
        加载任务列表
        
        Returns:
            任务字典 {task_id: task_data}
        """
        data = self.storage.load(self._data_name, {'tasks': {}})
        return data.get('tasks', {})
    
    def get_last_task_id(self) -> int:
        """获取最后一个任务 ID（用于恢复计数器）"""
        tasks = self.load_tasks()
        if not tasks:
            return 0
        
        max_id = 0
        for task_id in tasks.keys():
            try:
                num = int(task_id)
                max_id = max(max_id, num)
            except ValueError:
                continue
        
        return max_id


if __name__ == '__main__':
    # 测试
    storage = Storage()
    
    # 测试保存
    test_data = {'name': 'test', 'value': 123}
    storage.save('test', test_data)
    
    # 测试加载
    loaded = storage.load('test')
    print(f"加载数据: {loaded}")
    
    # 测试列表
    print(f"所有数据: {storage.list_all()}")
    
    # 清理
    storage.delete('test')

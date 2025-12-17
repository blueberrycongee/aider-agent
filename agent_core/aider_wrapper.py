"""
Aider 封装器 - 调用 Aider CLI 执行代码修改任务
"""
import subprocess
import threading
import os
from pathlib import Path
from typing import Callable, Optional


class AiderWrapper:
    def __init__(self, repo_path: str, model: str = None):
        """
        初始化 Aider 封装器
        
        Args:
            repo_path: 仓库本地路径
            model: 使用的模型，如 'gpt-4', 'claude-3-sonnet' 等
        """
        self.repo_path = Path(repo_path)
        self.model = model
        self.process = None
        
        if not self.repo_path.exists():
            raise ValueError(f"仓库路径不存在: {repo_path}")
    
    def _build_command(self, message: str, files: list = None, 
                       auto_commit: bool = True, yes: bool = True) -> list:
        """构建 Aider 命令"""
        cmd = ['aider']
        
        if self.model:
            cmd.extend(['--model', self.model])
        
        if yes:
            cmd.append('--yes')
        
        if not auto_commit:
            cmd.append('--no-auto-commits')
        
        if files:
            for f in files:
                cmd.extend(['--file', f])
        
        cmd.extend(['--message', message])
        
        return cmd
    
    def run(self, message: str, files: list = None,
            on_output: Callable[[str], None] = None,
            auto_commit: bool = True) -> tuple[int, str]:
        """
        运行 Aider 任务
        
        Args:
            message: 发送给 Aider 的消息/指令
            files: 要处理的文件列表
            on_output: 输出回调函数，实时接收输出
            auto_commit: 是否自动提交
        
        Returns:
            (返回码, 完整输出)
        """
        cmd = self._build_command(message, files, auto_commit)
        
        output_lines = []
        
        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=str(self.repo_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env={**os.environ}
            )
            
            for line in iter(self.process.stdout.readline, ''):
                if line:
                    line = line.rstrip()
                    output_lines.append(line)
                    if on_output:
                        on_output(line)
            
            self.process.wait()
            return self.process.returncode, '\n'.join(output_lines)
            
        except Exception as e:
            return -1, str(e)
    
    def run_async(self, message: str, files: list = None,
                  on_output: Callable[[str], None] = None,
                  on_complete: Callable[[int, str], None] = None,
                  auto_commit: bool = True) -> threading.Thread:
        """
        异步运行 Aider 任务
        
        Args:
            message: 发送给 Aider 的消息
            files: 要处理的文件列表
            on_output: 输出回调
            on_complete: 完成回调，参数为 (返回码, 完整输出)
            auto_commit: 是否自动提交
        
        Returns:
            运行任务的线程
        """
        def _run():
            code, output = self.run(message, files, on_output, auto_commit)
            if on_complete:
                on_complete(code, output)
        
        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return thread
    
    def stop(self):
        """停止当前运行的 Aider 进程"""
        if self.process and self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
    
    def review_code(self, on_output: Callable[[str], None] = None) -> tuple[int, str]:
        """
        审查项目代码结构
        
        Returns:
            (返回码, 审查结果)
        """
        message = """请审查这个项目的代码结构，告诉我：
1. 项目的主要功能是什么
2. 代码结构如何组织
3. 有哪些主要的模块和文件
4. 技术栈是什么
5. 有什么可以改进的地方"""
        
        return self.run(message, on_output=on_output, auto_commit=False)
    
    def fix_issue(self, issue_title: str, issue_body: str,
                  files: list = None,
                  on_output: Callable[[str], None] = None) -> tuple[int, str]:
        """
        修复一个 Issue
        
        Args:
            issue_title: Issue 标题
            issue_body: Issue 内容
            files: 相关文件列表
            on_output: 输出回调
        
        Returns:
            (返回码, 修复结果)
        """
        message = f"""请修复以下 Issue：

## Issue 标题
{issue_title}

## Issue 描述
{issue_body}

请：
1. 分析问题原因
2. 找到相关代码
3. 实现修复
4. 确保修改不会破坏现有功能"""
        
        return self.run(message, files=files, on_output=on_output, auto_commit=True)


if __name__ == '__main__':
    # 测试代码
    import sys
    if len(sys.argv) > 1:
        wrapper = AiderWrapper(sys.argv[1])
        code, output = wrapper.review_code(on_output=print)
        print(f"\n完成，返回码: {code}")

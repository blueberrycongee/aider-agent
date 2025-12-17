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
        self.model = model or os.getenv('AIDER_MODEL')
        self.process = None
        
        # 使用虚拟环境中的 aider
        venv_aider = Path(__file__).parent.parent / 'aider_venv' / 'Scripts' / 'aider.exe'
        if venv_aider.exists():
            self.aider_cmd = str(venv_aider)
        else:
            self.aider_cmd = 'aider'
        
        if not self.repo_path.exists():
            raise ValueError(f"仓库路径不存在: {repo_path}")
    
    def _build_command(self, message: str, files: list = None, 
                       auto_commit: bool = True, yes: bool = True) -> list:
        """构建 Aider 命令"""
        cmd = [self.aider_cmd]
        
        if self.model:
            cmd.extend(['--model', self.model])
        
        if yes:
            cmd.append('--yes')
        
        if not auto_commit:
            cmd.append('--no-auto-commits')
        
        # 禁止打开浏览器
        cmd.append('--no-show-release-notes')
        
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
    
    def review_diff(self, diff: str, on_output: Callable[[str], None] = None) -> tuple[int, str]:
        """
        审查代码更改（PR Review 风格）
        
        Args:
            diff: git diff 内容
            on_output: 输出回调
        
        Returns:
            (返回码, 审查结果 JSON)
        """
        message = f"""你是一个代码审查员，请审查以下代码更改。

## 审查准则

判断是否为 Bug 的标准：
- 会对代码的准确性、性能、安全性或可维护性产生实质影响
- Bug 是具体且可操作的（不是泛泛的问题）
- 修复 Bug 不需要超出代码库其他部分的严格程度
- Bug 是在这次提交中引入的（不要标记已存在的问题）
- 不要仅仅推测更改可能破坏其他部分，必须指出受影响的具体代码

## 优先级定义

- [P0] 必须立即修复，阻塞发布
- [P1] 紧急，应在下个周期解决
- [P2] 正常，最终需要修复
- [P3] 低优先级，锦上添花

## 评论准则

- 清楚说明为什么是 Bug
- 准确传达问题的严重性
- 简洁，正文最多一段
- 代码片段不超过 3 行
- 使用事实性语气，不带指责

## 代码更改

```diff
{diff}
```

## 输出格式

请以 JSON 格式输出，包含：
{{
  "findings": [
    {{
      "title": "标题（不超过 80 字符）",
      "body": "问题描述",
      "priority": 0-3,
      "confidence_score": 0.0-1.0,
      "file": "文件路径",
      "line": 行号
    }}
  ],
  "overall_correctness": "patch is correct" | "patch is incorrect",
  "overall_explanation": "总体评价（1-3句话）",
  "overall_confidence_score": 0.0-1.0
}}

如果没有发现问题，findings 应为空数组。"""
        
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

"""
Issue 修复工作流 - 完整的自动修复流程
"""
import subprocess
import os
from pathlib import Path
from typing import Callable, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

from .aider_wrapper import AiderWrapper
from .github_client import GitHubClient


class FixStatus(Enum):
    PENDING = 'pending'
    BRANCHING = 'branching'
    FIXING = 'fixing'
    REVIEWING = 'reviewing'
    DIFF_READY = 'diff_ready'
    COMMITTING = 'committing'
    PUSHING = 'pushing'
    CREATING_PR = 'creating_pr'
    COMPLETED = 'completed'
    ERROR = 'error'


@dataclass
class FixResult:
    """修复结果"""
    success: bool = False
    status: FixStatus = FixStatus.PENDING
    branch_name: str = ''
    diff: str = ''
    review: dict = None  # 代码审查结果
    pr_url: str = ''
    error: str = ''
    output: str = ''


class FixWorkflow:
    """Issue 修复工作流"""
    
    def __init__(self, repo_path: str, github_client: GitHubClient = None):
        """
        初始化工作流
        
        Args:
            repo_path: 本地仓库路径
            github_client: GitHub 客户端（用于创建 PR）
        """
        self.repo_path = Path(repo_path)
        self.github_client = github_client
        self.aider = AiderWrapper(repo_path)
        
    def _run_git(self, *args) -> tuple[int, str, str]:
        """运行 Git 命令"""
        result = subprocess.run(
            ['git'] + list(args),
            cwd=str(self.repo_path),
            capture_output=True,
            text=True
        )
        return result.returncode, result.stdout, result.stderr
    
    def get_current_branch(self) -> str:
        """获取当前分支名"""
        code, stdout, _ = self._run_git('branch', '--show-current')
        return stdout.strip() if code == 0 else 'main'
    
    def get_default_branch(self) -> str:
        """获取默认分支名"""
        code, stdout, _ = self._run_git('symbolic-ref', 'refs/remotes/origin/HEAD', '--short')
        if code == 0:
            return stdout.strip().replace('origin/', '')
        return 'main'
    
    def create_fix_branch(self, issue_number: int) -> tuple[bool, str]:
        """
        创建修复分支
        
        Args:
            issue_number: Issue 编号
        
        Returns:
            (成功, 分支名)
        """
        branch_name = f"fix/issue-{issue_number}"
        
        # 先切回默认分支
        default_branch = self.get_default_branch()
        self._run_git('checkout', default_branch)
        self._run_git('pull', 'origin', default_branch)
        
        # 检查分支是否已存在
        code, _, _ = self._run_git('show-ref', '--verify', f'refs/heads/{branch_name}')
        if code == 0:
            # 分支已存在，切换过去
            self._run_git('checkout', branch_name)
        else:
            # 创建新分支
            code, _, stderr = self._run_git('checkout', '-b', branch_name)
            if code != 0:
                return False, stderr
        
        return True, branch_name
    
    def get_diff(self) -> str:
        """获取当前更改的 diff"""
        # 获取已暂存和未暂存的更改
        code, staged, _ = self._run_git('diff', '--cached')
        code2, unstaged, _ = self._run_git('diff')
        
        diff = ""
        if staged:
            diff += "=== Staged Changes ===\n" + staged + "\n"
        if unstaged:
            diff += "=== Unstaged Changes ===\n" + unstaged + "\n"
        
        if not diff:
            # 检查是否有新文件
            code, status, _ = self._run_git('status', '--porcelain')
            if status:
                diff = "=== File Status ===\n" + status
        
        return diff or "No changes detected"
    
    def commit_changes(self, issue_number: int, issue_title: str) -> tuple[bool, str]:
        """
        提交更改
        
        Args:
            issue_number: Issue 编号
            issue_title: Issue 标题
        
        Returns:
            (成功, 消息)
        """
        # 添加所有更改
        self._run_git('add', '-A')
        
        # 提交
        commit_msg = f"fix: resolve issue #{issue_number} - {issue_title}"
        code, stdout, stderr = self._run_git('commit', '-m', commit_msg)
        
        if code != 0:
            if 'nothing to commit' in stderr or 'nothing to commit' in stdout:
                return False, "没有需要提交的更改"
            return False, stderr
        
        return True, commit_msg
    
    def push_branch(self, branch_name: str) -> tuple[bool, str]:
        """
        推送分支到远程
        
        Args:
            branch_name: 分支名
        
        Returns:
            (成功, 消息)
        """
        code, stdout, stderr = self._run_git('push', '-u', 'origin', branch_name)
        
        if code != 0:
            return False, stderr
        
        return True, f"已推送到 origin/{branch_name}"
    
    def create_pr(self, owner: str, repo_name: str, issue_number: int, 
                  issue_title: str, branch_name: str) -> tuple[bool, str]:
        """
        创建 Pull Request
        
        Args:
            owner: 仓库所有者
            repo_name: 仓库名称
            issue_number: Issue 编号
            issue_title: Issue 标题
            branch_name: 分支名
        
        Returns:
            (成功, PR URL 或错误消息)
        """
        if not self.github_client:
            return False, "GitHub 客户端未配置"
        
        try:
            # 构建 PR 内容
            pr_title = f"Fix #{issue_number}: {issue_title}"
            pr_body = f"""## Summary
This PR fixes #{issue_number}.

## Changes
- Automated fix generated by Aider Agent

## Related Issue
Closes #{issue_number}
"""
            # 获取当前用户名
            username = self.github_client.user.login
            head = f"{username}:{branch_name}"
            
            # 如果是自己的仓库，head 不需要用户名前缀
            try:
                repo = self.github_client.get_repo(owner, repo_name)
                if repo.owner.login == username:
                    head = branch_name
            except:
                pass
            
            pr = self.github_client.create_pull_request(
                owner=owner,
                repo_name=repo_name,
                title=pr_title,
                body=pr_body,
                head_branch=head,
                base_branch=self.get_default_branch()
            )
            
            return True, pr['url']
            
        except Exception as e:
            return False, str(e)
    
    def run_fix(self, issue: Dict[str, Any],
                on_status: Callable[[FixStatus, str], None] = None,
                on_output: Callable[[str], None] = None,
                auto_commit: bool = False,
                auto_push: bool = False,
                auto_pr: bool = False,
                owner: str = None,
                repo_name: str = None) -> FixResult:
        """
        运行完整的修复流程
        
        Args:
            issue: Issue 信息字典
            on_status: 状态回调
            on_output: 输出回调
            auto_commit: 是否自动提交
            auto_push: 是否自动推送
            auto_pr: 是否自动创建 PR
            owner: 仓库所有者（创建 PR 需要）
            repo_name: 仓库名称（创建 PR 需要）
        
        Returns:
            FixResult
        """
        result = FixResult()
        issue_number = issue['number']
        issue_title = issue['title']
        issue_body = issue.get('body', '')
        
        def update_status(status: FixStatus, msg: str):
            result.status = status
            if on_status:
                on_status(status, msg)
        
        def log(msg: str):
            result.output += msg + '\n'
            if on_output:
                on_output(msg)
        
        try:
            # Step 1: 创建分支
            update_status(FixStatus.BRANCHING, f"创建分支 fix/issue-{issue_number}...")
            success, branch = self.create_fix_branch(issue_number)
            if not success:
                raise Exception(f"创建分支失败: {branch}")
            result.branch_name = branch
            log(f"✓ 已创建分支: {branch}")
            
            # Step 2: Aider 修复
            update_status(FixStatus.FIXING, "Aider 正在分析并修复...")
            
            def _on_aider_output(line: str):
                log(line)
            
            code, output = self.aider.fix_issue(issue_title, issue_body, on_output=_on_aider_output)
            
            if code != 0:
                raise Exception(f"Aider 修复失败，返回码: {code}")
            log("✓ Aider 修复完成")
            
            # Step 3: 获取 diff
            update_status(FixStatus.REVIEWING, "获取代码更改...")
            result.diff = self.get_diff()
            log(f"=== Git Diff ===\n{result.diff}")
            
            # Step 4: Aider 审查修复（PR Review 风格）
            if result.diff and result.diff != "No changes detected":
                update_status(FixStatus.REVIEWING, "Aider 正在审查代码更改...")
                review_code, review_output = self.aider.review_diff(result.diff, on_output=_on_aider_output)
                log("✓ 代码审查完成")
                
                # 尝试解析审查结果
                try:
                    import json
                    import re
                    # 提取 JSON
                    json_match = re.search(r'\{[\s\S]*\}', review_output)
                    if json_match:
                        review_result = json.loads(json_match.group())
                        result.review = review_result
                        
                        # 如果有 P0/P1 问题，记录警告
                        findings = review_result.get('findings', [])
                        critical = [f for f in findings if f.get('priority', 3) <= 1]
                        if critical:
                            log(f"⚠ 发现 {len(critical)} 个高优先级问题")
                            for f in critical:
                                log(f"  - [P{f.get('priority', '?')}] {f.get('title', '未知问题')}")
                        
                        correctness = review_result.get('overall_correctness', '')
                        log(f"审查结论: {correctness}")
                except:
                    pass  # 解析失败不影响流程
            
            # Step 5: 准备好 diff，等待用户确认
            update_status(FixStatus.DIFF_READY, "修复完成，等待确认...")
            
            if not auto_commit:
                # 等待用户确认
                update_status(FixStatus.DIFF_READY, "等待确认提交...")
                result.success = True
                return result
            
            # Step 5: 提交
            update_status(FixStatus.COMMITTING, "提交更改...")
            success, msg = self.commit_changes(issue_number, issue_title)
            if not success:
                if "没有需要提交的更改" in msg:
                    log("⚠ 没有代码更改")
                else:
                    raise Exception(f"提交失败: {msg}")
            else:
                log(f"✓ 已提交: {msg}")
            
            if not auto_push:
                result.success = True
                return result
            
            # Step 6: 推送
            update_status(FixStatus.PUSHING, f"推送分支 {branch}...")
            success, msg = self.push_branch(branch)
            if not success:
                raise Exception(f"推送失败: {msg}")
            log(f"✓ {msg}")
            
            if not auto_pr or not owner or not repo_name:
                result.success = True
                return result
            
            # Step 7: 创建 PR
            update_status(FixStatus.CREATING_PR, "创建 Pull Request...")
            success, pr_url = self.create_pr(owner, repo_name, issue_number, issue_title, branch)
            if not success:
                raise Exception(f"创建 PR 失败: {pr_url}")
            result.pr_url = pr_url
            log(f"✓ PR 已创建: {pr_url}")
            
            # 完成
            update_status(FixStatus.COMPLETED, "修复完成！")
            result.success = True
            
        except Exception as e:
            result.error = str(e)
            result.status = FixStatus.ERROR
            update_status(FixStatus.ERROR, f"错误: {str(e)}")
            log(f"✗ 错误: {str(e)}")
        
        return result


if __name__ == '__main__':
    # 测试
    import os
    os.chdir(r"D:\Desktop\aider-agent\data\repos\deer-flow")
    
    workflow = FixWorkflow(".")
    print(f"当前分支: {workflow.get_current_branch()}")
    print(f"默认分支: {workflow.get_default_branch()}")

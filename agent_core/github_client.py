"""
GitHub API 客户端 - 处理仓库、Issue、PR 操作
"""
import os
from github import Github
from github.GithubException import GithubException


class GitHubClient:
    def __init__(self, token=None):
        """
        初始化 GitHub 客户端
        
        Args:
            token: GitHub Personal Access Token，如果不提供则从环境变量读取
        """
        self.token = token or os.getenv('GITHUB_TOKEN')
        if not self.token:
            raise ValueError("需要提供 GITHUB_TOKEN")
        
        self.client = Github(self.token)
        self.user = self.client.get_user()
    
    def get_repo(self, owner, repo_name):
        """获取仓库对象"""
        return self.client.get_repo(f"{owner}/{repo_name}")
    
    def get_issues(self, owner, repo_name, labels=None, state='open', limit=30):
        """
        获取仓库的 Issues
        
        Args:
            owner: 仓库所有者
            repo_name: 仓库名称
            labels: 标签过滤列表，如 ['good first issue', 'bug']
            state: Issue 状态 ('open', 'closed', 'all')
            limit: 最大返回数量
        
        Returns:
            Issue 列表
        """
        repo = self.get_repo(owner, repo_name)
        
        if labels:
            issues = repo.get_issues(state=state, labels=labels)
        else:
            issues = repo.get_issues(state=state)
        
        result = []
        for issue in issues[:limit]:
            # 跳过 PR（GitHub API 把 PR 也算作 Issue）
            if issue.pull_request:
                continue
            
            result.append({
                'number': issue.number,
                'title': issue.title,
                'body': issue.body or '',
                'labels': [l.name for l in issue.labels],
                'url': issue.html_url,
                'created_at': issue.created_at.isoformat(),
                'comments': issue.comments,
                'assignees': [a.login for a in issue.assignees]
            })
        
        return result
    
    def get_good_first_issues(self, owner, repo_name, limit=10):
        """获取适合新手的 Issues"""
        # 常见的新手友好标签
        good_labels = [
            'good first issue',
            'good-first-issue', 
            'help wanted',
            'beginner',
            'easy'
        ]
        
        all_issues = []
        for label in good_labels:
            try:
                issues = self.get_issues(owner, repo_name, labels=[label], limit=limit)
                all_issues.extend(issues)
            except GithubException:
                continue
        
        # 去重
        seen = set()
        unique_issues = []
        for issue in all_issues:
            if issue['number'] not in seen:
                seen.add(issue['number'])
                unique_issues.append(issue)
        
        return unique_issues[:limit]
    
    def fork_repo(self, owner, repo_name):
        """Fork 仓库到自己账户"""
        repo = self.get_repo(owner, repo_name)
        forked = self.user.create_fork(repo)
        return forked
    
    def create_pull_request(self, owner, repo_name, title, body, head_branch, base_branch='main'):
        """
        创建 Pull Request
        
        Args:
            owner: 目标仓库所有者
            repo_name: 目标仓库名称
            title: PR 标题
            body: PR 描述
            head_branch: 源分支（格式：your_username:branch_name）
            base_branch: 目标分支
        
        Returns:
            PR 对象
        """
        repo = self.get_repo(owner, repo_name)
        pr = repo.create_pull(
            title=title,
            body=body,
            head=head_branch,
            base=base_branch
        )
        return {
            'number': pr.number,
            'url': pr.html_url,
            'title': pr.title
        }
    
    def clone_url(self, owner, repo_name, use_ssh=False):
        """获取克隆 URL"""
        repo = self.get_repo(owner, repo_name)
        return repo.ssh_url if use_ssh else repo.clone_url


if __name__ == '__main__':
    # 测试代码
    client = GitHubClient()
    print(f"已登录: {client.user.login}")

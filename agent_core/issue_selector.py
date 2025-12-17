"""
Issue 筛选器 - 评估 Issue 难度，筛选适合修复的 Issue
"""
import re
from typing import List, Dict, Optional
from dataclasses import dataclass, field


@dataclass
class Issue:
    """Issue 数据结构"""
    number: int
    title: str
    body: str
    labels: List[str] = field(default_factory=list)
    url: str = ''
    comments: int = 0
    assignees: List[str] = field(default_factory=list)
    created_at: str = ''
    
    # 评估结果
    difficulty_score: Optional[int] = None  # 1-5, 1 最简单
    recommendation: str = ''
    estimated_files: int = 0
    
    def to_dict(self) -> dict:
        return {
            'number': self.number,
            'title': self.title,
            'body': self.body,
            'labels': self.labels,
            'url': self.url,
            'comments': self.comments,
            'assignees': self.assignees,
            'created_at': self.created_at,
            'difficulty_score': self.difficulty_score,
            'recommendation': self.recommendation,
            'estimated_files': self.estimated_files,
        }


class IssueSelector:
    """Issue 筛选器"""
    
    # 优先处理的标签
    GOOD_LABELS = [
        'good first issue',
        'good-first-issue',
        'help wanted',
        'help-wanted',
        'beginner',
        'beginner-friendly',
        'easy',
        'low-hanging-fruit',
        'starter',
        'first-timers-only',
        'documentation',
        'docs',
        'typo',
    ]
    
    # 应该跳过的标签
    SKIP_LABELS = [
        'wontfix',
        'won\'t fix',
        'invalid',
        'duplicate',
        'question',
        'discussion',
        'needs-discussion',
        'breaking-change',
        'breaking',
        'security',
    ]
    
    # 简单 Issue 的关键词
    EASY_KEYWORDS = [
        'typo', 'typos',
        'spelling',
        'grammar',
        'documentation',
        'readme',
        'comment',
        'rename',
        'format',
        'formatting',
        'indent',
        'whitespace',
        'missing',
        'add',
        'update',
        'fix link',
        'broken link',
    ]
    
    def __init__(self):
        pass
    
    def filter_issues(self, issues: List[Dict]) -> List[Issue]:
        """
        过滤 Issues，移除不适合的
        
        Args:
            issues: 原始 Issue 列表（字典格式）
        
        Returns:
            过滤后的 Issue 对象列表
        """
        result = []
        
        for issue_dict in issues:
            issue = Issue(
                number=issue_dict.get('number'),
                title=issue_dict.get('title', ''),
                body=issue_dict.get('body', '') or '',
                labels=issue_dict.get('labels', []),
                url=issue_dict.get('url', ''),
                comments=issue_dict.get('comments', 0),
                assignees=issue_dict.get('assignees', []),
                created_at=issue_dict.get('created_at', ''),
            )
            
            # 跳过已被认领的
            if issue.assignees:
                continue
            
            # 跳过包含跳过标签的
            labels_lower = [l.lower() for l in issue.labels]
            if any(skip in labels_lower for skip in self.SKIP_LABELS):
                continue
            
            result.append(issue)
        
        return result
    
    def quick_score(self, issue: Issue) -> int:
        """
        快速评估 Issue 难度（不使用 LLM）
        
        Returns:
            1-5 的分数，1 最简单
        """
        score = 3  # 默认中等难度
        
        title_lower = issue.title.lower()
        body_lower = issue.body.lower()
        labels_lower = [l.lower() for l in issue.labels]
        
        # 有好标签，降低难度
        if any(good in labels_lower for good in self.GOOD_LABELS):
            score -= 1
        
        # 包含简单关键词，降低难度
        for keyword in self.EASY_KEYWORDS:
            if keyword in title_lower or keyword in body_lower:
                score -= 1
                break
        
        # Issue 描述很短，可能更简单
        if len(issue.body) < 200:
            score -= 0.5
        
        # Issue 描述很长，可能更复杂
        if len(issue.body) > 1000:
            score += 1
        
        # 很多评论，可能有争议或复杂
        if issue.comments > 10:
            score += 1
        elif issue.comments > 5:
            score += 0.5
        
        # 提到多个文件
        file_mentions = len(re.findall(r'\b\w+\.(py|js|ts|go|rs|java|cpp|c|h)\b', issue.body))
        if file_mentions > 3:
            score += 1
        issue.estimated_files = max(1, file_mentions)
        
        # 限制范围
        score = max(1, min(5, int(score)))
        issue.difficulty_score = score
        
        # 生成推荐理由
        issue.recommendation = self._generate_recommendation(issue, score)
        
        return score
    
    def _generate_recommendation(self, issue: Issue, score: int) -> str:
        """生成推荐理由"""
        reasons = []
        
        labels_lower = [l.lower() for l in issue.labels]
        
        if any(good in labels_lower for good in self.GOOD_LABELS):
            reasons.append("有新手友好标签")
        
        title_lower = issue.title.lower()
        if any(kw in title_lower for kw in ['typo', 'spelling', 'grammar']):
            reasons.append("是拼写/语法修复")
        elif any(kw in title_lower for kw in ['doc', 'readme']):
            reasons.append("是文档更新")
        
        if issue.comments == 0:
            reasons.append("无评论讨论")
        
        if score <= 2:
            return "推荐修复: " + ", ".join(reasons) if reasons else "推荐修复"
        elif score == 3:
            return "可以尝试: " + ", ".join(reasons) if reasons else "中等难度"
        else:
            return "难度较高，建议跳过"
    
    def sort_by_difficulty(self, issues: List[Issue]) -> List[Issue]:
        """按难度排序（简单的在前）"""
        # 先评估所有 Issue
        for issue in issues:
            if issue.difficulty_score is None:
                self.quick_score(issue)
        
        return sorted(issues, key=lambda x: (x.difficulty_score or 5, x.comments))
    
    def get_best_issues(self, issues: List[Dict], limit: int = 5) -> List[Issue]:
        """
        获取最适合修复的 Issues
        
        Args:
            issues: 原始 Issue 列表
            limit: 返回数量
        
        Returns:
            排序后的 Issue 列表
        """
        filtered = self.filter_issues(issues)
        sorted_issues = self.sort_by_difficulty(filtered)
        return sorted_issues[:limit]


if __name__ == '__main__':
    # 测试
    test_issues = [
        {
            'number': 1,
            'title': 'Fix typo in README',
            'body': 'There is a typo in line 10',
            'labels': ['good first issue', 'documentation'],
            'comments': 0,
            'assignees': []
        },
        {
            'number': 2,
            'title': 'Refactor authentication system',
            'body': 'We need to completely redesign the auth flow...' * 50,
            'labels': ['enhancement', 'breaking-change'],
            'comments': 15,
            'assignees': []
        },
        {
            'number': 3,
            'title': 'Add missing docstring',
            'body': 'Function foo() needs a docstring',
            'labels': ['help wanted'],
            'comments': 2,
            'assignees': []
        }
    ]
    
    selector = IssueSelector()
    best = selector.get_best_issues(test_issues)
    
    for issue in best:
        print(f"#{issue.number} [{issue.difficulty_score}] {issue.title}")
        print(f"  → {issue.recommendation}")

"""
S-HAI Hands - Git Operations

Level 3: Git operations for version control.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import subprocess
from pathlib import Path
from typing import List, Optional

from ..core import Hand, HandAction, HandResult, ActionLevel


class GitHand(Hand):
    """
    Hand for git operations.

    Capabilities:
    - git_status: Show working tree status
    - git_add: Stage files
    - git_commit: Commit staged changes
    - git_push: Push to remote
    - git_pull: Pull from remote
    - git_branch: Create/list branches
    - git_checkout: Switch branches
    - git_log: Show commit history
    - git_diff: Show changes
    """

    def __init__(self, sandbox_root: Path, repo_path: Optional[Path] = None, **kwargs):
        super().__init__(sandbox_root, **kwargs)
        self.repo_path = Path(repo_path or sandbox_root).resolve()

    def get_level(self) -> ActionLevel:
        return ActionLevel.GIT_OPS

    def get_capabilities(self) -> List[str]:
        return [
            'git_status',
            'git_add',
            'git_commit',
            'git_push',
            'git_pull',
            'git_branch',
            'git_checkout',
            'git_log',
            'git_diff'
        ]

    def _run_git(self, *args) -> tuple:
        """Run a git command and return (success, output/error)."""
        try:
            result = subprocess.run(
                ['git'] + list(args),
                cwd=str(self.repo_path),
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode == 0:
                return True, result.stdout
            else:
                return False, result.stderr
        except subprocess.TimeoutExpired:
            return False, "Command timed out"
        except Exception as e:
            return False, str(e)

    def _execute(self, action: HandAction) -> HandResult:
        """Execute a git operation."""
        name = action.name
        params = action.params

        try:
            if name == 'git_status':
                return self._git_status()
            elif name == 'git_add':
                return self._git_add(params.get('files', ['.']))
            elif name == 'git_commit':
                return self._git_commit(
                    params['message'],
                    params.get('author')
                )
            elif name == 'git_push':
                return self._git_push(
                    params.get('remote', 'origin'),
                    params.get('branch')
                )
            elif name == 'git_pull':
                return self._git_pull(
                    params.get('remote', 'origin'),
                    params.get('branch')
                )
            elif name == 'git_branch':
                return self._git_branch(
                    params.get('name'),
                    params.get('create', False)
                )
            elif name == 'git_checkout':
                return self._git_checkout(params['branch'])
            elif name == 'git_log':
                return self._git_log(params.get('limit', 10))
            elif name == 'git_diff':
                return self._git_diff(params.get('cached', False))
            else:
                return HandResult(success=False, error=f"Unknown action: {name}")

        except Exception as e:
            return HandResult(success=False, error=str(e))

    def _git_status(self) -> HandResult:
        """Get repository status."""
        success, output = self._run_git('status', '--porcelain')
        if not success:
            return HandResult(success=False, error=output)

        # Parse status
        changes = []
        for line in output.strip().split('\n'):
            if line:
                status = line[:2]
                path = line[3:]
                changes.append({'status': status, 'path': path})

        return HandResult(
            success=True,
            output={'changes': changes, 'clean': len(changes) == 0}
        )

    def _git_add(self, files: List[str]) -> HandResult:
        """Stage files."""
        # Validate paths are in sandbox
        for f in files:
            if f != '.' and not self.is_path_safe(self.repo_path / f):
                return HandResult(
                    success=False,
                    error=f"Path outside sandbox: {f}"
                )

        success, output = self._run_git('add', *files)
        if not success:
            return HandResult(success=False, error=output)

        return HandResult(success=True, output={'staged': files})

    def _git_commit(self, message: str, author: Optional[str] = None) -> HandResult:
        """Commit staged changes."""
        # Add our signature
        full_message = f"{message}\n\n🤖 Built by S-HAI Hands\nπ×φ = 5.083203692315260"

        args = ['commit', '-m', full_message]
        if author:
            args.extend(['--author', author])

        success, output = self._run_git(*args)
        if not success:
            return HandResult(success=False, error=output)

        return HandResult(success=True, output={'message': message, 'output': output})

    def _git_push(self, remote: str = 'origin', branch: Optional[str] = None) -> HandResult:
        """Push to remote."""
        # Safety: Never force push
        args = ['push', remote]
        if branch:
            args.append(branch)

        success, output = self._run_git(*args)
        if not success:
            return HandResult(success=False, error=output)

        return HandResult(success=True, output={'remote': remote, 'output': output})

    def _git_pull(self, remote: str = 'origin', branch: Optional[str] = None) -> HandResult:
        """Pull from remote."""
        args = ['pull', remote]
        if branch:
            args.append(branch)

        success, output = self._run_git(*args)
        if not success:
            return HandResult(success=False, error=output)

        return HandResult(success=True, output={'remote': remote, 'output': output})

    def _git_branch(self, name: Optional[str] = None, create: bool = False) -> HandResult:
        """List or create branches."""
        if name and create:
            success, output = self._run_git('checkout', '-b', name)
        elif name:
            success, output = self._run_git('branch', name)
        else:
            success, output = self._run_git('branch', '-a')

        if not success:
            return HandResult(success=False, error=output)

        if not name:
            # Parse branch list
            branches = []
            current = None
            for line in output.strip().split('\n'):
                if line.startswith('* '):
                    current = line[2:].strip()
                    branches.append(current)
                elif line.strip():
                    branches.append(line.strip())
            return HandResult(
                success=True,
                output={'branches': branches, 'current': current}
            )

        return HandResult(success=True, output={'branch': name, 'created': create})

    def _git_checkout(self, branch: str) -> HandResult:
        """Switch branches."""
        success, output = self._run_git('checkout', branch)
        if not success:
            return HandResult(success=False, error=output)

        return HandResult(success=True, output={'branch': branch})

    def _git_log(self, limit: int = 10) -> HandResult:
        """Get commit history."""
        success, output = self._run_git(
            'log',
            f'-{limit}',
            '--pretty=format:%H|%an|%ae|%s|%ci'
        )
        if not success:
            return HandResult(success=False, error=output)

        commits = []
        for line in output.strip().split('\n'):
            if line:
                parts = line.split('|')
                if len(parts) >= 5:
                    commits.append({
                        'hash': parts[0],
                        'author': parts[1],
                        'email': parts[2],
                        'message': parts[3],
                        'date': parts[4]
                    })

        return HandResult(success=True, output={'commits': commits})

    def _git_diff(self, cached: bool = False) -> HandResult:
        """Show changes."""
        args = ['diff']
        if cached:
            args.append('--cached')

        success, output = self._run_git(*args)
        if not success:
            return HandResult(success=False, error=output)

        return HandResult(success=True, output={'diff': output})

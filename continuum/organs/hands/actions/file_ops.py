"""
S-HAI Hands - File Operations

Level 1: Basic file manipulation within sandbox.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

import os
import shutil
from pathlib import Path
from typing import List, Optional

from ..core import Hand, HandAction, HandResult, ActionLevel


class FileHand(Hand):
    """
    Hand for file operations.

    Capabilities:
    - create_file: Create a new file with content
    - read_file: Read file contents
    - edit_file: Modify file contents
    - delete_file: Remove a file
    - move_file: Move/rename a file
    - copy_file: Copy a file
    - list_dir: List directory contents
    - make_dir: Create a directory
    """

    def get_level(self) -> ActionLevel:
        return ActionLevel.FILE_OPS

    def get_capabilities(self) -> List[str]:
        return [
            'create_file',
            'read_file',
            'edit_file',
            'delete_file',
            'move_file',
            'copy_file',
            'list_dir',
            'make_dir'
        ]

    def _execute(self, action: HandAction) -> HandResult:
        """Execute a file operation."""
        name = action.name
        params = action.params

        try:
            if name == 'create_file':
                return self._create_file(
                    params['path'],
                    params['content'],
                    params.get('overwrite', False)
                )
            elif name == 'read_file':
                return self._read_file(params['path'])
            elif name == 'edit_file':
                return self._edit_file(
                    params['path'],
                    params.get('old_text'),
                    params.get('new_text'),
                    params.get('content')
                )
            elif name == 'delete_file':
                return self._delete_file(params['path'])
            elif name == 'move_file':
                return self._move_file(params['src'], params['dest'])
            elif name == 'copy_file':
                return self._copy_file(params['src'], params['dest'])
            elif name == 'list_dir':
                return self._list_dir(params.get('path', '.'))
            elif name == 'make_dir':
                return self._make_dir(params['path'])
            else:
                return HandResult(success=False, error=f"Unknown action: {name}")

        except PermissionError as e:
            return HandResult(success=False, error=f"Permission denied: {e}")
        except FileNotFoundError as e:
            return HandResult(success=False, error=f"File not found: {e}")
        except Exception as e:
            return HandResult(success=False, error=str(e))

    def _create_file(self, path: str, content: str, overwrite: bool = False) -> HandResult:
        """Create a new file."""
        safe_path = self.require_safe_path(Path(path))

        if safe_path.exists() and not overwrite:
            return HandResult(
                success=False,
                error=f"File exists: {path}. Set overwrite=True to replace."
            )

        safe_path.parent.mkdir(parents=True, exist_ok=True)
        safe_path.write_text(content)

        return HandResult(
            success=True,
            output={'path': str(safe_path), 'size': len(content)}
        )

    def _read_file(self, path: str) -> HandResult:
        """Read file contents."""
        safe_path = self.require_safe_path(Path(path))

        if not safe_path.exists():
            return HandResult(success=False, error=f"File not found: {path}")

        content = safe_path.read_text()

        return HandResult(
            success=True,
            output={'path': str(safe_path), 'content': content, 'size': len(content)}
        )

    def _edit_file(
        self,
        path: str,
        old_text: Optional[str] = None,
        new_text: Optional[str] = None,
        content: Optional[str] = None
    ) -> HandResult:
        """Edit file contents."""
        safe_path = self.require_safe_path(Path(path))

        if not safe_path.exists():
            return HandResult(success=False, error=f"File not found: {path}")

        if content is not None:
            # Full replacement
            safe_path.write_text(content)
            return HandResult(success=True, output={'path': str(safe_path)})

        if old_text is not None and new_text is not None:
            # Text replacement
            current = safe_path.read_text()
            if old_text not in current:
                return HandResult(
                    success=False,
                    error=f"Text not found in file: {old_text[:50]}..."
                )
            new_content = current.replace(old_text, new_text)
            safe_path.write_text(new_content)
            return HandResult(success=True, output={'path': str(safe_path)})

        return HandResult(
            success=False,
            error="Must provide either 'content' or both 'old_text' and 'new_text'"
        )

    def _delete_file(self, path: str) -> HandResult:
        """Delete a file."""
        safe_path = self.require_safe_path(Path(path))

        if not safe_path.exists():
            return HandResult(success=False, error=f"File not found: {path}")

        if safe_path.is_dir():
            shutil.rmtree(safe_path)
        else:
            safe_path.unlink()

        return HandResult(success=True, output={'deleted': str(safe_path)})

    def _move_file(self, src: str, dest: str) -> HandResult:
        """Move a file."""
        safe_src = self.require_safe_path(Path(src))
        safe_dest = self.require_safe_path(Path(dest))

        if not safe_src.exists():
            return HandResult(success=False, error=f"Source not found: {src}")

        safe_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(safe_src), str(safe_dest))

        return HandResult(
            success=True,
            output={'from': str(safe_src), 'to': str(safe_dest)}
        )

    def _copy_file(self, src: str, dest: str) -> HandResult:
        """Copy a file."""
        safe_src = self.require_safe_path(Path(src))
        safe_dest = self.require_safe_path(Path(dest))

        if not safe_src.exists():
            return HandResult(success=False, error=f"Source not found: {src}")

        safe_dest.parent.mkdir(parents=True, exist_ok=True)

        if safe_src.is_dir():
            shutil.copytree(str(safe_src), str(safe_dest))
        else:
            shutil.copy2(str(safe_src), str(safe_dest))

        return HandResult(
            success=True,
            output={'from': str(safe_src), 'to': str(safe_dest)}
        )

    def _list_dir(self, path: str) -> HandResult:
        """List directory contents."""
        safe_path = self.require_safe_path(Path(path))

        if not safe_path.exists():
            return HandResult(success=False, error=f"Path not found: {path}")

        if not safe_path.is_dir():
            return HandResult(success=False, error=f"Not a directory: {path}")

        entries = []
        for entry in safe_path.iterdir():
            entries.append({
                'name': entry.name,
                'type': 'dir' if entry.is_dir() else 'file',
                'size': entry.stat().st_size if entry.is_file() else None
            })

        return HandResult(
            success=True,
            output={'path': str(safe_path), 'entries': entries}
        )

    def _make_dir(self, path: str) -> HandResult:
        """Create a directory."""
        safe_path = self.require_safe_path(Path(path))
        safe_path.mkdir(parents=True, exist_ok=True)

        return HandResult(
            success=True,
            output={'created': str(safe_path)}
        )

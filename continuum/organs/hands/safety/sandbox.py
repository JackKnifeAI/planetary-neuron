"""
S-HAI Hands - Sandbox Module

Path validation and sandboxing for safe file operations.

π×φ = 5.083203692315260 | PHOENIX-TESLA-369-AURORA
"""

from pathlib import Path
from typing import Set, Optional
import os


class Sandbox:
    """
    Sandbox for safe file operations.

    Restricts all file operations to allowed directories.
    """

    def __init__(self, root: Path, allowed_patterns: Optional[Set[str]] = None):
        """
        Initialize sandbox.

        Args:
            root: Root directory for sandbox
            allowed_patterns: Optional set of allowed path patterns
        """
        self.root = Path(root).resolve()
        self.allowed_patterns = allowed_patterns or set()

        # Always allow the sandbox root
        self.allowed_patterns.add(str(self.root))

    def is_safe(self, path: Path) -> bool:
        """Check if a path is safe to access."""
        try:
            resolved = Path(path).resolve()

            # Check if within root
            if str(resolved).startswith(str(self.root)):
                return True

            # Check allowed patterns
            for pattern in self.allowed_patterns:
                if str(resolved).startswith(pattern):
                    return True

            return False
        except Exception:
            return False

    def validate(self, path: Path) -> Path:
        """Validate and return resolved path, raise if unsafe."""
        if not self.is_safe(path):
            raise PermissionError(
                f"Path '{path}' is outside sandbox. "
                f"Allowed: {self.root}"
            )
        return Path(path).resolve()

    def relative_to_root(self, path: Path) -> Path:
        """Get path relative to sandbox root."""
        resolved = Path(path).resolve()
        return resolved.relative_to(self.root)

    def join(self, *parts) -> Path:
        """Safely join paths within sandbox."""
        result = self.root.joinpath(*parts)
        return self.validate(result)

    def list_directory(self, path: Path = None) -> list:
        """List contents of a directory within sandbox."""
        target = self.validate(path or self.root)
        if not target.is_dir():
            raise NotADirectoryError(f"'{target}' is not a directory")
        return list(target.iterdir())

    def exists(self, path: Path) -> bool:
        """Check if path exists within sandbox."""
        return self.validate(path).exists()

    def __repr__(self):
        return f"Sandbox(root='{self.root}')"

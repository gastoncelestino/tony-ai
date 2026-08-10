"""
Tony Kernel — Scope Guard

Validates that code changes stay within allowed file boundaries.
Prevents "scope creep" where agents modify files outside their assigned scope.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Set
from enum import Enum
import re
import fnmatch


class ScopeViolationType(str, Enum):
    UNAUTHORIZED_FILE = "unauthorized_file"
    UNAUTHORIZED_DIRECTORY = "unauthorized_directory"
    FORBIDDEN_PATTERN = "forbidden_pattern"
    OUTSIDE_PROJECT = "outside_project"


@dataclass(frozen=True, slots=True)
class ScopeViolation:
    file_path: str
    violation_type: ScopeViolationType
    message: str
    matched_pattern: Optional[str] = None


@dataclass
class ScopeGuard:
    """
    Validates that changes stay within allowed scope.
    
    Allowed scope is defined by:
    - allowed_patterns: glob patterns of allowed files/directories
    - forbidden_patterns: glob patterns that are never allowed
    - project_root: root directory of the project (changes outside are violations)
    """
    allowed_patterns: Tuple[str, ...] = field(default_factory=tuple)
    forbidden_patterns: Tuple[str, ...] = field(default_factory=tuple)
    project_root: str = ""
    
    # Default forbidden patterns
    DEFAULT_FORBIDDEN = (
        "*.secret", "*.key", "*.pem", "*.p12",
        ".env*", "*.env",
        "id_rsa*", "id_ed25519*",
        "*.pem", "*.crt", "*.cer",
        ".git/config",
        ".aws/credentials",
        ".docker/config.json",
    )
    
    def __post_init__(self):
        # Merge default forbidden patterns
        all_forbidden = set(self.forbidden_patterns)
        all_forbidden.update(self.DEFAULT_FORBIDDEN)
        object.__setattr__(self, 'forbidden_patterns', tuple(all_forbidden))
    
    def check_diff(self, git_diff: str, allowed_files: Tuple[str, ...] = ()) -> 'ScopeCheckResult':
        """
        Check a git diff against allowed scope.
        
        Args:
            git_diff: Output of `git diff` or `git diff --name-only`
            allowed_files: Additional allowed file patterns for this specific change
        
        Returns:
            ScopeCheckResult with violations if any
        """
        if not git_diff:
            return ScopeCheckResult(passed=True, violations=(), modified_files=())
        
        # Parse modified files from diff
        modified_files = self._parse_diff_files(git_diff)
        
        # Combine base allowed patterns with task-specific ones
        all_allowed = set(self.allowed_patterns)
        all_allowed.update(allowed_files)
        
        violations = []
        for file_path in modified_files:
            # Check if file is outside project root
            if self.project_root and not file_path.startswith(self.project_root.lstrip('/')):
                violations.append(ScopeViolation(
                    file_path=file_path,
                    violation_type="outside_project",
                    message=f"File {file_path} is outside project root",
                ))
                continue
            
            # Check forbidden patterns first (highest priority)
            for pattern in self.forbidden_patterns:
                if fnmatch.fnmatch(file_path, pattern):
                    violations.append(ScopeViolation(
                        file_path=file_path,
                        violation_type=ScopeViolationType.FORBIDDEN_PATTERN,
                        message=f"File {file_path} matches forbidden pattern: {pattern}",
                        matched_pattern=pattern,
                    ))
                    break
            
            # Check if file is allowed
            allowed = False
            for pattern in all_allowed:
                if fnmatch.fnmatch(file_path, pattern):
                    allowed = True
                    break
            
            if not allowed:
                violations.append(ScopeViolation(
                    file_path=file_path,
                    violation_type=ScopeViolationType.UNAUTHORIZED_FILE,
                    message=f"File {file_path} not in allowed patterns: {', '.join(all_allowed) if all_allowed else 'none'}",
                ))
        
        passed = len(violations) == 0
        return ScopeCheckResult(
            passed=passed,
            violations=tuple(violations),
            modified_files=tuple(modified_files),
        )
    
    def check_file_access(self, file_path: str, operation: str = "read") -> bool:
        """Check if a file access is allowed."""
        # Check forbidden patterns
        for pattern in self.forbidden_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return False
        
        # Check allowed patterns
        for pattern in self.allowed_patterns:
            if fnmatch.fnmatch(file_path, pattern):
                return True
        
        return False
    
    def _parse_diff_files(self, git_diff: str) -> List[str]:
        """Parse git diff to extract modified file paths."""
        files = set()
        
        for line in git_diff.split('\n'):
            # Match diff headers: +++ b/path/to/file or --- a/path/to/file
            if line.startswith('+++') or line.startswith('---'):
                # Format: +++ b/path/to/file or --- a/path/to/file
                parts = line.split('\t')
                if len(parts) > 1:
                    file_path = parts[1]
                    # Remove a/ or b/ prefix
                    if file_path.startswith(('a/', 'b/')):
                        file_path = file_path[2:]
                    if file_path != '/dev/null':
                        files.add(file_path)
            # Also match `diff --git a/file b/file` format
            elif line.startswith('diff --git'):
                match = re.search(r'diff --git a/(.+) b/(.+)', line)
                if match:
                    files.add(match.group(1))
                    files.add(match.group(2))
        
        return list(files)
    
    def add_allowed_pattern(self, pattern: str) -> None:
        """Add an allowed pattern at runtime."""
        object.__setattr__(self, 'allowed_patterns', self.allowed_patterns + (pattern,))
    
    def add_forbidden_pattern(self, pattern: str) -> None:
        """Add a forbidden pattern at runtime."""
        object.__setattr__(self, 'forbidden_patterns', self.forbidden_patterns + (pattern,))
    
    def set_project_root(self, root: str) -> None:
        object.__setattr__(self, 'project_root', root)


@dataclass(frozen=True, slots=True)
class ScopeCheckResult:
    """Result of a scope check."""
    passed: bool
    violations: Tuple[ScopeViolation, ...]
    modified_files: Tuple[str, ...]
    
    @property
    def violation_count(self) -> int:
        return len(self.violations)
    
    def get_violation_summary(self) -> str:
        if not self.violations:
            return "No scope violations"
        return f"{len(self.violations)} scope violations: " + "; ".join(
            f"{v.file_path} ({v.violation_type.value})" for v in self.violations
        )


# Default scope guard for SDD phases
def create_sdd_scope_guard(phase: str, change_name: str, project_root: str = "") -> 'ScopeGuard':
    """
    Create a scope guard for a specific SDD phase.
    
    Args:
        phase: Current SDD phase (explore, propose, spec, design, tasks, apply, verify, archive)
        change_name: Name of the change (used for artifact paths)
        project_root: Project root directory
    """
    # Base patterns allowed for all phases
    base_allowed = (
        "*.md",           # Documentation
        "*.txt",          # Text files
        "*.json",         # Config files
        "*.yaml", "*.yml", # YAML configs
        "*.toml",         # TOML configs
        "*.py",           # Python files
        "*.js", "*.ts", "*.jsx", "*.tsx",  # JavaScript/TypeScript
        "*.go",           # Go files
        "*.rs",           # Rust files
        "*.java",         # Java files
        "*.c", "*.h", "*.cpp", "*.hpp",  # C/C++
        "*.rs",           # Rust
        "Dockerfile*",    # Docker
        "docker-compose*.yml",
        "Makefile*",      # Makefiles
        "*.sh", "*.bash", # Shell scripts
    )
    
    # Phase-specific allowed patterns
    phase_patterns = {
        "explore": (
            "*",  # Exploration can read anything
        ),
        "propose": (
            "*.md", "*.txt", "*.json", "*.yaml", "*.yml",
        ),
        "spec": (
            "openspec/**",
            "docs/**",
            "*.md",
        ),
        "design": (
            "openspec/**",
            "docs/**",
            "architecture/**",
            "*.md",
        ),
        "tasks": (
            "openspec/**",
            "*.md",
        ),
        "apply": (
            "src/**",
            "lib/**",
            "app/**",
            "tests/**",
            "test/**",
            "spec/**",
            "*.py", "*.js", "*.ts", "*.go", "*.rs", "*.java",
            "*.c", "*.h", "*.cpp", "*.hpp",
        ),
        "verify": (
            "tests/**",
            "test/**",
            "spec/**",
            "*.py", "*.js", "*.ts", "*.go", "*.rs",
        ),
        "archive": (
            "*.md",
            "openspec/**",
        ),
    }
    
    allowed = set(base_allowed)
    allowed.update(phase_patterns.get(phase, ()))
    
    return ScopeGuard(
        allowed_patterns=tuple(allowed),
        forbidden_patterns=(),
        project_root=project_root,
    )


@dataclass
class ScopeGuardConfig:
    """Configuration for ScopeGuard."""
    allowed_patterns: Tuple[str, ...] = field(default_factory=tuple)
    forbidden_patterns: Tuple[str, ...] = field(default_factory=tuple)
    project_root: str = ""
    
    def to_scope_guard(self) -> ScopeGuard:
        return ScopeGuard(
            allowed_patterns=self.allowed_patterns,
            forbidden_patterns=self.forbidden_patterns,
            project_root=self.project_root,
        )
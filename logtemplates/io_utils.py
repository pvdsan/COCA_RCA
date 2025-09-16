"""
I/O utilities for repository walking and JSONL operations.
"""

import os
import json
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Iterator, Optional, Set
from dataclasses import asdict
from tqdm import tqdm

from .models import LogTemplate


class RepositoryWalker:
    """
    Walks through repository files with exclusion patterns.
    """
    
    def __init__(self, 
                 root_path: str, 
                 include_patterns: List[str] = None,
                 exclude_patterns: List[str] = None):
        self.root_path = Path(root_path).resolve()
        self.include_patterns = include_patterns or ["*.java"]
        self.exclude_patterns = exclude_patterns or []
        
        # Common exclusion patterns
        default_excludes = [
            "*/target/*", "*/build/*", "*/bin/*", "*/out/*",
            "*/.git/*", "*/.svn/*", "*/.hg/*",
            "*/node_modules/*", "*/__pycache__/*",
            "*/test/*", "*/tests/*", "*/testing/*",
            "*/example/*", "*/examples/*", "*/sample/*", "*/samples/*"
        ]
        self.exclude_patterns.extend(default_excludes)
    
    def _matches_pattern(self, file_path: Path, patterns: List[str]) -> bool:
        """Check if file path matches any of the given patterns."""
        relative_path = str(file_path.relative_to(self.root_path))
        
        for pattern in patterns:
            if fnmatch.fnmatch(relative_path, pattern):
                return True
            if fnmatch.fnmatch(str(file_path), pattern):
                return True
        
        return False
    
    def walk_files(self) -> Iterator[Path]:
        """
        Walk repository and yield matching files.
        
        Yields:
            Path objects for files that match include patterns
            and don't match exclude patterns.
        """
        for root, dirs, files in os.walk(self.root_path):
            root_path = Path(root)
            
            # Filter directories to avoid walking excluded paths
            dirs[:] = [d for d in dirs if not self._matches_pattern(
                root_path / d, self.exclude_patterns
            )]
            
            for file in files:
                file_path = root_path / file
                
                # Check include patterns
                if not self._matches_pattern(file_path, self.include_patterns):
                    continue
                
                # Check exclude patterns
                if self._matches_pattern(file_path, self.exclude_patterns):
                    continue
                
                yield file_path
    
    def count_files(self) -> int:
        """Count the total number of files that would be processed."""
        return sum(1 for _ in self.walk_files())


class JSONLWriter:
    """
    Writer for JSONL (JSON Lines) format.
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
        self.file_handle = None
    
    def __enter__(self):
        self.file_handle = open(self.file_path, 'w', encoding='utf-8')
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.file_handle:
            self.file_handle.close()
    
    def write_template(self, template: LogTemplate) -> None:
        """Write a single template to the JSONL file."""
        if not self.file_handle:
            raise ValueError("JSONLWriter not opened")
        
        # Convert to dict using dataclasses_json
        template_dict = template.to_dict()
        json.dump(template_dict, self.file_handle, ensure_ascii=False)
        self.file_handle.write('\n')
    
    def write_templates(self, templates: List[LogTemplate]) -> None:
        """Write multiple templates to the JSONL file."""
        for template in templates:
            self.write_template(template)


class JSONLReader:
    """
    Reader for JSONL (JSON Lines) format.
    """
    
    def __init__(self, file_path: str):
        self.file_path = Path(file_path)
    
    def read_templates(self) -> List[LogTemplate]:
        """Read all templates from the JSONL file."""
        templates = []
        
        if not self.file_path.exists():
            return templates
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    template_dict = json.loads(line)
                    template = LogTemplate.from_dict(template_dict)
                    templates.append(template)
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    print(f"Warning: Skipping invalid template at line {line_num}: {e}")
        
        return templates
    
    def __iter__(self) -> Iterator[LogTemplate]:
        """Iterate over templates in the file."""
        if not self.file_path.exists():
            return
        
        with open(self.file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                try:
                    template_dict = json.loads(line)
                    template = LogTemplate.from_dict(template_dict)
                    yield template
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    print(f"Warning: Skipping invalid template at line {line_num}: {e}")



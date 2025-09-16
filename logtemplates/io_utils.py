"""
I/O utilities for repository walking, caching, and JSONL operations.
"""

import os
import json
import hashlib
import fnmatch
from pathlib import Path
from typing import List, Dict, Any, Iterator, Optional, Set
from dataclasses import asdict
import pickle
from tqdm import tqdm

from .models import LogTemplate


class CacheManager:
    """
    Manages incremental caching based on file modification times.
    """
    
    def __init__(self, cache_dir: str = ".logtemplates_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.metadata_file = self.cache_dir / "metadata.json"
        self.templates_file = self.cache_dir / "templates.pkl"
        
        # Load existing metadata
        self.metadata = self._load_metadata()
    
    def _load_metadata(self) -> Dict[str, float]:
        """Load file metadata (mtime) from cache."""
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                pass
        return {}
    
    def _save_metadata(self) -> None:
        """Save file metadata to cache."""
        with open(self.metadata_file, 'w') as f:
            json.dump(self.metadata, f, indent=2)
    
    def is_file_cached(self, file_path: str) -> bool:
        """Check if file is already cached and up-to-date."""
        try:
            current_mtime = os.path.getmtime(file_path)
            cached_mtime = self.metadata.get(file_path, 0)
            return current_mtime <= cached_mtime
        except OSError:
            return False
    
    def mark_file_processed(self, file_path: str) -> None:
        """Mark file as processed with current mtime."""
        try:
            self.metadata[file_path] = os.path.getmtime(file_path)
        except OSError:
            pass
    
    def get_cached_templates(self) -> List[LogTemplate]:
        """Load cached templates."""
        if self.templates_file.exists():
            try:
                with open(self.templates_file, 'rb') as f:
                    return pickle.load(f)
            except (pickle.PickleError, IOError):
                pass
        return []
    
    def save_templates(self, templates: List[LogTemplate]) -> None:
        """Save templates to cache."""
        with open(self.templates_file, 'wb') as f:
            pickle.dump(templates, f)
        self._save_metadata()
    
    def invalidate_file(self, file_path: str) -> None:
        """Remove file from cache."""
        self.metadata.pop(file_path, None)
        self._save_metadata()
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self.metadata.clear()
        if self.templates_file.exists():
            self.templates_file.unlink()
        self._save_metadata()


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


def create_file_hash(file_path: str) -> str:
    """Create a hash of file content for change detection."""
    hasher = hashlib.md5()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except IOError:
        return ""


def ensure_directory(path: str) -> Path:
    """Ensure directory exists and return Path object."""
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path

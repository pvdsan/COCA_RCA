"""
Core data models for log template extraction and matching.
"""

from dataclasses import dataclass, field
from typing import List, Optional
from dataclasses_json import dataclass_json, config
from enum import Enum


class LogLevel(Enum):
    """Standard logging levels."""
    TRACE = "trace"
    DEBUG = "debug"
    INFO = "info"
    WARN = "warn"
    ERROR = "error"
    FATAL = "fatal"
    UNKNOWN = "unknown"
    
    def __str__(self) -> str:
        return self.value


@dataclass_json
@dataclass
class SourceLocation:
    """Source code location information."""
    file_path: str
    class_name: Optional[str]
    method_name: Optional[str]
    line_number: int
    
    def __str__(self) -> str:
        parts = [self.file_path]
        if self.class_name:
            parts.append(f"class:{self.class_name}")
        if self.method_name:
            parts.append(f"method:{self.method_name}")
        parts.append(f"line:{self.line_number}")
        return ":".join(parts)


@dataclass_json
@dataclass
class LogTemplate:
    """A log template extracted from source code."""
    template_id: str  # unique identifier
    pattern: str  # template with <*> placeholders
    static_token_count: int  # number of literal tokens
    location: SourceLocation
    level: LogLevel = field(metadata=config(
        encoder=lambda x: x.value,
        decoder=lambda x: LogLevel(x)
    ))
    branch_variant: int = 0  # for branch-aware extraction
    


@dataclass_json
@dataclass
class LogMatch:
    """Result of matching a runtime log line to a template."""
    template: LogTemplate
    confidence: float  # matching confidence score
    extracted_values: List[str]  # values that matched <*> placeholders
    
    def __str__(self) -> str:
        return (f"Match(template_id={self.template.template_id}, "
                f"confidence={self.confidence:.3f}, "
                f"location={self.template.location})")


@dataclass
class ExtractionContext:
    """Context information during template extraction."""
    file_path: str
    class_name: Optional[str] = None
    method_name: Optional[str] = None
    current_line: int = 0
    def copy(self) -> 'ExtractionContext':
        """Create a copy of this context."""
        return ExtractionContext(
            file_path=self.file_path,
            class_name=self.class_name,
            method_name=self.method_name,
            current_line=self.current_line
        )

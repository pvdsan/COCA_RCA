"""
Log Template Extraction and Matching System

A Python library for extracting logging templates from Java codebases
and matching runtime log lines back to their source templates.
"""

__version__ = "1.0.0"
__author__ = "Log Template Extraction System"

from .java_extractor import JavaLogExtractor
from .templating import TemplateRule, LogTemplateBuilder
from .trie import TemplateTrie
from .io_utils import JSONLWriter, JSONLReader

__all__ = [
    "JavaLogExtractor",
    "TemplateRule", 
    "LogTemplateBuilder",
    "TemplateTrie",
    "JSONLWriter",
    "JSONLReader"
]

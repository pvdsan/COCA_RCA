"""
Trie-based template matcher with wildcard support.

Implements a non-prunable trie that supports <*> wildcard placeholders
and uses the most-specific template rule (highest static_token_count wins).
"""

from typing import List, Optional, Dict, Tuple
import re
from .models import LogTemplate, LogMatch


class TrieNode:
    """A node in the template trie."""
    
    def __init__(self):
        self.children: Dict[str, 'TrieNode'] = {}
        self.wildcard_child: Optional['TrieNode'] = None
        self.templates: List[LogTemplate] = []
        self.is_terminal = False
    
    def add_child(self, token: str) -> 'TrieNode':
        """Add a child node for the given token."""
        if token == "<*>":
            if self.wildcard_child is None:
                self.wildcard_child = TrieNode()
            return self.wildcard_child
        else:
            if token not in self.children:
                self.children[token] = TrieNode()
            return self.children[token]
    
    def get_child(self, token: str) -> Optional['TrieNode']:
        """Get child node for the given token."""
        if token == "<*>":
            return self.wildcard_child
        return self.children.get(token)


class TemplateTrie:
    """
    Trie data structure for efficient template matching.
    
    Supports wildcard placeholders (<*>) and implements most-specific
    template matching based on static token count.
    """
    
    def __init__(self):
        self.root = TrieNode()
        self._tokenizer_pattern = re.compile(r'\S+')
    
    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into words, preserving structure for matching."""
        return self._tokenizer_pattern.findall(text)
    
    def add_template(self, template: LogTemplate) -> None:
        """Add a template to the trie."""
        tokens = self.tokenize(template.pattern)
        current = self.root
        
        for token in tokens:
            current = current.add_child(token)
        
        current.is_terminal = True
        current.templates.append(template)
    
    def _match_recursive(self, tokens: List[str], node: TrieNode, 
                        token_idx: int, captured_values: List[str]) -> List[Tuple[LogTemplate, List[str]]]:
        """
        Recursively match tokens against the trie.
        
        Returns list of (template, captured_values) tuples for all matches.
        """
        matches = []
        
        # If we've consumed all tokens and this is a terminal node
        if token_idx >= len(tokens):
            if node.is_terminal:
                for template in node.templates:
                    matches.append((template, captured_values.copy()))
            return matches
        
        current_token = tokens[token_idx]
        
        # Try exact match
        exact_child = node.get_child(current_token)
        if exact_child:
            matches.extend(self._match_recursive(
                tokens, exact_child, token_idx + 1, captured_values
            ))
        
        # Try wildcard match
        if node.wildcard_child:
            # Wildcard can match one or more tokens
            for end_idx in range(token_idx + 1, len(tokens) + 1):
                captured_value = " ".join(tokens[token_idx:end_idx])
                new_captured = captured_values + [captured_value]
                
                matches.extend(self._match_recursive(
                    tokens, node.wildcard_child, end_idx, new_captured
                ))
        
        return matches
    
    def match(self, log_line: str, level: Optional[str] = None) -> List[LogMatch]:
        """
        Match a log line against all templates in the trie.
        
        Args:
            log_line: The log line to match
            level: Optional log level filter
            
        Returns:
            List of LogMatch objects, sorted by specificity (most specific first)
        """
        tokens = self.tokenize(log_line.strip())
        if not tokens:
            return []
        
        # Get all potential matches
        raw_matches = self._match_recursive(tokens, self.root, 0, [])
        
        # Filter by log level if provided
        if level:
            raw_matches = [
                (template, values) for template, values in raw_matches
                if template.matches_level(level)
            ]
        
        # Convert to LogMatch objects with confidence scores
        log_matches = []
        for template, captured_values in raw_matches:
            confidence = self._calculate_confidence(template, tokens, captured_values)
            log_matches.append(LogMatch(
                template=template,
                confidence=confidence,
                extracted_values=captured_values
            ))
        
        # Sort by static token count (most specific first), then by confidence
        log_matches.sort(key=lambda m: (-m.template.static_token_count, -m.confidence))
        
        return log_matches
    
    def _calculate_confidence(self, template: LogTemplate, tokens: List[str], 
                            captured_values: List[str]) -> float:
        """
        Calculate matching confidence based on template specificity.
        
        Higher static token count = higher confidence.
        Also considers template pattern length vs actual token count.
        """
        if not tokens:
            return 0.0
        
        # Base confidence from static token ratio
        base_confidence = template.static_token_count / len(tokens)
        
        # Bonus for exact length match
        template_tokens = self.tokenize(template.pattern)
        if len(template_tokens) == len(tokens):
            base_confidence += 0.1
        
        # Penalty for very long captured values (likely over-matching)
        avg_captured_length = (
            sum(len(val.split()) for val in captured_values) / len(captured_values)
            if captured_values else 0
        )
        if avg_captured_length > 5:  # arbitrary threshold
            base_confidence -= 0.1
        
        return min(1.0, max(0.0, base_confidence))
    
    def get_best_match(self, log_line: str, level: Optional[str] = None) -> Optional[LogMatch]:
        """
        Get the best (most specific) match for a log line.
        
        Args:
            log_line: The log line to match
            level: Optional log level filter
            
        Returns:
            The best LogMatch or None if no matches found
        """
        matches = self.match(log_line, level)
        return matches[0] if matches else None
    
    def size(self) -> int:
        """Return the number of templates stored in the trie."""
        return self._count_templates(self.root)
    
    def _count_templates(self, node: TrieNode) -> int:
        """Recursively count templates in the trie."""
        count = len(node.templates)
        
        for child in node.children.values():
            count += self._count_templates(child)
        
        if node.wildcard_child:
            count += self._count_templates(node.wildcard_child)
        
        return count

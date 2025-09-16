"""
Template generation rules for different Java logging patterns.

Handles SLF4J, String.format, concatenation, and StringBuilder patterns.
"""

import re
from typing import List, Optional, Dict, Any, Tuple
from abc import ABC, abstractmethod
from .models import LogTemplate, LogLevel, SourceLocation, ExtractionContext


class TemplateRule(ABC):
    """Base class for template extraction rules."""
    
    @abstractmethod
    def can_handle(self, node: Any, context: ExtractionContext) -> bool:
        """Check if this rule can handle the given AST node."""
        pass
    
    @abstractmethod
    def extract_template(self, node: Any, context: ExtractionContext) -> List[str]:
        """Extract template patterns from the AST node."""
        pass
    
    def count_static_tokens(self, pattern: str) -> int:
        """Count static tokens in a template pattern."""
        tokens = pattern.split()
        return sum(1 for token in tokens if token != "<*>")


class SLF4JTemplateRule(TemplateRule):
    """
    Handles SLF4J logging patterns like:
    log.info("User {} logged in from {}", username, ipAddress)
    logger.error("Failed to process {} records", count)
    """
    
    def __init__(self):
        self.slf4j_methods = {'trace', 'debug', 'info', 'warn', 'error', 'log'}
        self.slf4j_loggers = {'log', 'logger', 'LOG', 'LOGGER'}
    
    def can_handle(self, node: Any, context: ExtractionContext) -> bool:
        """Check if node is an SLF4J logging call."""
        try:
            # Check if it's a method invocation
            if node.type != 'method_invocation':
                return False
            
            # Get the method name
            object_node = node.child_by_field_name('object')
            name_node = node.child_by_field_name('name')
            
            if not (object_node and name_node):
                return False
            
            # Check if object is a logger
            object_text = object_node.text.decode('utf-8')
            method_name = name_node.text.decode('utf-8')
            
            return (object_text in self.slf4j_loggers and 
                    method_name in self.slf4j_methods)
        except:
            return False
    
    def extract_template(self, node: Any, context: ExtractionContext) -> List[str]:
        """Extract SLF4J template pattern."""
        try:
            # Get arguments
            args_node = node.child_by_field_name('arguments')
            if not args_node:
                return []
            
            # Find the message argument
            # For most logging methods, it's the first argument
            # For logger.log(), it's typically the 4th argument (after marker, fqcn, level)
            message_arg = None
            
            # Get method name to determine argument position
            name_node = node.child_by_field_name('name')
            method_name = name_node.text.decode('utf-8') if name_node else ""
            
            # Collect all non-punctuation arguments
            args = []
            for child in args_node.children:
                if child.type in ['string_literal', 'binary_expression', 'method_invocation', 'identifier', 'null_literal']:
                    args.append(child)
            
            if method_name == 'log' and len(args) >= 4:
                # For logger.log(marker, fqcn, level, message, ...), message is 4th argument
                message_arg = args[3]
            elif len(args) >= 1:
                # For other methods, message is typically first argument
                message_arg = args[0]
            
            if not message_arg:
                return []
            
            # Extract message content based on argument type
            message = self._extract_message_from_node(message_arg)
            if not message:
                return []
            
            # Replace {} placeholders with <*>
            template = re.sub(r'\{\}', '<*>', message)
            
            # Handle escaped braces
            template = template.replace('\\{\\}', '{}')
            
            return [template]
            
        except Exception:
            return []
    
    def _extract_message_from_node(self, node: Any) -> str:
        """Extract message string from various node types."""
        if node.type == 'string_literal':
            # Simple string literal
            message = node.text.decode('utf-8')
            if message.startswith('"') and message.endswith('"'):
                return message[1:-1]
            elif message.startswith("'") and message.endswith("'"):
                return message[1:-1]
            return message
        
        elif node.type == 'binary_expression':
            # Handle string concatenation like "str1" + "str2"
            return self._extract_concatenated_string(node)
        
        elif node.type in ['identifier', 'field_access']:
            # Variables, field access - return special marker for slicing
            return "<!PLACEHOLDER!>"
        
        elif node.type == 'method_invocation':
            # Method calls - try to extract a meaningful pattern
            return self._extract_method_call_pattern(node)
        
        return ""
    
    def _extract_concatenated_string(self, node: Any) -> str:
        """Extract concatenated string from binary expression."""
        if node.type != 'binary_expression':
            return ""
        
        # Check if this is string concatenation (+)
        operator = node.child_by_field_name('operator')
        if not operator or operator.text.decode('utf-8') != '+':
            return ""
        
        left = node.child_by_field_name('left')
        right = node.child_by_field_name('right')
        
        if not (left and right):
            return ""
        
        # Recursively extract parts
        left_str = self._extract_message_from_node(left)
        right_str = self._extract_message_from_node(right)
        
        # Replace placeholder markers and combine
        if left_str or right_str:
            result_left = left_str.replace("<!PLACEHOLDER!>", "<*>") if left_str else "<*>"
            result_right = right_str.replace("<!PLACEHOLDER!>", "<*>") if right_str else "<*>"
            return result_left + result_right
        
        return ""
    
    def _extract_method_call_pattern(self, node: Any) -> str:
        """Extract pattern from method call."""
        try:
            # Get method name
            name_node = node.child_by_field_name('name')
            if not name_node:
                return "<!PLACEHOLDER!>"
            
            method_name = name_node.text.decode('utf-8')
            
            # Handle common patterns
            if method_name in ['addPrefix', 'addSuffix', 'format', 'toString']:
                # For these methods, we can try to create a meaningful pattern
                args_node = node.child_by_field_name('arguments')
                if args_node:
                    # Look for string literals in arguments
                    for child in args_node.children:
                        if child.type == 'identifier':
                            # If method takes a variable, create a placeholder pattern
                            return f"<method:{method_name}(<*>)>"
                        elif child.type == 'string_literal':
                            # If method takes a literal, include it
                            content = child.text.decode('utf-8')
                            if content.startswith('"') and content.endswith('"'):
                                content = content[1:-1]
                            return f"<method:{method_name}({content})>"
                
                # Default pattern for method calls
                return f"<method:{method_name}(<*>)>"
            
            # For unknown methods, return generic placeholder
            return "<!PLACEHOLDER!>"
        
        except Exception:
            return "<!PLACEHOLDER!>"


class StringFormatTemplateRule(TemplateRule):
    """
    Handles String.format patterns like:
    String.format("User %s logged in from %s", username, ipAddress)
    String.format("Processing %d records", count)
    """
    
    def can_handle(self, node: Any, context: ExtractionContext) -> bool:
        """Check if node is a String.format call."""
        try:
            if node.type != 'method_invocation':
                return False
            
            object_node = node.child_by_field_name('object')
            name_node = node.child_by_field_name('name')
            
            if not (object_node and name_node):
                return False
            
            object_text = object_node.text.decode('utf-8')
            method_name = name_node.text.decode('utf-8')
            
            return object_text == 'String' and method_name == 'format'
        except:
            return False
    
    def extract_template(self, node: Any, context: ExtractionContext) -> List[str]:
        """Extract String.format template pattern."""
        try:
            args_node = node.child_by_field_name('arguments')
            if not args_node:
                return []
            
            # First argument is the format string
            first_arg = None
            for child in args_node.children:
                if child.type == 'string_literal':
                    first_arg = child
                    break
            
            if not first_arg:
                return []
            
            # Extract string content
            message = first_arg.text.decode('utf-8')
            if message.startswith('"') and message.endswith('"'):
                message = message[1:-1]
            elif message.startswith("'") and message.endswith("'"):
                message = message[1:-1]
            
            # Replace format specifiers with <*>
            # Handle common Java format specifiers
            format_patterns = [
                r'%[+-]?[0-9]*\.?[0-9]*[diouxXeEfFgGaAcsSn]',  # Standard format specifiers
                r'%[+-]?[0-9]*\.?[0-9]*[diouxXeEfFgGaAcsSn]',
            ]
            
            template = message
            for pattern in format_patterns:
                template = re.sub(pattern, '<*>', template)
            
            return [template]
            
        except Exception:
            return []


class ConcatenationTemplateRule(TemplateRule):
    """
    Handles string concatenation patterns like:
    log.info("User " + username + " logged in")
    logger.error("Error: " + ex.getMessage())
    """
    
    def can_handle(self, node: Any, context: ExtractionContext) -> bool:
        """Check if node contains string concatenation."""
        try:
            return self._has_string_concatenation(node)
        except:
            return False
    
    def _has_string_concatenation(self, node: Any) -> bool:
        """Recursively check for string concatenation."""
        if node.type == 'binary_expression':
            operator = node.child_by_field_name('operator')
            if operator and operator.text.decode('utf-8') == '+':
                left = node.child_by_field_name('left')
                right = node.child_by_field_name('right')
                return (self._is_string_like(left) or 
                        self._is_string_like(right) or
                        self._has_string_concatenation(left) or
                        self._has_string_concatenation(right))
        return False
    
    def _is_string_like(self, node: Any) -> bool:
        """Check if node represents a string or string-like expression."""
        if not node:
            return False
        
        return node.type in ['string_literal', 'identifier', 
                           'method_invocation', 'field_access']
    
    def extract_template(self, node: Any, context: ExtractionContext) -> List[str]:
        """Extract concatenation template pattern."""
        try:
            template_parts = self._extract_concatenation_parts(node)
            if template_parts:
                return [' '.join(template_parts)]
            return []
        except Exception:
            return []
    
    def _extract_concatenation_parts(self, node: Any) -> List[str]:
        """Extract parts of a concatenation expression."""
        if node.type == 'string_literal':
            content = node.text.decode('utf-8')
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]
            elif content.startswith("'") and content.endswith("'"):
                content = content[1:-1]
            return [content] if content.strip() else []
        
        elif node.type == 'binary_expression':
            operator = node.child_by_field_name('operator')
            if operator and operator.text.decode('utf-8') == '+':
                left = node.child_by_field_name('left')
                right = node.child_by_field_name('right')
                
                left_parts = self._extract_concatenation_parts(left)
                right_parts = self._extract_concatenation_parts(right)
                
                # Join adjacent string literals, replace variables with <*>
                result = []
                result.extend(left_parts)
                result.extend(right_parts)
                
                return result
        
        else:
            # Variable, method call, etc. - replace with placeholder
            return ['<*>']


class StringBuilderTemplateRule(TemplateRule):
    """
    Handles StringBuilder patterns like:
    new StringBuilder().append("User ").append(username).append(" logged in").toString()
    sb.append("Error: ").append(error.getMessage())
    """
    
    def can_handle(self, node: Any, context: ExtractionContext) -> bool:
        """Check if node is a StringBuilder chain."""
        try:
            return self._is_stringbuilder_chain(node)
        except:
            return False
    
    def _is_stringbuilder_chain(self, node: Any) -> bool:
        """Check if node represents a StringBuilder method chain."""
        if node.type == 'method_invocation':
            name_node = node.child_by_field_name('name')
            if name_node:
                method_name = name_node.text.decode('utf-8')
                if method_name in ['append', 'toString']:
                    # Check if the object is StringBuilder or another append call
                    object_node = node.child_by_field_name('object')
                    if object_node:
                        object_text = object_node.text.decode('utf-8')
                        return ('StringBuilder' in object_text or 
                                self._is_stringbuilder_chain(object_node))
        return False
    
    def extract_template(self, node: Any, context: ExtractionContext) -> List[str]:
        """Extract StringBuilder template pattern."""
        try:
            parts = self._extract_stringbuilder_parts(node)
            if parts:
                return [' '.join(parts)]
            return []
        except Exception:
            return []
    
    def _extract_stringbuilder_parts(self, node: Any) -> List[str]:
        """Extract parts from StringBuilder chain."""
        if node.type == 'method_invocation':
            name_node = node.child_by_field_name('name')
            if name_node:
                method_name = name_node.text.decode('utf-8')
                
                if method_name == 'append':
                    # Get the argument
                    args_node = node.child_by_field_name('arguments')
                    if args_node:
                        for child in args_node.children:
                            if child.type == 'string_literal':
                                content = child.text.decode('utf-8')
                                if content.startswith('"') and content.endswith('"'):
                                    content = content[1:-1]
                                elif content.startswith("'") and content.endswith("'"):
                                    content = content[1:-1]
                                
                                # Get parts from the object (previous chain)
                                object_node = node.child_by_field_name('object')
                                object_parts = []
                                if object_node:
                                    object_parts = self._extract_stringbuilder_parts(object_node)
                                
                                return object_parts + [content] if content.strip() else object_parts
                            else:
                                # Non-string argument, replace with placeholder
                                object_node = node.child_by_field_name('object')
                                object_parts = []
                                if object_node:
                                    object_parts = self._extract_stringbuilder_parts(object_node)
                                return object_parts + ['<*>']
                
                elif method_name == 'toString':
                    # Just pass through to the object
                    object_node = node.child_by_field_name('object')
                    if object_node:
                        return self._extract_stringbuilder_parts(object_node)
        
        return []


class LogTemplateBuilder:
    """
    Main builder that coordinates all template extraction rules.
    """
    
    def __init__(self):
        self.rules = [
            SLF4JTemplateRule(),
            StringFormatTemplateRule(),
            ConcatenationTemplateRule(),
            StringBuilderTemplateRule(),
        ]
    
    def extract_templates(self, node: Any, context: ExtractionContext) -> List[LogTemplate]:
        """
        Extract all possible templates from an AST node.
        
        Args:
            node: Tree-sitter AST node
            context: Extraction context with file/class/method info
            
        Returns:
            List of extracted LogTemplate objects
        """
        templates = []
        
        for rule in self.rules:
            if rule.can_handle(node, context):
                try:
                    patterns = rule.extract_template(node, context)
                    for i, pattern in enumerate(patterns):
                        if pattern.strip():
                            # Determine log level from context or rule
                            level = self._extract_log_level(node, context)
                            
                            # Create unique template ID
                            template_id = self._create_template_id(
                                context, pattern, i
                            )
                            
                            # Create source location
                            location = SourceLocation(
                                file_path=context.file_path,
                                class_name=context.class_name,
                                method_name=context.method_name,
                                line_number=context.current_line
                            )
                            
                            # Count static tokens
                            static_count = rule.count_static_tokens(pattern)
                            
                            template = LogTemplate(
                                template_id=template_id,
                                pattern=pattern,
                                static_token_count=static_count,
                                location=location,
                                level=level,
                                branch_variant=i
                            )
                            
                            templates.append(template)
                            
                except Exception as e:
                    # Log the error but continue processing
                    print(f"Warning: Error extracting template: {e}")
                    continue
        
        return templates
    
    def _extract_log_level(self, node: Any, context: ExtractionContext) -> LogLevel:
        """Extract log level from the logging call."""
        try:
            if node.type == 'method_invocation':
                name_node = node.child_by_field_name('name')
                if name_node:
                    method_name = name_node.text.decode('utf-8').lower()
                    try:
                        return LogLevel(method_name)
                    except ValueError:
                        pass
        except:
            pass
        
        return LogLevel.UNKNOWN
    
    def _create_template_id(self, context: ExtractionContext, pattern: str, variant: int) -> str:
        """Create a unique template identifier."""
        import hashlib
        
        # Create a hash from file path, line number, pattern, and variant
        content = f"{context.file_path}:{context.current_line}:{pattern}:{variant}"
        hash_obj = hashlib.md5(content.encode('utf-8'))
        return hash_obj.hexdigest()[:16]

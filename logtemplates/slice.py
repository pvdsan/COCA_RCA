"""
Simple intraprocedural backward slicing for message variable tracking.

Performs reaching definitions analysis within a single method to track
how log message variables are constructed.
"""

from typing import Dict, List, Set, Optional, Any, Tuple
from collections import defaultdict, deque
from .models import ExtractionContext


class Variable:
    """Represents a variable and its definition."""
    
    def __init__(self, name: str, node: Any, line: int):
        self.name = name
        self.node = node  # AST node where variable is defined
        self.line = line
        self.definition_type = self._get_definition_type(node)
    
    def _get_definition_type(self, node: Any) -> str:
        """Determine the type of variable definition."""
        if not node:
            return "unknown"
        
        node_type = node.type
        if node_type == "variable_declarator":
            return "declaration"
        elif node_type == "assignment_expression":
            return "assignment"
        elif node_type == "parameter":
            return "parameter"
        else:
            return "unknown"
    
    def __str__(self) -> str:
        return f"{self.name}@{self.line}({self.definition_type})"


class SliceNode:
    """Node in the program slice representing a statement."""
    
    def __init__(self, node: Any, line: int, variables_used: Set[str], variables_defined: Set[str]):
        self.node = node
        self.line = line
        self.variables_used = variables_used
        self.variables_defined = variables_defined
        self.predecessors: Set[int] = set()
        self.successors: Set[int] = set()
    
    def __str__(self) -> str:
        return f"Line {self.line}: uses {self.variables_used}, defines {self.variables_defined}"


class IntraproceduralSlicer:
    """
    Performs intraprocedural backward slicing to track variable definitions.
    
    Given a logging statement that uses a variable (e.g., log.warn(msg)),
    this slicer finds all statements that contribute to the definition
    of that variable within the same method.
    """
    
    def __init__(self):
        self.slice_nodes: Dict[int, SliceNode] = {}
        self.variable_definitions: Dict[str, List[Variable]] = defaultdict(list)
        self.reaching_definitions: Dict[int, Dict[str, Set[Variable]]] = defaultdict(lambda: defaultdict(set))
    
    def slice_variable(self, method_node: Any, target_variable: str, target_line: int, context: ExtractionContext) -> List[str]:
        """
        Perform backward slice for a target variable.
        
        Args:
            method_node: AST node of the method containing the target
            target_variable: Name of the variable to slice
            target_line: Line number where variable is used
            context: Extraction context
            
        Returns:
            List of template patterns that could be the value of target_variable
        """
        # Build the slice representation
        self._build_slice_nodes(method_node)
        
        # Perform reaching definitions analysis
        self._compute_reaching_definitions()
        
        # Backward slice from the target
        slice_lines = self._backward_slice(target_variable, target_line)
        
        # Extract patterns from sliced statements
        patterns = self._extract_patterns_from_slice(slice_lines, target_variable)
        
        # If no patterns found, check if it's a method parameter or class constant
        if not patterns:
            if self._is_method_parameter(method_node, target_variable):
                return [f"<param:{target_variable}>"]
            elif self._is_class_constant(method_node, target_variable):
                constant_value = self._get_class_constant_value(method_node, target_variable)
                if constant_value:
                    return [constant_value]
                else:
                    return [f"<const:{target_variable}>"]
            else:
                # Fallback for unknown variables
                return ["<*>"]
        
        return patterns
    
    def _is_method_parameter(self, method_node: Any, variable_name: str) -> bool:
        """Check if a variable is a method parameter."""
        try:
            parameters_node = method_node.child_by_field_name('parameters')
            if not parameters_node:
                return False
            
            # Look through parameter list
            for child in parameters_node.children:
                if child.type == 'formal_parameter':
                    name_node = child.child_by_field_name('name')
                    if name_node and name_node.text.decode('utf-8') == variable_name:
                        return True
            
            return False
        except Exception:
            return False
    
    def _is_class_constant(self, method_node: Any, variable_name: str) -> bool:
        """Check if a variable is a class-level constant (static final field)."""
        try:
            # Navigate up to find the class containing this method
            class_node = self._find_containing_class(method_node)
            if not class_node:
                return False
            
            # Look for field declarations in the class
            class_body = None
            for child in class_node.children:
                if child.type == 'class_body':
                    class_body = child
                    break
            
            if not class_body:
                return False
            
            # Search for static final fields
            for member in class_body.children:
                if member.type == 'field_declaration':
                    # Check if it's static final
                    is_static = False
                    is_final = False
                    
                    for child in member.children:
                        if child.type == 'modifiers':
                            for modifier in child.children:
                                if modifier.text.decode('utf-8') == 'static':
                                    is_static = True
                                elif modifier.text.decode('utf-8') == 'final':
                                    is_final = True
                    
                    # If it's a static final field, check the variable name
                    if is_static and is_final:
                        for child in member.children:
                            if child.type == 'variable_declarator':
                                name_node = child.child_by_field_name('name')
                                if name_node and name_node.text.decode('utf-8') == variable_name:
                                    return True
            
            return False
        except Exception:
            return False
    
    def _get_class_constant_value(self, method_node: Any, variable_name: str) -> str:
        """Get the value of a class constant if it's a simple string or pattern."""
        try:
            # Navigate up to find the class containing this method
            class_node = self._find_containing_class(method_node)
            if not class_node:
                return ""
            
            # Look for the field declaration
            class_body = None
            for child in class_node.children:
                if child.type == 'class_body':
                    class_body = child
                    break
            
            if not class_body:
                return ""
            
            # Search for the specific constant
            for member in class_body.children:
                if member.type == 'field_declaration':
                    for child in member.children:
                        if child.type == 'variable_declarator':
                            name_node = child.child_by_field_name('name')
                            value_node = child.child_by_field_name('value')
                            
                            if (name_node and name_node.text.decode('utf-8') == variable_name and value_node):
                                # Try to extract the constant value
                                return self._node_to_pattern(value_node)
            
            return ""
        except Exception:
            return ""
    
    def _find_containing_class(self, method_node: Any) -> Any:
        """Find the class node that contains the given method."""
        try:
            current = method_node.parent
            while current:
                if current.type == 'class_declaration':
                    return current
                current = current.parent
            return None
        except Exception:
            return None
    
    def _build_slice_nodes(self, method_node: Any) -> None:
        """Build slice nodes from the method AST."""
        self.slice_nodes.clear()
        self.variable_definitions.clear()
        
        # Traverse the method to find all statements
        for node in self._traverse_statements(method_node):
            line = self._get_line_number(node)
            
            # Analyze variable usage and definitions
            used_vars = self._get_variables_used(node)
            defined_vars = self._get_variables_defined(node)
            
            # Create slice node
            slice_node = SliceNode(node, line, used_vars, defined_vars)
            self.slice_nodes[line] = slice_node
            
            # Record variable definitions
            for var_name in defined_vars:
                variable = Variable(var_name, node, line)
                self.variable_definitions[var_name].append(variable)
    
    def _traverse_statements(self, node: Any) -> List[Any]:
        """Traverse AST to find all statement nodes."""
        statements = []
        
        def visit(n):
            if self._is_statement(n):
                statements.append(n)
                
                # For blocks and control structures, also recurse into their children
                # to find nested statements
                if n.type in ['block', 'if_statement', 'while_statement', 'for_statement']:
                    for child in n.children if hasattr(n, 'children') else []:
                        visit(child)
            else:
                # If not a statement, keep looking deeper
                for child in n.children if hasattr(n, 'children') else []:
                    visit(child)
        
        visit(node)
        return statements
    
    def _is_statement(self, node: Any) -> bool:
        """Check if node represents a statement."""
        statement_types = {
            'expression_statement', 'local_variable_declaration',
            'assignment_expression', 'method_invocation',
            'if_statement', 'while_statement', 'for_statement',
            'return_statement', 'throw_statement', 'block'
        }
        return node.type in statement_types
    
    def _get_line_number(self, node: Any) -> int:
        """Get line number from AST node."""
        try:
            return node.start_point[0] + 1  # Tree-sitter uses 0-based line numbers
        except:
            return 0
    
    def _get_variables_used(self, node: Any) -> Set[str]:
        """Extract variables used in a statement."""
        used_vars = set()
        
        def visit(n):
            if n.type == 'identifier':
                # Check if this identifier is being used (not defined)
                parent = n.parent
                if parent and not self._is_definition_context(n, parent):
                    used_vars.add(n.text.decode('utf-8'))
            
            for child in n.children if hasattr(n, 'children') else []:
                visit(child)
        
        visit(node)
        return used_vars
    
    def _get_variables_defined(self, node: Any) -> Set[str]:
        """Extract variables defined in a statement."""
        defined_vars = set()
        
        if node.type == 'local_variable_declaration':
            # Find variable declarators
            for child in node.children:
                if child.type == 'variable_declarator':
                    name_node = child.child_by_field_name('name')
                    if name_node:
                        defined_vars.add(name_node.text.decode('utf-8'))
        
        elif node.type == 'assignment_expression':
            # Left side of assignment
            left = node.child_by_field_name('left')
            if left and left.type == 'identifier':
                defined_vars.add(left.text.decode('utf-8'))
        
        elif node.type == 'expression_statement':
            # Check if this contains a variable declaration or assignment
            for child in node.children:
                child_defined = self._get_variables_defined(child)
                defined_vars.update(child_defined)
        
        return defined_vars
    
    def _is_definition_context(self, identifier_node: Any, parent_node: Any) -> bool:
        """Check if identifier is in a definition context."""
        if parent_node.type == 'variable_declarator':
            # Check if this is the name being declared
            name_field = parent_node.child_by_field_name('name')
            return name_field == identifier_node
        
        elif parent_node.type == 'assignment_expression':
            # Check if this is the left side of assignment
            left_field = parent_node.child_by_field_name('left')
            return left_field == identifier_node
        
        return False
    
    def _compute_reaching_definitions(self) -> None:
        """Compute reaching definitions for each statement."""
        self.reaching_definitions.clear()
        
        # Initialize with empty sets
        for line in self.slice_nodes:
            self.reaching_definitions[line] = defaultdict(set)
        
        # Simple sequential flow: each statement can reach the next
        # This is a simplified approach for intraprocedural analysis
        sorted_lines = sorted(self.slice_nodes.keys())
        
        for i, line in enumerate(sorted_lines):
            slice_node = self.slice_nodes[line]
            
            # Start with definitions from previous line
            if i > 0:
                prev_line = sorted_lines[i-1]
                for var, defs in self.reaching_definitions[prev_line].items():
                    self.reaching_definitions[line][var].update(defs)
            
            # Add definitions from current line
            for var in slice_node.variables_defined:
                # Kill previous definitions of this variable
                self.reaching_definitions[line][var] = set()
                # Add new definition
                for variable in self.variable_definitions[var]:
                    if variable.line == line:
                        self.reaching_definitions[line][var].add(variable)
    
    def _backward_slice(self, target_variable: str, target_line: int) -> Set[int]:
        """
        Perform backward slice starting from target variable usage.
        
        Returns set of line numbers that contribute to the target variable.
        """
        slice_lines = set()
        worklist = deque([(target_variable, target_line)])
        processed = set()
        
        while worklist:
            var_name, line = worklist.popleft()
            
            if (var_name, line) in processed:
                continue
            processed.add((var_name, line))
            
            # Find definitions of this variable that reach this line
            if line in self.reaching_definitions:
                reaching_defs = self.reaching_definitions[line].get(var_name, set())
                
                for definition in reaching_defs:
                    def_line = definition.line
                    slice_lines.add(def_line)
                    
                    # Add variables used in the definition to worklist
                    if def_line in self.slice_nodes:
                        slice_node = self.slice_nodes[def_line]
                        for used_var in slice_node.variables_used:
                            worklist.append((used_var, def_line))
        
        return slice_lines
    
    def _extract_patterns_from_slice(self, slice_lines: Set[int], target_variable: str) -> List[str]:
        """
        Extract template patterns from the sliced statements.
        
        This analyzes the sliced statements to determine possible values
        of the target variable and converts them to template patterns.
        """
        patterns = []
        
        for line in sorted(slice_lines):
            if line not in self.slice_nodes:
                continue
            
            slice_node = self.slice_nodes[line]
            
            # Check if this statement defines our target variable
            if target_variable in slice_node.variables_defined:
                pattern = self._extract_pattern_from_definition(slice_node.node, target_variable)
                if pattern:
                    patterns.append(pattern)
        
        return patterns
    
    def _extract_pattern_from_definition(self, node: Any, variable_name: str) -> Optional[str]:
        """Extract template pattern from a variable definition statement."""
        try:
            if node.type == 'local_variable_declaration':
                # Find the variable declarator
                for child in node.children:
                    if child.type == 'variable_declarator':
                        name_node = child.child_by_field_name('name')
                        value_node = child.child_by_field_name('value')
                        
                        if (name_node and 
                            name_node.text.decode('utf-8') == variable_name and
                            value_node):
                            pattern = self._node_to_pattern(value_node)
                            return pattern
            
            elif node.type == 'assignment_expression':
                left = node.child_by_field_name('left')
                right = node.child_by_field_name('right')
                
                if (left and right and 
                    left.type == 'identifier' and
                    left.text.decode('utf-8') == variable_name):
                    pattern = self._node_to_pattern(right)
                    return pattern
            
            elif node.type == 'expression_statement':
                # Check if this contains a variable declaration or assignment
                for child in node.children:
                    result = self._extract_pattern_from_definition(child, variable_name)
                    if result:
                        return result
        
        except Exception as e:
            pass
        
        return None
    
    def _node_to_pattern(self, node: Any) -> str:
        """Convert an AST node to a template pattern."""
        try:
            if node.type == 'string_literal':
                content = node.text.decode('utf-8')
                if content.startswith('"') and content.endswith('"'):
                    return content[1:-1]
                elif content.startswith("'") and content.endswith("'"):
                    return content[1:-1]
                return content
            
            elif node.type == 'binary_expression':
                # Handle string concatenation
                operator = node.child_by_field_name('operator')
                if operator and operator.text.decode('utf-8') == '+':
                    left = node.child_by_field_name('left')
                    right = node.child_by_field_name('right')
                    
                    left_pattern = self._node_to_pattern(left) if left else "<*>"
                    right_pattern = self._node_to_pattern(right) if right else "<*>"
                    
                    return f"{left_pattern} {right_pattern}"
            
            elif node.type == 'method_invocation':
                # Could be StringBuilder.toString(), String.format(), etc.
                return self._method_call_to_pattern(node)
            
            else:
                # Unknown expression, treat as placeholder
                return "<*>"
        
        except Exception:
            return "<*>"
    
    def _method_call_to_pattern(self, node: Any) -> str:
        """Convert method call to template pattern."""
        try:
            object_node = node.child_by_field_name('object')
            name_node = node.child_by_field_name('name')
            
            if not name_node:
                return "<*>"
            
            object_text = object_node.text.decode('utf-8') if object_node else ""
            method_name = name_node.text.decode('utf-8')
            
            if method_name == 'toString':
                # Could be StringBuilder.toString()
                return self._node_to_pattern(object_node)
            
            elif method_name == 'format' and object_text == 'String':
                # String.format call
                args_node = node.child_by_field_name('arguments')
                if args_node:
                    # First argument is format string - look through all children
                    for child in args_node.children:
                        if child.type == 'string_literal':
                            format_str = child.text.decode('utf-8')
                            if format_str.startswith('"') and format_str.endswith('"'):
                                format_str = format_str[1:-1]
                            elif format_str.startswith("'") and format_str.endswith("'"):
                                format_str = format_str[1:-1]
                            
                            # Replace format specifiers with placeholders
                            import re
                            # Handle common Java format specifiers: %s, %d, %f, etc.
                            pattern = re.sub(r'%[+-]?[0-9]*\.?[0-9]*[diouxXeEfFgGaAcsSn]', '<*>', format_str)
                            return pattern
                        elif child.type == 'binary_expression':
                            # Handle concatenated format string
                            concatenated_str = self._extract_concatenated_format_string(child)
                            if concatenated_str:
                                import re
                                pattern = re.sub(r'%[+-]?[0-9]*\.?[0-9]*[diouxXeEfFgGaAcsSn]', '<*>', concatenated_str)
                                return pattern
            
            # For other method calls, create a meaningful pattern
            # This helps identify what kind of method call generated the log message
            if object_text and method_name:
                return f"<method:{object_text}.{method_name}()>"
            elif method_name:
                return f"<method:{method_name}()>"
            else:
                return "<*>"
        
        except Exception as e:
            return "<*>"
    
    def _extract_concatenated_format_string(self, node: Any) -> str:
        """Extract concatenated string from binary expression for format strings."""
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
        left_str = self._extract_string_content(left)
        right_str = self._extract_string_content(right)
        
        # Combine the strings
        if left_str is not None and right_str is not None:
            return left_str + right_str
        elif left_str is not None:
            return left_str
        elif right_str is not None:
            return right_str
        
        return ""
    
    def _extract_string_content(self, node: Any) -> str:
        """Extract string content from various node types."""
        if node.type == 'string_literal':
            content = node.text.decode('utf-8')
            if content.startswith('"') and content.endswith('"'):
                return content[1:-1]
            elif content.startswith("'") and content.endswith("'"):
                return content[1:-1]
            return content
        elif node.type == 'binary_expression':
            # Recursively handle nested concatenation
            return self._extract_concatenated_format_string(node)
        else:
            # Non-string node, can't extract
            return None

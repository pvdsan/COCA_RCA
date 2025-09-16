"""
Java log template extractor using tree-sitter.

Parses Java source files to find logging calls and extract template patterns
with support for intraprocedural backward slicing and branch-aware extraction.
"""

import os
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
import tree_sitter_languages
from tqdm import tqdm

from .models import LogTemplate, LogLevel, SourceLocation, ExtractionContext
from .templating import LogTemplateBuilder
from .slice import IntraproceduralSlicer
from .io_utils import CacheManager, RepositoryWalker


class JavaLogExtractor:
    """
    Main extractor for Java logging templates.
    
    Uses tree-sitter to parse Java files and extract logging patterns
    with support for various logging frameworks and patterns.
    """
    
    def __init__(self, 
                 cache_dir: str = ".logtemplates_cache",
                 max_branch_variants: int = 16,
                 parallel_workers: int = None):
        """
        Initialize the Java log extractor.
        
        Args:
            cache_dir: Directory for caching extracted templates
            max_branch_variants: Maximum variants per logging site to prevent explosion
            parallel_workers: Number of parallel workers for file processing
        """
        self.cache_manager = CacheManager(cache_dir)
        self.template_builder = LogTemplateBuilder()
        self.slicer = IntraproceduralSlicer()
        self.max_branch_variants = max_branch_variants
        self.parallel_workers = parallel_workers or min(32, (os.cpu_count() or 1) + 4)
        
        # Initialize tree-sitter parser
        self.parser = tree_sitter_languages.get_parser("java")
        
        # Logging method patterns
        self.logging_methods = {
            'trace', 'debug', 'info', 'warn', 'error', 'fatal',
            'log', 'print', 'println'
        }
        
        # Logger object names
        self.logger_names = {
            'log', 'logger', 'LOG', 'LOGGER', 'log4j', 'slf4j'
        }
    
    def extract_from_repository(self, 
                               repo_path: str,
                               include_patterns: List[str] = None,
                               exclude_patterns: List[str] = None,
                               use_cache: bool = True) -> List[LogTemplate]:
        """
        Extract log templates from entire repository.
        
        Args:
            repo_path: Path to repository root
            include_patterns: File patterns to include (default: ["*.java"])
            exclude_patterns: File patterns to exclude
            use_cache: Whether to use incremental caching
            
        Returns:
            List of extracted LogTemplate objects
        """
        print(f"Extracting log templates from repository: {repo_path}")
        
        # Set up repository walker
        walker = RepositoryWalker(
            repo_path, 
            include_patterns or ["*.java"],
            exclude_patterns or []
        )
        
        # Get all files to process
        all_files = list(walker.walk_files())
        print(f"Found {len(all_files)} Java files to process")
        
        if not all_files:
            print("No Java files found to process")
            return []
        
        # Filter files based on cache if enabled
        files_to_process = []
        cached_templates = []
        
        if use_cache:
            cached_templates = self.cache_manager.get_cached_templates()
            print(f"Loaded {len(cached_templates)} templates from cache")
            
            for file_path in all_files:
                if not self.cache_manager.is_file_cached(str(file_path)):
                    files_to_process.append(file_path)
        else:
            files_to_process = all_files
        
        print(f"Processing {len(files_to_process)} files (cached: {len(all_files) - len(files_to_process)})")
        
        # Process files in parallel
        new_templates = []
        if files_to_process:
            new_templates = self._process_files_parallel(files_to_process)
        
        # Combine with cached templates
        all_templates = cached_templates + new_templates
        
        # Update cache with incremental approach
        if use_cache and new_templates:
            # Only save new templates to cache, don't resave existing ones
            existing_cached_templates = self.cache_manager.get_cached_templates()
            
            # Filter out any new templates that might already exist (deduplication)
            new_template_ids = {t.template_id for t in new_templates}
            existing_template_ids = {t.template_id for t in existing_cached_templates}
            truly_new_templates = [t for t in new_templates if t.template_id not in existing_template_ids]
            
            if truly_new_templates:
                # Save the complete set: existing + truly new
                final_templates = existing_cached_templates + truly_new_templates
                self.cache_manager.save_templates(final_templates)
            
            # Mark processed files
            for file_path in files_to_process:
                self.cache_manager.mark_file_processed(str(file_path))
        
        print(f"Extracted {len(all_templates)} total templates ({len(new_templates)} new)")
        return all_templates
    
    def extract_from_file(self, file_path: str) -> List[LogTemplate]:
        """
        Extract log templates from a single Java file.
        
        Args:
            file_path: Path to Java source file
            
        Returns:
            List of extracted LogTemplate objects
        """
        return self._process_single_file(Path(file_path))
    
    def _process_files_parallel(self, file_paths: List[Path]) -> List[LogTemplate]:
        """Process multiple files in parallel."""
        all_templates = []
        
        with ProcessPoolExecutor(max_workers=self.parallel_workers) as executor:
            # Submit all files for processing
            future_to_file = {
                executor.submit(self._process_single_file_wrapper, str(file_path)): file_path
                for file_path in file_paths
            }
            
            # Collect results with progress bar
            with tqdm(total=len(file_paths), desc="Processing files") as pbar:
                for future in as_completed(future_to_file):
                    file_path = future_to_file[future]
                    try:
                        templates = future.result()
                        all_templates.extend(templates)
                    except Exception as e:
                        print(f"Error processing {file_path}: {e}")
                    finally:
                        pbar.update(1)
        
        return all_templates
    
    @staticmethod
    def _process_single_file_wrapper(file_path_str: str) -> List[LogTemplate]:
        """Wrapper for single file processing (needed for multiprocessing)."""
        extractor = JavaLogExtractor()
        return extractor._process_single_file(Path(file_path_str))
    
    def _process_single_file(self, file_path: Path) -> List[LogTemplate]:
        """Process a single Java file and extract templates."""
        try:
            # Read file content
            with open(file_path, 'r', encoding='utf-8') as f:
                source_code = f.read()
            
            # Parse with tree-sitter
            tree = self.parser.parse(bytes(source_code, 'utf8'))
            
            # Extract templates
            context = ExtractionContext(file_path=str(file_path))
            templates = self._extract_from_ast(tree.root_node, context, source_code)
            
            return templates
            
        except Exception as e:
            print(f"Error processing file {file_path}: {e}")
            return []
    
    def _extract_from_ast(self, root_node, context: ExtractionContext, source_code: str) -> List[LogTemplate]:
        """Extract templates from AST tree."""
        templates = []
        
        # Find all classes (including anonymous and nested classes)
        for class_node in self._find_nodes_by_type(root_node, 'class_declaration'):
            class_name = self._get_class_name(class_node)
            class_context = context.copy()
            class_context.class_name = class_name
            
            # Extract from this class
            class_templates = self._extract_from_class(class_node, class_context)
            templates.extend(class_templates)
        
        # Also look for anonymous classes and other method containers
        for method_node in self._find_all_methods(root_node):
            # For methods not in a named class, use a generic context
            if not any(self._is_inside_class(method_node, class_node) 
                      for class_node in self._find_nodes_by_type(root_node, 'class_declaration')):
                method_name = self._get_method_name(method_node)
                method_context = context.copy()
                method_context.method_name = method_name
                
                # Extract templates from this method
                method_templates = self._extract_from_method(method_node, method_context)
                templates.extend(method_templates)
        
        return templates
    
    def _extract_from_class(self, class_node, class_context: ExtractionContext) -> List[LogTemplate]:
        """Extract templates from all methods in a class, including nested structures."""
        templates = []
        
        # Find all methods in this class (including nested ones)
        for method_node in self._find_all_methods(class_node):
            method_name = self._get_method_name(method_node)
            method_context = class_context.copy()
            method_context.method_name = method_name
            
            # Extract templates from this method
            method_templates = self._extract_from_method(method_node, method_context)
            templates.extend(method_templates)
        
        return templates
    
    def _find_all_methods(self, root_node) -> List:
        """Find all method declarations, including those in anonymous classes."""
        methods = []
        
        def visit(node):
            if node.type == 'method_declaration':
                methods.append(node)
            # Recurse into children
            for child in node.children:
                visit(child)
        
        visit(root_node)
        return methods
    
    def _is_inside_class(self, method_node, class_node) -> bool:
        """Check if a method node is inside a specific class node."""
        current = method_node.parent
        while current:
            if current == class_node:
                return True
            current = current.parent
        return False
    
    def _extract_from_method(self, method_node, context: ExtractionContext) -> List[LogTemplate]:
        """Extract templates from a single method."""
        templates = []
        
        # Find all potential logging calls
        logging_calls = self._find_logging_calls(method_node)
        
        for call_node in logging_calls:
            # Find the most specific method context for this logging call
            specific_method = self._find_innermost_method_for_call(call_node, method_node)
            
            call_context = context.copy()
            call_context.current_line = self._get_line_number(call_node)
            
            # Update method name to the most specific one
            if specific_method != method_node:
                specific_method_name = self._get_method_name(specific_method)
                if specific_method_name:
                    call_context.method_name = specific_method_name
            
            # Try direct template extraction
            direct_templates = self.template_builder.extract_templates(call_node, call_context)
            
            if direct_templates:
                templates.extend(direct_templates)
            else:
                # Try backward slicing for indirect patterns using the specific method context
                indirect_templates = self._extract_with_slicing(call_node, specific_method, call_context)
                templates.extend(indirect_templates)
        
        # Limit branch variants to prevent explosion
        templates = self._limit_branch_variants(templates)
        
        return templates
    
    def _find_innermost_method_for_call(self, call_node, outer_method_node):
        """Find the innermost method that contains the logging call."""
        # Start from the call node and walk up to find the nearest method declaration
        current = call_node.parent
        innermost_method = outer_method_node  # Default to outer method
        
        while current and current != outer_method_node.parent:
            if current.type == 'method_declaration':
                # This is a more specific method than the outer one
                innermost_method = current
                break
            current = current.parent
        
        return innermost_method
    
    def _find_logging_calls(self, method_node) -> List:
        """Find all potential logging method calls in a method."""
        logging_calls = []
        
        for node in self._traverse_depth_first(method_node):
            if self._is_logging_call(node):
                logging_calls.append(node)
        
        return logging_calls
    
    def _is_logging_call(self, node) -> bool:
        """Check if a node represents a logging method call."""
        if node.type != 'method_invocation':
            return False
        
        try:
            object_node = node.child_by_field_name('object')
            name_node = node.child_by_field_name('name')
            
            if not (object_node and name_node):
                return False
            
            object_text = object_node.text.decode('utf-8')
            method_name = name_node.text.decode('utf-8')
            
            # Check if it's a logging call
            return (object_text in self.logger_names and 
                    method_name in self.logging_methods)
        except:
            return False
    
    def _extract_with_slicing(self, call_node, method_node, context: ExtractionContext) -> List[LogTemplate]:
        """Extract templates using backward slicing for indirect patterns."""
        templates = []
        
        try:
            # Find variables used in the logging call
            variables = self._get_message_variables(call_node)
            
            for var_name in variables:
                # Perform backward slice
                patterns = self.slicer.slice_variable(
                    method_node, var_name, context.current_line, context
                )
                
                # Create templates from sliced patterns
                for i, pattern in enumerate(patterns):
                    if pattern and pattern.strip():
                        template_id = self._create_template_id(context, pattern, i)
                        
                        location = SourceLocation(
                            file_path=context.file_path,
                            class_name=context.class_name,
                            method_name=context.method_name,
                            line_number=context.current_line
                        )
                        
                        # Count static tokens
                        static_count = self._count_static_tokens(pattern)
                        
                        template = LogTemplate(
                            template_id=template_id,
                            pattern=pattern,
                            static_token_count=static_count,
                            location=location,
                            level=LogLevel.UNKNOWN,  # Can't determine from slice
                            branch_variant=i
                        )
                        
                        templates.append(template)
        
        except Exception as e:
            print(f"Warning: Error in backward slicing: {e}")
        
        return templates
    
    def _get_message_variables(self, call_node) -> Set[str]:
        """Extract variable names used as log message arguments."""
        variables = set()
        
        try:
            args_node = call_node.child_by_field_name('arguments')
            if args_node:
                # Look for identifier arguments (variables)
                for child in args_node.children:
                    if child.type == 'identifier':
                        variables.add(child.text.decode('utf-8'))
        except:
            pass
        
        return variables
    
    def _limit_branch_variants(self, templates: List[LogTemplate]) -> List[LogTemplate]:
        """Limit branch variants per logging site to prevent explosion."""
        # Group templates by location (file, class, method, line)
        location_groups = {}
        
        for template in templates:
            key = (
                template.location.file_path,
                template.location.class_name,
                template.location.method_name,
                template.location.line_number
            )
            
            if key not in location_groups:
                location_groups[key] = []
            location_groups[key].append(template)
        
        # Limit each group
        limited_templates = []
        for group in location_groups.values():
            # Sort by static token count (keep most specific)
            group.sort(key=lambda t: t.static_token_count, reverse=True)
            limited_templates.extend(group[:self.max_branch_variants])
        
        return limited_templates
    
    def _find_nodes_by_type(self, root_node, node_type: str) -> List:
        """Find all nodes of a specific type."""
        nodes = []
        
        def visit(node):
            if node.type == node_type:
                nodes.append(node)
            for child in node.children:
                visit(child)
        
        visit(root_node)
        return nodes
    
    def _traverse_depth_first(self, node) -> List:
        """Traverse AST in depth-first order."""
        nodes = [node]
        
        def visit(n):
            for child in n.children:
                nodes.append(child)
                visit(child)
        
        visit(node)
        return nodes
    
    def _get_class_name(self, class_node) -> Optional[str]:
        """Extract class name from class declaration node."""
        try:
            name_node = class_node.child_by_field_name('name')
            if name_node:
                return name_node.text.decode('utf-8')
        except:
            pass
        return None
    
    def _get_method_name(self, method_node) -> Optional[str]:
        """Extract method name from method declaration node."""
        try:
            name_node = method_node.child_by_field_name('name')
            if name_node:
                return name_node.text.decode('utf-8')
        except:
            pass
        return None
    
    def _get_line_number(self, node) -> int:
        """Get line number from AST node."""
        try:
            return node.start_point[0] + 1  # Tree-sitter uses 0-based line numbers
        except:
            return 0
    
    def _count_static_tokens(self, pattern: str) -> int:
        """Count static tokens in a template pattern."""
        tokens = pattern.split()
        return sum(1 for token in tokens if token != "<*>")
    
    def _create_template_id(self, context: ExtractionContext, pattern: str, variant: int) -> str:
        """Create a unique template identifier."""
        import hashlib
        
        content = f"{context.file_path}:{context.current_line}:{pattern}:{variant}"
        hash_obj = hashlib.md5(content.encode('utf-8'))
        return hash_obj.hexdigest()[:16]

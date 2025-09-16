"""
Tests for template extraction rules.
"""

import unittest
from pathlib import Path
import tree_sitter_languages

from logtemplates.templating import (
    SLF4JTemplateRule, StringFormatTemplateRule, 
    ConcatenationTemplateRule, StringBuilderTemplateRule,
    LogTemplateBuilder
)
from logtemplates.models import ExtractionContext
from tests.test_data.java_samples import TEST_CASES


class TestTemplatingRules(unittest.TestCase):
    """Test individual templating rules."""
    
    def setUp(self):
        """Set up parser and rules."""
        self.parser = tree_sitter_languages.get_parser("java")
        self.slf4j_rule = SLF4JTemplateRule()
        self.format_rule = StringFormatTemplateRule()
        self.concat_rule = ConcatenationTemplateRule()
        self.builder_rule = StringBuilderTemplateRule()
        self.template_builder = LogTemplateBuilder()
    
    def _parse_java(self, code: str):
        """Parse Java code and return AST."""
        return self.parser.parse(bytes(code, 'utf8'))
    
    def _find_method_calls(self, root_node):
        """Find all method invocation nodes."""
        calls = []
        
        def visit(node):
            if node.type == 'method_invocation':
                calls.append(node)
            for child in node.children:
                visit(child)
        
        visit(root_node)
        return calls
    
    def test_slf4j_rule_detection(self):
        """Test SLF4J rule can detect logging calls."""
        code = '''
        public class Test {
            private Logger log = LoggerFactory.getLogger(Test.class);
            
            public void test() {
                log.info("Test message with {}", param);
                log.error("Error: {}", error);
                System.out.println("Not a log call");
            }
        }
        '''
        
        tree = self._parse_java(code)
        calls = self._find_method_calls(tree.root_node)
        context = ExtractionContext("test.java")
        
        slf4j_calls = [call for call in calls if self.slf4j_rule.can_handle(call, context)]
        other_calls = [call for call in calls if not self.slf4j_rule.can_handle(call, context)]
        
        self.assertEqual(len(slf4j_calls), 2)  # log.info and log.error
        self.assertEqual(len(other_calls), 1)  # System.out.println
    
    def test_slf4j_template_extraction(self):
        """Test SLF4J template pattern extraction."""
        code = '''
        public void test() {
            log.info("User {} logged in from {}", username, ipAddress);
            log.warn("Processing {} items", count);
        }
        '''
        
        tree = self._parse_java(code)
        calls = self._find_method_calls(tree.root_node)
        context = ExtractionContext("test.java")
        
        for call in calls:
            if self.slf4j_rule.can_handle(call, context):
                patterns = self.slf4j_rule.extract_template(call, context)
                if "logged in" in str(call.text):
                    self.assertIn("User <*> logged in from <*>", patterns)
                elif "Processing" in str(call.text):
                    self.assertIn("Processing <*> items", patterns)
    
    def test_string_format_rule_detection(self):
        """Test String.format rule detection."""
        code = '''
        public void test() {
            String.format("User %s has %d points", name, points);
            log.info(String.format("Processing %d records", count));
            someOtherMethod("not a format call");
        }
        '''
        
        tree = self._parse_java(code)
        calls = self._find_method_calls(tree.root_node)
        context = ExtractionContext("test.java")
        
        format_calls = [call for call in calls if self.format_rule.can_handle(call, context)]
        
        self.assertEqual(len(format_calls), 2)  # Two String.format calls
    
    def test_string_format_template_extraction(self):
        """Test String.format template extraction."""
        code = '''
        public void test() {
            logger.info(String.format("User %s has %d points and %.2f score", 
                                     name, points, score));
        }
        '''
        
        tree = self._parse_java(code)
        calls = self._find_method_calls(tree.root_node)
        context = ExtractionContext("test.java")
        
        for call in calls:
            if "String.format" in str(call.text):
                # Find the nested String.format call
                for child in call.children:
                    if self.format_rule.can_handle(child, context):
                        patterns = self.format_rule.extract_template(child, context)
                        expected = "User <*> has <*> points and <*> score"
                        self.assertIn(expected, patterns)
    
    def test_concatenation_rule_detection(self):
        """Test string concatenation rule detection."""
        code = '''
        public void test() {
            log.info("User " + username + " logged in");
            log.error("Error: " + ex.getMessage());
            int sum = a + b;  // Not string concatenation
        }
        '''
        
        tree = self._parse_java(code)
        
        # Find binary expressions (+ operations)
        expressions = []
        def visit(node):
            if node.type == 'binary_expression':
                expressions.append(node)
            for child in node.children:
                visit(child)
        
        visit(tree.root_node)
        context = ExtractionContext("test.java")
        
        concat_exprs = [expr for expr in expressions 
                       if self.concat_rule.can_handle(expr, context)]
        
        self.assertGreaterEqual(len(concat_exprs), 2)  # At least the two string concats
    
    def test_stringbuilder_rule_detection(self):
        """Test StringBuilder rule detection."""
        code = '''
        public void test() {
            StringBuilder sb = new StringBuilder()
                .append("User ")
                .append(username)
                .append(" logged in");
            log.info(sb.toString());
            
            log.debug(new StringBuilder("Processing ").append(count).toString());
        }
        '''
        
        tree = self._parse_java(code)
        calls = self._find_method_calls(tree.root_node)
        context = ExtractionContext("test.java")
        
        builder_calls = [call for call in calls 
                        if self.builder_rule.can_handle(call, context)]
        
        self.assertGreaterEqual(len(builder_calls), 1)  # At least one StringBuilder chain


class TestIntegratedTemplateExtraction(unittest.TestCase):
    """Test complete template extraction on real Java samples."""
    
    def setUp(self):
        """Set up extractor."""
        self.parser = tree_sitter_languages.get_parser("java")
        self.template_builder = LogTemplateBuilder()
    
    def _extract_templates_from_code(self, java_code: str, class_name: str = "TestClass"):
        """Extract templates from Java code."""
        tree = self.parser.parse(bytes(java_code, 'utf8'))
        context = ExtractionContext(
            file_path="test.java",
            class_name=class_name,
            method_name="testMethod"
        )
        
        templates = []
        
        def visit(node):
            if node.type == 'method_invocation':
                extracted = self.template_builder.extract_templates(node, context)
                templates.extend(extracted)
            for child in node.children:
                visit(child)
        
        visit(tree.root_node)
        return templates
    
    def test_slf4j_extraction(self):
        """Test SLF4J pattern extraction."""
        test_case = next(tc for tc in TEST_CASES if tc["name"] == "slf4j_basic")
        
        templates = self._extract_templates_from_code(test_case["java_code"])
        patterns = [t.pattern for t in templates]
        
        for expected in test_case["expected_patterns"]:
            self.assertIn(expected, patterns, 
                         f"Expected pattern '{expected}' not found in {patterns}")
    
    def test_string_format_extraction(self):
        """Test String.format pattern extraction."""
        test_case = next(tc for tc in TEST_CASES if tc["name"] == "string_format_basic")
        
        templates = self._extract_templates_from_code(test_case["java_code"])
        patterns = [t.pattern for t in templates]
        
        for expected in test_case["expected_patterns"]:
            # String.format patterns might be extracted differently
            found = any(expected in pattern for pattern in patterns)
            self.assertTrue(found, 
                          f"Expected pattern '{expected}' not found in {patterns}")
    
    def test_concatenation_extraction(self):
        """Test concatenation pattern extraction."""
        test_case = next(tc for tc in TEST_CASES if tc["name"] == "concatenation_simple")
        
        templates = self._extract_templates_from_code(test_case["java_code"])
        patterns = [t.pattern for t in templates]
        
        # Concatenation patterns may have slightly different spacing
        for expected in test_case["expected_patterns"]:
            found = any(self._patterns_match(expected, pattern) for pattern in patterns)
            self.assertTrue(found,
                          f"Expected pattern '{expected}' not found in {patterns}")
    
    def test_template_metadata(self):
        """Test that templates have correct metadata."""
        code = '''
        public class UserService {
            private Logger log = LoggerFactory.getLogger(UserService.class);
            
            public void loginUser(String username) {
                log.info("User {} logged in", username);
            }
        }
        '''
        
        templates = self._extract_templates_from_code(code, "UserService")
        
        self.assertGreater(len(templates), 0)
        
        template = templates[0]
        self.assertIsNotNone(template.template_id)
        self.assertEqual(template.location.class_name, "UserService")
        self.assertEqual(template.location.method_name, "testMethod")
        self.assertGreater(template.static_token_count, 0)
    
    def test_static_token_counting(self):
        """Test static token count calculation."""
        test_patterns = [
            ("User <*> logged in", 3),
            ("<*> failed with error <*>", 3),
            ("<*>", 0),
            ("Processing request", 2),
            ("Error: <*> in method <*> at line <*>", 5)
        ]
        
        for pattern, expected_count in test_patterns:
            # Create a mock template and test the count
            count = self.template_builder.rules[0].count_static_tokens(pattern)
            self.assertEqual(count, expected_count,
                           f"Pattern '{pattern}' should have {expected_count} static tokens, got {count}")
    
    def _patterns_match(self, expected: str, actual: str) -> bool:
        """Check if patterns match, allowing for spacing differences."""
        # Normalize whitespace
        expected_norm = ' '.join(expected.split())
        actual_norm = ' '.join(actual.split())
        return expected_norm == actual_norm


if __name__ == '__main__':
    unittest.main()

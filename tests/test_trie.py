"""
Tests for the template trie matcher.
"""

import unittest
from logtemplates.trie import TemplateTrie
from logtemplates.models import LogTemplate, LogLevel, SourceLocation


class TestTemplateTrie(unittest.TestCase):
    """Test the template trie matcher."""
    
    def setUp(self):
        """Set up test trie with sample templates."""
        self.trie = TemplateTrie()
        
        # Create test templates
        self.templates = [
            LogTemplate(
                template_id="t1",
                pattern="User <*> logged in",
                static_token_count=3,
                location=SourceLocation("test1.java", "UserService", "login", 10),
                level=LogLevel.INFO
            ),
            LogTemplate(
                template_id="t2",
                pattern="User <*> logged in from <*>",
                static_token_count=4,
                location=SourceLocation("test1.java", "UserService", "login", 11),
                level=LogLevel.INFO
            ),
            LogTemplate(
                template_id="t3",
                pattern="Error processing request <*>",
                static_token_count=3,
                location=SourceLocation("test2.java", "RequestHandler", "process", 20),
                level=LogLevel.ERROR
            ),
            LogTemplate(
                template_id="t4",
                pattern="Processing <*> items",
                static_token_count=2,
                location=SourceLocation("test3.java", "BatchProcessor", "process", 30),
                level=LogLevel.DEBUG
            ),
            LogTemplate(
                template_id="t5",
                pattern="<*> operation completed successfully",
                static_token_count=3,
                location=SourceLocation("test4.java", "OperationManager", "complete", 40),
                level=LogLevel.INFO
            )
        ]
        
        # Add templates to trie
        for template in self.templates:
            self.trie.add_template(template)
    
    def test_exact_matches(self):
        """Test exact pattern matches."""
        test_cases = [
            ("User john logged in", "t1", ["john"]),
            ("User alice logged in from 192.168.1.1", "t2", ["alice", "192.168.1.1"]),
            ("Error processing request 12345", "t3", ["12345"]),
            ("Processing 100 items", "t4", ["100"]),
            ("Database operation completed successfully", "t5", ["Database"])
        ]
        
        for log_line, expected_template_id, expected_values in test_cases:
            with self.subTest(log_line=log_line):
                matches = self.trie.match(log_line)
                
                self.assertGreater(len(matches), 0, f"No matches found for: {log_line}")
                
                best_match = matches[0]  # Should be sorted by specificity
                self.assertEqual(best_match.template.template_id, expected_template_id)
                self.assertEqual(best_match.extracted_values, expected_values)
    
    def test_most_specific_wins(self):
        """Test that most specific template wins."""
        # This should match both t1 and t2, but t2 should win (higher static_token_count)
        log_line = "User bob logged in from office"
        matches = self.trie.match(log_line)
        
        self.assertGreater(len(matches), 0)
        
        # Best match should be t2 (more specific)
        best_match = matches[0]
        self.assertEqual(best_match.template.template_id, "t2")
        self.assertEqual(best_match.extracted_values, ["bob", "office"])
        
        # Check that t1 is also in matches but with lower priority
        template_ids = [m.template.template_id for m in matches]
        self.assertIn("t1", template_ids)
    
    def test_no_matches(self):
        """Test cases with no matches."""
        no_match_cases = [
            "Completely unrelated message",
            "User",  # Too short
            "",  # Empty
            "logged in User john",  # Wrong order
        ]
        
        for log_line in no_match_cases:
            with self.subTest(log_line=log_line):
                matches = self.trie.match(log_line)
                self.assertEqual(len(matches), 0, f"Unexpected match for: {log_line}")
    
    def test_level_filtering(self):
        """Test log level filtering."""
        log_line = "Error processing request 404"
        
        # Match with correct level
        matches = self.trie.match(log_line, "ERROR")
        self.assertGreater(len(matches), 0)
        self.assertEqual(matches[0].template.template_id, "t3")
        
        # No match with wrong level
        matches = self.trie.match(log_line, "DEBUG")
        self.assertEqual(len(matches), 0)
        
        # Match with unknown level (should work for templates with UNKNOWN level)
        matches = self.trie.match(log_line)  # No level filter
        self.assertGreater(len(matches), 0)
    
    def test_wildcard_matching(self):
        """Test wildcard placeholder matching."""
        test_cases = [
            # Single token wildcards
            ("User admin logged in", "t1", ["admin"]),
            ("User super-user logged in", "t1", ["super-user"]),
            
            # Multi-token wildcards
            ("User john doe logged in from remote office", "t2", ["john", "doe logged in from remote office"]),
            ("Processing many different items", "t4", ["many different"]),
            
            # Complex wildcards
            ("Complex database operation completed successfully", "t5", ["Complex database"]),
        ]
        
        for log_line, expected_template_id, expected_values in test_cases:
            with self.subTest(log_line=log_line):
                matches = self.trie.match(log_line)
                
                # Find the expected template in matches
                target_match = None
                for match in matches:
                    if match.template.template_id == expected_template_id:
                        target_match = match
                        break
                
                self.assertIsNotNone(target_match, 
                                   f"Template {expected_template_id} not found in matches for: {log_line}")
                self.assertEqual(target_match.extracted_values, expected_values)
    
    def test_confidence_scoring(self):
        """Test confidence score calculation."""
        # More specific templates should have higher confidence
        log_line = "User alice logged in from 10.0.0.1"
        matches = self.trie.match(log_line)
        
        self.assertGreaterEqual(len(matches), 2)  # Should match both t1 and t2
        
        # t2 should have higher confidence (more specific)
        t1_match = next(m for m in matches if m.template.template_id == "t1")
        t2_match = next(m for m in matches if m.template.template_id == "t2")
        
        self.assertGreater(t2_match.confidence, t1_match.confidence)
        
        # All confidences should be between 0 and 1
        for match in matches:
            self.assertGreaterEqual(match.confidence, 0.0)
            self.assertLessEqual(match.confidence, 1.0)
    
    def test_tokenization(self):
        """Test log line tokenization."""
        test_cases = [
            ("simple message", ["simple", "message"]),
            ("  spaced   message  ", ["spaced", "message"]),
            ("user@host.com:8080", ["user@host.com:8080"]),
            ("key=value param=123", ["key=value", "param=123"]),
            ("", []),
        ]
        
        for text, expected_tokens in test_cases:
            with self.subTest(text=text):
                tokens = self.trie.tokenize(text)
                self.assertEqual(tokens, expected_tokens)
    
    def test_trie_size(self):
        """Test trie size calculation."""
        expected_size = len(self.templates)
        actual_size = self.trie.size()
        self.assertEqual(actual_size, expected_size)
    
    def test_get_best_match(self):
        """Test getting single best match."""
        log_line = "User charlie logged in from 192.168.1.100"
        
        best_match = self.trie.get_best_match(log_line)
        self.assertIsNotNone(best_match)
        self.assertEqual(best_match.template.template_id, "t2")  # Most specific
        
        # Test no match case
        no_match = self.trie.get_best_match("Completely unrelated message")
        self.assertIsNone(no_match)
    
    def test_empty_trie(self):
        """Test behavior with empty trie."""
        empty_trie = TemplateTrie()
        
        matches = empty_trie.match("Any message")
        self.assertEqual(len(matches), 0)
        
        best_match = empty_trie.get_best_match("Any message")
        self.assertIsNone(best_match)
        
        self.assertEqual(empty_trie.size(), 0)
    
    def test_duplicate_templates(self):
        """Test handling of duplicate templates."""
        duplicate_trie = TemplateTrie()
        
        # Add same template twice
        template = LogTemplate(
            template_id="dup1",
            pattern="Test message <*>",
            static_token_count=2,
            location=SourceLocation("test.java", "Test", "test", 1),
            level=LogLevel.INFO
        )
        
        duplicate_trie.add_template(template)
        duplicate_trie.add_template(template)
        
        matches = duplicate_trie.match("Test message hello")
        # Should find both instances
        self.assertEqual(len(matches), 2)
        
        # Both should have same template_id
        for match in matches:
            self.assertEqual(match.template.template_id, "dup1")


class TestTrieEdgeCases(unittest.TestCase):
    """Test edge cases for the trie matcher."""
    
    def test_very_long_patterns(self):
        """Test handling of very long patterns."""
        trie = TemplateTrie()
        
        # Create a template with many tokens
        long_pattern = " ".join(["token"] * 20 + ["<*>"] + ["more"] * 10)
        template = LogTemplate(
            template_id="long",
            pattern=long_pattern,
            static_token_count=30,
            location=SourceLocation("test.java", "Test", "test", 1),
            level=LogLevel.INFO
        )
        
        trie.add_template(template)
        
        # Create matching log line
        log_tokens = ["token"] * 20 + ["PLACEHOLDER"] + ["more"] * 10
        log_line = " ".join(log_tokens)
        
        matches = trie.match(log_line)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].extracted_values, ["PLACEHOLDER"])
    
    def test_special_characters(self):
        """Test handling of special characters in patterns."""
        trie = TemplateTrie()
        
        template = LogTemplate(
            template_id="special",
            pattern="Request: method=<*> path=<*> status=<*>",
            static_token_count=3,
            location=SourceLocation("test.java", "Test", "test", 1),
            level=LogLevel.INFO
        )
        
        trie.add_template(template)
        
        log_line = "Request: method=GET path=/api/users/123 status=200"
        matches = trie.match(log_line)
        
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].extracted_values, ["GET", "/api/users/123", "200"])
    
    def test_multiple_wildcards_adjacent(self):
        """Test patterns with multiple adjacent wildcards."""
        trie = TemplateTrie()
        
        template = LogTemplate(
            template_id="multi",
            pattern="User <*> <*> logged in",
            static_token_count=3,
            location=SourceLocation("test.java", "Test", "test", 1),
            level=LogLevel.INFO
        )
        
        trie.add_template(template)
        
        log_line = "User John Doe logged in"
        matches = trie.match(log_line)
        
        self.assertEqual(len(matches), 1)
        # Should capture both first and last names
        self.assertEqual(len(matches[0].extracted_values), 2)


if __name__ == '__main__':
    unittest.main()

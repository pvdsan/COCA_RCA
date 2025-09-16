"""
Integration tests for the complete log template extraction system.
"""

import unittest
import tempfile
import os
from pathlib import Path

from logtemplates import JavaLogExtractor, TemplateTrie
from logtemplates.io_utils import JSONLWriter, JSONLReader
from tests.test_data.java_samples import MIXED_SAMPLES


class TestIntegration(unittest.TestCase):
    """Integration tests for the complete system."""
    
    def setUp(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.java_file_path = Path(self.temp_dir) / "TestService.java"
        self.templates_file = Path(self.temp_dir) / "templates.jsonl"
        self.log_file = Path(self.temp_dir) / "test.log"
    
    def tearDown(self):
        """Clean up test environment."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_end_to_end_extraction_and_matching(self):
        """Test complete end-to-end workflow."""
        # 1. Create a Java file with various logging patterns
        java_code = '''
package com.example;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OrderService {
    private static final Logger log = LoggerFactory.getLogger(OrderService.class);
    
    public void processOrder(String orderId, String userId, double amount) {
        // SLF4J patterns
        log.info("Processing order {} for user {}", orderId, userId);
        log.debug("Order amount: ${}", amount);
        
        // String concatenation
        String message = "Order " + orderId + " validation started";
        log.info(message);
        
        // String.format
        String summary = String.format("Order %s: user=%s amount=%.2f", orderId, userId, amount);
        log.info(summary);
        
        if (amount > 1000) {
            log.warn("Large order detected: {} amount=${}", orderId, amount);
        }
        
        try {
            processPayment(amount);
            log.info("Payment processed successfully for order {}", orderId);
        } catch (Exception e) {
            log.error("Payment failed for order {}: {}", orderId, e.getMessage());
        }
    }
    
    private void processPayment(double amount) throws Exception {
        if (amount <= 0) {
            throw new Exception("Invalid amount");
        }
    }
}
'''
        
        # Write Java file
        with open(self.java_file_path, 'w') as f:
            f.write(java_code)
        
        # 2. Extract templates
        extractor = JavaLogExtractor(cache_dir=str(Path(self.temp_dir) / "cache"))
        templates = extractor.extract_from_repository(
            repo_path=str(self.temp_dir),
            use_cache=False
        )
        
        # Verify templates were extracted
        self.assertGreater(len(templates), 0, "No templates extracted")
        
        # Check for expected patterns
        patterns = [t.pattern for t in templates]
        expected_substrings = [
            "Processing order",
            "Order amount",
            "validation started",
            "Large order detected",
            "Payment processed successfully",
            "Payment failed"
        ]
        
        for expected in expected_substrings:
            found = any(expected in pattern for pattern in patterns)
            self.assertTrue(found, f"Expected pattern containing '{expected}' not found")
        
        # 3. Save templates to JSONL
        with JSONLWriter(str(self.templates_file)) as writer:
            writer.write_templates(templates)
        
        # Verify file was written
        self.assertTrue(self.templates_file.exists())
        
        # 4. Load templates back
        reader = JSONLReader(str(self.templates_file))
        loaded_templates = reader.read_templates()
        
        self.assertEqual(len(loaded_templates), len(templates))
        
        # 5. Build trie for matching
        trie = TemplateTrie()
        for template in loaded_templates:
            trie.add_template(template)
        
        # 6. Create test log lines
        test_logs = [
            "2023-10-15 14:30:00 INFO  Processing order 12345 for user john_doe",
            "2023-10-15 14:30:01 DEBUG Order amount: $599.99",
            "2023-10-15 14:30:02 INFO  Order 12345 validation started",
            "2023-10-15 14:30:03 INFO  Order 12345: user=john_doe amount=599.99",
            "2023-10-15 14:30:04 WARN  Large order detected: 67890 amount=$1500.00",
            "2023-10-15 14:30:05 INFO  Payment processed successfully for order 12345",
            "2023-10-15 14:30:06 ERROR Payment failed for order 67891: Insufficient funds",
            "2023-10-15 14:30:07 INFO  Unrelated log message that won't match"
        ]
        
        # Write log file
        with open(self.log_file, 'w') as f:
            for log in test_logs:
                f.write(log + '\n')
        
        # 7. Match log lines
        matches_found = 0
        no_matches = 0
        
        with open(self.log_file, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                
                # Extract message part (simple parsing)
                parts = line.split(None, 3)  # Split on whitespace, max 4 parts
                if len(parts) >= 4:
                    message = parts[3]  # Everything after timestamp, level, logger
                else:
                    message = line
                
                matches = trie.match(message)
                
                if matches:
                    matches_found += 1
                    best_match = matches[0]
                    
                    # Verify match quality
                    self.assertGreater(best_match.confidence, 0.0)
                    self.assertIsNotNone(best_match.template.template_id)
                    
                    print(f"Line {line_num}: '{message}' -> {best_match.template.pattern} "
                          f"(confidence: {best_match.confidence:.3f})")
                else:
                    no_matches += 1
                    print(f"Line {line_num}: '{message}' -> No match")
        
        # Should match most lines (except the "Unrelated" one)
        self.assertGreaterEqual(matches_found, 6)  # At least 6 out of 7 should match
        self.assertLessEqual(no_matches, 2)  # At most 2 should not match
    
    def test_caching_functionality(self):
        """Test incremental caching."""
        # Create Java file
        java_code = '''
public class CacheTest {
    private Logger log = LoggerFactory.getLogger(CacheTest.class);
    
    public void test() {
        log.info("Test message with {}", param);
    }
}
'''
        
        with open(self.java_file_path, 'w') as f:
            f.write(java_code)
        
        cache_dir = Path(self.temp_dir) / "cache"
        extractor = JavaLogExtractor(cache_dir=str(cache_dir))
        
        # First extraction - should process the file
        templates1 = extractor.extract_from_repository(str(self.temp_dir), use_cache=True)
        self.assertGreater(len(templates1), 0)
        
        # Check cache was created
        self.assertTrue(cache_dir.exists())
        
        # Second extraction - should use cache
        templates2 = extractor.extract_from_repository(str(self.temp_dir), use_cache=True)
        
        # Results should be identical
        self.assertEqual(len(templates1), len(templates2))
        
        template_ids1 = {t.template_id for t in templates1}
        template_ids2 = {t.template_id for t in templates2}
        self.assertEqual(template_ids1, template_ids2)
    
    def test_large_file_handling(self):
        """Test handling of larger Java files."""
        # Create a more complex Java file
        java_code = MIXED_SAMPLES["kitchen_sink"]
        
        with open(self.java_file_path, 'w') as f:
            f.write(java_code)
        
        extractor = JavaLogExtractor()
        templates = extractor.extract_from_repository(str(self.temp_dir), use_cache=False)
        
        # Should extract multiple templates from the mixed patterns
        self.assertGreaterEqual(len(templates), 4)
        
        # Check template diversity
        patterns = [t.pattern for t in templates]
        levels = [t.level for t in templates]
        
        # Should have different patterns
        unique_patterns = set(patterns)
        self.assertGreater(len(unique_patterns), 1)
        
        # Should have valid template IDs
        for template in templates:
            self.assertIsNotNone(template.template_id)
            self.assertTrue(len(template.template_id) > 0)
    
    def test_error_handling(self):
        """Test error handling for invalid inputs."""
        extractor = JavaLogExtractor()
        
        # Test with non-existent directory
        templates = extractor.extract_from_repository("/non/existent/path")
        self.assertEqual(len(templates), 0)
        
        # Test with empty directory
        empty_dir = Path(self.temp_dir) / "empty"
        empty_dir.mkdir()
        templates = extractor.extract_from_repository(str(empty_dir))
        self.assertEqual(len(templates), 0)
        
        # Test with invalid Java file
        invalid_java = Path(self.temp_dir) / "invalid.java"
        with open(invalid_java, 'w') as f:
            f.write("This is not valid Java code {}{}")
        
        templates = extractor.extract_from_repository(str(self.temp_dir))
        # Should handle gracefully and not crash
        self.assertIsInstance(templates, list)
    
    def test_template_uniqueness(self):
        """Test that duplicate templates are handled correctly."""
        # Create Java file with repeated patterns
        java_code = '''
public class DuplicateTest {
    private Logger log = LoggerFactory.getLogger(DuplicateTest.class);
    
    public void method1() {
        log.info("Processing request {}", id);
    }
    
    public void method2() {
        log.info("Processing request {}", requestId);
    }
    
    public void method3() {
        log.info("Processing request {}", req);
    }
}
'''
        
        with open(self.java_file_path, 'w') as f:
            f.write(java_code)
        
        extractor = JavaLogExtractor()
        templates = extractor.extract_from_repository(str(self.temp_dir))
        
        # All three calls should generate templates (different locations)
        self.assertGreaterEqual(len(templates), 3)
        
        # But they should all have the same pattern
        patterns = [t.pattern for t in templates]
        expected_pattern = "Processing request <*>"
        
        matching_templates = [t for t in templates if t.pattern == expected_pattern]
        self.assertGreaterEqual(len(matching_templates), 3)
        
        # Should have different template IDs (different source locations)
        template_ids = [t.template_id for t in matching_templates]
        unique_ids = set(template_ids)
        self.assertEqual(len(unique_ids), len(template_ids))  # All unique


class TestPerformance(unittest.TestCase):
    """Basic performance tests."""
    
    def setUp(self):
        """Set up performance test environment."""
        self.temp_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_large_trie_performance(self):
        """Test trie performance with many templates."""
        from logtemplates.models import LogTemplate, LogLevel, SourceLocation
        import time
        
        trie = TemplateTrie()
        
        # Create many templates
        num_templates = 1000
        templates = []
        
        for i in range(num_templates):
            template = LogTemplate(
                template_id=f"t{i}",
                pattern=f"Operation {i % 10} processing <*> with status <*>",
                static_token_count=5,
                location=SourceLocation(f"test{i}.java", "Test", "method", i),
                level=LogLevel.INFO
            )
            templates.append(template)
            trie.add_template(template)
        
        # Test matching performance
        test_line = "Operation 5 processing item12345 with status SUCCESS"
        
        start_time = time.time()
        for _ in range(100):  # 100 matches
            matches = trie.match(test_line)
            self.assertGreater(len(matches), 0)
        end_time = time.time()
        
        avg_time_ms = (end_time - start_time) * 1000 / 100
        print(f"Average matching time: {avg_time_ms:.2f}ms for {num_templates} templates")
        
        # Should be reasonably fast (< 10ms per match on average)
        self.assertLess(avg_time_ms, 10.0)


if __name__ == '__main__':
    unittest.main()

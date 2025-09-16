#!/usr/bin/env python3
"""
Demo script for the log template extraction system.
"""

import tempfile
import os
from pathlib import Path

from logtemplates import JavaLogExtractor, TemplateTrie
from logtemplates.io_utils import JSONLWriter, JSONLReader


def create_sample_java_file():
    """Create a sample Java file for demonstration."""
    java_code = '''
package com.example.demo;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class DemoService {
    private static final Logger log = LoggerFactory.getLogger(DemoService.class);
    
    public void processUser(String userId, String action, int count) {
        // SLF4J logging
        log.info("User {} performed action: {}", userId, action);
        log.debug("Processing {} items for user {}", count, userId);
        
        // String concatenation
        String message = "User " + userId + " processing started";
        log.info(message);
        
        // String.format
        String summary = String.format("Action %s completed for user %s with %d items", 
                                      action, userId, count);
        log.info(summary);
        
        if (count > 100) {
            log.warn("Large batch detected: user={} count={}", userId, count);
        }
        
        try {
            processItems(count);
            log.info("Processing completed successfully for user {}", userId);
        } catch (Exception e) {
            log.error("Processing failed for user {}: {}", userId, e.getMessage());
        }
    }
    
    private void processItems(int count) throws Exception {
        if (count <= 0) {
            throw new Exception("Invalid count");
        }
        // Processing logic here
    }
}
'''
    return java_code


def create_sample_logs():
    """Create sample log lines for matching."""
    return [
        "2023-10-15 14:30:00 INFO  User alice performed action: login",
        "2023-10-15 14:30:01 DEBUG Processing 50 items for user alice",
        "2023-10-15 14:30:02 INFO  User alice processing started",
        "2023-10-15 14:30:03 INFO  Action login completed for user alice with 50 items",
        "2023-10-15 14:30:04 INFO  Processing completed successfully for user alice",
        "2023-10-15 14:30:05 WARN  Large batch detected: user=bob count=150",
        "2023-10-15 14:30:06 ERROR Processing failed for user charlie: Database connection failed",
        "2023-10-15 14:30:07 INFO  Some unrelated log message that won't match any template"
    ]


def main():
    """Run the demo."""
    print("🚀 Log Template Extraction System Demo")
    print("=" * 50)
    
    # Create temporary directory
    temp_dir = tempfile.mkdtemp()
    print(f"📁 Working in temporary directory: {temp_dir}")
    
    try:
        # Step 1: Create sample Java file
        java_file = Path(temp_dir) / "DemoService.java"
        with open(java_file, 'w') as f:
            f.write(create_sample_java_file())
        print(f"📝 Created sample Java file: {java_file.name}")
        
        # Step 2: Extract templates
        print("\n🔍 Extracting log templates...")
        extractor = JavaLogExtractor(cache_dir=str(Path(temp_dir) / "cache"))
        templates = extractor.extract_from_repository(str(temp_dir), use_cache=False)
        
        print(f"✅ Extracted {len(templates)} templates")
        
        # Show extracted templates
        print("\n📋 Extracted Templates:")
        for i, template in enumerate(templates, 1):
            print(f"  {i:2}. [{template.level.value.upper():5}] {template.pattern}")
            print(f"      📍 {template.location.method_name}() line {template.location.line_number}")
            print(f"      🎯 Static tokens: {template.static_token_count}")
        
        # Step 3: Save templates
        templates_file = Path(temp_dir) / "templates.jsonl"
        with JSONLWriter(str(templates_file)) as writer:
            writer.write_templates(templates)
        print(f"\n💾 Saved templates to: {templates_file.name}")
        
        # Step 4: Build matching trie
        print("\n🌳 Building template trie...")
        trie = TemplateTrie()
        for template in templates:
            trie.add_template(template)
        print(f"✅ Trie built with {trie.size()} templates")
        
        # Step 5: Match sample logs
        print("\n🎯 Matching sample log lines:")
        sample_logs = create_sample_logs()
        
        matched_count = 0
        for i, log_line in enumerate(sample_logs, 1):
            # Extract message part (simple parsing)
            parts = log_line.split(None, 3)
            if len(parts) >= 4:
                message = parts[3]
            else:
                message = log_line
            
            matches = trie.match(message)
            
            print(f"\n  {i}. Log: {log_line}")
            print(f"     Message: {message}")
            
            if matches:
                matched_count += 1
                best_match = matches[0]
                print(f"     ✅ Match: {best_match.template.pattern}")
                print(f"     📊 Confidence: {best_match.confidence:.3f}")
                print(f"     📤 Extracted: {best_match.extracted_values}")
                print(f"     📍 Source: {best_match.template.location.method_name}() "
                      f"line {best_match.template.location.line_number}")
            else:
                print(f"     ❌ No match found")
        
        # Summary
        print(f"\n📊 Matching Summary:")
        print(f"   • Total log lines: {len(sample_logs)}")
        print(f"   • Matched lines: {matched_count}")
        print(f"   • Match rate: {matched_count/len(sample_logs)*100:.1f}%")
        
        # Step 6: Demonstrate programmatic usage
        print(f"\n🔧 Programmatic Usage Example:")
        print("```python")
        print("from logtemplates import JavaLogExtractor, TemplateTrie")
        print("from logtemplates.io_utils import JSONLReader")
        print("")
        print("# Extract templates")
        print("extractor = JavaLogExtractor()")
        print("templates = extractor.extract_from_repository('/path/to/java/project')")
        print("")
        print("# Build matcher")
        print("trie = TemplateTrie()")
        print("for template in templates:")
        print("    trie.add_template(template)")
        print("")
        print("# Match log line")
        print("matches = trie.match('User admin logged in successfully')")
        print("if matches:")
        print("    print(f'Best match: {matches[0].template.pattern}')")
        print("```")
        
        print(f"\n🎉 Demo completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
        print(f"\n🧹 Cleaned up temporary directory")


if __name__ == '__main__':
    main()

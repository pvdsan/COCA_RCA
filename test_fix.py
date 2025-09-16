#!/usr/bin/env python3
"""
Test the SLF4J fix with the problematic code pattern.
"""

import tree_sitter_languages
from logtemplates.templating import SLF4JTemplateRule
from logtemplates.models import ExtractionContext

def test_slf4j_concatenation():
    """Test SLF4J extraction with string concatenation."""
    
    # Sample code similar to the problematic Kafka code
    test_code = '''
    public void warnDisablingExponentialBackoff() {
        log.warn("Configuration '{}' with value '{}' is greater than configuration '{}' with value '{}'. " +
                "A static backoff with value '{}' will be applied.",
            RETRY_BACKOFF_MS_CONFIG, retryBackoffMs,
            RETRY_BACKOFF_MAX_MS_CONFIG, retryBackoffMaxMs, retryBackoffMaxMs);
    }
    '''
    
    parser = tree_sitter_languages.get_parser("java")
    tree = parser.parse(bytes(test_code, 'utf8'))
    
    # Find the log.warn call
    def find_method_calls(node):
        calls = []
        if node.type == 'method_invocation':
            calls.append(node)
        for child in node.children:
            calls.extend(find_method_calls(child))
        return calls
    
    calls = find_method_calls(tree.root_node)
    slf4j_rule = SLF4JTemplateRule()
    context = ExtractionContext("test.java")
    
    for call in calls:
        if slf4j_rule.can_handle(call, context):
            patterns = slf4j_rule.extract_template(call, context)
            print("Found SLF4J call:")
            print(f"Patterns extracted: {patterns}")
            
            if patterns:
                expected = "Configuration '<*>' with value '<*>' is greater than configuration '<*>' with value '<*>'. A static backoff with value '<*>' will be applied."
                actual = patterns[0]
                print(f"Expected: {expected}")
                print(f"Actual:   {actual}")
                print(f"Match: {expected == actual}")
            else:
                print("❌ No patterns extracted!")
            break
    else:
        print("❌ No SLF4J calls found!")

if __name__ == '__main__':
    test_slf4j_concatenation()

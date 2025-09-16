#!/usr/bin/env python3
"""
Analyze the extraction runs to understand why template counts keep increasing.
"""

def analyze_extraction_runs():
    """Analyze the pattern of increasing template counts."""
    
    # From the terminal output, let's track the runs
    runs = [
        {"run": 1, "total": 1813, "new": 1813, "locations": 1305, "patterns": 986},
        {"run": 2, "total": 3543, "new": 1730, "locations": 1368, "patterns": 1179},
        {"run": 3, "total": 5356, "new": 1813, "locations": 1368, "patterns": 1179},
        {"run": 4, "total": 7169, "new": 1813, "locations": 1368, "patterns": 1179},
        {"run": 5, "total": 1725, "new": 1725, "locations": 1364, "patterns": 1174, "note": "templates_multistring.jsonl"},
        {"run": 6, "total": 1730, "new": 1730, "locations": 1368, "patterns": 1179, "note": "templates_literal_concat.jsonl"},
        {"run": 7, "total": 3460, "new": 1730, "locations": 1368, "patterns": 1179},
        {"run": 8, "total": 5190, "new": 1730, "locations": 1368, "patterns": 1179},
    ]
    
    print("=== EXTRACTION RUN ANALYSIS ===")
    print()
    
    print("Run progression:")
    for run in runs:
        note = f" ({run.get('note', 'templates.jsonl')})" if run.get('note') else ""
        print(f"Run {run['run']:2}: {run['total']:5} total, {run['new']:4} new, "
              f"{run['locations']:4} locations, {run['patterns']:4} patterns{note}")
    
    print()
    print("Key observations:")
    print()
    
    # Issue 1: Template duplication
    print("1. TEMPLATE DUPLICATION ISSUE:")
    print("   - Run 1: 1813 templates extracted")
    print("   - Run 2: 3543 total (1730 new) - should be ~1813 if no duplication")
    print("   - Run 3: 5356 total (1813 new) - adding same 1813 again!")
    print("   - Run 4: 7169 total (1813 new) - another 1813 duplicate set!")
    print()
    
    # Issue 2: Consistent new additions
    print("2. CONSISTENT NEW TEMPLATE GENERATION:")
    print("   - Same repo, same files, but keeps generating 'new' templates")
    print("   - Suggests template IDs are not stable across runs")
    print("   - Possibly timestamp-based or random template ID generation")
    print()
    
    # Issue 3: Locations vs templates mismatch
    print("3. LOCATIONS VS TEMPLATES MISMATCH:")
    print("   - 1368 unique source locations")
    print("   - But 7169 templates in run 4")
    print("   - Ratio: 7169/1368 = 5.2 templates per location")
    print("   - This suggests massive duplication or branch explosion")
    print()
    
    # Issue 4: Pattern count plateau
    print("4. PATTERN COUNT PLATEAU:")
    print("   - Unique patterns stabilize around 1179")
    print("   - But total templates keep growing")
    print("   - Multiple templates with identical patterns but different IDs")
    print()
    
    print("ROOT CAUSES:")
    print("==============")
    print()
    print("A. NON-DETERMINISTIC TEMPLATE IDs:")
    print("   Template IDs likely include random/timestamp components")
    print("   Same logging call generates different IDs on each run")
    print()
    print("B. CACHE NOT WORKING PROPERLY:")
    print("   Cache says 'Loaded X templates from cache'")
    print("   But then processes all 1299 files again anyway")
    print("   Cache metadata not preventing re-processing")
    print()
    print("C. DUPLICATE DETECTION MISSING:")
    print("   No deduplication of identical patterns from same location")
    print("   Multiple templates for same logging call")
    print()
    print("D. TEMPLATE ID GENERATION ISSUE:")
    print("   Hash includes non-deterministic elements")
    print("   Should be based only on: file_path + line + pattern")

if __name__ == '__main__':
    analyze_extraction_runs()

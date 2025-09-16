#!/usr/bin/env python3
"""
CLI tool for extracting log templates from Java repositories.

Usage:
    python extract_templates.py --src <repo_root> --out templates.jsonl --exclude '*/test/*' '*/examples/*'
"""

import click
import os
import sys
from pathlib import Path
from typing import List

# Add the package to Python path
sys.path.insert(0, os.path.dirname(__file__))

from logtemplates import JavaLogExtractor
from logtemplates.io_utils import JSONLWriter


@click.command()
@click.option('--src', '-s', 
              required=True,
              type=click.Path(exists=True, file_okay=False, dir_okay=True),
              help='Source repository root directory')
@click.option('--out', '-o',
              required=True,
              type=click.Path(),
              help='Output JSONL file for extracted templates')
@click.option('--include', '-i',
              multiple=True,
              default=['*.java'],
              help='Include file patterns (can be specified multiple times)')
@click.option('--exclude', '-e',
              multiple=True,
              help='Exclude file patterns (can be specified multiple times)')
@click.option('--cache-dir',
              default='.logtemplates_cache',
              type=click.Path(),
              help='Cache directory for incremental processing')
@click.option('--no-cache',
              is_flag=True,
              help='Disable caching and reprocess all files')
@click.option('--workers', '-w',
              type=int,
              default=None,
              help='Number of parallel workers (default: auto)')
@click.option('--max-variants',
              type=int,
              default=16,
              help='Maximum template variants per logging site')
@click.option('--verbose', '-v',
              is_flag=True,
              help='Enable verbose output')
def extract_templates(src: str, 
                     out: str, 
                     include: tuple, 
                     exclude: tuple,
                     cache_dir: str,
                     no_cache: bool,
                     workers: int,
                     max_variants: int,
                     verbose: bool):
    """
    Extract log templates from Java source code.
    
    This tool analyzes Java source files to find logging statements and extracts
    template patterns with <*> placeholders for variable content. It supports
    various logging frameworks including SLF4J, String.format, and concatenation.
    
    Examples:
    
    \b
    # Extract from current directory
    python extract_templates.py --src . --out templates.jsonl
    
    \b
    # Extract with custom exclusions
    python extract_templates.py --src /path/to/kafka \\
        --out kafka_templates.jsonl \\
        --exclude '*/test/*' '*/examples/*' '*/benchmarks/*'
    
    \b
    # Force reprocessing without cache
    python extract_templates.py --src . --out templates.jsonl --no-cache
    """
    
    if verbose:
        click.echo(f"Extracting templates from: {src}")
        click.echo(f"Output file: {out}")
        click.echo(f"Include patterns: {list(include)}")
        click.echo(f"Exclude patterns: {list(exclude)}")
        click.echo(f"Cache directory: {cache_dir}")
        click.echo(f"Use cache: {not no_cache}")
        click.echo(f"Workers: {workers or 'auto'}")
        click.echo(f"Max variants per site: {max_variants}")
        click.echo()
    
    try:
        # Initialize extractor
        extractor = JavaLogExtractor(
            cache_dir=cache_dir,
            max_branch_variants=max_variants,
            parallel_workers=workers
        )
        
        # Extract templates
        templates = extractor.extract_from_repository(
            repo_path=src,
            include_patterns=list(include) if include else None,
            exclude_patterns=list(exclude) if exclude else None,
            use_cache=not no_cache
        )
        
        if not templates:
            click.echo("No templates extracted. Check if the repository contains Java files with logging statements.")
            return
        
        # Ensure output directory exists
        output_path = Path(out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write templates to JSONL file
        with JSONLWriter(str(output_path)) as writer:
            writer.write_templates(templates)
        
        # Summary statistics
        total_templates = len(templates)
        unique_locations = len(set(
            (t.location.file_path, t.location.line_number) 
            for t in templates
        ))
        unique_patterns = len(set(t.pattern for t in templates))
        
        click.echo(f"\n✅ Extraction completed successfully!")
        click.echo(f"📊 Statistics:")
        click.echo(f"   • Total templates: {total_templates}")
        click.echo(f"   • Unique source locations: {unique_locations}")
        click.echo(f"   • Unique patterns: {unique_patterns}")
        click.echo(f"   • Output file: {output_path.absolute()}")
        
        if verbose:
            # Show level distribution
            level_counts = {}
            for template in templates:
                level = template.level.value
                level_counts[level] = level_counts.get(level, 0) + 1
            
            click.echo(f"   • Level distribution:")
            for level, count in sorted(level_counts.items()):
                click.echo(f"     - {level}: {count}")
        
    except KeyboardInterrupt:
        click.echo("\n❌ Extraction cancelled by user")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n❌ Error during extraction: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


@click.command()
@click.option('--templates', '-t',
              required=True,
              type=click.Path(exists=True),
              help='Path to templates JSONL file')
@click.option('--stats', '-s',
              is_flag=True,
              help='Show detailed statistics about templates')
def analyze_templates(templates: str, stats: bool):
    """
    Analyze extracted templates and show statistics.
    
    This tool reads a templates JSONL file and provides detailed analysis
    including pattern distribution, source file coverage, and complexity metrics.
    """
    
    from logtemplates.io_utils import JSONLReader
    
    try:
        # Load templates
        reader = JSONLReader(templates)
        template_list = reader.read_templates()
        
        if not template_list:
            click.echo("No templates found in the file.")
            return
        
        click.echo(f"📋 Template Analysis for: {templates}")
        click.echo(f"=" * 60)
        
        # Basic statistics
        total_templates = len(template_list)
        unique_files = len(set(t.location.file_path for t in template_list))
        unique_patterns = len(set(t.pattern for t in template_list))
        
        click.echo(f"Total templates: {total_templates}")
        click.echo(f"Unique source files: {unique_files}")
        click.echo(f"Unique patterns: {unique_patterns}")
        click.echo()
        
        # Level distribution
        level_counts = {}
        for template in template_list:
            level = template.level.value
            level_counts[level] = level_counts.get(level, 0) + 1
        
        click.echo("Log Level Distribution:")
        for level, count in sorted(level_counts.items()):
            percentage = (count / total_templates) * 100
            click.echo(f"  {level:8}: {count:6} ({percentage:5.1f}%)")
        click.echo()
        
        # Static token distribution
        if stats:
            static_counts = [t.static_token_count for t in template_list]
            avg_static = sum(static_counts) / len(static_counts)
            max_static = max(static_counts)
            min_static = min(static_counts)
            
            click.echo("Template Complexity (Static Token Count):")
            click.echo(f"  Average: {avg_static:.1f}")
            click.echo(f"  Maximum: {max_static}")
            click.echo(f"  Minimum: {min_static}")
            click.echo()
            
            # Most common patterns
            pattern_counts = {}
            for template in template_list:
                pattern = template.pattern
                pattern_counts[pattern] = pattern_counts.get(pattern, 0) + 1
            
            click.echo("Most Common Patterns (top 10):")
            sorted_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)
            for i, (pattern, count) in enumerate(sorted_patterns[:10], 1):
                # Truncate long patterns
                display_pattern = pattern[:60] + "..." if len(pattern) > 60 else pattern
                click.echo(f"  {i:2}. [{count:3}x] {display_pattern}")
            click.echo()
        
        # File coverage
        file_counts = {}
        for template in template_list:
            file_path = template.location.file_path
            file_counts[file_path] = file_counts.get(file_path, 0) + 1
        
        click.echo("Top Files by Template Count:")
        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        for i, (file_path, count) in enumerate(sorted_files[:10], 1):
            # Show relative path if possible
            display_path = Path(file_path).name
            click.echo(f"  {i:2}. [{count:3}x] {display_path}")
        
    except Exception as e:
        click.echo(f"❌ Error analyzing templates: {e}")
        sys.exit(1)


if __name__ == '__main__':
    extract_templates()

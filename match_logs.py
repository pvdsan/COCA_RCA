#!/usr/bin/env python3
"""
CLI tool for matching runtime log lines to extracted templates.

Usage:
    python match_logs.py --templates templates.jsonl --in server.log --out match_report.csv
"""

import click
import csv
import sys
import os
import re
from pathlib import Path
from typing import List, Dict, Optional, Iterator, Tuple
from dataclasses import asdict
from collections import defaultdict

# Add the package to Python path
sys.path.insert(0, os.path.dirname(__file__))

from logtemplates import TemplateTrie
from logtemplates.io_utils import JSONLReader
from logtemplates.models import LogMatch, LogTemplate


class LogLineParser:
    """
    Parser for common log line formats.
    
    Extracts timestamp, level, logger, and message from log lines.
    """
    
    def __init__(self):
        # Common log patterns
        self.patterns = [
            # ISO timestamp with level: 2023-10-15T14:30:00.123Z INFO [main] com.example.Class - Message
            re.compile(r'^(?P<timestamp>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\s]*)\s+(?P<level>\w+)\s+(?:\[(?P<thread>[^\]]+)\])?\s*(?P<logger>[^\s-]+)?\s*-?\s*(?P<message>.+)$'),
            
            # Standard format: 2023-10-15 14:30:00.123 INFO  [main] com.example.Class: Message
            re.compile(r'^(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[^\s]*)\s+(?P<level>\w+)\s+(?:\[(?P<thread>[^\]]+)\])?\s*(?P<logger>[^\s:]+)?:?\s*(?P<message>.+)$'),
            
            # Simple format: INFO: Message
            re.compile(r'^(?P<level>\w+):\s*(?P<message>.+)$'),
            
            # Log4j format: INFO  2023-10-15 14:30:00,123 [main] com.example.Class - Message
            re.compile(r'^(?P<level>\w+)\s+(?P<timestamp>\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}[^\s]*)\s+(?:\[(?P<thread>[^\]]+)\])?\s*(?P<logger>[^\s-]+)?\s*-?\s*(?P<message>.+)$'),
            
            # Fallback: treat entire line as message
            re.compile(r'^(?P<message>.+)$'),
        ]
    
    def parse_line(self, line: str) -> Dict[str, Optional[str]]:
        """
        Parse a log line and extract components.
        
        Returns:
            Dict with keys: timestamp, level, thread, logger, message
        """
        line = line.strip()
        if not line:
            return {}
        
        for pattern in self.patterns:
            match = pattern.match(line)
            if match:
                result = match.groupdict()
                # Ensure all expected keys exist
                for key in ['timestamp', 'level', 'thread', 'logger', 'message']:
                    if key not in result:
                        result[key] = None
                return result
        
        # Fallback: treat as message only
        return {
            'timestamp': None,
            'level': None,
            'thread': None,
            'logger': None,
            'message': line
        }


class LogMatchingReport:
    """
    Generates reports from log matching results.
    """
    
    def __init__(self):
        self.total_lines = 0
        self.matched_lines = 0
        self.template_usage = defaultdict(int)
        self.level_stats = defaultdict(int)
        self.unmatched_samples = []
        self.max_unmatched_samples = 100
    
    def add_match(self, log_line: str, parsed_line: Dict, match: LogMatch):
        """Record a successful match."""
        self.total_lines += 1
        self.matched_lines += 1
        self.template_usage[match.template.template_id] += 1
        
        level = parsed_line.get('level', 'unknown')
        if level:
            self.level_stats[level.lower()] += 1
    
    def add_no_match(self, log_line: str, parsed_line: Dict):
        """Record a failed match."""
        self.total_lines += 1
        
        level = parsed_line.get('level', 'unknown')
        if level:
            self.level_stats[level.lower()] += 1
        
        # Sample unmatched lines for analysis
        if len(self.unmatched_samples) < self.max_unmatched_samples:
            message = parsed_line.get('message', log_line)
            self.unmatched_samples.append(message[:200])  # Truncate long messages
    
    def get_summary(self) -> Dict:
        """Get summary statistics."""
        match_rate = (self.matched_lines / self.total_lines * 100) if self.total_lines > 0 else 0
        
        return {
            'total_lines': self.total_lines,
            'matched_lines': self.matched_lines,
            'unmatched_lines': self.total_lines - self.matched_lines,
            'match_rate': match_rate,
            'unique_templates_used': len(self.template_usage),
            'level_distribution': dict(self.level_stats),
            'top_templates': sorted(self.template_usage.items(), key=lambda x: x[1], reverse=True)[:10],
            'unmatched_samples': self.unmatched_samples[:20]  # Show top 20 samples
        }


@click.command()
@click.option('--templates', '-t',
              required=True,
              type=click.Path(exists=True),
              help='Path to templates JSONL file')
@click.option('--input', '--in', 'input_file',
              required=True,
              type=click.Path(exists=True),
              help='Input log file to match')
@click.option('--output', '--out', 'output_file',
              required=True,
              type=click.Path(),
              help='Output CSV file for match results')
@click.option('--format',
              type=click.Choice(['csv', 'jsonl', 'summary']),
              default='csv',
              help='Output format (default: csv)')
@click.option('--threshold',
              type=float,
              default=0.0,
              help='Minimum confidence threshold for matches (0.0-1.0)')
@click.option('--best-only',
              is_flag=True,
              help='Only report the best match per line (default: all matches above threshold)')
@click.option('--level-filter',
              help='Filter log lines by level (e.g., "ERROR,WARN")')
@click.option('--verbose', '-v',
              is_flag=True,
              help='Enable verbose output')
@click.option('--sample-lines',
              type=int,
              help='Process only first N lines (for testing)')
def match_logs(templates: str,
               input_file: str,
               output_file: str,
               format: str,
               threshold: float,
               best_only: bool,
               level_filter: str,
               verbose: bool,
               sample_lines: int):
    """
    Match runtime log lines to extracted templates.
    
    This tool reads log lines from a file and matches them against extracted
    templates using a trie-based matcher. Results include template ID,
    confidence score, and extracted placeholder values.
    
    Examples:
    
    \b
    # Basic matching with CSV output
    python match_logs.py --templates templates.jsonl --in server.log --out matches.csv
    
    \b
    # Only high-confidence matches for errors
    python match_logs.py --templates templates.jsonl --in error.log \\
        --out error_matches.csv --threshold 0.8 --level-filter ERROR
    
    \b
    # Generate summary report
    python match_logs.py --templates templates.jsonl --in server.log \\
        --out summary.txt --format summary
    """
    
    if threshold < 0.0 or threshold > 1.0:
        click.echo("Error: Threshold must be between 0.0 and 1.0")
        sys.exit(1)
    
    try:
        # Load templates
        if verbose:
            click.echo(f"Loading templates from: {templates}")
        
        reader = JSONLReader(templates)
        template_list = reader.read_templates()
        
        if not template_list:
            click.echo("Error: No templates found in templates file")
            sys.exit(1)
        
        if verbose:
            click.echo(f"Loaded {len(template_list)} templates")
        
        # Build trie
        trie = TemplateTrie()
        for template in template_list:
            trie.add_template(template)
        
        if verbose:
            click.echo(f"Built trie with {trie.size()} templates")
        
        # Parse level filter
        allowed_levels = None
        if level_filter:
            allowed_levels = set(level.strip().upper() for level in level_filter.split(','))
            if verbose:
                click.echo(f"Filtering by levels: {allowed_levels}")
        
        # Initialize parser and report
        parser = LogLineParser()
        report = LogMatchingReport()
        
        # Process log file
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        if format == 'csv':
            _process_logs_csv(input_file, trie, parser, report, output_path, 
                            threshold, best_only, allowed_levels, verbose, sample_lines)
        elif format == 'jsonl':
            _process_logs_jsonl(input_file, trie, parser, report, output_path,
                              threshold, best_only, allowed_levels, verbose, sample_lines)
        elif format == 'summary':
            _process_logs_summary(input_file, trie, parser, report, output_path,
                                threshold, best_only, allowed_levels, verbose, sample_lines)
        
        # Print summary
        summary = report.get_summary()
        click.echo(f"\n✅ Matching completed!")
        click.echo(f"📊 Results:")
        click.echo(f"   • Total lines processed: {summary['total_lines']}")
        click.echo(f"   • Matched lines: {summary['matched_lines']}")
        click.echo(f"   • Match rate: {summary['match_rate']:.1f}%")
        click.echo(f"   • Unique templates used: {summary['unique_templates_used']}")
        click.echo(f"   • Output file: {output_path.absolute()}")
        
        if verbose and summary['unmatched_lines'] > 0:
            click.echo(f"\n🔍 Sample unmatched lines:")
            for i, sample in enumerate(summary['unmatched_samples'][:5], 1):
                click.echo(f"   {i}. {sample}")
            if len(summary['unmatched_samples']) > 5:
                click.echo(f"   ... and {len(summary['unmatched_samples']) - 5} more")
        
    except KeyboardInterrupt:
        click.echo("\n❌ Matching cancelled by user")
        sys.exit(1)
    except Exception as e:
        click.echo(f"\n❌ Error during matching: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


def _process_logs_csv(input_file: str, trie: TemplateTrie, parser: LogLineParser,
                     report: LogMatchingReport, output_path: Path,
                     threshold: float, best_only: bool, allowed_levels: Optional[set],
                     verbose: bool, sample_lines: Optional[int]):
    """Process logs and write CSV output."""
    
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as infile, \
         open(output_path, 'w', newline='', encoding='utf-8') as outfile:
        
        writer = csv.writer(outfile)
        
        # Write header
        writer.writerow([
            'line_number', 'timestamp', 'level', 'logger', 'message',
            'template_id', 'confidence', 'pattern', 'extracted_values',
            'source_file', 'source_line'
        ])
        
        line_num = 0
        for line in infile:
            line_num += 1
            
            if sample_lines and line_num > sample_lines:
                break
            
            if verbose and line_num % 10000 == 0:
                click.echo(f"Processed {line_num} lines...")
            
            # Parse log line
            parsed = parser.parse_line(line)
            message = parsed.get('message', '').strip()
            
            if not message:
                continue
            
            # Apply level filter
            if allowed_levels:
                log_level = parsed.get('level', '').upper()
                if log_level not in allowed_levels:
                    continue
            
            # Match against templates
            level_hint = parsed.get('level')
            matches = trie.match(message, level_hint)
            
            # Filter by threshold
            matches = [m for m in matches if m.confidence >= threshold]
            
            if best_only and matches:
                matches = [matches[0]]  # Already sorted by specificity
            
            if matches:
                # Write all matches
                for match in matches:
                    report.add_match(line, parsed, match)
                    
                    # Format extracted values
                    extracted_str = ' | '.join(match.extracted_values) if match.extracted_values else ''
                    
                    writer.writerow([
                        line_num,
                        parsed.get('timestamp', ''),
                        parsed.get('level', ''),
                        parsed.get('logger', ''),
                        message,
                        match.template.template_id,
                        f"{match.confidence:.3f}",
                        match.template.pattern,
                        extracted_str,
                        match.template.location.file_path,
                        match.template.location.line_number
                    ])
            else:
                # No match found
                report.add_no_match(line, parsed)
                
                # Write empty match row
                writer.writerow([
                    line_num,
                    parsed.get('timestamp', ''),
                    parsed.get('level', ''),
                    parsed.get('logger', ''),
                    message,
                    '', '', '', '', '', ''
                ])


def _process_logs_jsonl(input_file: str, trie: TemplateTrie, parser: LogLineParser,
                       report: LogMatchingReport, output_path: Path,
                       threshold: float, best_only: bool, allowed_levels: Optional[set],
                       verbose: bool, sample_lines: Optional[int]):
    """Process logs and write JSONL output."""
    
    import json
    
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        line_num = 0
        for line in infile:
            line_num += 1
            
            if sample_lines and line_num > sample_lines:
                break
            
            if verbose and line_num % 10000 == 0:
                click.echo(f"Processed {line_num} lines...")
            
            # Parse log line
            parsed = parser.parse_line(line)
            message = parsed.get('message', '').strip()
            
            if not message:
                continue
            
            # Apply level filter
            if allowed_levels:
                log_level = parsed.get('level', '').upper()
                if log_level not in allowed_levels:
                    continue
            
            # Match against templates
            level_hint = parsed.get('level')
            matches = trie.match(message, level_hint)
            
            # Filter by threshold
            matches = [m for m in matches if m.confidence >= threshold]
            
            if best_only and matches:
                matches = [matches[0]]
            
            # Create result object
            result = {
                'line_number': line_num,
                'timestamp': parsed.get('timestamp'),
                'level': parsed.get('level'),
                'logger': parsed.get('logger'),
                'message': message,
                'matches': []
            }
            
            if matches:
                for match in matches:
                    report.add_match(line, parsed, match)
                    
                    match_data = {
                        'template_id': match.template.template_id,
                        'confidence': match.confidence,
                        'pattern': match.template.pattern,
                        'extracted_values': match.extracted_values,
                        'source_location': {
                            'file': match.template.location.file_path,
                            'line': match.template.location.line_number,
                            'class': match.template.location.class_name,
                            'method': match.template.location.method_name
                        }
                    }
                    result['matches'].append(match_data)
            else:
                report.add_no_match(line, parsed)
            
            # Write JSONL
            json.dump(result, outfile, ensure_ascii=False)
            outfile.write('\n')


def _process_logs_summary(input_file: str, trie: TemplateTrie, parser: LogLineParser,
                         report: LogMatchingReport, output_path: Path,
                         threshold: float, best_only: bool, allowed_levels: Optional[set],
                         verbose: bool, sample_lines: Optional[int]):
    """Process logs and write summary report."""
    
    # First pass: collect statistics
    with open(input_file, 'r', encoding='utf-8', errors='ignore') as infile:
        line_num = 0
        for line in infile:
            line_num += 1
            
            if sample_lines and line_num > sample_lines:
                break
            
            if verbose and line_num % 10000 == 0:
                click.echo(f"Processed {line_num} lines...")
            
            # Parse log line
            parsed = parser.parse_line(line)
            message = parsed.get('message', '').strip()
            
            if not message:
                continue
            
            # Apply level filter
            if allowed_levels:
                log_level = parsed.get('level', '').upper()
                if log_level not in allowed_levels:
                    continue
            
            # Match against templates
            level_hint = parsed.get('level')
            matches = trie.match(message, level_hint)
            
            # Filter by threshold
            matches = [m for m in matches if m.confidence >= threshold]
            
            if best_only and matches:
                matches = [matches[0]]
            
            if matches:
                report.add_match(line, parsed, matches[0])
            else:
                report.add_no_match(line, parsed)
    
    # Write summary report
    summary = report.get_summary()
    
    with open(output_path, 'w', encoding='utf-8') as outfile:
        outfile.write("LOG TEMPLATE MATCHING SUMMARY REPORT\n")
        outfile.write("=" * 50 + "\n\n")
        
        outfile.write(f"Input file: {input_file}\n")
        outfile.write(f"Total lines processed: {summary['total_lines']}\n")
        outfile.write(f"Matched lines: {summary['matched_lines']}\n")
        outfile.write(f"Unmatched lines: {summary['unmatched_lines']}\n")
        outfile.write(f"Match rate: {summary['match_rate']:.1f}%\n")
        outfile.write(f"Unique templates used: {summary['unique_templates_used']}\n\n")
        
        # Level distribution
        outfile.write("LOG LEVEL DISTRIBUTION:\n")
        outfile.write("-" * 25 + "\n")
        for level, count in sorted(summary['level_distribution'].items()):
            percentage = (count / summary['total_lines']) * 100 if summary['total_lines'] > 0 else 0
            outfile.write(f"{level:8}: {count:8} ({percentage:5.1f}%)\n")
        outfile.write("\n")
        
        # Top templates
        if summary['top_templates']:
            outfile.write("TOP TEMPLATES BY USAGE:\n")
            outfile.write("-" * 25 + "\n")
            for i, (template_id, count) in enumerate(summary['top_templates'], 1):
                outfile.write(f"{i:2}. [{count:6}x] {template_id}\n")
            outfile.write("\n")
        
        # Unmatched samples
        if summary['unmatched_samples']:
            outfile.write("SAMPLE UNMATCHED LINES:\n")
            outfile.write("-" * 25 + "\n")
            for i, sample in enumerate(summary['unmatched_samples'], 1):
                outfile.write(f"{i:2}. {sample}\n")


if __name__ == '__main__':
    match_logs()

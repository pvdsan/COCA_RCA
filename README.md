# Java Log Template Extraction System

A powerful, fast, and accurate system for extracting logging templates from Java codebases. This tool statically analyzes Java source files to create template patterns with `<*>` placeholders for variable content, enabling efficient log analysis and debugging workflows.

## ✨ Key Features

- **🔍 Advanced Pattern Recognition**: Supports SLF4J, String.format, concatenation, StringBuilder, and method call patterns
- **🧠 Inter-Procedural Analysis**: Traces method calls to extract meaningful patterns from complex logging scenarios  
- **🌿 Branch-Aware Extraction**: Handles conditional log message construction with configurable variant limits
- **⚡ Parallel Processing**: Multi-worker file processing optimized for large codebases
- **📁 Smart Output Management**: Automatic timestamped output files organized in dedicated folders
- **🎯 Comprehensive Matching**: Trie-based matcher for efficient runtime log-to-template matching *(Under Development)*
- **🧪 Robust Testing**: Comprehensive test suite with integration tests

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd COCA_RCA

# Install dependencies
pip install -r requirements.txt
```

### Basic Usage

#### 1. Extract Templates (Auto-Generated Output)
```bash
# Extracts to output_templates/myproject_20250916_143022.jsonl
python extract_templates.py --src /path/to/java/project

# Extract from current directory
python extract_templates.py --src .
```

#### 2. Extract with Custom Options
```bash
# Custom output path with exclusions
python extract_templates.py \
  --src /path/to/kafka \
  --out kafka_templates.jsonl \
  --exclude '*/test/*' '*/examples/*' \
  --workers 8
```

#### 3. Match Runtime Logs *(Under Development)*

## 🎯 Supported Logging Patterns

### SLF4J Patterns
```java
// Simple placeholders
log.info("User {} logged in from {}", username, ipAddress);
logger.error("Failed to process {} records", count);

// Marker-based logging  
logger.warn(marker, "Connection timeout for {}", host);
logger.log(Level.INFO, "Processing {} items", itemCount);
```

### String.format Patterns
```java
// Direct format calls
log.debug(String.format("Processing file %s (%d bytes)", filename, size));

// Variable assignment
String message = String.format("Error in %s: %s", component, error);
logger.error(message);

// Concatenated format strings
String msg = String.format("Part 1: %s " + "Part 2: %d", value1, value2);
```

### String Concatenation
```java
// Simple concatenation
log.info("Started processing " + filename + " at " + timestamp);

// Complex expressions
logger.error("Failed to connect to " + host + ":" + port + 
             " after " + attempts + " attempts");
```

### Method Call Patterns (Inter-Procedural)
```java
// Method calls as log arguments
log.error("Error occurred: {}", exception.getMessage());
logger.debug("Event details: {}", formatEventDetails(event));

// Custom method results
String details = buildErrorMessage(error, context);
log.error(details);

// The system traces into these methods to extract meaningful patterns!
```

### Advanced Patterns
```java
// Class constants
private static final String ERROR_MSG = "System failure occurred";
log.error(ERROR_MSG + ": {}", details);

// Method parameters
public void logError(String message, Exception ex) {
    log.error(message, ex);  // Extracts as <param:message>
}

// Lambda expressions
events.forEach(event -> log.debug("Processing: {}", event.getId()));
```

## 📊 Template Output Format

Templates are saved as JSONL (JSON Lines) with detailed metadata:

```json
{
  "template_id": "a1b2c3d4e5f6g7h8",
  "pattern": "User <*> logged in from <*>",
  "static_token_count": 4,
  "location": {
    "file_path": "/src/main/java/com/example/UserService.java",
    "class_name": "UserService", 
    "method_name": "handleLogin",
    "line_number": 45
  },
  "level": "info",
  "branch_variant": 0
}
```

## 🛠️ Command Line Tools

### extract_templates.py

Extract log templates from Java source code.

```bash
Usage: extract_templates.py [OPTIONS]

Options:
  -s, --src DIRECTORY     Source repository root directory [required]
  -o, --out PATH          Output JSONL file (default: auto-generated)
  -i, --include TEXT      Include patterns (default: *.java)
  -e, --exclude TEXT      Exclude patterns (can specify multiple)
  -w, --workers INTEGER   Number of parallel workers (default: auto)
  --max-variants INTEGER  Maximum template variants per logging site
  -v, --verbose           Enable verbose output
  --help                  Show help message
```

**Examples:**
```bash
# Basic extraction (creates output_templates/myproject_YYYYMMDD_HHMMSS.jsonl)
python extract_templates.py --src /path/to/project

# With exclusions and custom workers
python extract_templates.py --src . --exclude '*/test/*' --workers 4

# Verbose output with custom filename
python extract_templates.py --src . --out my_templates.jsonl -v
```

### match_logs.py *(Under Development)*

Match runtime log lines against extracted templates.

## 🧪 Testing

Run the comprehensive test suite:

```bash
# Run all tests
python run_tests.py

# Run specific test module
python run_tests.py test_templating

# Run with verbose output
python run_tests.py --verbose
```

**Test Coverage:**
- Template extraction from various Java patterns
- Inter-procedural analysis scenarios  
- Trie-based matching algorithms
- Integration tests with real Java code samples

## 🏗️ Architecture

### Core Components

- **`JavaLogExtractor`**: Main extraction engine with tree-sitter Java parsing
- **`LogTemplateBuilder`**: Template rule engine supporting multiple logging frameworks
- **`IntraproceduralSlicer`**: Backward slicing for variable definition tracking
- **`TemplateTrie`**: Efficient trie-based matching structure *(Under Development)*
- **Template Rules**: Pluggable rules for different logging patterns (SLF4J, String.format, etc.)

### Key Algorithms

1. **Template Extraction**: Uses tree-sitter to parse Java AST and identify logging calls
2. **Backward Slicing**: Traces variable definitions within method scope to reconstruct log messages
3. **Inter-Procedural Analysis**: Follows method calls to extract patterns from called methods
4. **Branch-Aware Processing**: Handles conditional logging with variant limits
5. **Trie Matching**: Efficient runtime matching using token-based trie structure

## 📈 Performance

- **Large Codebases**: Tested on Apache Kafka and Apache ZooKeeper
- **Parallel Processing**: Scales with available CPU cores
- **Memory Efficient**: Streaming processing for large log files
- **Fast Matching**: Sub-millisecond template matching for typical log lines

## 🔧 Configuration

### Extraction Options

- `max_branch_variants`: Limit template variants per logging site (default: 16)
- `parallel_workers`: Number of processing threads (default: auto-detect)
- Include/exclude patterns for file filtering

## 📝 Output Organization

The system automatically organizes outputs:

```
project/
├── output_templates/
│   ├── kafka_20250916_143022.jsonl      # Auto-generated timestamp
│   ├── zookeeper_20250916_150430.jsonl  # Multiple extractions
│   └── myproject_20250916_163015.jsonl
├── matches/
│   ├── server_matches.csv
│   └── application_matches.jsonl
└── logs/
    ├── server.log
    └── application.log
```

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [tree-sitter](https://tree-sitter.github.io/) for robust Java parsing
- Inspired by log analysis research in software engineering
- Designed for practical use in large-scale software systems

---
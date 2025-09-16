"""
Java code samples for testing template extraction.
"""

# SLF4J logging samples
SLF4J_SAMPLES = {
    "basic": '''
public class UserService {
    private static final Logger log = LoggerFactory.getLogger(UserService.class);
    
    public void loginUser(String username, String ipAddress) {
        log.info("User {} logged in from {}", username, ipAddress);
        log.debug("Login attempt for user: {}", username);
    }
    
    public void processOrder(int orderId, double amount) {
        log.warn("Processing large order {} with amount ${}", orderId, amount);
        log.error("Failed to process order {}", orderId);
    }
}
''',
    
    "complex": '''
public class TransactionProcessor {
    private static final Logger logger = LoggerFactory.getLogger(TransactionProcessor.class);
    
    public void processTransaction(Transaction tx) {
        logger.trace("Starting transaction processing for {}", tx.getId());
        
        if (tx.getAmount() > 10000) {
            logger.warn("Large transaction detected: {} amount={} user={}", 
                       tx.getId(), tx.getAmount(), tx.getUserId());
        }
        
        try {
            processInternal(tx);
            logger.info("Successfully processed transaction {}", tx.getId());
        } catch (Exception e) {
            logger.error("Transaction {} failed with error: {}", tx.getId(), e.getMessage());
            logger.debug("Full exception details for {}", tx.getId(), e);
        }
    }
}
''',
    
    "nested": '''
public class OrderHandler {
    private final Logger LOG = LoggerFactory.getLogger(OrderHandler.class);
    
    public void handleOrder(Order order) {
        for (OrderItem item : order.getItems()) {
            if (item.getQuantity() > 100) {
                LOG.warn("High quantity order item: {} quantity={} order={}", 
                        item.getProductId(), item.getQuantity(), order.getId());
            }
            
            if (item.getPrice() <= 0) {
                LOG.error("Invalid price for item {} in order {}: price={}", 
                         item.getProductId(), order.getId(), item.getPrice());
                continue;
            }
            
            LOG.debug("Processing item {} for order {}", item.getProductId(), order.getId());
        }
    }
}
'''
}

# String.format samples
STRING_FORMAT_SAMPLES = {
    "basic": '''
public class ReportGenerator {
    public void generateReport(String reportType, int recordCount) {
        String message = String.format("Generated %s report with %d records", reportType, recordCount);
        System.out.println(message);
        
        log.info(String.format("Report generation completed: type=%s, records=%d", 
                               reportType, recordCount));
    }
    
    public void logError(String operation, double value) {
        logger.error(String.format("Operation %s failed with value %.2f", operation, value));
    }
}
''',
    
    "complex": '''
public class MetricsCollector {
    public void logMetrics(String service, long responseTime, int errorCount, double successRate) {
        String summary = String.format(
            "Service %s metrics: response_time=%dms errors=%d success_rate=%.1f%%",
            service, responseTime, errorCount, successRate
        );
        
        if (errorCount > 0) {
            logger.warn(String.format("Service %s has %d errors (success rate: %.2f%%)", 
                                    service, errorCount, successRate));
        }
        
        logger.info(summary);
    }
}
'''
}

# String concatenation samples
CONCATENATION_SAMPLES = {
    "simple": '''
public class NotificationService {
    private Logger log = LoggerFactory.getLogger(NotificationService.class);
    
    public void sendNotification(String userId, String message) {
        log.info("Sending notification to user " + userId + ": " + message);
        log.debug("Notification payload size: " + message.length() + " characters");
    }
    
    public void handleError(String operation, Exception ex) {
        log.error("Error in " + operation + ": " + ex.getMessage());
        log.warn("Operation " + operation + " failed, retrying...");
    }
}
''',
    
    "complex": '''
public class ConnectionManager {
    public void logConnection(String host, int port, String protocol, boolean secure) {
        String prefix = "Connecting to ";
        String location = host + ":" + port;
        String details = " using " + protocol + (secure ? " (secure)" : " (insecure)");
        
        logger.info(prefix + location + details);
        
        if (!secure) {
            logger.warn("Insecure connection to " + host + ":" + port + 
                       " - consider using secure " + protocol);
        }
    }
}
'''
}

# StringBuilder samples
STRINGBUILDER_SAMPLES = {
    "basic": '''
public class QueryBuilder {
    private Logger logger = LoggerFactory.getLogger(QueryBuilder.class);
    
    public void executeQuery(String table, List<String> columns, String whereClause) {
        StringBuilder query = new StringBuilder()
            .append("SELECT ")
            .append(String.join(", ", columns))
            .append(" FROM ")
            .append(table);
            
        if (whereClause != null) {
            query.append(" WHERE ").append(whereClause);
        }
        
        logger.debug("Executing query: " + query.toString());
        logger.info(new StringBuilder("Query execution started for table ").append(table).toString());
    }
}
''',
    
    "complex": '''
public class MessageFormatter {
    public void formatComplexMessage(String event, Map<String, Object> context, long timestamp) {
        StringBuilder msg = new StringBuilder("Event: ").append(event);
        
        for (Map.Entry<String, Object> entry : context.entrySet()) {
            msg.append(" ").append(entry.getKey()).append("=").append(entry.getValue());
        }
        
        msg.append(" at ").append(new Date(timestamp));
        
        logger.info(msg.toString());
        
        // Alternative pattern
        String formatted = new StringBuilder()
            .append("Processing event ")
            .append(event)
            .append(" with ")
            .append(context.size())
            .append(" context parameters")
            .toString();
            
        logger.debug(formatted);
    }
}
'''
}

# Variable assignment and slicing samples
VARIABLE_SAMPLES = {
    "simple": '''
public class AlertManager {
    private static final Logger log = LoggerFactory.getLogger(AlertManager.class);
    
    public void sendAlert(String alertType, String message, int severity) {
        String logMessage = "Alert: " + alertType + " - " + message;
        log.warn(logMessage);
        
        String details = String.format("Alert severity: %d, type: %s", severity, alertType);
        log.info(details);
    }
}
''',
    
    "complex": '''
public class BatchProcessor {
    public void processBatch(List<Item> items, String batchId) {
        String statusMsg;
        
        if (items.isEmpty()) {
            statusMsg = "Empty batch received: " + batchId;
            logger.warn(statusMsg);
        } else {
            statusMsg = "Processing batch " + batchId + " with " + items.size() + " items";
            logger.info(statusMsg);
            
            for (Item item : items) {
                String itemMsg = "Processing item " + item.getId() + " in batch " + batchId;
                logger.debug(itemMsg);
                
                if (item.isExpired()) {
                    String errorMsg = String.format("Expired item %s found in batch %s", 
                                                   item.getId(), batchId);
                    logger.error(errorMsg);
                }
            }
        }
    }
}
''',
    
    "branching": '''
public class PaymentProcessor {
    public void processPayment(Payment payment) {
        String message;
        String paymentId = payment.getId();
        double amount = payment.getAmount();
        
        if (payment.getType() == PaymentType.CREDIT_CARD) {
            message = "Processing credit card payment " + paymentId + " for $" + amount;
        } else if (payment.getType() == PaymentType.BANK_TRANSFER) {
            message = "Processing bank transfer " + paymentId + " amount: $" + amount;
        } else {
            message = "Processing payment " + paymentId + " of unknown type";
        }
        
        logger.info(message);
        
        // Another branching pattern
        String status;
        if (amount > 1000) {
            status = "Large payment " + paymentId + " requires approval";
            logger.warn(status);
        } else {
            status = "Standard payment " + paymentId + " auto-approved";
            logger.info(status);
        }
    }
}
'''
}

# Mixed patterns
MIXED_SAMPLES = {
    "kitchen_sink": '''
public class OrderService {
    private static final Logger log = LoggerFactory.getLogger(OrderService.class);
    
    public void processOrder(Order order) {
        // SLF4J pattern
        log.info("Processing order {}", order.getId());
        
        // String concatenation
        String userMsg = "Order " + order.getId() + " for user " + order.getUserId();
        log.debug(userMsg);
        
        // String.format
        String summary = String.format("Order %s: %d items, total $%.2f", 
                                      order.getId(), order.getItemCount(), order.getTotal());
        log.info(summary);
        
        // StringBuilder
        StringBuilder details = new StringBuilder("Order details: ")
            .append("id=").append(order.getId())
            .append(", status=").append(order.getStatus())
            .append(", created=").append(order.getCreatedDate());
        log.debug(details.toString());
        
        // Variable with conditional
        String statusMsg;
        if (order.isPriority()) {
            statusMsg = "Priority order " + order.getId() + " - expedited processing";
        } else {
            statusMsg = "Standard order " + order.getId() + " - normal processing";
        }
        log.info(statusMsg);
    }
}
'''
}

# Test samples with expected outputs
TEST_CASES = [
    {
        "name": "slf4j_basic",
        "java_code": SLF4J_SAMPLES["basic"],
        "expected_patterns": [
            "User <*> logged in from <*>",
            "Login attempt for user: <*>",
            "Processing large order <*> with amount $<*>",
            "Failed to process order <*>"
        ]
    },
    {
        "name": "string_format_basic", 
        "java_code": STRING_FORMAT_SAMPLES["basic"],
        "expected_patterns": [
            "Generated <*> report with <*> records",
            "Report generation completed: type=<*>, records=<*>",
            "Operation <*> failed with value <*>"
        ]
    },
    {
        "name": "concatenation_simple",
        "java_code": CONCATENATION_SAMPLES["simple"],
        "expected_patterns": [
            "Sending notification to user <*>: <*>",
            "Notification payload size: <*> characters",
            "Error in <*>: <*>",
            "Operation <*> failed, retrying..."
        ]
    },
    {
        "name": "stringbuilder_basic",
        "java_code": STRINGBUILDER_SAMPLES["basic"],
        "expected_patterns": [
            "Executing query: <*>",
            "Query execution started for table <*>"
        ]
    },
    {
        "name": "variable_simple",
        "java_code": VARIABLE_SAMPLES["simple"],
        "expected_patterns": [
            "Alert: <*> - <*>",
            "Alert severity: <*>, type: <*>"
        ]
    }
]

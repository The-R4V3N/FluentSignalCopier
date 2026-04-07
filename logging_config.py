# logging_config.py - Logging system for FluentSignalCopier

# Licensed under the Attribution-NonCommercial-ShareAlike 4.0 International
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

import logging
import logging.handlers
import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
from dataclasses import dataclass, asdict
import sys
import traceback

@dataclass
class LogMetrics:
    """Track logging metrics for monitoring"""
    total_messages: int = 0
    error_count: int = 0
    warning_count: int = 0
    signal_count: int = 0
    trade_count: int = 0
    last_activity: float = 0
    start_time: float = 0

class StructuredFormatter(logging.Formatter):
    """JSON formatter for structured logging"""
    
    def format(self, record):
        log_entry = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info)
            }
        
        # Add custom fields if present
        if hasattr(record, 'extra_data'):
            log_entry.update(record.extra_data)
            
        return json.dumps(log_entry, ensure_ascii=False)

class TradingLogger:
    """Enhanced logger specifically designed for trading applications"""
    
    def __init__(self, name: str, log_dir: Path, max_bytes: int = 50*1024*1024, backup_count: int = 10):
        self.name = name
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.metrics = LogMetrics(start_time=time.time())
        self._lock = threading.Lock()
        
        # Create logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers.clear()  # Remove any existing handlers
        
        # File handlers
        self._setup_file_handlers(max_bytes, backup_count)
        
        # Console handler
        self._setup_console_handler()
        
        # Start metrics tracking
        self._start_metrics_thread()
    
    def _setup_file_handlers(self, max_bytes: int, backup_count: int):
        """Setup rotating file handlers for different log levels"""
        
        # Main log file (all levels) - JSON format
        main_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f"{self.name}.log",
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        main_handler.setLevel(logging.DEBUG)
        main_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(main_handler)
        
        # Error log file (errors only) - JSON format
        error_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f"{self.name}_errors.log",
            maxBytes=max_bytes // 5,
            backupCount=backup_count,
            encoding='utf-8'
        )
        error_handler.setLevel(logging.ERROR)
        error_handler.setFormatter(StructuredFormatter())
        self.logger.addHandler(error_handler)
        
        # Trading activity log (signals and trades) - Human readable
        trading_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        trading_handler = logging.handlers.RotatingFileHandler(
            self.log_dir / f"{self.name}_trading.log",
            maxBytes=max_bytes // 2,
            backupCount=backup_count,
            encoding='utf-8'
        )
        trading_handler.setLevel(logging.INFO)
        trading_handler.addFilter(lambda record: hasattr(record, 'is_trading'))
        trading_handler.setFormatter(trading_formatter)
        self.logger.addHandler(trading_handler)
    
    def _setup_console_handler(self):
        """Setup console handler with colored output"""
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        
        # Colored formatter for console
        class ColoredFormatter(logging.Formatter):
            COLORS = {
                'DEBUG': '\033[36m',    # Cyan
                'INFO': '\033[32m',     # Green
                'WARNING': '\033[33m',  # Yellow
                'ERROR': '\033[31m',    # Red
                'CRITICAL': '\033[35m', # Magenta
                'RESET': '\033[0m'      # Reset
            }
            
            def format(self, record):
                log_color = self.COLORS.get(record.levelname, self.COLORS['RESET'])
                record.levelname = f"{log_color}{record.levelname}{self.COLORS['RESET']}"
                return super().format(record)
        
        console_formatter = ColoredFormatter(
            '[%(asctime)s] %(levelname)s %(name)s: %(message)s',
            datefmt='%H:%M:%S'
        )
        console_handler.setFormatter(console_formatter)
        self.logger.addHandler(console_handler)
    
    def _start_metrics_thread(self):
        """Start background thread for metrics collection"""
        def collect_metrics():
            while True:
                time.sleep(60)  # Update metrics every minute
                self._write_metrics()
        
        metrics_thread = threading.Thread(target=collect_metrics, daemon=True)
        metrics_thread.start()
    
    def _write_metrics(self):
        """Write current metrics to file"""
        try:
            metrics_file = self.log_dir / f"{self.name}_metrics.json"
            with self._lock:
                current_metrics = asdict(self.metrics)
                current_metrics['uptime_seconds'] = time.time() - self.metrics.start_time
                current_metrics['timestamp'] = datetime.now().isoformat()
            
            with open(metrics_file, 'w', encoding='utf-8') as f:
                json.dump(current_metrics, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self.logger.error(f"Failed to write metrics: {e}")
    
    def _log_with_metrics(self, level: int, msg: str, extra_data: Optional[Dict[str, Any]] = None):
        """Internal logging with metrics tracking"""
        with self._lock:
            self.metrics.total_messages += 1
            self.metrics.last_activity = time.time()
            
            if level >= logging.ERROR:
                self.metrics.error_count += 1
            elif level >= logging.WARNING:
                self.metrics.warning_count += 1
        
        # Create log record with extra data
        if extra_data:
            record = self.logger.makeRecord(
                self.logger.name, level, "", 0, msg, (), None
            )
            record.extra_data = extra_data
            self.logger.handle(record)
        else:
            self.logger.log(level, msg)
    
    # Public logging methods
    def debug(self, msg: str, **kwargs):
        self._log_with_metrics(logging.DEBUG, msg, kwargs if kwargs else None)
    
    def info(self, msg: str, **kwargs):
        self._log_with_metrics(logging.INFO, msg, kwargs if kwargs else None)
    
    def warning(self, msg: str, **kwargs):
        self._log_with_metrics(logging.WARNING, msg, kwargs if kwargs else None)
    
    def error(self, msg: str, exception: Optional[Exception] = None, **kwargs):
        if exception:
            self.logger.error(msg, exc_info=exception, extra={'extra_data': kwargs} if kwargs else None)
        else:
            self._log_with_metrics(logging.ERROR, msg, kwargs if kwargs else None)
    
    def critical(self, msg: str, exception: Optional[Exception] = None, **kwargs):
        if exception:
            self.logger.critical(msg, exc_info=exception, extra={'extra_data': kwargs} if kwargs else None)
        else:
            self._log_with_metrics(logging.CRITICAL, msg, kwargs if kwargs else None)
    
    # Trading-specific logging methods
    def log_signal(self, action: str, symbol: str, source: str, details: Dict[str, Any] = None):
        """Log trading signal with specific formatting"""
        with self._lock:
            self.metrics.signal_count += 1
        
        msg = f"SIGNAL {action}: {symbol} from {source}"
        extra_data = {
            'signal_type': action,
            'symbol': symbol,
            'source': source,
            'is_trading': True
        }
        if details:
            extra_data.update(details)
        
        record = self.logger.makeRecord(
            self.logger.name, logging.INFO, "", 0, msg, (), None
        )
        record.extra_data = extra_data
        record.is_trading = True
        self.logger.handle(record)
    
    def log_trade(self, action: str, symbol: str, side: str, volume: float, price: float = None, 
                  ticket: int = None, success: bool = True, error: str = None):
        """Log trade execution with specific formatting"""
        with self._lock:
            self.metrics.trade_count += 1
        
        status = "SUCCESS" if success else "FAILED"
        msg = f"TRADE {action} {status}: {side} {volume} {symbol}"
        if price:
            msg += f" @ {price}"
        if ticket:
            msg += f" (#{ticket})"
        if error:
            msg += f" - {error}"
        
        extra_data = {
            'trade_action': action,
            'symbol': symbol,
            'side': side,
            'volume': volume,
            'price': price,
            'ticket': ticket,
            'success': success,
            'error': error,
            'is_trading': True
        }
        
        level = logging.INFO if success else logging.ERROR
        record = self.logger.makeRecord(
            self.logger.name, level, "", 0, msg, (), None
        )
        record.extra_data = extra_data
        record.is_trading = True
        self.logger.handle(record)
    
    def log_heartbeat(self, component: str, status: str, details: Dict[str, Any] = None):
        """Log heartbeat/health check information"""
        msg = f"HEARTBEAT {component}: {status}"
        extra_data = {
            'component': component,
            'status': status,
            'heartbeat': True
        }
        if details:
            extra_data.update(details)
        
        self.debug(msg, **extra_data)
    
    def log_connection(self, service: str, status: str, details: Dict[str, Any] = None):
        """Log connection status changes"""
        msg = f"CONNECTION {service}: {status}"
        extra_data = {
            'service': service,
            'connection_status': status
        }
        if details:
            extra_data.update(details)
        
        level = logging.INFO if status in ['CONNECTED', 'RECONNECTED'] else logging.WARNING
        self._log_with_metrics(level, msg, extra_data)
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        with self._lock:
            metrics = asdict(self.metrics)
            metrics['uptime_seconds'] = time.time() - self.metrics.start_time
            return metrics

# Factory function for easy logger creation
def create_logger(component: str, log_dir: str = "logs") -> TradingLogger:
    """Create a logger for a specific component"""
    return TradingLogger(
        name=f"fluent_{component}",
        log_dir=Path(log_dir),
        max_bytes=50*1024*1024,  # 50MB
        backup_count=10
    )

# Context manager for operation logging
class LogOperation:
    """Context manager for logging operations with timing"""
    
    def __init__(self, logger: TradingLogger, operation: str, **context):
        self.logger = logger
        self.operation = operation
        self.context = context
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        self.logger.debug(f"Starting {self.operation}", **self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        
        if exc_type:
            self.logger.error(
                f"Failed {self.operation} after {duration:.2f}s: {exc_val}",
                exception=exc_val,
                duration_seconds=duration,
                **self.context
            )
        else:
            self.logger.info(
                f"Completed {self.operation} in {duration:.2f}s",
                duration_seconds=duration,
                **self.context
            )

# Example usage and integration helper
def setup_application_logging(app_name: str = "fluent_copier") -> TradingLogger:
    """Setup application-wide logging"""
    
    # Create logs directory
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    
    # Create main logger
    logger = create_logger(app_name)
    
    # Log startup information
    logger.info("=" * 50)
    logger.info(f"Starting {app_name}")
    logger.info(f"Python version: {sys.version}")
    logger.info(f"Log directory: {log_dir.absolute()}")
    logger.info("=" * 50)
    
    # Setup global exception handler
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        
        logger.critical(
            "Uncaught exception",
            exception=exc_value,
            exc_type=exc_type.__name__
        )
    
    sys.excepthook = handle_exception
    
    return logger

if __name__ == "__main__":
    # Test the logging system
    logger = setup_application_logging("test")
    
    # Test different log levels
    logger.debug("Debug message", user_id=123)
    logger.info("Info message", session_id="abc123")
    logger.warning("Warning message", error_code=404)
    logger.error("Error message", stack_trace="example")
    
    # Test trading-specific logs
    logger.log_signal("OPEN", "XAUUSD", "Test Channel", {
        "side": "BUY",
        "entry": 2000.50,
        "sl": 1995.00,
        "tp": 2010.00
    })
    
    logger.log_trade("OPEN", "XAUUSD", "BUY", 0.1, 2000.50, 12345, True)
    logger.log_trade("CLOSE", "XAUUSD", "BUY", 0.1, 2010.00, 12345, False, "Insufficient margin")
    
    # Test operation logging
    with LogOperation(logger, "signal_processing", symbol="XAUUSD", source="VIP"):
        time.sleep(0.1)  # Simulate work
    
    # Show metrics
    print("\nCurrent metrics:")
    print(json.dumps(logger.get_metrics(), indent=2))
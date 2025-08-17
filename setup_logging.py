# setup_logging.py - Setup script for enhanced logging system
"""
Setup script for FluentSignalCopier enhanced logging system.

This script will:
1. Create necessary directory structure
2. Install required dependencies
3. Generate configuration files
4. Validate the setup
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any

def create_directories():
    """Create necessary directory structure"""
    directories = [
        "logs",
        "logs/archive",
        "config",
        "monitoring"
    ]
    
    print("Creating directory structure...")
    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"  ✓ Created: {directory}")

def install_dependencies():
    """Install required Python packages"""
    dependencies = [
        "rich>=13.0.0",  # For enhanced terminal display
        "aiohttp>=3.8.0",  # For webhook notifications
    ]
    
    print("\nInstalling optional dependencies...")
    for dep in dependencies:
        try:
            print(f"  Installing {dep}...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", dep])
            print(f"  ✓ Installed: {dep}")
        except subprocess.CalledProcessError as e:
            print(f"  ⚠ Failed to install {dep}: {e}")
            print(f"    You can install manually: pip install {dep}")

def create_alert_config():
    """Create alert configuration file"""
    config_path = Path("config/alert_config.json")
    
    if config_path.exists():
        print(f"\n⚠ Alert config already exists: {config_path}")
        return
    
    print(f"\nCreating alert configuration: {config_path}")
    
    config = {
        "email": {
            "enabled": False,
            "smtp_server": "smtp.gmail.com",
            "smtp_port": 587,
            "username": "your-email@gmail.com",
            "password": "your-app-password",
            "from_email": "your-email@gmail.com",
            "to_emails": ["admin@yourcompany.com"]
        },
        "webhook": {
            "enabled": False,
            "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
            "webhook_type": "slack"
        },
        "monitoring": {
            "check_interval": 30,
            "log_dir": "logs"
        },
        "rules": {
            "heartbeat_timeout": 300,
            "error_rate_threshold": 10,
            "signal_activity_timeout": 7200,
            "trade_failure_threshold": 3
        }
    }
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"  ✓ Created: {config_path}")
    print("  📝 Edit this file to configure email and webhook notifications")

def create_logging_config():
    """Create logging configuration file"""
    config_path = Path("config/logging_config.json")
    
    if config_path.exists():
        print(f"\n⚠ Logging config already exists: {config_path}")
        return
    
    print(f"\nCreating logging configuration: {config_path}")
    
    config = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "detailed": {
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(funcName)s:%(lineno)d - %(message)s"
            },
            "simple": {
                "format": "%(asctime)s - %(levelname)s - %(message)s"
            }
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": "INFO",
                "formatter": "simple",
                "stream": "ext://sys.stdout"
            },
            "file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "DEBUG",
                "formatter": "detailed",
                "filename": "logs/system.log",
                "maxBytes": 10485760,
                "backupCount": 5
            }
        },
        "loggers": {
            "fluent_copier": {
                "level": "DEBUG",
                "handlers": ["console", "file"],
                "propagate": False
            }
        },
        "root": {
            "level": "INFO",
            "handlers": ["console"]
        }
    }
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"  ✓ Created: {config_path}")

def create_monitoring_scripts():
    """Create monitoring helper scripts"""
    
    # Create start monitoring script
    monitor_script = Path("monitoring/start_monitor.py")
    print(f"\nCreating monitoring scripts...")
    
    monitor_code = '''#!/usr/bin/env python3
"""
Start the FluentSignalCopier monitoring dashboard.
Usage: python monitoring/start_monitor.py [--refresh 5] [--log-dir logs]
"""
import sys
sys.path.append('..')
from monitoring_dashboard import main

if __name__ == "__main__":
    main()
'''
    
    with open(monitor_script, 'w') as f:
        f.write(monitor_code)
    
    # Make executable on Unix systems
    if os.name != 'nt':
        os.chmod(monitor_script, 0o755)
    
    print(f"  ✓ Created: {monitor_script}")
    
    # Create start alerts script
    alerts_script = Path("monitoring/start_alerts.py")
    
    alerts_code = '''#!/usr/bin/env python3
"""
Start the FluentSignalCopier alert system.
Usage: python monitoring/start_alerts.py
"""
import sys
sys.path.append('..')
from alert_system import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())
'''
    
    with open(alerts_script, 'w') as f:
        f.write(alerts_code)
    
    if os.name != 'nt':
        os.chmod(alerts_script, 0o755)
    
    print(f"  ✓ Created: {alerts_script}")
    
    # Create batch/shell scripts for easy execution
    if os.name == 'nt':
        # Windows batch files
        with open("monitoring/monitor.bat", 'w') as f:
            f.write('@echo off\npython start_monitor.py %*\n')
        
        with open("monitoring/alerts.bat", 'w') as f:
            f.write('@echo off\npython start_alerts.py %*\n')
        
        print("  ✓ Created: monitor.bat, alerts.bat")
    else:
        # Unix shell scripts
        with open("monitoring/monitor.sh", 'w') as f:
            f.write('#!/bin/bash\npython3 start_monitor.py "$@"\n')
        
        with open("monitoring/alerts.sh", 'w') as f:
            f.write('#!/bin/bash\npython3 start_alerts.py "$@"\n')
        
        os.chmod("monitoring/monitor.sh", 0o755)
        os.chmod("monitoring/alerts.sh", 0o755)
        
        print("  ✓ Created: monitor.sh, alerts.sh")

def create_systemd_service():
    """Create systemd service file for Linux systems"""
    if os.name == 'nt':
        return  # Skip on Windows
    
    print("\nCreating systemd service file...")
    
    service_content = f'''[Unit]
Description=FluentSignalCopier Alert System
After=network.target

[Service]
Type=simple
User={os.getenv('USER', 'ubuntu')}
WorkingDirectory={Path.cwd()}
Environment=PATH={os.environ.get('PATH')}
ExecStart={sys.executable} -m alert_system
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
'''
    
    service_path = Path("config/fluent-alerts.service")
    with open(service_path, 'w') as f:
        f.write(service_content)
    
    print(f"  ✓ Created: {service_path}")
    print("  📝 To install as system service (run as root):")
    print(f"    sudo cp {service_path} /etc/systemd/system/")
    print("    sudo systemctl enable fluent-alerts")
    print("    sudo systemctl start fluent-alerts")

def create_readme():
    """Create setup README with instructions"""
    readme_path = Path("LOGGING_SETUP.md")
    
    readme_content = '''# FluentSignalCopier Enhanced Logging Setup

This directory contains the enhanced logging and monitoring system for FluentSignalCopier.

## 📁 Directory Structure

```
logs/                  # Log files (auto-created)
├── fluent_copier_*.log       # Main application logs
├── fluent_copier_*_errors.log  # Error-only logs
├── fluent_copier_*_trading.log # Trading activity logs
└── fluent_copier_*_metrics.json # Performance metrics

config/               # Configuration files
├── alert_config.json       # Alert system configuration
├── logging_config.json     # Logging configuration
└── fluent-alerts.service   # Systemd service file (Linux)

monitoring/           # Monitoring tools
├── start_monitor.py        # Dashboard launcher
├── start_alerts.py         # Alert system launcher
└── monitor.sh/bat          # Helper scripts
```

## 🚀 Quick Start

### 1. Start Real-time Monitoring Dashboard
```bash
# Terminal dashboard
python monitoring/start_monitor.py

# With custom refresh rate
python monitoring/start_monitor.py --refresh 3

# Single report (no live updates)
python monitoring/start_monitor.py --once
```

### 2. Start Alert System
```bash
# Start alert monitoring
python monitoring/start_alerts.py

# On Windows
monitoring\\alerts.bat

# On Linux/Mac
./monitoring/alerts.sh
```

### 3. Configure Notifications

Edit `config/alert_config.json` to enable email and webhook alerts:

```json
{
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "username": "your-email@gmail.com",
    "password": "your-app-password",
    "from_email": "your-email@gmail.com",
    "to_emails": ["admin@yourcompany.com"]
  },
  "webhook": {
    "enabled": true,
    "webhook_url": "https://hooks.slack.com/services/YOUR/SLACK/WEBHOOK",
    "webhook_type": "slack"
  }
}
```

## 📊 Monitoring Features

### Real-time Dashboard
- System uptime and health status
- Signal processing statistics
- Recent events and errors
- Performance metrics

### Alert System
- **Critical**: System heartbeat dead, emergency stops
- **Error**: High error rates, trade failures
- **Warning**: No activity, connection issues
- **Configurable**: Custom rules and thresholds

### Log Analysis
- Structured JSON logging
- Automatic log rotation
- Trading activity tracking
- Performance metrics collection

## 🔧 Integration with FluentSignalCopier

Add these imports to your `fluent_copier.py`:

```python
from logging_config import setup_application_logging, LogOperation
```

Initialize logging in your main classes:

```python
class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.app_logger = setup_application_logging("fluent_copier_gui")
        # ... rest of your code

class CopierThread(QThread):
    def __init__(self, cfg: AppConfig, parent=None):
        super().__init__(parent)
        self.logger = setup_application_logging("copier_thread")
        # ... rest of your code
```

## 📈 Performance Monitoring

### Metrics Collected
- Messages processed per minute
- Signals generated per hour
- Trade execution success rate
- Error rates and types
- System resource usage

### Health Checks
- Telegram connection status
- MT5 file system access
- Signal processing pipeline
- Trade execution pipeline

## 🚨 Alert Rules

### Default Rules
1. **Heartbeat Dead** (Critical) - System unresponsive > 5 minutes
2. **High Error Rate** (Error) - >10 errors in 10 minutes
3. **No Signal Activity** (Warning) - No signals > 2 hours
4. **Emergency Close** (Critical) - Emergency stop triggered
5. **Trade Failures** (Error) - >3 failed trades
6. **Connection Issues** (Warning) - Telegram disconnections

### Custom Rules
You can add custom alert rules by modifying the AlertManager class:

```python
manager.add_rule(AlertRule(
    name="Custom Rule",
    condition=lambda data: your_condition(data),
    level=AlertLevel.WARNING,
    message_template="Your custom message: {data}",
    cooldown_minutes=15
))
```

## 🔍 Troubleshooting

### Dashboard Not Working
- Check if logs directory exists and has recent files
- Verify Python path and dependencies
- Run with `--once` flag for single report

### Alerts Not Sending
- Verify `config/alert_config.json` settings
- Check email credentials and SMTP settings
- Test webhook URL manually
- Check alert system logs for errors

### Missing Log Data
- Ensure logging system is initialized in main application
- Check file permissions in logs directory
- Verify log rotation settings

## 🔧 Advanced Configuration

### Custom Log Levels
```python
# In your code
logger.debug("Detailed debugging info")
logger.info("General information")
logger.warning("Something unexpected happened")
logger.error("An error occurred")
logger.critical("Critical system failure")
```

### Trading-Specific Logging
```python
# Log signals
logger.log_signal("OPEN", "XAUUSD", "Trading Channel", {
    "side": "BUY",
    "entry": 2000.50,
    "confidence": 85
})

# Log trades
logger.log_trade("OPEN", "XAUUSD", "BUY", 0.1, 2000.50, 12345, True)

# Log with operation timing
with LogOperation(logger, "signal_processing", symbol="XAUUSD"):
    # Your signal processing code
    pass
```

## 📋 Maintenance

### Log Cleanup
Logs automatically rotate when they reach 50MB. Cleanup old logs:

```bash
# Keep only last 30 days
find logs/ -name "*.log.*" -mtime +30 -delete

# Archive old logs
tar -czf logs_backup_$(date +%Y%m%d).tar.gz logs/*.log.*
```

### Performance Optimization
- Adjust log levels in production (INFO or WARNING)
- Increase rotation size for high-volume systems
- Monitor disk space usage
- Consider log shipping to external systems

---

**Need Help?** Check the main FluentSignalCopier documentation or create an issue on GitHub.
'''
    
    with open(readme_path, 'w') as f:
        f.write(readme_content)
    
    print(f"\n✓ Created: {readme_path}")

def validate_setup():
    """Validate the setup"""
    print("\n🔍 Validating setup...")
    
    issues = []
    
    # Check directories
    required_dirs = ["logs", "config", "monitoring"]
    for directory in required_dirs:
        if not Path(directory).exists():
            issues.append(f"Missing directory: {directory}")
    
    # Check config files
    required_configs = ["config/alert_config.json", "config/logging_config.json"]
    for config_file in required_configs:
        if not Path(config_file).exists():
            issues.append(f"Missing config file: {config_file}")
    
    # Check Python modules
    try:
        import json
        import logging
        import logging.handlers
        print("  ✓ Core Python modules available")
    except ImportError as e:
        issues.append(f"Missing Python module: {e}")
    
    # Check optional dependencies
    optional_deps = ["rich", "aiohttp"]
    for dep in optional_deps:
        try:
            __import__(dep)
            print(f"  ✓ Optional dependency available: {dep}")
        except ImportError:
            print(f"  ⚠ Optional dependency missing: {dep}")
    
    if issues:
        print("\n❌ Setup validation failed:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        print("\n✅ Setup validation passed!")
        return True

def print_next_steps():
    """Print next steps for the user"""
    print("\n" + "="*60)
    print("🎉 Enhanced Logging Setup Complete!")
    print("="*60)
    
    print("\n📋 Next Steps:")
    print("1. Review and edit configuration files:")
    print("   - config/alert_config.json (email/webhook settings)")
    print("   - config/logging_config.json (logging preferences)")
    
    print("\n2. Integrate with your FluentSignalCopier:")
    print("   - Add logging imports to fluent_copier.py")
    print("   - Initialize loggers in your classes")
    print("   - See LOGGING_SETUP.md for detailed instructions")
    
    print("\n3. Start monitoring:")
    print("   - Dashboard: python monitoring/start_monitor.py")
    print("   - Alerts: python monitoring/start_alerts.py")
    
    print("\n4. Test the system:")
    print("   - Run your FluentSignalCopier with logging enabled")
    print("   - Check logs/ directory for log files")
    print("   - Verify dashboard shows activity")
    
    print("\n📚 Documentation:")
    print("   - Read LOGGING_SETUP.md for detailed instructions")
    print("   - Check monitoring/ directory for helper scripts")
    
    print("\n⚠️  Important:")
    print("   - Test email/webhook alerts before production use")
    print("   - Monitor disk space usage for log files")
    print("   - Configure log rotation based on your needs")

def main():
    """Main setup function"""
    print("🚀 FluentSignalCopier Enhanced Logging Setup")
    print("=" * 50)
    
    try:
        create_directories()
        install_dependencies()
        create_alert_config()
        create_logging_config()
        create_monitoring_scripts()
        create_systemd_service()
        create_readme()
        
        if validate_setup():
            print_next_steps()
        else:
            print("\n❌ Setup completed with issues. Please review the validation errors above.")
            sys.exit(1)
            
    except KeyboardInterrupt:
        print("\n\n⚠️  Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Setup failed with error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
# monitoring_dashboard.py - Real-time monitoring dashboard for FluentSignalCopier

# Licensed under the Fluent Signal Copier Limited Use License v1.0
# See LICENSE.txt for terms. No warranty; use at your own risk.
# Copyright (c) 2025 R4V3N. All rights reserved.

import json
import time
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import argparse
import sys

# Try importing rich for better terminal display
try:
    from rich.console import Console
    from rich.table import Table
    from rich.live import Live
    from rich.panel import Panel
    from rich.columns import Columns
    from rich.text import Text
    from rich.progress import Progress, SpinnerColumn, TextColumn
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False
    print("Install 'rich' for enhanced display: pip install rich")

@dataclass
class SystemMetrics:
    """System-wide metrics"""
    uptime: float = 0
    total_messages: int = 0
    signals_processed: int = 0
    trades_executed: int = 0
    error_count: int = 0
    warning_count: int = 0
    last_activity: Optional[datetime] = None
    heartbeat_status: str = "unknown"
    
@dataclass
class SignalStats:
    """Signal processing statistics"""
    open_signals: int = 0
    close_signals: int = 0
    modify_signals: int = 0
    modify_tp_signals: int = 0
    emergency_signals: int = 0
    avg_confidence: float = 0
    symbols_active: set = None
    sources_active: set = None
    
    def __post_init__(self):
        if self.symbols_active is None:
            self.symbols_active = set()
        if self.sources_active is None:
            self.sources_active = set()

@dataclass
class PerformanceStats:
    """Performance and health statistics"""
    messages_per_minute: float = 0
    signals_per_hour: float = 0
    avg_processing_time: float = 0
    connection_uptime: float = 0
    file_write_errors: int = 0
    telegram_errors: int = 0

class LogMonitor:
    """Monitor log files and extract metrics"""
    
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = Path(log_dir)
        self.metrics = SystemMetrics()
        self.signal_stats = SignalStats()
        self.perf_stats = PerformanceStats()
        self.recent_events = []
        self.max_recent_events = 50
        
        # File positions for tailing
        self.file_positions = {}
        
    def update_metrics(self) -> bool:
        """Update all metrics from log files. Returns True if updated successfully."""
        try:
            # Read metrics file if available
            self._read_metrics_file()
            
            # Tail log files for recent activity
            self._tail_log_files()
            
            # Check heartbeat
            self._check_heartbeat()
            
            return True
        except Exception as e:
            print(f"Error updating metrics: {e}")
            return False
    
    def _read_metrics_file(self):
        """Read the metrics JSON file"""
        metrics_files = list(self.log_dir.glob("*_metrics.json"))
        if not metrics_files:
            return
            
        # Use the most recent metrics file
        latest_file = max(metrics_files, key=lambda f: f.stat().st_mtime)
        
        try:
            with open(latest_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            self.metrics.uptime = data.get('uptime_seconds', 0)
            self.metrics.total_messages = data.get('total_messages', 0)
            self.metrics.error_count = data.get('error_count', 0)
            self.metrics.warning_count = data.get('warning_count', 0)
            self.metrics.signals_processed = data.get('signal_count', 0)
            self.metrics.trades_executed = data.get('trade_count', 0)
            
            if data.get('last_activity'):
                self.metrics.last_activity = datetime.fromtimestamp(data['last_activity'])
                
        except Exception as e:
            print(f"Error reading metrics file {latest_file}: {e}")
    
    def _tail_log_files(self):
        """Tail log files for recent events"""
        log_files = [
            self.log_dir / "fluent_copier_gui.log",
            self.log_dir / "fluent_copier_thread.log",
            self.log_dir / "fluent_copier_main.log"
        ]
        
        for log_file in log_files:
            if not log_file.exists():
                continue
                
            self._tail_single_file(log_file)
    
    def _tail_single_file(self, log_file: Path):
        """Tail a single log file"""
        try:
            current_pos = self.file_positions.get(str(log_file), 0)
            
            with open(log_file, 'r', encoding='utf-8') as f:
                f.seek(current_pos)
                new_lines = f.readlines()
                self.file_positions[str(log_file)] = f.tell()
            
            for line in new_lines:
                self._process_log_line(line.strip())
                
        except Exception as e:
            print(f"Error tailing {log_file}: {e}")
    
    def _process_log_line(self, line: str):
        """Process a single log line"""
        if not line:
            return
            
        try:
            # Try to parse as JSON
            data = json.loads(line)
            self._process_json_log(data)
        except json.JSONDecodeError:
            # Handle non-JSON lines
            self._process_text_log(line)
    
    def _process_json_log(self, data: Dict[str, Any]):
        """Process a JSON log entry"""
        timestamp_str = data.get('timestamp', '')
        message = data.get('message', '')
        level = data.get('level', 'INFO')
        extra = data.get('extra_data', {})
        
        # Update last activity
        if timestamp_str:
            try:
                self.metrics.last_activity = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except:
                pass
        
        # Track signal activities
        if extra.get('signal_type'):
            signal_type = extra['signal_type']
            symbol = extra.get('symbol', '')
            source = extra.get('source', '')
            
            if signal_type == 'OPEN':
                self.signal_stats.open_signals += 1
            elif signal_type == 'CLOSE':
                self.signal_stats.close_signals += 1
            elif signal_type == 'MODIFY':
                self.signal_stats.modify_signals += 1
            elif signal_type == 'MODIFY_TP':
                self.signal_stats.modify_tp_signals += 1
            elif signal_type == 'EMERGENCY_CLOSE_ALL':
                self.signal_stats.emergency_signals += 1
            
            if symbol:
                self.signal_stats.symbols_active.add(symbol)
            if source:
                self.signal_stats.sources_active.add(source)
        
        # Track trade activities
        if extra.get('trade_action'):
            self.metrics.trades_executed += 1
        
        # Track errors and warnings
        if level == 'ERROR':
            self.metrics.error_count += 1
        elif level == 'WARNING':
            self.metrics.warning_count += 1
        
        # Add to recent events
        self.recent_events.append({
            'timestamp': timestamp_str,
            'level': level,
            'message': message,
            'extra': extra
        })
        
        # Keep only recent events
        if len(self.recent_events) > self.max_recent_events:
            self.recent_events.pop(0)
    
    def _process_text_log(self, line: str):
        """Process a text log line"""
        # Simple parsing for non-JSON logs
        if '[ERROR]' in line:
            self.metrics.error_count += 1
        elif '[WARN' in line:
            self.metrics.warning_count += 1
        
        # Add to recent events (simplified)
        self.recent_events.append({
            'timestamp': datetime.now().isoformat(),
            'level': 'INFO',
            'message': line,
            'extra': {}
        })
        
        if len(self.recent_events) > self.max_recent_events:
            self.recent_events.pop(0)
    
    def _check_heartbeat(self):
        """Check system heartbeat"""
        heartbeat_files = list(self.log_dir.parent.glob("**/fluent_heartbeat.txt"))
        
        if not heartbeat_files:
            self.metrics.heartbeat_status = "no_file"
            return
        
        try:
            # Use the most recent heartbeat file
            latest_heartbeat = max(heartbeat_files, key=lambda f: f.stat().st_mtime)
            
            with open(latest_heartbeat, 'r') as f:
                timestamp_str = f.read().strip()
            
            if timestamp_str.isdigit():
                heartbeat_time = datetime.fromtimestamp(int(timestamp_str))
                age = datetime.now() - heartbeat_time
                
                if age.total_seconds() < 30:
                    self.metrics.heartbeat_status = "healthy"
                elif age.total_seconds() < 120:
                    self.metrics.heartbeat_status = "stale"
                else:
                    self.metrics.heartbeat_status = "dead"
            else:
                self.metrics.heartbeat_status = "invalid"
                
        except Exception as e:
            self.metrics.heartbeat_status = f"error: {e}"

class TerminalDashboard:
    """Terminal-based dashboard display"""
    
    def __init__(self, monitor: LogMonitor):
        self.monitor = monitor
        self.console = Console() if RICH_AVAILABLE else None
        
    def create_dashboard(self) -> str:
        """Create dashboard content"""
        if RICH_AVAILABLE and self.console:
            return self._create_rich_dashboard()
        else:
            return self._create_simple_dashboard()
    
    def _create_rich_dashboard(self):
        """Create rich dashboard with tables and panels"""
        # System overview panel
        system_table = Table(title="System Overview", show_header=False)
        system_table.add_column("Metric", style="bold")
        system_table.add_column("Value")
        
        uptime_str = str(timedelta(seconds=int(self.monitor.metrics.uptime)))
        heartbeat_color = {
            "healthy": "green",
            "stale": "yellow", 
            "dead": "red",
            "no_file": "red",
            "invalid": "red"
        }.get(self.monitor.metrics.heartbeat_status, "red")
        
        system_table.add_row("Uptime", uptime_str)
        system_table.add_row("Heartbeat", f"[{heartbeat_color}]{self.monitor.metrics.heartbeat_status}[/{heartbeat_color}]")
        system_table.add_row("Messages", str(self.monitor.metrics.total_messages))
        system_table.add_row("Errors", f"[red]{self.monitor.metrics.error_count}[/red]")
        system_table.add_row("Warnings", f"[yellow]{self.monitor.metrics.warning_count}[/yellow]")
        
        if self.monitor.metrics.last_activity:
            age = datetime.now() - self.monitor.metrics.last_activity
            age_str = f"{int(age.total_seconds())}s ago"
            system_table.add_row("Last Activity", age_str)
        
        # Signal statistics panel
        signal_table = Table(title="Signal Statistics", show_header=False)
        signal_table.add_column("Type", style="bold")
        signal_table.add_column("Count")
        
        signal_table.add_row("OPEN", f"[green]{self.monitor.signal_stats.open_signals}[/green]")
        signal_table.add_row("CLOSE", f"[blue]{self.monitor.signal_stats.close_signals}[/blue]")
        signal_table.add_row("MODIFY", f"[yellow]{self.monitor.signal_stats.modify_signals}[/yellow]")
        signal_table.add_row("MODIFY_TP", f"[cyan]{self.monitor.signal_stats.modify_tp_signals}[/cyan]")
        signal_table.add_row("EMERGENCY", f"[red]{self.monitor.signal_stats.emergency_signals}[/red]")
        signal_table.add_row("Active Symbols", str(len(self.monitor.signal_stats.symbols_active)))
        signal_table.add_row("Active Sources", str(len(self.monitor.signal_stats.sources_active)))
        
        # Recent events panel
        events_table = Table(title="Recent Events (Last 10)", show_header=True)
        events_table.add_column("Time", width=12)
        events_table.add_column("Level", width=8)
        events_table.add_column("Message", width=60)
        
        recent_events = self.monitor.recent_events[-10:]
        for event in recent_events:
            timestamp = event.get('timestamp', '')
            if timestamp:
                try:
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    time_str = dt.strftime('%H:%M:%S')
                except:
                    time_str = timestamp[:8]
            else:
                time_str = "unknown"
            
            level = event.get('level', 'INFO')
            level_color = {
                'ERROR': 'red',
                'WARNING': 'yellow',
                'INFO': 'green',
                'DEBUG': 'blue'
            }.get(level, 'white')
            
            message = event.get('message', '')[:60]
            
            events_table.add_row(
                time_str,
                f"[{level_color}]{level}[/{level_color}]",
                message
            )
        
        # Combine panels
        top_row = Columns([Panel(system_table), Panel(signal_table)])
        bottom_panel = Panel(events_table)
        
        return f"{top_row}\n{bottom_panel}"
    
    def _create_simple_dashboard(self) -> str:
        """Create simple text dashboard"""
        lines = []
        lines.append("="*80)
        lines.append("FluentSignalCopier - Monitoring Dashboard")
        lines.append("="*80)
        lines.append("")
        
        # System overview
        lines.append("SYSTEM OVERVIEW:")
        lines.append(f"  Uptime: {timedelta(seconds=int(self.monitor.metrics.uptime))}")
        lines.append(f"  Heartbeat: {self.monitor.metrics.heartbeat_status}")
        lines.append(f"  Messages: {self.monitor.metrics.total_messages}")
        lines.append(f"  Errors: {self.monitor.metrics.error_count}")
        lines.append(f"  Warnings: {self.monitor.metrics.warning_count}")
        
        if self.monitor.metrics.last_activity:
            age = datetime.now() - self.monitor.metrics.last_activity
            lines.append(f"  Last Activity: {int(age.total_seconds())}s ago")
        
        lines.append("")
        
        # Signal statistics
        lines.append("SIGNAL STATISTICS:")
        lines.append(f"  OPEN: {self.monitor.signal_stats.open_signals}")
        lines.append(f"  CLOSE: {self.monitor.signal_stats.close_signals}")
        lines.append(f"  MODIFY: {self.monitor.signal_stats.modify_signals}")
        lines.append(f"  MODIFY_TP: {self.monitor.signal_stats.modify_tp_signals}")
        lines.append(f"  EMERGENCY: {self.monitor.signal_stats.emergency_signals}")
        lines.append(f"  Active Symbols: {len(self.monitor.signal_stats.symbols_active)}")
        lines.append(f"  Active Sources: {len(self.monitor.signal_stats.sources_active)}")
        lines.append("")
        
        # Recent events
        lines.append("RECENT EVENTS:")
        recent_events = self.monitor.recent_events[-10:]
        for event in recent_events:
            timestamp = event.get('timestamp', 'unknown')[:19]
            level = event.get('level', 'INFO')
            message = event.get('message', '')[:50]
            lines.append(f"  {timestamp} [{level:>7}] {message}")
        
        lines.append("")
        lines.append(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(lines)

async def monitor_loop(log_dir: str, refresh_interval: int = 5):
    """Main monitoring loop"""
    monitor = LogMonitor(log_dir)
    dashboard = TerminalDashboard(monitor)
    
    if RICH_AVAILABLE:
        console = Console()
        with Live(console=console, refresh_per_second=1/refresh_interval) as live:
            while True:
                if monitor.update_metrics():
                    content = dashboard.create_dashboard()
                    live.update(Panel(content, title="FluentSignalCopier Monitor"))
                await asyncio.sleep(refresh_interval)
    else:
        while True:
            if monitor.update_metrics():
                # Clear screen
                print("\033[2J\033[H")
                content = dashboard.create_dashboard()
                print(content)
            await asyncio.sleep(refresh_interval)

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="FluentSignalCopier Monitoring Dashboard")
    parser.add_argument("--log-dir", default="logs", help="Log directory to monitor")
    parser.add_argument("--refresh", type=int, default=5, help="Refresh interval in seconds")
    parser.add_argument("--once", action="store_true", help="Run once and exit (no live updates)")
    parser.add_argument("--export", help="Export metrics to JSON file")
    
    args = parser.parse_args()
    
    monitor = LogMonitor(args.log_dir)
    
    if args.once:
        # Single run mode
        if monitor.update_metrics():
            dashboard = TerminalDashboard(monitor)
            print(dashboard.create_dashboard())
            
            if args.export:
                export_metrics(monitor, args.export)
        else:
            print("Failed to read metrics")
            sys.exit(1)
    else:
        # Live monitoring mode
        try:
            asyncio.run(monitor_loop(args.log_dir, args.refresh))
        except KeyboardInterrupt:
            print("\nMonitoring stopped by user")

def export_metrics(monitor: LogMonitor, filename: str):
    """Export current metrics to JSON file"""
    export_data = {
        "timestamp": datetime.now().isoformat(),
        "system_metrics": {
            "uptime": monitor.metrics.uptime,
            "total_messages": monitor.metrics.total_messages,
            "signals_processed": monitor.metrics.signals_processed,
            "trades_executed": monitor.metrics.trades_executed,
            "error_count": monitor.metrics.error_count,
            "warning_count": monitor.metrics.warning_count,
            "heartbeat_status": monitor.metrics.heartbeat_status,
            "last_activity": monitor.metrics.last_activity.isoformat() if monitor.metrics.last_activity else None
        },
        "signal_stats": {
            "open_signals": monitor.signal_stats.open_signals,
            "close_signals": monitor.signal_stats.close_signals,
            "modify_signals": monitor.signal_stats.modify_signals,
            "modify_tp_signals": monitor.signal_stats.modify_tp_signals,
            "emergency_signals": monitor.signal_stats.emergency_signals,
            "symbols_active": list(monitor.signal_stats.symbols_active),
            "sources_active": list(monitor.signal_stats.sources_active)
        },
        "recent_events": monitor.recent_events[-20:]  # Last 20 events
    }
    
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    print(f"Metrics exported to {filename}")

if __name__ == "__main__":
    main()
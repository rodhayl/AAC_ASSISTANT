"""
Notification Service - System-wide notifications and alerts
Handles desktop notifications, in-app notifications, and notification history
"""

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from loguru import logger

try:
    from plyer import notification as plyer_notification

    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    logger.warning("plyer not available, desktop notifications disabled")


class NotificationType(Enum):
    """Types of notifications"""

    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    ACHIEVEMENT = "achievement"
    COLLABORATION = "collaboration"
    LEARNING = "learning"


class NotificationPriority(Enum):
    """Notification priority levels"""

    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class Notification:
    """Notification data structure"""

    id: str
    title: str
    message: str
    notification_type: NotificationType
    priority: NotificationPriority
    timestamp: datetime
    read: bool = False
    actions: List[Dict[str, Any]] = None
    timeout: Optional[int] = None  # seconds

    def __post_init__(self):
        if self.actions is None:
            self.actions = []


class NotificationService:
    """System notification service"""

    def __init__(self):
        self.notifications: List[Notification] = []
        self.callbacks: Dict[str, List[Callable]] = {}
        self.enabled_types = set(NotificationType)
        self.desktop_notifications_enabled = PLYER_AVAILABLE
        self.in_app_notifications_enabled = True
        self.max_history = 100

        # Start cleanup thread
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """Start background thread for cleanup"""

        def cleanup_worker():
            while True:
                try:
                    self._cleanup_old_notifications()
                    time.sleep(300)  # Cleanup every 5 minutes
                except Exception as e:
                    logger.error(f"Notification cleanup error: {e}")

        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()

    def _cleanup_old_notifications(self):
        """Remove old notifications from history"""
        cutoff_time = datetime.now().timestamp() - (24 * 60 * 60)  # 24 hours ago
        self.notifications = [
            n for n in self.notifications if n.timestamp.timestamp() > cutoff_time
        ]

        # Keep only max_history notifications
        if len(self.notifications) > self.max_history:
            self.notifications = self.notifications[-self.max_history :]

    def show_notification(
        self, title: str, message: str, config: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Show a notification

        Args:
            title: Notification title
            message: Notification message
            config: Optional configuration dict with keys:
                - notification_type: Type of notification (default: INFO)
                - priority: Priority level (default: NORMAL)
                - timeout: Timeout in seconds (None for default)
                - actions: List of action dictionaries
                - show_desktop: Whether to show desktop notification (default: True)

        Returns:
            Notification ID
        """
        notification = self._create_notification(title, message, config or {})
        self.notifications.append(notification)

        # Show desktop notification if conditions met
        show_desktop = (config or {}).get("show_desktop", True)
        if show_desktop and self._should_show_desktop(notification):
            self._show_desktop_notification(notification)

        # Trigger callbacks
        self._trigger_callbacks("notification_shown", notification)

        logger.info(f"Notification shown: {title} - {message}")
        return notification.id

    def _create_notification(
        self, title: str, message: str, config: Dict[str, Any]
    ) -> Notification:
        """Create notification object from parameters"""
        return Notification(
            id=f"notif_{int(time.time() * 1000)}",
            title=title,
            message=message,
            notification_type=config.get("notification_type", NotificationType.INFO),
            priority=config.get("priority", NotificationPriority.NORMAL),
            timestamp=datetime.now(),
            actions=config.get("actions", []),
            timeout=config.get("timeout"),
        )

    def _should_show_desktop(self, notification: Notification) -> bool:
        """Check if desktop notification should be shown"""
        return (
            self.desktop_notifications_enabled
            and notification.notification_type in self.enabled_types
        )

    def _show_desktop_notification(self, notification: Notification):
        """Show desktop notification using plyer"""
        try:
            # Show notification (plyer doesn't use type differentiation)
            plyer_notification.notify(
                title=notification.title,
                message=notification.message,
                app_name="AAC Assistant",
                timeout=notification.timeout or 10,
            )
        except Exception as e:
            logger.error(f"Failed to show desktop notification: {e}")

    def show_info(self, title: str, message: str, **kwargs):
        """Show info notification"""
        return self.show_notification(title, message, NotificationType.INFO, **kwargs)

    def show_success(self, title: str, message: str, **kwargs):
        """Show success notification"""
        return self.show_notification(
            title, message, NotificationType.SUCCESS, **kwargs
        )

    def show_warning(self, title: str, message: str, **kwargs):
        """Show warning notification"""
        return self.show_notification(
            title, message, NotificationType.WARNING, **kwargs
        )

    def show_error(self, title: str, message: str, **kwargs):
        """Show error notification"""
        return self.show_notification(
            title,
            message,
            NotificationType.ERROR,
            priority=NotificationPriority.HIGH,
            **kwargs,
        )

    def show_achievement(self, title: str, message: str, **kwargs):
        """Show achievement notification"""
        return self.show_notification(
            title,
            message,
            NotificationType.ACHIEVEMENT,
            priority=NotificationPriority.HIGH,
            timeout=15,
            **kwargs,
        )

    def show_collaboration(self, title: str, message: str, **kwargs):
        """Show collaboration notification"""
        return self.show_notification(
            title, message, NotificationType.COLLABORATION, **kwargs
        )

    def show_learning(self, title: str, message: str, **kwargs):
        """Show learning notification"""
        return self.show_notification(
            title, message, NotificationType.LEARNING, **kwargs
        )

    def get_notifications(
        self,
        unread_only: bool = False,
        notification_type: Optional[NotificationType] = None,
        limit: Optional[int] = None,
    ) -> List[Notification]:
        """Get notifications from history"""
        filtered = self.notifications

        if unread_only:
            filtered = [n for n in filtered if not n.read]

        if notification_type:
            filtered = [n for n in filtered if n.notification_type == notification_type]

        if limit:
            filtered = filtered[-limit:]

        return filtered

    def mark_as_read(self, notification_id: str):
        """Mark notification as read"""
        for notification in self.notifications:
            if notification.id == notification_id:
                notification.read = True
                self._trigger_callbacks("notification_read", notification)
                break

    def mark_all_as_read(self):
        """Mark all notifications as read"""
        for notification in self.notifications:
            notification.read = True
        self._trigger_callbacks("all_notifications_read", None)

    def clear_notifications(self, notification_type: Optional[NotificationType] = None):
        """Clear notifications"""
        if notification_type:
            self.notifications = [
                n
                for n in self.notifications
                if n.notification_type != notification_type
            ]
        else:
            self.notifications = []

        self._trigger_callbacks("notifications_cleared", notification_type)

    def add_callback(self, event: str, callback: Callable):
        """Add callback for notification events"""
        if event not in self.callbacks:
            self.callbacks[event] = []
        self.callbacks[event].append(callback)

    def remove_callback(self, event: str, callback: Callable):
        """Remove callback for notification events"""
        if event in self.callbacks and callback in self.callbacks[event]:
            self.callbacks[event].remove(callback)

    def _trigger_callbacks(self, event: str, data: Any):
        """Trigger callbacks for an event"""
        if event in self.callbacks:
            for callback in self.callbacks[event]:
                try:
                    callback(data)
                except Exception as e:
                    logger.error(f"Notification callback error: {e}")

    def enable_type(self, notification_type: NotificationType):
        """Enable notification type"""
        self.enabled_types.add(notification_type)

    def disable_type(self, notification_type: NotificationType):
        """Disable notification type"""
        self.enabled_types.discard(notification_type)

    def set_desktop_enabled(self, enabled: bool):
        """Enable/disable desktop notifications"""
        self.desktop_notifications_enabled = enabled and PLYER_AVAILABLE

    def set_in_app_enabled(self, enabled: bool):
        """Enable/disable in-app notifications"""
        self.in_app_notifications_enabled = enabled

    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        total = len(self.notifications)
        unread = len([n for n in self.notifications if not n.read])

        by_type = {}
        for notification_type in NotificationType:
            count = len(
                [
                    n
                    for n in self.notifications
                    if n.notification_type == notification_type
                ]
            )
            by_type[notification_type.value] = count

        return {
            "total": total,
            "unread": unread,
            "by_type": by_type,
            "desktop_enabled": self.desktop_notifications_enabled,
            "in_app_enabled": self.in_app_notifications_enabled,
        }


# Global notification service instance
_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create the global notification service instance"""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service

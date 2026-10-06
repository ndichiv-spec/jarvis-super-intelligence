"""
JARVIS Mobile App Backend API
=============================
Backend APIs for mobile applications with optimized responses and mobile-specific features.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from enum import Enum
import uuid
import json

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from core.config import settings
from core.advanced_ai_integration import get_advanced_ai_engine
from marketplace.agent_marketplace import get_agent_marketplace

logger = logging.getLogger(__name__)


class MobilePlatform(Enum):
    """Mobile platform enumeration"""
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class NotificationType(Enum):
    """Notification type enumeration"""
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
    IN_APP = "in_app"


@dataclass
class MobileDevice:
    """Mobile device registration"""
    id: str
    user_id: str
    platform: MobilePlatform
    device_token: str
    app_version: str
    os_version: str
    device_model: str
    is_active: bool = True
    registered_at: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)


@dataclass
class PushNotification:
    """Push notification structure"""
    id: str
    user_id: str
    title: str
    body: str
    data: Dict[str, Any] = field(default_factory=dict)
    notification_type: NotificationType = NotificationType.PUSH
    priority: str = "normal"  # normal, high
    ttl: int = 3600  # Time to live in seconds
    created_at: datetime = field(default_factory=datetime.now)
    sent_at: Optional[datetime] = None
    delivered: bool = False


class MobileBackendAPI:
    """Mobile backend API handler"""
    
    def __init__(self):
        self.devices: Dict[str, MobileDevice] = {}
        self.notifications: Dict[str, PushNotification] = {}
        self.user_devices: Dict[str, List[str]] = {}  # user_id -> [device_ids]
        
        # Load existing data
        self._load_data()
    
    async def register_device(
        self,
        user_id: str,
        platform: str,
        device_token: str,
        app_version: str,
        os_version: str,
        device_model: str
    ) -> str:
        """Register a mobile device"""
        device_id = str(uuid.uuid4())
        
        device = MobileDevice(
            id=device_id,
            user_id=user_id,
            platform=MobilePlatform(platform),
            device_token=device_token,
            app_version=app_version,
            os_version=os_version,
            device_model=device_model
        )
        
        self.devices[device_id] = device
        
        # Update user devices mapping
        if user_id not in self.user_devices:
            self.user_devices[user_id] = []
        self.user_devices[user_id].append(device_id)
        
        await self._save_data()
        
        logger.info(f"Registered mobile device: {platform} for user {user_id}")
        return device_id
    
    async def unregister_device(self, device_id: str, user_id: str) -> bool:
        """Unregister a mobile device"""
        device = self.devices.get(device_id)
        if not device or device.user_id != user_id:
            return False
        
        device.is_active = False
        
        # Remove from user devices
        if user_id in self.user_devices:
            self.user_devices[user_id] = [
                d_id for d_id in self.user_devices[user_id] if d_id != device_id
            ]
        
        await self._save_data()
        
        logger.info(f"Unregistered mobile device: {device_id}")
        return True
    
    async def send_push_notification(
        self,
        user_id: str,
        title: str,
        body: str,
        data: Optional[Dict[str, Any]] = None,
        priority: str = "normal"
    ) -> str:
        """Send push notification to user's devices"""
        notification_id = str(uuid.uuid4())
        
        notification = PushNotification(
            id=notification_id,
            user_id=user_id,
            title=title,
            body=body,
            data=data or {},
            priority=priority
        )
        
        self.notifications[notification_id] = notification
        
        # Get user's active devices
        user_device_ids = self.user_devices.get(user_id, [])
        active_devices = [
            self.devices[d_id] for d_id in user_device_ids
            if self.devices.get(d_id, {}).get("is_active", False)
        ]
        
        if active_devices:
            # Send to all active devices
            await self._send_to_devices(notification, active_devices)
            notification.sent_at = datetime.now()
            notification.delivered = True
        
        await self._save_data()
        
        logger.info(f"Sent push notification to {len(active_devices)} devices for user {user_id}")
        return notification_id
    
    async def _send_to_devices(self, notification: PushNotification, devices: List[MobileDevice]):
        """Send notification to specific devices"""
        for device in devices:
            try:
                if device.platform == MobilePlatform.IOS:
                    await self._send_ios_notification(notification, device)
                elif device.platform == MobilePlatform.ANDROID:
                    await self._send_android_notification(notification, device)
                elif device.platform == MobilePlatform.WEB:
                    await self._send_web_notification(notification, device)
            except Exception as e:
                logger.error(f"Failed to send notification to device {device.id}: {e}")
    
    async def _send_ios_notification(self, notification: PushNotification, device: MobileDevice):
        """Send iOS push notification"""
        # Implementation would use APNS (Apple Push Notification Service)
        # For now, simulate the send
        logger.info(f"iOS notification sent to device {device.id}: {notification.title}")
    
    async def _send_android_notification(self, notification: PushNotification, device: MobileDevice):
        """Send Android push notification"""
        # Implementation would use FCM (Firebase Cloud Messaging)
        # For now, simulate the send
        logger.info(f"Android notification sent to device {device.id}: {notification.title}")
    
    async def _send_web_notification(self, notification: PushNotification, device: MobileDevice):
        """Send web push notification"""
        # Implementation would use Web Push Protocol
        # For now, simulate the send
        logger.info(f"Web notification sent to device {device.id}: {notification.title}")
    
    async def get_user_devices(self, user_id: str) -> List[Dict[str, Any]]:
        """Get user's registered devices"""
        user_device_ids = self.user_devices.get(user_id, [])
        devices = []
        
        for device_id in user_device_ids:
            device = self.devices.get(device_id)
            if device:
                devices.append({
                    "id": device.id,
                    "platform": device.platform.value,
                    "app_version": device.app_version,
                    "os_version": device.os_version,
                    "device_model": device.device_model,
                    "is_active": device.is_active,
                    "registered_at": device.registered_at.isoformat(),
                    "last_seen": device.last_seen.isoformat()
                })
        
        return devices
    
    async def update_device_last_seen(self, device_id: str) -> bool:
        """Update device last seen timestamp"""
        device = self.devices.get(device_id)
        if not device:
            return False
        
        device.last_seen = datetime.now()
        await self._save_data()
        
        return True
    
    async def get_mobile_optimized_response(
        self,
        endpoint: str,
        user_id: str,
        data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Get mobile-optimized response for endpoint"""
        
        if endpoint == "conversations":
            return await self._get_mobile_conversations(user_id, data)
        elif endpoint == "agents":
            return await self._get_mobile_agents(user_id, data)
        elif endpoint == "analytics":
            return await self._get_mobile_analytics(user_id, data)
        elif endpoint == "notifications":
            return await self._get_mobile_notifications(user_id, data)
        else:
            return {"error": f"Unknown endpoint: {endpoint}"}
    
    async def _get_mobile_conversations(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get mobile-optimized conversations list"""
        # This would integrate with actual conversation system
        # For now, return mock data optimized for mobile
        
        limit = data.get("limit", 20)
        offset = data.get("offset", 0)
        
        conversations = [
            {
                "id": f"conv_{i}",
                "title": f"Conversation {i}",
                "last_message": "This is the last message in the conversation...",
                "timestamp": (datetime.now() - timedelta(hours=i)).isoformat(),
                "unread_count": i % 5,
                "agent_type": "general_assistant"
            }
            for i in range(offset, min(offset + limit, 50))
        ]
        
        return {
            "conversations": conversations,
            "total_count": 50,
            "has_more": offset + limit < 50
        }
    
    async def _get_mobile_agents(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get mobile-optimized agents list"""
        marketplace = get_agent_marketplace()
        
        # Get featured agents for mobile
        featured_agents = await marketplace.get_featured_agents(limit=10)
        
        # Optimize for mobile
        mobile_agents = []
        for agent in featured_agents:
            mobile_agents.append({
                "id": agent["id"],
                "name": agent["name"],
                "description": agent["description"][:100] + "...",  # Truncate for mobile
                "category": agent["category"],
                "rating": agent.get("average_rating", 0),
                "icon": f"/api/v1/marketplace/agents/{agent['id']}/icon",
                "quick_actions": ["chat", "execute"]
            })
        
        return {
            "agents": mobile_agents,
            "categories": ["productivity", "customer_service", "content_creation"]
        }
    
    async def _get_mobile_analytics(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get mobile-optimized analytics"""
        # Simplified analytics for mobile dashboard
        return {
            "usage_stats": {
                "conversations_today": 5,
                "tokens_used_today": 1250,
                "active_agents": 3,
                "savings_hours": 2.5
            },
            "quick_insights": [
                "Your productivity increased by 15% this week",
                "Most used agent: Customer Service Assistant",
                "Peak usage time: 2-4 PM"
            ],
            "trends": {
                "daily_usage": [12, 15, 8, 20, 18, 25, 22],  # Last 7 days
                "agent_distribution": {
                    "customer_service": 40,
                    "productivity": 35,
                    "content_creation": 25
                }
            }
        }
    
    async def _get_mobile_notifications(self, user_id: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Get mobile notifications"""
        limit = data.get("limit", 20)
        
        notifications = [
            {
                "id": f"notif_{i}",
                "title": f"Notification {i}",
                "body": f"This is notification number {i}",
                "timestamp": (datetime.now() - timedelta(hours=i)).isoformat(),
                "read": i % 3 != 0,
                "type": "info",
                "action_url": f"/mobile/action/{i}"
            }
            for i in range(limit)
        ]
        
        return {
            "notifications": notifications,
            "unread_count": sum(1 for n in notifications if not n["read"])
        }
    
    async def _save_data(self):
        """Save mobile data to storage"""
        try:
            import os
            import aiofiles
            
            os.makedirs("./data/mobile", exist_ok=True)
            
            data = {
                "devices": {
                    device_id: {
                        "id": device.id,
                        "user_id": device.user_id,
                        "platform": device.platform.value,
                        "device_token": device.device_token,
                        "app_version": device.app_version,
                        "os_version": device.os_version,
                        "device_model": device.device_model,
                        "is_active": device.is_active,
                        "registered_at": device.registered_at.isoformat(),
                        "last_seen": device.last_seen.isoformat()
                    }
                    for device_id, device in self.devices.items()
                },
                "notifications": {
                    notif_id: {
                        "id": notif.id,
                        "user_id": notif.user_id,
                        "title": notif.title,
                        "body": notif.body,
                        "data": notif.data,
                        "notification_type": notif.notification_type.value,
                        "priority": notif.priority,
                        "ttl": notif.ttl,
                        "created_at": notif.created_at.isoformat(),
                        "sent_at": notif.sent_at.isoformat() if notif.sent_at else None,
                        "delivered": notif.delivered
                    }
                    for notif_id, notif in self.notifications.items()
                },
                "user_devices": self.user_devices
            }
            
            async with aiofiles.open("./data/mobile/mobile_data.json", "w") as f:
                await f.write(json.dumps(data, indent=2))
                
        except Exception as e:
            logger.error(f"Failed to save mobile data: {e}")
    
    def _load_data(self):
        """Load mobile data from storage"""
        try:
            import os
            
            if not os.path.exists("./data/mobile/mobile_data.json"):
                return
            
            with open("./data/mobile/mobile_data.json", "r") as f:
                data = json.load(f)
            
            # Load devices
            for device_id, device_data in data.get("devices", {}).items():
                device = MobileDevice(
                    id=device_data["id"],
                    user_id=device_data["user_id"],
                    platform=MobilePlatform(device_data["platform"]),
                    device_token=device_data["device_token"],
                    app_version=device_data["app_version"],
                    os_version=device_data["os_version"],
                    device_model=device_data["device_model"],
                    is_active=device_data.get("is_active", True),
                    registered_at=datetime.fromisoformat(device_data["registered_at"]),
                    last_seen=datetime.fromisoformat(device_data["last_seen"])
                )
                self.devices[device_id] = device
            
            # Load notifications
            for notif_id, notif_data in data.get("notifications", {}).items():
                notification = PushNotification(
                    id=notif_data["id"],
                    user_id=notif_data["user_id"],
                    title=notif_data["title"],
                    body=notif_data["body"],
                    data=notif_data.get("data", {}),
                    notification_type=NotificationType(notif_data.get("notification_type", "push")),
                    priority=notif_data.get("priority", "normal"),
                    ttl=notif_data.get("ttl", 3600),
                    created_at=datetime.fromisoformat(notif_data["created_at"]),
                    sent_at=datetime.fromisoformat(notif_data["sent_at"]) if notif_data.get("sent_at") else None,
                    delivered=notif_data.get("delivered", False)
                )
                self.notifications[notif_id] = notification
            
            # Load user devices mapping
            self.user_devices = data.get("user_devices", {})
            
            logger.info(f"Loaded {len(self.devices)} devices and {len(self.notifications)} notifications")
            
        except Exception as e:
            logger.error(f"Failed to load mobile data: {e}")


# Global instance
_mobile_backend = None


def get_mobile_backend() -> MobileBackendAPI:
    """Get global mobile backend instance"""
    global _mobile_backend
    if _mobile_backend is None:
        _mobile_backend = MobileBackendAPI()
    return _mobile_backend

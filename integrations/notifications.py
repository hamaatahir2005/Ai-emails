from sqlalchemy import select
from backend.app.db import Session
from backend.app.models import Settings, Notification, Device, User

def deliver_notifications():
    import firebase_admin
    from firebase_admin import messaging
    with Session.begin() as db:
        settings = db.get(Settings, 1)
        if not settings or not settings.notifications_enabled:
            return
        if not firebase_admin._apps:
            firebase_admin.initialize_app(options={"httpTimeout": 30})
        devices = list(db.scalars(select(Device).join(User).where(User.disabled.is_(False))))
        for notice in db.scalars(select(Notification).where(Notification.delivered.is_(False)).limit(50).with_for_update(skip_locked=True)):
            # Mark delivered only when there are devices and all valid-device calls succeed.
            if not devices:
                return
            for device in devices:
                try:
                    messaging.send(messaging.Message(token=device.token,
                        notification=messaging.Notification(title="AI Email Marketing OS", body=notice.text),
                        data={"kind": notice.kind}))
                except messaging.UnregisteredError:
                    db.delete(device)
            notice.delivered = True

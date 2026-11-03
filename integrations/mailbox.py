import email
import imaplib
import hashlib
from email.utils import parseaddr
from email.policy import default
from sqlalchemy import select
from backend.app.config import config
from backend.app.db import Session
from backend.app.models import Counter, Recipient, Message, Customer, Event, now
from backend.app.services import locked_settings, notify

def poll():
    cfg = config()
    if not (cfg.mailbox_host and cfg.mailbox_user and cfg.mailbox_password):
        return
    with imaplib.IMAP4_SSL(cfg.mailbox_host, cfg.mailbox_port) as mailbox:
        mailbox.login(cfg.mailbox_user, cfg.mailbox_password)
        mailbox.select(cfg.mailbox_folder, readonly=True)
        validity = mailbox.response("UIDVALIDITY")[1][0].decode()
        cursor_key = "imap:" + hashlib.sha256((cfg.mailbox_host + cfg.mailbox_user + cfg.mailbox_folder + validity).encode()).hexdigest()
        with Session.begin() as db:
            locked_settings(db)
            cursor = db.get(Counter, cursor_key)
            if cursor is None:
                # Start at current UIDNEXT; do not classify historical mail as new replies.
                raw = mailbox.response("UIDNEXT")[1]
                cursor = Counter(name=cursor_key, value=int(raw[0]) - 1 if raw and raw[0] else 0)
                db.add(cursor)
                return
            status, results = mailbox.uid("search", None, "UID", str(cursor.value + 1) + ":*")
            if status != "OK":
                raise RuntimeError("IMAP search failed")
            for uid in results[0].split()[:100]:
                if int(uid) <= cursor.value:
                    continue
                status, parts = mailbox.uid("fetch", uid, "(BODY.PEEK[HEADER.FIELDS (FROM IN-REPLY-TO REFERENCES AUTO-SUBMITTED)])")
                if status != "OK":
                    raise RuntimeError("IMAP fetch failed")
                raw = b"".join(p[1] for p in parts if isinstance(p, tuple))
                headers = email.message_from_bytes(raw, policy=default)
                sender = parseaddr(str(headers.get("From", "")))[1].lower()
                references = str(headers.get("In-Reply-To", "")) + " " + str(headers.get("References", ""))
                import re
                ids = re.findall(r"<[^>]+>", references)
                if ids and str(headers.get("Auto-Submitted", "no")).lower() == "no":
                    messages = db.scalars(select(Message).join(Recipient).join(Customer).where(Message.provider_id.in_(ids), Customer.email == sender))
                    for message in messages:
                        recipient = db.get(Recipient, message.recipient_id)
                        if not recipient.replied_at:
                            recipient.replied_at = now()
                            db.add(Event(id=hashlib.sha256(("reply:" + str(recipient.id)).encode()).hexdigest(), message_id=message.id, kind="replied"))
                            for queued in db.scalars(select(Message).where(Message.recipient_id == recipient.id, Message.state.in_(["queued", "retry"]))):
                                queued.state = "suppressed"
                            notify(db, "replied", "A customer replied to campaign " + str(recipient.campaign_id))
                cursor.value = int(uid)

"""Initial relational schema.

The revision contains its own schema snapshot. Do not import live application
models here; later model changes must use new Alembic revisions.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password", sa.Text, nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("disabled", sa.Boolean, nullable=False),
        sa.Column("token_version", sa.Integer, nullable=False))
    op.create_table("settings",
        sa.Column("id", sa.Integer, primary_key=True),
        *[sa.Column(k, sa.Integer, nullable=False) for k in ["daily_limit", "provider_daily_limit", "provider_per_minute", "start_hour", "end_hour"]],
        sa.Column("timezone", sa.String(100), nullable=False),
        sa.Column("sender_email", sa.String(320), nullable=False),
        sa.Column("sender_name", sa.String(200), nullable=False),
        sa.Column("postal_address", sa.Text, nullable=False),
        sa.Column("dns_confirmed", sa.Boolean, nullable=False),
        sa.Column("emergency_stop", sa.Boolean, nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("notifications_enabled", sa.Boolean, nullable=False),
        sa.Column("gemini_key", sa.Text, nullable=False),
        sa.Column("brevo_key", sa.Text, nullable=False))
    op.create_table("customers",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("company_name", sa.String(200), nullable=False),
        sa.Column("business_category", sa.String(200), nullable=False),
        sa.Column("country", sa.String(100), nullable=False),
        sa.Column("language", sa.String(8), nullable=False),
        sa.Column("consent_status", sa.Boolean, nullable=False),
        sa.Column("consent_timestamp", sa.DateTime(timezone=True)),
        sa.Column("consent_source", sa.Text, nullable=False),
        sa.Column("subscription_status", sa.String(30), nullable=False),
        sa.Column("segment", sa.String(100), nullable=False),
        sa.Column("preferences", sa.JSON, nullable=False),
        sa.Column("last_email_date", sa.DateTime(timezone=True)))
    op.create_table("suppressions",
        sa.Column("email_hash", sa.String(64), primary_key=True),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("campaigns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("service_description", sa.Text, nullable=False),
        sa.Column("segment", sa.String(100), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("daily_limit", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by", sa.Integer, sa.ForeignKey("users.id")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("approval_digest", sa.String(64), nullable=False),
        sa.Column("followups", sa.JSON, nullable=False),
        sa.Column("pause_reason", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("recipients",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("customer_id", sa.Integer, sa.ForeignKey("customers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("replied_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("campaign_id", "customer_id"))
    op.create_table("messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_id", sa.Integer, sa.ForeignKey("recipients.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer, nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_id", sa.String(300), unique=True),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.Column("error", sa.Text, nullable=False),
        sa.UniqueConstraint("recipient_id", "sequence"))
    op.create_table("daily_usage",
        sa.Column("day", sa.Date, primary_key=True),
        sa.Column("campaign_id", sa.Integer, primary_key=True),
        sa.Column("reserved", sa.Integer, nullable=False))
    op.create_table("events",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("audit",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("devices",
        sa.Column("token", sa.String(500), primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False))
    op.create_table("notifications",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("kind", sa.String(50), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("delivered", sa.Boolean, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("counters",
        sa.Column("name", sa.String(100), primary_key=True),
        sa.Column("value", sa.Integer, nullable=False))
    op.create_index("ix_messages_state_due", "messages", ["state", "due_at"])
    op.create_index("ix_events_kind_time", "events", ["kind", "occurred_at"])
    op.create_index("ix_customers_segment", "customers", ["segment"])

def downgrade():
    for table in ["counters", "notifications", "devices", "audit", "events", "daily_usage", "messages", "recipients", "campaigns", "suppressions", "customers", "settings", "users"]:
        op.drop_table(table)

"""Tables for Phase 2 (spec §5.2, 5.4, 5.5, 5.9, 5.11). People, readings, workers and orgs come in later phases.
What may be stored is spec §5.1: no exact GPS, names, drug names or free text; phones only encrypted + HMAC."""
from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, new_id, utcnow


class Household(Base):
    __tablename__ = "household"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    token_hash: Mapped[str | None] = mapped_column(String(64), unique=True)        # WhatsApp sign-ups have no app token
    token_created_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    lang: Mapped[str] = mapped_column(String(2), default="en")
    cell_lat: Mapped[float] = mapped_column(Float)                                # 0.1 deg; the exact GPS is never stored
    cell_lon: Mapped[float] = mapped_column(Float)
    elev_bucket_m: Mapped[int | None] = mapped_column(Integer)
    district_id: Mapped[str | None] = mapped_column(String(40))
    district: Mapped[str | None] = mapped_column(String(80))
    state: Mapped[str | None] = mapped_column(String(80))
    ward_no: Mapped[str | None] = mapped_column(String(10))
    in_delhi: Mapped[bool] = mapped_column(Boolean, default=False)
    roof: Mapped[str | None] = mapped_column(String(20))
    roof_access: Mapped[bool | None] = mapped_column(Boolean)
    cross_ventilation: Mapped[bool | None] = mapped_column(Boolean)
    budget: Mapped[str | None] = mapped_column(String(10))
    tenure: Mapped[str | None] = mapped_column(String(10))
    floor_level: Mapped[int | None] = mapped_column(Integer)
    fan: Mapped[bool | None] = mapped_column(Boolean)
    cooler: Mapped[bool | None] = mapped_column(Boolean)
    ac: Mapped[bool | None] = mapped_column(Boolean)
    power_cuts: Mapped[bool | None] = mapped_column(Boolean)
    power_cut_hours: Mapped[list | None] = mapped_column(JSON)
    water_short: Mapped[bool | None] = mapped_column(Boolean)
    higher_risk: Mapped[bool] = mapped_column(Boolean, default=False)
    outdoor_work_window: Mapped[list | None] = mapped_column(JSON)               # ["HH:MM", "HH:MM"]
    share_counts: Mapped[bool] = mapped_column(Boolean, default=False)
    counts: Mapped[dict | None] = mapped_column(JSON)
    alerts_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    alert_hour_ist: Mapped[int] = mapped_column(Integer, default=19)
    alert_min_level: Mapped[str] = mapped_column(String(8), default="high")
    managed_by: Mapped[str] = mapped_column(String(8), default="self")
    worker_id: Mapped[str | None] = mapped_column(String(36))
    consent_version: Mapped[str | None] = mapped_column(String(20))
    consent_at: Mapped[datetime | None] = mapped_column(DateTime)
    consent_by: Mapped[str | None] = mapped_column(String(8))
    retention_prompt_at: Mapped[datetime | None] = mapped_column(DateTime)
    calib_bias_day_c: Mapped[float | None] = mapped_column(Float)
    calib_bias_night_c: Mapped[float | None] = mapped_column(Float)
    calib_n_day: Mapped[int] = mapped_column(Integer, default=0)
    calib_n_night: Mapped[int] = mapped_column(Integer, default=0)
    calib_sd_c: Mapped[float | None] = mapped_column(Float)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime)


class PushTarget(Base):
    __tablename__ = "push_target"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("household.id", ondelete="CASCADE"))
    worker_id: Mapped[str | None] = mapped_column(String(36))
    kind: Mapped[str] = mapped_column(String(10))                                 # fcm, webpush, sms, whatsapp
    fcm_token: Mapped[str | None] = mapped_column(Text)
    endpoint: Mapped[str | None] = mapped_column(Text)
    p256dh: Mapped[str | None] = mapped_column(Text)
    auth: Mapped[str | None] = mapped_column(Text)
    phone_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_id: Mapped[str | None] = mapped_column(String(20))
    phone_hmac: Mapped[str | None] = mapped_column(String(64), index=True)
    verified_via: Mapped[str | None] = mapped_column(String(20))
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_ok_at: Mapped[datetime | None] = mapped_column(DateTime)
    fail_count: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Otp(Base):
    __tablename__ = "otp"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    phone_hmac: Mapped[str] = mapped_column(String(64), index=True)
    purpose: Mapped[str] = mapped_column(String(20))
    code_hash: Mapped[str] = mapped_column(String(64))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime)


class NoticeLog(Base):
    __tablename__ = "notice_log"
    __table_args__ = (UniqueConstraint("recipient_key", "for_date", "kind", "channel", name="uq_notice_once"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    recipient_key: Mapped[str] = mapped_column(String(40), nullable=False)         # "h:<household_id>" or "w:<worker_id>"
    target_id: Mapped[str | None] = mapped_column(String(36))
    for_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(String(16))         # evening, morning_work, imd_warning, worker_brief, test, on_request, retention
    level: Mapped[str | None] = mapped_column(String(8))
    channel: Mapped[str] = mapped_column(String(10))
    template_id: Mapped[str | None] = mapped_column(String(40))
    lang: Mapped[str] = mapped_column(String(2), default="en")
    text: Mapped[str | None] = mapped_column(Text)                                  # no health details (spec §2 rule 7)
    status: Mapped[str] = mapped_column(String(20), default="queued")   # queued, sent, failed, opened, skipped_duplicate, skipped_fatigue
    error: Mapped[str | None] = mapped_column(String(80))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime)
    provider_msg_id: Mapped[str | None] = mapped_column(String(80), index=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime)


class ConsentEvent(Base):
    """Kept after a household is deleted; holds nothing else about it (spec §5.11)."""
    __tablename__ = "consent_event"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str | None] = mapped_column(String(36))                   # no foreign key: survives deletion
    worker_id: Mapped[str | None] = mapped_column(String(36))
    action: Mapped[str] = mapped_column(String(12))                                 # given, withdrawn, exported, deleted
    consent_version: Mapped[str | None] = mapped_column(String(20))
    by: Mapped[str] = mapped_column(String(8))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class JobLock(Base):
    __tablename__ = "job_lock"
    name: Mapped[str] = mapped_column(String(40), primary_key=True)
    holder: Mapped[str] = mapped_column(String(36))
    locked_until: Mapped[datetime] = mapped_column(DateTime)


class ImdWarning(Base):
    __tablename__ = "imd_warning"
    district_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    for_date: Mapped[date] = mapped_column(Date, primary_key=True)
    phenomenon: Mapped[str] = mapped_column(String(16), primary_key=True)           # heat_wave, warm_night, hot_humid
    color: Mapped[str] = mapped_column(String(8))                                    # green, yellow, orange, red
    issued_at: Mapped[datetime | None] = mapped_column(DateTime)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    source_url: Mapped[str | None] = mapped_column(Text)


class DailyAggregate(Base):
    """Counts below AGG_MIN_COUNT are stored as NULL (spec §5.11)."""
    __tablename__ = "daily_aggregate"
    for_date: Mapped[date] = mapped_column(Date, primary_key=True)
    district_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    households: Mapped[int | None] = mapped_column(Integer)
    households_high: Mapped[int | None] = mapped_column(Integer)
    households_extreme: Mapped[int | None] = mapped_column(Integer)
    people_older: Mapped[int | None] = mapped_column(Integer)
    people_infant: Mapped[int | None] = mapped_column(Integer)
    people_pregnant: Mapped[int | None] = mapped_column(Integer)
    people_outdoor_work: Mapped[int | None] = mapped_column(Integer)
    alerts_sent: Mapped[int | None] = mapped_column(Integer)
    alerts_opened: Mapped[int | None] = mapped_column(Integer)
    nights_could_not_sleep: Mapped[int | None] = mapped_column(Integer)


class WaSession(Base):
    """WhatsApp sign-up in progress, keyed by the phone's HMAC (spec §6.5)."""
    __tablename__ = "wa_session"
    phone_hmac: Mapped[str] = mapped_column(String(64), primary_key=True)
    step: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class InboundMessage(Base):
    """Provider message ids already handled, so a repeated webhook is processed once (spec §6.5)."""
    __tablename__ = "inbound_message"
    provider_msg_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    channel: Mapped[str] = mapped_column(String(10))
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


# ------------------------------------------------------------------ Phase 5: assisted mode (spec §5.3, §5.10)
class Org(Base):
    """Created only with the CLI (python -m app.admin create-org), never over HTTP."""
    __tablename__ = "org"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    type: Mapped[str] = mapped_column(String(12))                                   # health_dept, ngo, rwa, school, other
    state: Mapped[str | None] = mapped_column(String(80))
    district_id: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Worker(Base):
    __tablename__ = "worker"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(String(36), ForeignKey("org.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(12))                                   # asha, anganwadi, ngo, volunteer, org_admin
    display_name: Mapped[str] = mapped_column(String(60))
    phone_enc: Mapped[bytes] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(20))
    phone_hmac: Mapped[str] = mapped_column(String(64), unique=True)
    district_id: Mapped[str | None] = mapped_column(String(40))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class WorkerSession(Base):
    __tablename__ = "worker_session"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    worker_id: Mapped[str] = mapped_column(String(36), ForeignKey("worker.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)


class AccessLog(Base):
    """Every worker read and write of a household (kept 1 year)."""
    __tablename__ = "access_log"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    worker_id: Mapped[str] = mapped_column(String(36), index=True)
    household_id: Mapped[str] = mapped_column(String(36), index=True)
    action: Mapped[str] = mapped_column(String(8))                                  # view, create, edit, delete, brief
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Person(Base):
    """Worker-managed homes only. Nickname, condition and medicine classes are encrypted (PERSON_ENC_KEYS)."""
    __tablename__ = "person"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(String(36), ForeignKey("household.id", ondelete="CASCADE"), index=True)
    label_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    age_band: Mapped[str] = mapped_column(String(16))
    pregnant: Mapped[bool] = mapped_column(Boolean, default=False)
    conditions_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    medicine_classes_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    key_id: Mapped[str] = mapped_column(String(20))
    lives_alone: Mapped[bool] = mapped_column(Boolean, default=False)
    outdoor_work: Mapped[bool] = mapped_column(Boolean, default=False)
    work_start: Mapped[str | None] = mapped_column(String(5))
    work_end: Mapped[str | None] = mapped_column(String(5))
    work_type: Mapped[str | None] = mapped_column(String(12))


# ------------------------------------------------------------------ Phase 6: learning the home (spec §5.6-5.8)
class Reading(Base):
    __tablename__ = "reading"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    household_id: Mapped[str] = mapped_column(String(36), ForeignKey("household.id", ondelete="CASCADE"), index=True)
    ts: Mapped[datetime] = mapped_column(DateTime, index=True)                     # IST hour, stored naive
    room: Mapped[str] = mapped_column(String(10))                                  # bedroom, living, kitchen, other
    indoor_c: Mapped[float] = mapped_column(Float)
    outdoor_c: Mapped[float | None] = mapped_column(Float)                         # filled in by the server
    predicted_c: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(12))                                # thermometer, ac_remote, logger, other
    period: Mapped[str] = mapped_column(String(5))                                 # day, night
    used_for_calibration: Mapped[bool] = mapped_column(Boolean, default=False)
    outlier: Mapped[bool] = mapped_column(Boolean, default=False)
    fix_id: Mapped[str | None] = mapped_column(String(40))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Feedback(Base):
    """One answer per day; no free text. anyone_unwell is not a medical record (kept 90 days)."""
    __tablename__ = "feedback"
    household_id: Mapped[str] = mapped_column(String(36), ForeignKey("household.id", ondelete="CASCADE"), primary_key=True)
    for_date: Mapped[date] = mapped_column(Date, primary_key=True)
    night_feel: Mapped[str] = mapped_column(String(16))                            # fine, hot, could_not_sleep
    followed_plan: Mapped[str | None] = mapped_column(String(6))                   # yes, partly, no
    anyone_unwell: Mapped[bool | None] = mapped_column(Boolean)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FixProgress(Base):
    __tablename__ = "fix_progress"
    household_id: Mapped[str] = mapped_column(String(36), ForeignKey("household.id", ondelete="CASCADE"), primary_key=True)
    fix_id: Mapped[str] = mapped_column(String(40), primary_key=True)
    status: Mapped[str] = mapped_column(String(14))                                # planned, done, not_possible
    done_at: Mapped[date | None] = mapped_column(Date)
    measured_effect_c: Mapped[float | None] = mapped_column(Float)
    measured_n: Mapped[int | None] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

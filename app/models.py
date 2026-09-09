from datetime import datetime

from app.extensions import db


class Account(db.Model):
    """Single-row table holding the Apple ID we sync against."""

    id = db.Column(db.Integer, primary_key=True)
    apple_id = db.Column(db.String(255), nullable=False)
    encrypted_password = db.Column(db.LargeBinary, nullable=True)
    domain = db.Column(db.String(8), nullable=False, default="com")  # com | cn
    authenticated = db.Column(db.Boolean, nullable=False, default=False)
    session_trusted = db.Column(db.Boolean, nullable=False, default=False)
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    settings = db.relationship(
        "Settings", back_populates="account", uselist=False,
        cascade="all, delete-orphan",
    )


class Settings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)

    # Download
    directory = db.Column(db.String(512), nullable=False, default="/data/drive_d")
    size_original = db.Column(db.Boolean, nullable=False, default=True)
    size_medium = db.Column(db.Boolean, nullable=False, default=False)
    size_thumb = db.Column(db.Boolean, nullable=False, default=False)
    live_photo_size = db.Column(db.String(16), nullable=False, default="original")
    force_size = db.Column(db.Boolean, nullable=False, default=False)

    # Filtering
    # Empty means "whole library" (icloudpd's own default when --album is
    # omitted). A literal value here is looked up as an exact album name by
    # icloudpd and crashes with a KeyError if no such album exists, so this
    # must never default to a guessed name like "All Photos".
    album = db.Column(db.String(255), nullable=False, default="")
    file_match_policy = db.Column(
        db.String(64), nullable=False, default="name-size-dedup-with-suffix"
    )
    skip_videos = db.Column(db.Boolean, nullable=False, default=False)
    skip_live_photos = db.Column(db.Boolean, nullable=False, default=False)
    recent = db.Column(db.Integer, nullable=True)
    until_found = db.Column(db.Integer, nullable=True)

    # Behaviour
    auto_delete = db.Column(db.Boolean, nullable=False, default=False)
    dry_run = db.Column(db.Boolean, nullable=False, default=False)
    only_print_filenames = db.Column(db.Boolean, nullable=False, default=False)

    # Scheduling / performance
    watch_interval_seconds = db.Column(db.Integer, nullable=True)
    threads_num = db.Column(db.Integer, nullable=False, default=1)
    log_level = db.Column(db.String(16), nullable=False, default="info")

    # Escape hatch for any icloudpd flag not exposed as a dedicated field.
    extra_args = db.Column(db.Text, nullable=False, default="")

    account = db.relationship("Account", back_populates="settings")

    def size_list(self):
        sizes = []
        if self.size_original:
            sizes.append("original")
        if self.size_medium:
            sizes.append("medium")
        if self.size_thumb:
            sizes.append("thumb")
        return sizes or ["original"]


class RunLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("account.id"), nullable=False)
    mode = db.Column(db.String(16), nullable=False, default="once")  # once | continuous
    status = db.Column(
        db.String(16), nullable=False, default="running"
    )  # running | success | failed | stopped
    pid = db.Column(db.Integer, nullable=True)
    exit_code = db.Column(db.Integer, nullable=True)
    log_file = db.Column(db.String(512), nullable=False)
    started_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime, nullable=True)

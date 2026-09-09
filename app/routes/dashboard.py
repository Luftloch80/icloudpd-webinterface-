from flask import Blueprint, render_template
from flask_login import login_required

from app import icloudpd_runner
from app.models import Account, RunLog

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    account = Account.query.first()
    running = icloudpd_runner.is_running(account.id) if account else None
    recent_runs = []
    if account:
        recent_runs = (
            RunLog.query.filter_by(account_id=account.id)
            .order_by(RunLog.started_at.desc())
            .limit(5)
            .all()
        )
    return render_template(
        "dashboard.html", account=account, running=running, recent_runs=recent_runs
    )

"""Admin routes for persisted LLM token usage."""

from flask import Blueprint, current_app, jsonify, request


admin_usage_bp = Blueprint("admin_usage", __name__)


@admin_usage_bp.get("/api/admin/llm-usage")
def admin_llm_usage():
    # The application-wide admin guard is authoritative; keep a local check too.
    from app import _require_admin

    auth = _require_admin()
    if auth:
        return auth
    try:
        import competition_agents as agents
        from llm_usage_store import aggregate_usage

        days = request.args.get("days", default=30, type=int)
        limit = request.args.get("limit", default=20, type=int)
        return jsonify({"success": True, **aggregate_usage(
            agents._LLM_USAGE_DB_PATH, days=days, limit=limit)})
    except Exception as exc:
        print("[llm_usage] aggregate failed: %s" % exc)
        return jsonify({"success": False, "error": "Token 统计暂不可用"}), 500


@admin_usage_bp.get("/admin/llm-usage")
def admin_llm_usage_page():
    """Serve the dashboard through Flask's configured active static root."""
    return current_app.send_static_file("admin-llm-usage.html")

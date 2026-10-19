from flask import Flask, jsonify, request
from flask_compress import Compress
from flask_cors import CORS

from .config import Config


def create_app(config_class: type = Config) -> Flask:
    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)
    # Gzip JSON responses, the documents/cases lists are the hot paths and
    # compress well. flask-compress only kicks in above ~500 bytes by default.
    Compress(app)
    # Restrict cross-origin calls to known frontends rather than a wildcard,
    # which is unsafe alongside supports_credentials. Origins come from config
    # (CORS_ORIGINS env), defaulting to local dev.
    CORS(app, resources={r"/*": {"origins": app.config["CORS_ORIGINS"]}}, supports_credentials=True)

    from .blueprints.health import bp as health_bp
    from .blueprints.auth import bp as auth_bp
    from .blueprints.cases import bp as cases_bp
    from .blueprints.items import case_bp as case_items_bp, lib_bp as items_lib_bp
    from .blueprints.recommendations import bp as recs_bp
    from .blueprints.documents import bp as documents_bp
    from .blueprints.alerts import bp as alerts_bp
    from .blueprints.ml import bp as ml_bp
    from .blueprints.terms import bp as terms_bp
    from .blueprints.me import bp as me_bp
    from .blueprints.communications import bp as communications_bp
    from .blueprints.ale import bp as ale_bp
    from .blueprints.meta import bp as meta_bp

    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(cases_bp)
    app.register_blueprint(case_items_bp)
    app.register_blueprint(items_lib_bp)
    app.register_blueprint(recs_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(alerts_bp)
    app.register_blueprint(ml_bp)
    app.register_blueprint(terms_bp)
    app.register_blueprint(me_bp)
    app.register_blueprint(communications_bp)
    app.register_blueprint(ale_bp)
    app.register_blueprint(meta_bp)

    from .commands import register_commands

    register_commands(app)

    # The resources catalog rarely changes; let the browser cache it. Other
    # endpoints stay no-store because they're per-user and mutate often.
    @app.after_request
    def _cache_headers(response):
        from flask import request as _req
        if _req.path.startswith("/recommendations/resources"):
            response.headers.setdefault("Cache-Control", "private, max-age=300")
        elif _req.path.startswith("/meta/"):
            # Static lookup data; safe to cache for an hour.
            response.headers.setdefault("Cache-Control", "private, max-age=3600")
        else:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    # Defense-in-depth headers. This is a JSON API, so the CSP can be
    # maximally strict: nothing here should ever execute in a browser.
    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Content-Security-Policy", "default-src 'none'")
        return response

    # A Gemini outage that survives retries surfaces as ModelOverloaded. Map it
    # to 503 everywhere, so document analysis and program scraping degrade the
    # same friendly way the photo scan already does, instead of an opaque 500.
    from .services.gemini_client import ModelOverloaded

    @app.errorhandler(ModelOverloaded)
    def _model_overloaded(e):
        return jsonify({"error": str(e)}), 503

    @app.errorhandler(404)
    def _not_found(_e):
        return jsonify({"error": "not found"}), 404

    @app.errorhandler(405)
    def _method_not_allowed(_e):
        return jsonify({"error": "method not allowed"}), 405

    # Catch-all for unhandled exceptions. Without this, a raised error (e.g. a
    # Postgres constraint violation surfacing as a Supabase APIError) returns
    # an opaque HTML 500 with the traceback lost. Here we log the full
    # traceback server-side for diagnosis and return a clean JSON 500 so the
    # frontend can show its friendly message.
    @app.errorhandler(Exception)
    def _unhandled(e):
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e  # 4xx/5xx with their own handling pass through unchanged
        app.logger.exception("Unhandled exception on %s %s", request.method, request.path)
        return jsonify({"error": "Something went wrong on our side. Please try again."}), 500

    return app

#!/usr/bin/env python3
"""
Generate a self-contained HTML report from the SQLite test results.
Serves it on a simple HTTP server for remote access.

This dashboard renders a single section: the Skill Testing tab
(``skills_testing.reporting.dashboard.render_skill_tab``), which reads
skill-run grading/benchmarking results from the ``skill_test_results``,
``skill_grader_results``, and ``skill_release_evaluations`` tables. The
legacy Q&A/doc-search tabs (MCP Server Performance, MCP Retrieval Accuracy,
CLI Integration, LLM Comparison, Answer Quality, Cost & Routing) and their
underlying tables (``performance_results``, ``accuracy_results``,
``copilot_integration_results``, ``answer_quality_results``) and writer
functions have been removed outright -- that benchmark had no live entry
point.

Usage:
    python3 generate_report.py          # Generate report and serve on port 8080
    python3 generate_report.py --port 9090  # Custom port
"""

import argparse
import html as html_module
import sqlite3
import os
import sys
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, unquote


def query_db(db_path: str, sql: str, params: tuple = ()) -> list[dict]:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    result = [dict(r) for r in rows]
    conn.close()
    return result


def generate_html(db_path: str) -> str:
    # --- Skill Testing tab content ---
    try:
        from skills_testing.reporting.dashboard import render_skill_tab
        _conn_skill = sqlite3.connect(db_path)
        try:
            _skill_html = render_skill_tab(_conn_skill)
        finally:
            _conn_skill.close()
    except Exception as _exc:  # never block the rest of the dashboard
        _skill_html = (
            '<h2>Skill Testing</h2>'
            f'<p style="color:#cf222e">Failed to render: {html_module.escape(str(_exc))}</p>'
        )

    # --- Test run history (all runs recorded in test_runs) ---
    runs = query_db(db_path, "SELECT * FROM test_runs ORDER BY timestamp DESC")
    latest_run = runs[0] if runs else {}

    # ========================================================================
    # HTML GENERATION
    # ========================================================================
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Skill Testing Report</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0d1117; color: #e6edf3; padding: 20px; }}
  h1 {{ font-size: 1.8em; margin-bottom: 8px; color: #58a6ff; }}
  h2 {{ font-size: 1.4em; margin: 30px 0 16px 0; padding: 10px 16px; background: #161b22; border-left: 4px solid #58a6ff; border-radius: 4px; }}
  h3 {{ font-size: 1.1em; margin: 20px 0 10px 0; color: #8b949e; }}
  .subtitle {{ color: #8b949e; margin-bottom: 20px; font-size: 0.9em; }}
  .summary {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin: 16px 0; }}
  .stat {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; text-align: center; }}
  .stat .value {{ font-size: 1.8em; font-weight: bold; color: #58a6ff; }}
  .stat .label {{ font-size: 0.85em; color: #8b949e; margin-top: 4px; }}
  table {{ width: 100%; border-collapse: collapse; margin: 12px 0; font-size: 0.85em; }}
  th {{ background: #161b22; color: #8b949e; padding: 10px 12px; text-align: left; border-bottom: 2px solid #30363d; position: sticky; top: 0; }}
  td {{ padding: 8px 12px; border-bottom: 1px solid #21262d; }}
  tr:hover td {{ background: #161b22; }}
  .good {{ color: #3fb950; }}
  .warn {{ color: #d29922; }}
  .bad {{ color: #f85149; }}
  .table-wrap {{ max-height: 500px; overflow-y: auto; border: 1px solid #30363d; border-radius: 8px; }}
  .run-selector {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 10px 16px; margin: 12px 0; display: flex; align-items: center; gap: 12px; }}
  .run-selector label {{ color: #8b949e; font-weight: 600; font-size: 0.9em; white-space: nowrap; }}
  .run-selector select {{ background: #0d1117; color: #e6edf3; border: 1px solid #30363d; border-radius: 6px; padding: 6px 12px; font-size: 0.88em; font-family: 'SF Mono', SFMono-Regular, Consolas, monospace; min-width: 360px; cursor: pointer; }}
  .run-selector select:hover {{ border-color: #58a6ff; }}
  @media (max-width: 800px) {{ .summary {{ grid-template-columns: repeat(2, 1fr); }} .run-selector {{ flex-direction: column; align-items: flex-start; }} .run-selector select {{ min-width: 100%; }} }}
</style>
</head>
<body>

<h1>Skill Testing Report</h1>
<p class="subtitle">{len(runs)} test run(s) recorded{' | latest: ' + latest_run.get('timestamp','N/A')[:19].replace('T',' ') if latest_run else ''}</p>

<div id="tab-skill">
{_skill_html}
</div>

<h3>Test Run History</h3>
<div class="table-wrap"><table>
<thead><tr><th>Run ID</th><th>Timestamp</th><th>Device</th><th>Tool</th><th>Release</th><th>Suite</th><th>CLI</th><th>Queries</th></tr></thead><tbody>
"""
    for r in runs:
        html += f'<tr><td>{r["run_id"]}</td><td>{r["timestamp"][:19]}</td><td>{r["device_filter"]}</td><td>{r.get("tool_filter","all")}</td><td>{r["release_filter"]}</td><td>{r["suite"]}</td><td>{r.get("cli_backend","")}</td><td>{r["queries_run"]}</td></tr>\n'

    html += """</tbody></table></div>

</body></html>"""
    return html


class ReportHandler(BaseHTTPRequestHandler):
    """HTTP handler that regenerates the report on every request."""
    db_path = ""
    # Filesystem root the ``/logs/<...>`` download route serves from (the
    # session-log directory). Set in main(); "" disables the route.
    logs_root = ""
    # Reap idle sockets (e.g. a browser's speculative pre-connect that never
    # sends a request) instead of blocking a worker thread on them forever.
    timeout = 30

    def _send_no_cache(self):
        """Tell the browser never to cache — every reload must re-fetch so a
        refresh always reflects the latest results in the DB."""
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ("/", "/index.html"):
            html = generate_html(self.db_path)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self._send_no_cache()
            self.end_headers()
            self.wfile.write(html.encode("utf-8"))
        elif parsed.path.startswith("/logs/"):
            self._serve_session_log(unquote(parsed.path[len("/logs/"):]))
        else:
            self.send_error(404)

    def _serve_session_log(self, rel: str):
        """Serve a saved session-log JSON as a download, guarding against any
        path traversal outside ``logs_root``."""
        if not self.logs_root:
            self.send_error(404)
            return
        base = Path(self.logs_root).resolve()
        target = (base / rel).resolve()
        if base != target and base not in target.parents:
            self.send_error(403)
            return
        if not (target.is_file() and target.suffix == ".json"):
            self.send_error(404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Disposition",
                         f'attachment; filename="{target.name}"')
        self._send_no_cache()
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format, *args):
        pass  # Quiet logging


def main():
    parser = argparse.ArgumentParser(description="Generate and serve HTML test report")
    parser.add_argument("--port", type=int, default=8080, help="HTTP server port (default: 8080)")
    parser.add_argument("--db", type=str, default=None, help="Path to SQLite results DB (default: results.db)")
    args = parser.parse_args()

    if args.db:
        db_path = args.db
    else:
        # Resolve the DB the harness actually writes to (see db_writer._get_db_path),
        # not a stray reporting/results.db next to this module.
        import yaml
        from skills_testing.core import db_writer
        from skills_testing.core.paths import DEFAULT_CONFIG
        _cfg = yaml.safe_load(DEFAULT_CONFIG.read_text())
        db_path = str(db_writer._get_db_path(_cfg))
    from skills_testing.core.paths import REPORTS_DIR
    report_dir = REPORTS_DIR
    report_dir.mkdir(parents=True, exist_ok=True)

    # Line-buffer stdout so startup messages (and the URL to open) appear
    # immediately. Without this they are block-buffered when output is piped
    # or redirected, and serve_forever() then blocks forever — so the user
    # sees a hung terminal with no URL and assumes the report never started.
    try:
        sys.stdout.reconfigure(line_buffering=True)
    except Exception:
        pass

    # Also write a static copy
    print("Generating static report from", db_path, flush=True)
    if not os.path.exists(db_path):
        print(f"WARNING: results DB not found at {db_path} — the report will "
              f"be empty. Run a suite first, or pass --db <path>.", flush=True)
    html = generate_html(db_path)
    report_path = report_dir / "index.html"
    with open(report_path, "w") as f:
        f.write(html)
    print(f"Static report written to {report_path}", flush=True)

    # Serve dynamically
    ReportHandler.db_path = db_path
    # Resolve the session-log root so the /logs/<...> download route can serve
    # saved session-log JSON files (matches dashboard's ../logs/<rel> links).
    try:
        from skills_testing.core.paths import resolve_project_path
        from skills_testing.core.session_log import SessionLogConfig
        ReportHandler.logs_root = str(resolve_project_path(SessionLogConfig().dir))
    except Exception:
        ReportHandler.logs_root = ""
    try:
        # ThreadingHTTPServer (not the single-threaded HTTPServer): browsers
        # open speculative/pre-connect sockets, and a single-threaded server
        # blocks on the first one waiting for a request line that never comes,
        # so the actual refresh request stalls. One thread per connection keeps
        # reloads responsive (and idle sockets are reaped via handler.timeout).
        server = ThreadingHTTPServer(("0.0.0.0", args.port), ReportHandler)
    except OSError as exc:
        print(f"\nERROR: could not bind port {args.port}: {exc}", flush=True)
        print(f"The port may already be in use. Try a different one, e.g. "
              f"--port {args.port + 1}", flush=True)
        return
    # Bound to 0.0.0.0 (all interfaces), so localhost is the address to open
    # in the browser — 0.0.0.0 itself is not a browsable address.
    print(f"\nServing report — open it in your browser at:", flush=True)
    print(f"    http://localhost:{args.port}/", flush=True)
    print("Press Ctrl+C to stop.\n", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()

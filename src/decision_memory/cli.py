import argparse
import json
import os
from pathlib import Path
import sys

from .models import parse_record
from .store import MemoryError, Store, atomic_write, json_bytes, restore


PROJECT = Path(__file__).resolve().parents[2]
DEFAULT_VAULT = PROJECT / "vault"


def main():
    parser = argparse.ArgumentParser(description="人工审核的个人决策记忆库")
    parser.add_argument("--vault", type=Path, default=DEFAULT_VAULT)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init")
    doctor = commands.add_parser("doctor")
    doctor.add_argument("--rebuild", action="store_true")
    stage = commands.add_parser("stage", help="仅生成候选，不批准；需用户明确要求")
    stage.add_argument("file", type=Path)
    search = commands.add_parser("search")
    search.add_argument("query")
    search.add_argument("--project", default="")
    search.add_argument("--environment", action="append", default=[])
    context = commands.add_parser("context")
    context.add_argument("query")
    context.add_argument("--project", default="")
    context.add_argument("--environment", action="append", default=[])
    context.add_argument("--max-chars", type=int, default=10000)
    review = commands.add_parser("review")
    review.add_argument("--port", type=int, default=0)
    review.add_argument("--session-file", type=Path, default=PROJECT / "runtime/review-session.json")
    commands.add_parser("mcp")
    export = commands.add_parser("export")
    export.add_argument("destination", type=Path)
    recovering = commands.add_parser("restore")
    recovering.add_argument("archive", type=Path)
    recovering.add_argument("destination", type=Path)
    args = parser.parse_args()
    store = Store(args.vault)
    try:
        match args.command:
            case "init":
                store.init()
                result = store.doctor()
            case "doctor":
                result = store.doctor(args.rebuild)
            case "stage":
                result = {"draft": store.stage(parse_record(args.file.read_bytes())), "approved": False}
            case "search":
                result = store.search(args.query, args.project, args.environment)
            case "context":
                result = store.context(args.query, args.project, args.environment, args.max_chars)
            case "export":
                result = store.export(args.destination)
            case "restore":
                result = restore(args.archive, args.destination)
            case "review":
                from .review import create_server
                store.doctor()
                server = create_server(store, args.port)
                session = {"pid": os.getpid(), "url": server.review_url, "vault": str(store.root)}
                atomic_write(args.session_file, json_bytes(session))
                print(json.dumps(session, ensure_ascii=False), flush=True)
                try:
                    server.serve_forever()
                except KeyboardInterrupt:
                    pass
                finally:
                    server.server_close()
                return
            case "mcp":
                from .server import run
                run(store)
                return
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "doctor" and not result["ok"]:
            sys.exit(1)
    except (OSError, ValueError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)

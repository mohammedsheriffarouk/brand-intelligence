#!/usr/bin/env python3
"""Brand Intelligence CLI.
  python run.py validate          # validate ALL sources (homepage + RSS discovery/test)
  python run.py daily             # collect -> process -> classify/score -> DB -> reports -> sheet -> notify
  python run.py weekly | monthly  # periodic reports + notifications
  python run.py status            # print dashboard numbers
  python run.py rescore           # re-apply scoring rules to all stored articles + resync Sheet
  flags: --no-notify  --force (ignore source frequency)"""
import json, sys

from engine import db, pipeline, sources

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "daily"
    notify_on = "--no-notify" not in sys.argv
    if cmd == "validate":
        con = db.connect()
        res = sources.validate_all(con, log=pipeline.Logger("validate"))
        db.export(con)
        pipeline.dashboard(con)
        print(f"validated {len(res)} sources; working RSS: {sum(r['collection_method']=='rss' for r in res)}")
    elif cmd == "daily":
        sys.exit(0 if pipeline.run_daily(notify_on, force="--force" in sys.argv) == "ok" else 1)
    elif cmd in ("weekly", "monthly"):
        pipeline.run_periodic(cmd, notify_on)
    elif cmd == "rescore":
        pipeline.rescore()
    elif cmd == "status":
        print(json.dumps(pipeline.dashboard(db.connect()), indent=1))
    else:
        print(__doc__)

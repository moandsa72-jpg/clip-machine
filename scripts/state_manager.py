import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_state(path):
    path = Path(path)
    if not path.exists():
        return {"stages": {}, "updated_at": None}
    try:
        with path.open(encoding="utf-8") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {"stages": {}, "updated_at": None}
    except (OSError, json.JSONDecodeError):
        return {"stages": {}, "updated_at": None}


def save_state(path, state):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with path.open("w", encoding="utf-8") as file:
        json.dump(state, file, indent=2, ensure_ascii=False)


def is_complete(path, stage):
    return bool(load_state(path).get("stages", {}).get(stage, {}).get("status") == "complete")


def mark_complete(path, stage, outputs=None):
    state = load_state(path)
    state.setdefault("stages", {})[stage] = {
        "status": "complete",
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "outputs": outputs or [],
    }
    save_state(path, state)


def mark_failed(path, stage, error):
    state = load_state(path)
    state.setdefault("stages", {})[stage] = {
        "status": "failed",
        "error": str(error),
        "failed_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(path, state)


def main():
    if len(sys.argv) < 4:
        raise SystemExit("Usage: state_manager.py <is-complete|mark-complete|mark-failed> <state> <stage> [details]")

    command, path, stage = sys.argv[1:4]
    if command == "is-complete":
        raise SystemExit(0 if is_complete(path, stage) else 1)
    if command == "mark-complete":
        outputs = sys.argv[4:] if len(sys.argv) > 4 else []
        mark_complete(path, stage, outputs)
        return
    if command == "mark-failed":
        mark_failed(path, stage, " ".join(sys.argv[4:]) if len(sys.argv) > 4 else "unknown error")
        return
    raise SystemExit(f"Unknown command: {command}")


if __name__ == "__main__":
    main()

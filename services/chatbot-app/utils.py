def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_serialize(obj: Any) -> Any:
    if obj is None:
        return None

    if isinstance(obj, (str, int, float, bool)):
        return obj

    if isinstance(obj, dict):
        return {k: safe_serialize(v) for k, v in obj.items()}

    if isinstance(obj, list):
        return [safe_serialize(v) for v in obj]

    if hasattr(obj, "as_dict") and callable(obj.as_dict):
        try:
            return safe_serialize(obj.as_dict())
        except Exception:
            pass

    if hasattr(obj, "model_dump") and callable(obj.model_dump):
        try:
            return safe_serialize(obj.model_dump())
        except Exception:
            pass

    if hasattr(obj, "__dict__"):
        try:
            return safe_serialize(vars(obj))
        except Exception:
            pass

    return str(obj)


def append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
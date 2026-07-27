import re


def build_plot_tracks(items) -> dict:
    threads = []
    events = []
    for item in items:
        threads.append(item.name)
        events.extend(plot_track_events(item))

    events.sort(key=lambda event: event["chapter"])
    return {"threads": threads, "events": events}


def plot_track_events(item) -> list[dict]:
    progress_text = getattr(item, "progress", "") or ""
    lines = progress_text.splitlines()
    if not lines or all(not line.strip() for line in lines):
        return [{
            "chapter": getattr(item, "chapter_created", 1) or 1,
            "thread": item.name,
            "progress": "线索开启",
        }]

    events = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^[-*\s]*\[?第\s*(\d+)\s*章\]?\s*[:：]?\s*(.*)$", line)
        if match:
            events.append({
                "chapter": int(match.group(1)),
                "thread": item.name,
                "progress": match.group(2).strip(),
            })
        else:
            events.append({
                "chapter": getattr(item, "chapter_updated", 1) or 1,
                "thread": item.name,
                "progress": line.lstrip("-* ").strip(),
            })
    return events

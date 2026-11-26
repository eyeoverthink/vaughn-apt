"""Local Spatial Home OS server: serves static 3D web apps + REST JSON API for data/home_graph.json."""
import json
import os
import re
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

PROJECT_DIR = Path(__file__).resolve().parent.parent
GRAPH_PATH = PROJECT_DIR / "data" / "home_graph.json"
PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8765


def load_graph() -> dict:
    return json.loads(GRAPH_PATH.read_text(encoding="utf-8"))


def save_graph(data: dict) -> None:
    GRAPH_PATH.parent.mkdir(parents=True, exist_ok=True)
    GRAPH_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def find_best_node(nodes: list[dict], target_text: str) -> dict | None:
    q = target_text.lower().strip()
    tokens = [t for t in re.findall(r"[a-z0-9#]+", q) if len(t) > 1 or t.isdigit()]
    best, best_score = None, 0
    for node in nodes:
        hay = f"{node['id']} {node['room']} {node['label']} {node.get('category','')}".lower()
        score = 0
        if q in hay:
            score += 10
        for tok in tokens:
            if tok in hay:
                score += 3
            # Handle ordinal aliases ("second shelf" -> "shelf-2", "2nd" -> "2")
            if tok in ("second", "2nd") and ("shelf-2" in hay or "#2" in hay):
                score += 8
            if tok in ("first", "top", "1st") and ("shelf-1" in hay or "#1" in hay):
                score += 8
            if tok in ("third", "bottom", "lower", "3rd") and ("shelf-3" in hay or "#3" in hay):
                score += 8
            if tok in ("extra", "bedroom", "office") and "studio" in hay:
                score += 4
        if score > best_score:
            best, best_score = node, score
    return best if best_score > 0 else None


def search_graph(graph: dict, query: str) -> list[dict]:
    q = query.lower().strip()
    tokens = [t for t in re.findall(r"[a-z0-9]+", q) if len(t) > 1 or t.isdigit()]
    if not tokens:
        return []
    hits = []
    for node in graph.get("nodes", []):
        matched_items = []
        matched_files = []
        score = 0
        node_text = f"{node['id']} {node['room']} {node['label']} {node.get('notes','')} {node.get('category','')}".lower()
        for tok in tokens:
            if tok in node_text:
                score += 2
        for item in node.get("physical_items", []):
            it_text = f"{item['name']} {' '.join(item.get('tags', []))}".lower()
            s = sum(4 for tok in tokens if tok in it_text)
            if s > 0:
                score += s
                matched_items.append(item)
        for fobj in node.get("digital_files", []):
            ft_text = f"{fobj['name']} {fobj.get('path','')} {fobj.get('type','')}".lower()
            s = sum(4 for tok in tokens if tok in ft_text)
            if s > 0:
                score += s
                matched_files.append(fobj)
        if score > 0:
            hits.append({
                "node_id": node["id"],
                "label": node["label"],
                "room": node["room"],
                "score": score,
                "matched_items": matched_items,
                "matched_files": matched_files,
            })
    hits.sort(key=lambda x: x["score"], reverse=True)
    return hits


def handle_nl_command(graph: dict, raw_cmd: str) -> dict:
    """Parse natural-language spatial commands: add item, save file, bom check, or search."""
    cmd = raw_cmd.strip()
    low = cmd.lower()

    # 1) Save file command: "save <filename> to/on/in <location>"
    m_file = re.match(r"^(?:save|pin|attach)\s+(?:file\s+)?(.+?)\s+(?:to|on|in|at)\s+(.+)$", cmd, re.I)
    if m_file:
        fname, loc_txt = m_file.group(1).strip().strip("'\""), m_file.group(2).strip()
        node = find_best_node(graph["nodes"], loc_txt)
        if node:
            node.setdefault("digital_files", []).append({
                "name": Path(fname).name if ("/" in fname or "\\" in fname) else fname,
                "path": fname,
                "type": "file",
            })
            save_graph(graph)
            return {
                "action": "added_file",
                "node_id": node["id"],
                "message": f"Saved '{fname}' to {node['label']} ({node['id']})",
                "graph": graph,
            }

    # 2) Put/Add physical item: "add/put <item> [xN] to/on/in <location>"
    m_item = re.match(r"^(?:add|put|store|move)\s+(.+?)\s+(?:to|on|in|into|at)\s+(.+)$", cmd, re.I)
    if m_item:
        item_raw, loc_txt = m_item.group(1).strip(), m_item.group(2).strip()
        qty = 1
        m_qty = re.search(r"\b(?:x|\*)(\d+)\b|\b(\d+)\s*x\b", item_raw, re.I)
        if m_qty:
            qty = int(m_qty.group(1) or m_qty.group(2))
            item_raw = re.sub(r"\b(?:x|\*)\d+\b|\b\d+\s*x\b", "", item_raw, flags=re.I).strip()
        node = find_best_node(graph["nodes"], loc_txt)
        if node:
            tags = [t for t in re.findall(r"[a-z0-9]+", item_raw.lower()) if len(t) > 2]
            node.setdefault("physical_items", []).append({"name": item_raw, "qty": qty, "tags": tags})
            save_graph(graph)
            return {
                "action": "added_item",
                "node_id": node["id"],
                "message": f"Stored '{item_raw}' (×{qty}) at {node['label']} ({node['id']})",
                "graph": graph,
            }

    # 3) BOM / Project feasibility query: "bom <project>" or "build <project>" or "do i have <parts>"
    if low.startswith(("bom ", "build ", "do i have ", "parts for ")):
        cleaned = re.sub(r"^(?:bom|build|do i have|parts for)\s+", "", low)
        # Expand common maker project concepts to part keywords!
        expansions = {
            "lamp": "esp32 led wled mosfet smart lamp",
            "plant": "arduino esp32 sensor dht22 breadboard",
            "robot": "arduino raspberry pi sensor l293d breadboard 3d printer",
            "fpga": "basys fpga circuit breadboard ic",
            "synth": "midi arduino music mixer audio",
            "printer": "3d printer filament nozzle",
        }
        expanded = cleaned
        for k, v in expansions.items():
            if k in cleaned:
                expanded += " " + v
        hits = search_graph(graph, expanded)
        if hits:
            summary_lines = [f"{h['label']}: {', '.join(i['name'] for i in h['matched_items'][:3])}" for h in hits[:4] if h["matched_items"]]
            return {
                "action": "bom_result",
                "node_id": hits[0]["node_id"],
                "hits": hits,
                "message": "Found matching hardware across your apartment! " + (" | ".join(summary_lines) if summary_lines else ""),
            }
        return {"action": "not_found", "hits": [], "message": f"No matching parts found for '{cmd}' yet — try adding items to your Studio shelves!"}

    # 4) Default: Unified Spatial Search across atoms + bits + locations
    cleaned_q = re.sub(r"^(?:where is|where are|find|locate|show|go to|open)\s+(?:my\s+)?", "", low)
    hits = search_graph(graph, cleaned_q)
    if hits:
        top = hits[0]
        return {
            "action": "search_hit",
            "node_id": top["node_id"],
            "hits": hits,
            "message": f"Found in {top['room']} → {top['label']} ({len(hits)} matching zone{'s' if len(hits)!=1 else ''})",
        }
    return {"action": "not_found", "hits": [], "message": f"Nothing matched '{cmd}'. Try 'add <item> to studio shelf 2' or search 'basys', 'circuit', 'vault', 'tv'."}


class HomeOSHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(PROJECT_DIR), **kwargs)

    def send_json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length > 0 else b"{}"
        return json.loads(raw.decode("utf-8"))

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/graph":
            return self.send_json(load_graph())
        if parsed.path == "/api/health":
            return self.send_json({"ok": True, "service": "vaughn-apt-home-os", "port": PORT})
        if parsed.path in ("/", "/web", "/web/"):
            self.send_response(302)
            self.send_header("Location", "/web/home_os.html")
            self.end_headers()
            return
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        try:
            body = self.read_json()
        except Exception as exc:
            return self.send_json({"error": f"Invalid JSON: {exc}"}, 400)

        graph = load_graph()

        if parsed.path == "/api/command":
            res = handle_nl_command(graph, body.get("command", ""))
            return self.send_json(res)

        if parsed.path == "/api/node/add-item":
            nid = body.get("node_id")
            name = (body.get("name") or "").strip()
            qty = max(1, int(body.get("qty") or 1))
            tags = [t.strip().lower() for t in (body.get("tags") or []) if t.strip()]
            if not tags:
                tags = [t for t in re.findall(r"[a-z0-9]+", name.lower()) if len(t) > 2]
            for n in graph["nodes"]:
                if n["id"] == nid:
                    n.setdefault("physical_items", []).append({"name": name, "qty": qty, "tags": tags})
                    save_graph(graph)
                    return self.send_json({"ok": True, "graph": graph})
            return self.send_json({"error": "Node not found"}, 404)

        if parsed.path == "/api/node/delete-item":
            nid, idx = body.get("node_id"), int(body.get("index", -1))
            for n in graph["nodes"]:
                if n["id"] == nid and 0 <= idx < len(n.get("physical_items", [])):
                    n["physical_items"].pop(idx)
                    save_graph(graph)
                    return self.send_json({"ok": True, "graph": graph})
            return self.send_json({"error": "Item not found"}, 404)

        if parsed.path == "/api/node/add-file":
            nid = body.get("node_id")
            name = (body.get("name") or "").strip()
            path = (body.get("path") or name).strip()
            ftype = (body.get("type") or "file").strip()
            for n in graph["nodes"]:
                if n["id"] == nid:
                    n.setdefault("digital_files", []).append({"name": name, "path": path, "type": ftype})
                    save_graph(graph)
                    return self.send_json({"ok": True, "graph": graph})
            return self.send_json({"error": "Node not found"}, 404)

        if parsed.path == "/api/node/delete-file":
            nid, idx = body.get("node_id"), int(body.get("index", -1))
            for n in graph["nodes"]:
                if n["id"] == nid and 0 <= idx < len(n.get("digital_files", [])):
                    n["digital_files"].pop(idx)
                    save_graph(graph)
                    return self.send_json({"ok": True, "graph": graph})
            return self.send_json({"error": "File not found"}, 404)

        if parsed.path == "/api/node/notes":
            nid = body.get("node_id")
            notes = body.get("notes", "")
            for n in graph["nodes"]:
                if n["id"] == nid:
                    n["notes"] = notes
                    save_graph(graph)
                    return self.send_json({"ok": True, "graph": graph})
            return self.send_json({"error": "Node not found"}, 404)

        if parsed.path == "/api/mood":
            graph["lighting_mood"] = body.get("mood", "afternoon")
            save_graph(graph)
            return self.send_json({"ok": True, "graph": graph})

        if parsed.path == "/api/open-local":
            raw_p = (body.get("path") or "").strip()
            if raw_p.startswith(("http://", "https://")):
                return self.send_json({"ok": True, "url": raw_p})
            candidate = Path(raw_p)
            if not candidate.is_absolute():
                candidate = (PROJECT_DIR / raw_p).resolve()
            if candidate.exists():
                try:
                    os.startfile(str(candidate))
                    return self.send_json({"ok": True, "opened": str(candidate)})
                except Exception as exc:
                    return self.send_json({"ok": False, "error": str(exc)}, 500)
            return self.send_json({"ok": False, "error": f"Local path not found yet: {candidate}"}, 404)

        return self.send_json({"error": "Unknown API endpoint"}, 404)

    def log_message(self, fmt, *args):
        # Keep console clean
        pass


def main():
    print(f"vaughn-apt Spatial Home OS Server running on http://localhost:{PORT}/web/home_os.html")
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), HomeOSHandler)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()


if __name__ == "__main__":
    main()

"""Automated verification tests for vaughn-apt Spatial Home OS (Phases 1-4)."""
import copy
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import home_os_server as srv


def main() -> None:
    g = srv.load_graph()
    assert len(g["nodes"]) == 14, f"Expected 14 nodes, got {len(g['nodes'])}"

    # Phase 1: Spatial Search & BOM
    r1 = srv.handle_nl_command(copy.deepcopy(g), "where is my basys board")
    assert r1["node_id"] == "apt://studio/white-cube-shelf/shelf-2", r1
    r2 = srv.handle_nl_command(copy.deepcopy(g), "circuit drawing")
    assert r2["node_id"] == "apt://studio/white-cube-shelf/shelf-2", r2
    r3 = srv.handle_nl_command(copy.deepcopy(g), "bom smart lamp")
    assert r3["action"] == "bom_result" and len(r3["hits"]) >= 2, r3
    r4 = srv.handle_nl_command(copy.deepcopy(g), "find vault documents")
    assert r4["node_id"] == "apt://hall/closet", r4

    # Phase 2: Local Filesystem Browser
    fs = srv.browse_local_folder("docs")
    assert fs["ok"] and any(e["name"] == "REALITY_OS_ARCHITECTURE.md" for e in fs["entries"]), fs

    # Phase 3: Cyber-Physical Hardware Bridge (WLED simulated pulse)
    dev_res = srv.trigger_hardware_device(
        {"type": "wled_pick_to_light", "label": "Shelf 2 LED", "endpoint": ""}, "pulse"
    )
    assert dev_res["ok"] and dev_res["simulated"], dev_res

    # Phase 4: Room-Aware Spatial Agent
    a1 = srv.run_spatial_agent(copy.deepcopy(g), "what is here?", "apt://studio/white-cube-shelf/shelf-2")
    assert "Basys 3" in a1["reply"] and "circuit_drawing" in a1["reply"], a1
    a2 = srv.run_spatial_agent(copy.deepcopy(g), "bom robot", None)
    assert a2["node_id"] and "BOM Pick-List" in a2["reply"], a2
    a3 = srv.run_spatial_agent(copy.deepcopy(g), "inventory summary", None)
    assert "14 spatial nodes" in a3["reply"], a3

    print("ALL PHASES 1-4 SPATIAL HOME OS TESTS PASSED!")


if __name__ == "__main__":
    main()

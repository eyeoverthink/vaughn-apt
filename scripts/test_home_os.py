"""Automated verification tests for vaughn-apt Spatial Home OS (Phases 1-5 Complete)."""
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

    # Phase 5: Server-Side Guest Privacy Redaction & Front Door Doorman Triage
    srv.GUEST_ROOM_ACCESS["studio_unlocked"] = False
    redacted = srv.redact_graph_for_guest(copy.deepcopy(g))
    vault = next(n for n in redacted["nodes"] if n["id"] == "apt://hall/closet")
    shelf2 = next(n for n in redacted["nodes"] if n["id"] == "apt://studio/white-cube-shelf/shelf-2")
    tv = next(n for n in redacted["nodes"] if n["id"] == "apt://living/tv")
    assert vault.get("locked") is True and len(vault["physical_items"]) == 0, vault
    assert shelf2.get("locked") is True and len(shelf2["digital_files"]) == 0, shelf2
    assert not tv.get("locked") and len(tv["digital_files"]) > 0, tv

    # Unlock studio for guest collaboration while Vault stays strictly locked!
    srv.GUEST_ROOM_ACCESS["studio_unlocked"] = True
    redacted2 = srv.redact_graph_for_guest(copy.deepcopy(g))
    vault2 = next(n for n in redacted2["nodes"] if n["id"] == "apt://hall/closet")
    shelf2_open = next(n for n in redacted2["nodes"] if n["id"] == "apt://studio/white-cube-shelf/shelf-2")
    assert vault2.get("locked") is True, vault2
    assert not shelf2_open.get("locked") and len(shelf2_open["physical_items"]) > 0, shelf2_open
    srv.GUEST_ROOM_ACCESS["studio_unlocked"] = False

    # Doorman Comms Auto-Triage
    vip = srv.triage_incoming_message("Maya (VIP)", "SMS", "Coming over to jam!")
    promo = srv.triage_incoming_message("Deals", "Email", "Flash sale newsletter promo")
    std = srv.triage_incoming_message("GitHub", "Email", "Build complete")
    assert vip["status"] == "living_room" and promo["status"] == "held_outside" and std["status"] == "entryway"

    print("ALL PHASES 1-5 SPATIAL HOME OS TESTS PASSED!")


if __name__ == "__main__":
    main()

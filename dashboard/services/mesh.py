"""Mesh status aggregator for the Vivi Mesh dashboard."""

import json
import os
import subprocess
import time
from typing import Any, Dict, List

_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_CACHE_TTL = 30.0

import socket as _socket
def _detect_local_node():
    name = os.environ.get("VIVI_NODE")
    if name:
        return name
    try:
        return open("/proc/sys/kernel/hostname").read().strip()
    except Exception:
        pass
    try:
        return _socket.gethostname()
    except Exception:
        return "begonia"
_LOCAL_NODE = _detect_local_node()

NODES = [
    {"name": "begonia", "user": "joel", "host": "100.112.2.11", "ssh_port": 22, "local": _LOCAL_NODE == "begonia"},
    {"name": "laurel", "user": "user", "host": "100.120.97.92", "ssh_port": 22, "local": _LOCAL_NODE == "laurel"},
    {"name": "ruby", "user": "u0_a421", "host": "100.97.91.9", "ssh_port": 8022, "local": _LOCAL_NODE == "ruby"},
]

# Compact probe: prints one JSON line with node metrics. No secrets.
PROBE = "~/.local/bin/vivi-mesh-probe"


def _run(cmd: List[str], timeout: int = 8) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return None
    except Exception:
        return None


def _probe_local(node: Dict[str, Any]) -> Dict[str, Any]:
    out = _run(["bash", "-lc", PROBE], timeout=5)
    data = _parse(out)
    data["reachable"] = True
    data["node"] = node["name"]
    return data


def _probe_remote(node: Dict[str, Any]) -> Dict[str, Any]:
    ssh = [
        "ssh",
        "-o", "ConnectTimeout=5",
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-p", str(node["ssh_port"]),
        f"{node['user']}@{node['host']}",
        "bash -lc " + chr(39) + PROBE + chr(39),
    ]
    out = _run(ssh, timeout=12)
    data = _parse(out)
    data["reachable"] = bool(out)
    data["node"] = node["name"]
    if not out:
        data["error"] = "ssh_failed"
    return data


def _parse(out: Optional[str]) -> Dict[str, Any]:
    if not out:
        return {}
    try:
        return json.loads(out.splitlines()[-1])
    except Exception:
        return {"raw": out[:200]}


def _cluster_global() -> Dict[str, Any]:
    nats = os.path.expanduser("~/.local/bin/nats")
    out = _run([nats, "--context", "vivi", "kv", "get", "VIVI_HA", "gateway/lease", "--raw"], timeout=8)
    lease = {}
    if out:
        try:
            lease = json.loads(out)
        except Exception:
            lease = {"raw": out[:200]}
    # meta leader / quorum from the local monitor (no system account needed)
    meta_leader = None
    cluster_size = None
    quorum_needed = None
    out2 = _run(["curl", "-s", "http://127.0.0.1:8222/jsz?meta=1&streams=1"], timeout=8)
    if out2:
        try:
            j = json.loads(out2)
            meta = j.get("meta_cluster") or {}
            meta_leader = meta.get("leader")
            cluster_size = meta.get("cluster_size")
            quorum_needed = meta.get("quorum_needed")
        except Exception:
            pass
    kv_leader = None
    if out2:
        try:
            j = json.loads(out2)
            for a in j.get("account_details", []) or []:
                for s in a.get("stream_detail", []) or []:
                    if s.get("name") == "KV_VIVI_HA":
                        kv_leader = (s.get("cluster") or {}).get("leader")
        except Exception:
            pass
    return {
        "lease": lease,
        "meta_leader": meta_leader,
        "cluster_size": cluster_size,
        "quorum_needed": quorum_needed,
        "kv_leader": kv_leader,
    }


def get_mesh_status() -> Dict[str, Any]:
    global _CACHE
    now = time.time()
    if _CACHE["data"] is not None and (now - _CACHE["ts"]) < _CACHE_TTL:
        return _CACHE["data"]

    nodes_out: List[Dict[str, Any]] = []
    for n in NODES:
        if n["local"]:
            nodes_out.append(_probe_local(n))
        else:
            nodes_out.append(_probe_remote(n))

    cluster = _cluster_global()

    data = {
        "generated_at": now,
        "nodes": nodes_out,
        "cluster": cluster,
    }
    _CACHE["ts"] = now
    _CACHE["data"] = data
    return data

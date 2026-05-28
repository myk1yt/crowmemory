#!/usr/bin/env python3
"""
crow_core.py — Crow Memory core engine (complete).
Implements the 8-register synaptic weight matrix with Hebbian EMA updates,
spectral clipping, FAISS-powered value bank retrieval, build hook integration,
system prompt evolution, backup rotation, and drift auto-recovery.

Design: Architecture document v1.3.6, Sections 3–7.
"""

import json
import os
import sys
import time
import base64
import hashlib
import logging
import threading
import atexit
import warnings
from typing import Optional

from collections import OrderedDict

import numpy as np
from safetensors.numpy import load_file, save_file

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("crow_core")

# ---------------------------------------------------------------------------
# File Lock (cross-platform advisory lock via lockfile + PID)
# ---------------------------------------------------------------------------

def _acquire_file_lock(bin_path: str) -> bool:
    """Try to acquire an exclusive advisory lock on crow.bin.
    Returns True if lock acquired, False if another live process holds it."""
    lock_path = bin_path + ".lock"
    my_pid = os.getpid()
    try:
        if os.path.exists(lock_path):
            with open(lock_path, "r") as f:
                stale_pid_str = f.read().strip()
            try:
                stale_pid = int(stale_pid_str)
                if sys.platform == "win32":
                    import ctypes
                    kernel32 = ctypes.windll.kernel32
                    handle = kernel32.OpenProcess(0x0400, False, stale_pid)
                    if handle:
                        exit_code = ctypes.c_ulong()
                        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                        kernel32.CloseHandle(handle)
                        if exit_code.value == 259:
                            logger.warning("crow.bin locked by live process PID %s", stale_pid)
                            return False
                else:
                    try:
                        os.kill(stale_pid, 0)
                        logger.warning("crow.bin locked by live process PID %s", stale_pid)
                        return False
                    except OSError:
                        pass
            except (ValueError, OSError):
                pass
            try:
                os.remove(lock_path)
            except OSError:
                pass
        with open(lock_path, "w") as f:
            f.write(str(my_pid))
        atexit.register(_release_file_lock, lock_path)
        return True
    except OSError as exc:
        logger.warning("Could not acquire lock on crow.bin: %s", exc)
        return False

def _release_file_lock(lock_path: str):
    """Release the advisory lock file if we own it."""
    try:
        if os.path.exists(lock_path):
            with open(lock_path, "r") as f:
                pid_str = f.read().strip()
            if pid_str == str(os.getpid()):
                os.remove(lock_path)
    except OSError:
        pass

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DIM = 4096
EMBED_DIM = 768
MAX_SV = 2.0
NEG_DAMPEN = 0.6
VALUE_BANK_MAX = 500

# 8 registers: 4 coding (original) + 4 personal life
REGISTERS: dict[str, tuple[int, int, float]] = {
    # Coding domain (original v1.0 names preserved)
    "style":   (DIM, DIM,    0.9999),
    "bug":     (2048, 2048,  0.9995),
    "arch":    (2048, 2048,  0.9995),
    "context": (2048, DIM,   0.9500),
    # Life domain (NEW — personal/lifestyle memory)
    "life_pref":    (DIM, DIM,    0.9999),
    "life_avoid":   (2048, 2048,  0.9995),
    "life_phil":    (2048, 2048,  0.9995),
    "life_context": (2048, DIM,   0.9500),
}

# Domain groupings
DOMAINS: dict[str, list[str]] = {
    "code": ["style", "bug", "arch", "context"],
    "life": ["life_pref", "life_avoid", "life_phil", "life_context"],
    "all": ["style", "bug", "arch", "context",
            "life_pref", "life_avoid", "life_phil", "life_context"],
}
CODE_REGISTERS = DOMAINS["code"]
LIFE_REGISTERS = DOMAINS["life"]


# ---------------------------------------------------------------------------
# CrowMemory
# ---------------------------------------------------------------------------

class CrowMemory:
    """Fixed-size associative memory with 8 semantic registers (4 code + 4 life)."""

    def __init__(self, path: str = "./memory/crow.bin"):
        self.path = path
        self.memory_dir = os.path.dirname(path) or "."
        os.makedirs(self.memory_dir, exist_ok=True)

        # Acquire advisory file lock before touching crow.bin
        if not _acquire_file_lock(path):
            raise RuntimeError(
                f"crow.bin is locked by another live process. "
                f"Ensure only one MCP server (preferably SSE) is running."
            )

        try:
            self.data = load_file(path)
            # Migrate: add any missing registers from REGISTERS
            for name, (d_k, d_v, _) in REGISTERS.items():
                key = f"{name}_S"
                if key not in self.data:
                    self.data[key] = np.zeros((d_k, d_v), dtype=np.float16)
        except FileNotFoundError:
            self.data = self._init_blank()
        except ValueError:
            logger.error("crow.bin is corrupted (ValueError). Attempting backup recovery...")
            # Try to recover from the most recent backup
            import glob as _glob
            backups = sorted(_glob.glob(path + ".bak.*"), reverse=True)
            if backups:
                logger.warning("Recovering from backup: %s", backups[0])
                self.data = load_file(backups[0])
                for name, (d_k, d_v, _) in REGISTERS.items():
                    key = f"{name}_S"
                    if key not in self.data:
                        self.data[key] = np.zeros((d_k, d_v), dtype=np.float16)
            else:
                raise RuntimeError(
                    f"crow.bin is corrupted and no backup found at {path}. "
                    f"Please restore from a manual backup or remove the corrupted file to start fresh."
                ) from None

        self._encoder = None
        self._proj_W: Optional[np.ndarray] = None
        self._proj_b: Optional[np.ndarray] = None

        self._value_bank: list[dict] = []
        self._load_value_bank()

        self._faiss_indexes: dict[str, object] = {}
        self._faiss_vectors: dict[str, list[np.ndarray]] = {r: [] for r in REGISTERS}

        self._recall_stats: dict[str, dict] = {}
        self._load_recall_stats()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def _init_blank(self) -> dict:
        data: dict = {}
        for name, (d_k, d_v, _) in REGISTERS.items():
            data[f"{name}_S"] = np.zeros((d_k, d_v), dtype=np.float16)
        rng = np.random.default_rng(42)
        data["proj_W"] = (rng.normal(0, 0.01, (DIM, EMBED_DIM))
                          .astype(np.float16))
        data["proj_b"] = np.zeros(DIM, dtype=np.float16)
        data["update_count"] = np.int64(0)
        data["schema_version"] = np.int64(1)
        return data

    # ------------------------------------------------------------------
    # Encoder (lazy-load)
    # ------------------------------------------------------------------

    @property
    def encoder(self):
        if self._encoder is None:
            from sentence_transformers import SentenceTransformer
            self._encoder = SentenceTransformer(
                "nomic-ai/nomic-embed-text-v1.5",
                trust_remote_code=True,
            )
        return self._encoder

    @property
    def proj_W(self) -> np.ndarray:
        if self._proj_W is None:
            self._proj_W = self.data["proj_W"].astype(np.float32)
        return self._proj_W

    @property
    def proj_b(self) -> np.ndarray:
        if self._proj_b is None:
            self._proj_b = self.data["proj_b"].astype(np.float32)
        return self._proj_b

    _encode_cache_max = 1024

    def encode(self, text: str) -> np.ndarray:
        # Instance-level true LRU cache (initialized lazily)
        if not hasattr(self, '_encode_cache'):
            self._encode_cache: OrderedDict[str, np.ndarray] = OrderedDict()
        # Truncate long inputs — nomic-embed-text-v1.5 works on sentence/paragraph level
        truncated = text[:2000]
        cache_key = truncated[:200]
        if cache_key in self._encode_cache:
            self._encode_cache.move_to_end(cache_key)
            return self._encode_cache[cache_key]
        vec = self.encoder.encode(truncated, normalize_embeddings=True)
        projected = self.proj_W @ vec + self.proj_b
        projected /= (np.linalg.norm(projected) + 1e-8)
        result = projected.astype(np.float16)
        if len(self._encode_cache) >= self._encode_cache_max:
            self._encode_cache.popitem(last=False)  # Remove oldest (LRU)
        self._encode_cache[cache_key] = result
        return result

    def prewarm_encoder(self):
        """Pre-load the embedding model in a background thread so first
        recall/ingest is fast. Call this right after construction."""
        def _load():
            _ = self.encoder  # triggers SentenceTransformer download/load
            logger.info("Encoder pre-warmed.")
        t = threading.Thread(target=_load, daemon=True)
        t.start()

    # ------------------------------------------------------------------
    # Recall (Protocol Alpha)
    # ------------------------------------------------------------------

    def recall(self, query: str, register: str, top_k: int = 2) -> dict:
        if register not in REGISTERS:
            return {"hints": [], "confidence": 0.0, "register": register,
                    "error": f"Unknown register: {register}"}

        q = self.encode(query)
        S = self.data[f"{register}_S"]
        S_f32 = S.astype(np.float32)
        q_f32 = q.astype(np.float32)
        key_dim = REGISTERS[register][0]
        r = S_f32.T @ q_f32[:key_dim]

        S_norm = float(np.linalg.norm(S_f32))
        r_norm = float(np.linalg.norm(r))
        confidence = round(min(r_norm / (S_norm + 1e-8), 1.0), 4)

        hints = self._nearest_hints(r, register, top_k)
        self._track_recall(register, query, confidence, hints)

        return {"hints": hints, "confidence": confidence, "register": register}

    def _nearest_hints(self, r: np.ndarray, register: str, top_k: int) -> list[str]:
        # Try FAISS first, fall back to numpy
        ids, sims = self._faiss_search(r, register, top_k)

        candidates = [e for e in self._value_bank if e.get("register") == register]
        if not candidates:
            return [f"Crow recalls a faint {register} bias. Few memories stored yet."]

        import math
        hints = []
        for idx, sim in zip(ids, sims):
            if idx < len(candidates):
                entry = candidates[idx]
                importance = entry.get("importance", 1.0)
                # Importance-weighted similarity: frequently-ingested / frequently-recalled
                # patterns get a lower visibility threshold (higher effective similarity).
                importance_boost = 1.0 + 0.12 * math.log(max(importance, 0.1) + 1.0)
                effective_sim = sim * importance_boost
                # Base threshold 0.28, high-importance entries get additional leeway
                if effective_sim > 0.28 or (importance > 5.0 and sim > 0.15):
                    hints.append(
                        f"[{register}] {entry['value'][:200]}"
                        f" (sim={sim:.2f})"
                    )

        if not hints:
            hints = [f"Crow recalls a faint {register} bias. Few memories stored yet."]
        return hints

    # ------------------------------------------------------------------
    # Ingest (Protocol Beta)
    # ------------------------------------------------------------------

    def ingest(self, key: str, value: str, polarity: float, register: str) -> dict:
        if register not in REGISTERS:
            return {"status": "error", "message": f"Unknown register: {register}"}

        polarity = float(np.clip(polarity, -2.0, 2.0))
        if polarity < 0:
            polarity *= NEG_DAMPEN

        key_dim, value_dim, lam = REGISTERS[register]
        k = self.encode(key)
        v = self.encode(value)[:value_dim]
        S = self.data[f"{register}_S"]
        S *= lam

        k_trunc = k[:key_dim]
        delta = np.outer(k_trunc.astype(np.float32),
                         v.astype(np.float32)) * (1.0 - lam) * polarity
        S += delta.astype(np.float16)

        self.data["update_count"] = np.int64(int(self.data["update_count"]) + 1)
        self._maybe_clip(register)
        self._append_value_bank(key, value, v, register, polarity)
        self._persist()

        return {
            "status": "ingested",
            "register": register,
            "polarity_applied": round(polarity, 2),
            "update_count": int(self.data["update_count"]),
        }

    def _maybe_clip(self, register: str):
        if int(self.data["update_count"]) % 1000 != 0:
            return
        S = self.data[f"{register}_S"]
        if S.size == 0 or np.all(S == 0):
            return
        S_f32 = S.astype(np.float32)
        try:
            U, s, Vt = np.linalg.svd(S_f32, full_matrices=False)
            s_clipped = np.clip(s, -MAX_SV, MAX_SV)
            self.data[f"{register}_S"] = ((U * s_clipped) @ Vt).astype(np.float16)
        except np.linalg.LinAlgError:
            logger.warning("SVD clipping failed for register %s — falling back to norm clipping.", register)
            # Fallback: simple per-element clipping
            np.clip(S, -MAX_SV, MAX_SV, out=S)

    # ------------------------------------------------------------------
    # Evolve (Protocol Gamma)
    # ------------------------------------------------------------------

    def evolve_propose(self, min_confidence: float = 0.85,
                       min_occurrences: int = 3) -> dict:
        proposals = []
        for register in REGISTERS:
            stats = self._recall_stats.get(register, {})
            for _query_hash, entry in stats.items():
                occ = entry.get("occurrences", 0)
                conf = entry.get("avg_confidence", 0.0)
                last_hints = entry.get("last_hints", [])
                if occ >= min_occurrences and conf >= min_confidence:
                    for hint in last_hints:
                        clean_hint = hint.split("] ", 1)[-1] if "] " in hint else hint
                        if " (sim=" in clean_hint:
                            clean_hint = clean_hint.rsplit(" (sim=", 1)[0]
                        proposals.append({
                            "register": register,
                            "hint": clean_hint,
                            "occurrences": occ,
                            "avg_confidence": round(conf, 3),
                        })
        if not proposals:
            return {
                "proposal": None,
                "message": "No statistically significant patterns detected yet.",
                "requires_human_approval": True,
            }
        best = max(proposals, key=lambda p: p["avg_confidence"] * p["occurrences"])
        proposal_text = (
            f"RULE: When working with {best['register']}-related tasks, "
            f"{best['hint'][:300]}"
        )
        return {
            "proposal": proposal_text,
            "confidence": best["avg_confidence"],
            "occurrences": best["occurrences"],
            "register": best["register"],
            "requires_human_approval": True,
        }

    # ------------------------------------------------------------------
    # Value Bank
    # ------------------------------------------------------------------

    def _append_value_bank(self, key: str, value: str, vector: np.ndarray,
                           register: str, polarity: float = 1.0):
        key_trunc = key[:500]

        # Duplicate key handling: accumulate importance on re-ingest
        existing = None
        for entry in self._value_bank:
            if entry.get("register") == register and entry.get("key") == key_trunc:
                existing = entry
                break

        if existing:
            existing["value"] = value[:1000]
            existing["vector_b64"] = self._encode_vector(vector)
            existing["importance"] = existing.get("importance", 1.0) + abs(polarity)
            existing["ingest_count"] = existing.get("ingest_count", 1) + 1
            existing["timestamp"] = time.time()
            # Append new FAISS vector; index will be rebuilt lazily
            self._faiss_vectors.setdefault(register, []).append(vector.astype(np.float32))
            self._faiss_indexes.pop(register, None)
            return existing

        entry = {
            "key": key_trunc,
            "value": value[:1000],
            "vector_b64": self._encode_vector(vector),
            "register": register,
            "timestamp": time.time(),
            "importance": abs(polarity),
            "ingest_count": 1,
        }
        self._value_bank.append(entry)

        # Importance-based eviction: remove least important entries first
        while len(self._value_bank) > VALUE_BANK_MAX:
            # Find the entry with the lowest importance score
            min_idx = min(
                range(len(self._value_bank)),
                key=lambda i: self._value_bank[i].get("importance", 0),
            )
            self._value_bank.pop(min_idx)
            self._faiss_indexes.pop(register, None)

        self._faiss_vectors.setdefault(register, []).append(vector.astype(np.float32))
        while len(self._faiss_vectors[register]) > VALUE_BANK_MAX:
            self._faiss_vectors[register].pop(0)
        self._faiss_indexes.pop(register, None)
        return entry

    def _load_value_bank(self):
        vb_path = os.path.join(self.memory_dir, "value_bank.json")
        try:
            with open(vb_path, "r", encoding="utf-8") as f:
                self._value_bank = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._value_bank = []

    def _save_value_bank(self):
        vb_path = os.path.join(self.memory_dir, "value_bank.json")
        tmp_path = vb_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._value_bank, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, vb_path)

    @staticmethod
    def _encode_vector(vec: np.ndarray) -> str:
        return base64.b64encode(vec.astype(np.float16).tobytes()).decode("ascii")

    @staticmethod
    def _decode_vector(b64: str) -> np.ndarray:
        return np.frombuffer(base64.b64decode(b64), dtype=np.float16).astype(np.float32)

    # ------------------------------------------------------------------
    # Recall Stats
    # ------------------------------------------------------------------

    _last_recall_prune: float = 0.0
    _recall_stats_max_per_register = 1000

    def _track_recall(self, register: str, query: str,
                      confidence: float, hints: list[str]):
        query_hash = hashlib.md5(query.encode("utf-8")).hexdigest()
        stats = self._recall_stats.setdefault(register, {})
        entry = stats.setdefault(query_hash, {
            "occurrences": 0, "total_confidence": 0.0,
            "avg_confidence": 0.0, "last_hints": [], "last_seen": 0.0,
        })
        entry["occurrences"] += 1
        entry["total_confidence"] += confidence
        entry["avg_confidence"] = entry["total_confidence"] / entry["occurrences"]
        entry["last_hints"] = hints[:3]
        entry["last_seen"] = time.time()

        # Boost value_bank importance for frequently-recalled patterns
        # Each recall adds a small importance increment proportional to confidence
        for hint in hints:
            # Extract register prefix from hint (e.g., "[style] some value (sim=0.85)")
            if hint.startswith("[") and "] " in hint:
                hint_register = hint[1:].split("]", 1)[0]
                if hint_register == register:
                    # Try to match hint text to value_bank entries
                    hint_text = hint.split("] ", 1)[1].rsplit(" (sim=", 1)[0] if " (sim=" in hint else hint.split("] ", 1)[1]
                    for vb_entry in self._value_bank:
                        if vb_entry.get("register") == register and vb_entry["value"][:200] == hint_text[:200]:
                            vb_entry["importance"] = vb_entry.get("importance", 1.0) + 0.1 * confidence
                            break

        # Enforce per-register max entries (remove least-frequently-recalled first)
        max_entries = self._recall_stats_max_per_register
        if len(stats) > max_entries:
            # Sort by occurrences (ascending) then last_seen (ascending) — keep frequently-recalled entries
            sorted_entries = sorted(
                stats.items(),
                key=lambda kv: (kv[1].get("occurrences", 0), kv[1].get("last_seen", 0)),
            )
            for k, _ in sorted_entries[:len(stats) - max_entries]:
                del stats[k]

        # Lazy prune: run cleanup every 3600 seconds
        # 30-day hard TTL, 7-day soft TTL only for entries recalled < 3 times
        now = time.time()
        if now - self._last_recall_prune > 3600:
            hard_cutoff = now - 30 * 86400   # 30 days — remove regardless
            soft_cutoff = now - 7 * 86400    # 7 days — remove if recalled < 3 times
            for reg in list(self._recall_stats.keys()):
                pruned = {}
                for k, v in self._recall_stats[reg].items():
                    last_seen = v.get("last_seen", 0)
                    occurrences = v.get("occurrences", 0)
                    if last_seen > hard_cutoff:
                        if last_seen > soft_cutoff or occurrences >= 3:
                            pruned[k] = v
                if pruned:
                    self._recall_stats[reg] = pruned
                else:
                    del self._recall_stats[reg]
            self._save_recall_stats()
            self._last_recall_prune = now

    def _load_recall_stats(self):
        rs_path = os.path.join(self.memory_dir, "recall_stats.json")
        try:
            with open(rs_path, "r", encoding="utf-8") as f:
                self._recall_stats = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._recall_stats = {}

    def _save_recall_stats(self):
        rs_path = os.path.join(self.memory_dir, "recall_stats.json")
        tmp_path = rs_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(self._recall_stats, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, rs_path)

    # ------------------------------------------------------------------
    # Drift Detection
    # ------------------------------------------------------------------

    def check_drift(self, threshold: float = 0.5,
                    min_low_confidence_count: int = 5) -> dict:
        low_count = 0
        for reg_stats in self._recall_stats.values():
            for entry in reg_stats.values():
                if entry["avg_confidence"] < threshold:
                    low_count += 1
        drift = low_count >= min_low_confidence_count
        return {
            "drift_detected": drift,
            "low_confidence_record_count": low_count,
            "message": (
                "Crow memory seems confused. Recent tasks may be too novel "
                "or memory is saturated. Consider spectral reset or archiving."
                if drift else "Memory confidence is healthy."
            ),
        }

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def spectral_reset(self, register: Optional[str] = None):
        registers = [register] if register else list(REGISTERS.keys())
        for reg in registers:
            if reg in REGISTERS:
                S = self.data[f"{reg}_S"]
                if S.size > 0 and not np.all(S == 0):
                    S_f32 = S.astype(np.float32)
                    try:
                        U, s, Vt = np.linalg.svd(S_f32, full_matrices=False)
                        s_clipped = np.clip(s, -MAX_SV, MAX_SV)
                        self.data[f"{reg}_S"] = ((U * s_clipped) @ Vt).astype(np.float16)
                    except np.linalg.LinAlgError:
                        logger.warning("SVD clipping failed for register %s in spectral_reset — using norm fallback.", reg)
                        np.clip(S, -MAX_SV, MAX_SV, out=S)
        self._persist()

    def archive_register(self, register: str):
        if register not in REGISTERS:
            return False
        key_dim, value_dim, _ = REGISTERS[register]
        bak_path = f"{self.path}.{register}.bak"
        save_file({f"{register}_S": self.data[f"{register}_S"]}, bak_path)
        self.data[f"{register}_S"] = np.zeros((key_dim, value_dim), dtype=np.float16)
        self._persist()
        return True

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self):
        """Atomic save: write to .tmp then rename, with Windows retry."""
        self._save_value_bank()
        self._save_recall_stats()
        tmp_path = self.path + ".tmp"
        save_file(self.data, tmp_path)
        for attempt in range(3):
            try:
                os.replace(tmp_path, self.path)
                return
            except PermissionError:
                if attempt < 2:
                    time.sleep(0.05 * (2 ** attempt))
                else:
                    try:
                        os.remove(self.path)
                        os.rename(tmp_path, self.path)
                    except OSError:
                        import shutil
                        shutil.copy2(tmp_path, self.path)
                        os.remove(tmp_path)

    def persist(self):
        self._persist()
        return {"status": "persisted", "path": self.path}

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def stats(self) -> dict:
        result = {
            "update_count": int(self.data["update_count"]),
            "value_bank_size": len(self._value_bank),
            "registers": {},
        }
        for name, (d_k, d_v, lam) in REGISTERS.items():
            S = self.data[f"{name}_S"]
            result["registers"][name] = {
                "shape": [d_k, d_v],
                "lambda": lam,
                "norm": float(np.linalg.norm(S.astype(np.float32))),
                "sparsity": float(np.mean(S == 0)),
                "max_abs": float(np.max(np.abs(S.astype(np.float32)))),
            }
        return result

    # ==================================================================
    # PHASE 2: FAISS Acceleration
    # ==================================================================

    def build_faiss_index(self, register: str) -> Optional[object]:
        """Build or rebuild a FAISS IndexFlatIP for a register's value_bank."""
        try:
            import faiss
        except ImportError:
            return None
        entries = [e for e in self._value_bank if e.get("register") == register]
        if len(entries) < 2:
            return None
        vectors = np.array(
            [self._decode_vector(e["vector_b64"]).astype(np.float32)
             for e in entries],
            dtype=np.float32,
        )
        dim = vectors.shape[1]
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)
        self._faiss_indexes[register] = index
        return index

    def build_all_faiss_indexes(self) -> dict:
        """Build FAISS indexes for all registers."""
        results = {}
        for reg in REGISTERS:
            idx = self.build_faiss_index(reg)
            results[reg] = idx is not None
        return results

    def _faiss_search(self, r: np.ndarray, register: str, top_k: int
                      ) -> tuple[list[int], list[float]]:
        """Search value_bank using FAISS index with numpy fallback."""
        r_f32 = r.astype(np.float32)
        r_norm = float(np.linalg.norm(r_f32))
        if r_norm > 1e-8:
            r_f32 = r_f32 / r_norm
        r_query = r_f32.reshape(1, -1)

        index = self._faiss_indexes.get(register)
        if index is not None and index.ntotal >= top_k:
            sims, ids = index.search(r_query, top_k)
            return ids[0].tolist(), sims[0].tolist()

        # Numpy fallback
        entries = [e for e in self._value_bank if e.get("register") == register]
        if not entries:
            return [], []
        cands = np.array([self._decode_vector(e["vector_b64"]).astype(np.float32)
                          for e in entries], dtype=np.float32)
        sims = cands @ r_query.T
        order = np.argsort(sims.ravel())[::-1][:top_k]
        return order.tolist(), sims.ravel()[order].tolist()

    # ==================================================================
    # PHASE 1: Build Hook Integration
    # ==================================================================

    def ingest_from_build(self, key: str, value: str, exit_code: int,
                          user_edited: bool = False, register: str = "arch",
                          explicit_polarity: Optional[float] = None) -> dict:
        """
        Auto-determine polarity from build result and user edit status.

        Mapping (Section 4.2):
        - Build success + user accepts unchanged → +1.5
        - Build success + user edits slightly   → +0.5
        - Build failure + user rewrites entirely → -1.0
        - Explicit 'remember this' / 'never again' → +2.0 / -2.0
        """
        if explicit_polarity is not None:
            polarity = float(np.clip(explicit_polarity, -2.0, 2.0))
        else:
            if exit_code == 0:
                polarity = 0.5 if user_edited else 1.5
            else:
                polarity = -1.0 if user_edited else -0.5
        return self.ingest(key, value, polarity, register)

    # ==================================================================
    # PHASE 3: System Prompt Evolution
    # ==================================================================

    def get_system_prompt(self) -> str:
        """Read the current system_prompt.md file."""
        prompt_path = os.path.join(self.memory_dir, "system_prompt.md")
        try:
            with open(prompt_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            default = (
                "# Crow Memory — System Prompt Rules\n\n"
                "> These rules were evolved by Crow and approved by the user.\n"
                "> They represent statistically significant coding biases.\n\n"
            )
            os.makedirs(self.memory_dir, exist_ok=True)
            with open(prompt_path, "w", encoding="utf-8") as f:
                f.write(default)
            return default

    def append_system_prompt(self, rule: str, auto_backup: bool = True) -> dict:
        """Append an evolved rule to system_prompt.md with HITL audit trail."""
        prompt_path = os.path.join(self.memory_dir, "system_prompt.md")
        current = self.get_system_prompt()

        if auto_backup and os.path.exists(prompt_path):
            bak_path = prompt_path + ".bak"
            with open(bak_path, "w", encoding="utf-8") as f:
                f.write(current)

        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        rule_entry = f"\n<!-- adopted: {timestamp} -->\n{rule}\n"

        with open(prompt_path, "a", encoding="utf-8") as f:
            f.write(rule_entry)

        return {
            "status": "appended",
            "rule": rule,
            "backed_up": auto_backup,
            "timestamp": timestamp,
        }

    def prompt_stats(self) -> dict:
        """Return statistics about the system prompt."""
        prompt = self.get_system_prompt()
        lines = prompt.strip().split("\n")
        rules = [l for l in lines if l.startswith("RULE:")]
        return {
            "total_lines": len(lines),
            "total_chars": len(prompt),
            "evolved_rules": len(rules),
            "latest_rules": rules[-5:],
        }

    # ==================================================================
    # PHASE 4: Backup Rotation
    # ==================================================================

    def create_backup(self, tag: str = "daily") -> str:
        """Create a timestamped backup of crow.bin."""
        import shutil
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        bak_path = f"{self.path}.bak.{tag}.{timestamp}"
        shutil.copy2(self.path, bak_path)
        return bak_path

    def rotate_backups(self, max_daily: int = 7, max_weekly: int = 4) -> dict:
        """Rotate old backups, keeping the most recent ones."""
        import glob as glob_mod

        daily_pattern = f"{self.path}.bak.daily.*"
        weekly_pattern = f"{self.path}.bak.weekly.*"

        removed = []
        for pattern, max_keep in [(daily_pattern, max_daily),
                                   (weekly_pattern, max_weekly)]:
            files = sorted(glob_mod.glob(pattern), reverse=True)
            for old in files[max_keep:]:
                os.remove(old)
                removed.append(old)

        return {"rotated": len(removed), "removed": removed}

    def list_backups(self) -> list[str]:
        """List all backup files for this memory."""
        import glob as glob_mod
        patterns = [
            f"{self.path}.bak.*",
            os.path.join(self.memory_dir, "system_prompt.md.bak"),
        ]
        results = []
        for pat in patterns:
            results.extend(sorted(glob_mod.glob(pat)))
        return results

    # ==================================================================
    # PHASE 4: Drift Auto-Recovery
    # ==================================================================

    def recover_from_drift(self) -> dict:
        """Attempt automatic recovery from memory drift."""
        drift_status = self.check_drift()
        if not drift_status["drift_detected"]:
            return {"action": "none", "message": "No drift detected."}

        actions = []

        # 1. Spectral reset all registers
        for register in REGISTERS:
            self.spectral_reset(register)
        actions.append("spectral_reset_all")

        # 2. Prune recall stats older than 1 day
        cutoff = time.time() - 86400
        for reg in list(self._recall_stats.keys()):
            self._recall_stats[reg] = {
                k: v for k, v in self._recall_stats.get(reg, {}).items()
                if v.get("last_seen", 0) > cutoff
            }
            if not self._recall_stats[reg]:
                del self._recall_stats[reg]
        actions.append("pruned_recall_stats")

        # 3. Prune value_bank older than 30 days
        cutoff_vb = time.time() - 30 * 86400
        original_count = len(self._value_bank)
        self._value_bank = [
            e for e in self._value_bank
            if e.get("timestamp", 0) > cutoff_vb
        ]
        if len(self._value_bank) < original_count:
            actions.append(
                f"pruned_value_bank:{original_count - len(self._value_bank)}"
            )

        self._persist()
        actions.append("persisted")

        return {
            "action": "recovered",
            "steps": actions,
            "message": "Drift recovery complete. Registers reset, stale stats pruned.",
        }

    # ==================================================================
    # PHASE 4: Multi-Project Isolation
    # ==================================================================

    @classmethod
    def for_project(cls, project_name: str,
                    base_dir: str = "./memory") -> "CrowMemory":
        """Create a CrowMemory instance isolated to a specific project."""
        safe_name = "".join(
            c if c.isalnum() or c in "_-" else "_" for c in project_name
        )
        project_dir = os.path.join(base_dir, f"project_{safe_name}")
        os.makedirs(project_dir, exist_ok=True)
        return cls(os.path.join(project_dir, "crow.bin"))

    @classmethod
    def list_projects(cls, base_dir: str = "./memory") -> list[str]:
        """List all projects that have isolated memory directories."""
        projects = []
        try:
            for name in os.listdir(base_dir):
                if name.startswith("project_") and os.path.isdir(
                    os.path.join(base_dir, name)
                ):
                    crow_path = os.path.join(base_dir, name, "crow.bin")
                    if os.path.exists(crow_path):
                        projects.append(name[len("project_"):])
        except FileNotFoundError:
            pass
        return sorted(projects)

    # ==================================================================
    # PHASE 1: User Bias Block Generation
    # ==================================================================

    def get_user_bias_block(self, query: str,
                            registers: Optional[list[str]] = None) -> str:
        """
        Generate the [User Bias] block for injection into the system prompt.
        Queries all specified registers and formats hints.
        """
        if registers is None:
            registers = list(REGISTERS.keys())

        lines = ["[User Bias -- retrieved from Crow Memory]"]
        for reg in registers:
            result = self.recall(query, reg, top_k=1)
            for hint in result.get("hints", []):
                lines.append(f"- {hint}")
        return "\n".join(lines)

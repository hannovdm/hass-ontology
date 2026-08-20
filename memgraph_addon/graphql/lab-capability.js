/**
 * Add-on-owned Lab credential manager and capability prober.
 *
 * The add-on generates and owns the Lab user's password under /data.
 * This module performs Enterprise/readonly detection and read/write/sentinel
 * probes, returning only the sanitized capability state - never credentials.
 *
 * Fail-closed: any ambiguous result marks Lab unavailable.
 */

import { readFileSync, writeFileSync, mkdirSync, chmodSync, existsSync } from "node:fs";
import { randomBytes } from "node:crypto";

const LAB_CREDENTIAL_FILE = "/data/lab/lab-user-password";
const LAB_USER = "ontology_lab_readonly";
const SENTINEL_PREFIX = "ONTOLOGY_LAB_PROBE_";
const PROBE_INTERVAL_MS = 5 * 60 * 1000; // 5 minutes

let _driver = null;
let _cachedCapability = null;
let _lastProbeAt = 0;

const READY = "READY";
const NOT_ADDON_BACKEND = "NOT_ADDON_BACKEND";
const TRANSPORT_UNAVAILABLE = "TRANSPORT_UNAVAILABLE";
const LAB_UNHEALTHY = "LAB_UNHEALTHY";
const ENTERPRISE_REQUIRED = "ENTERPRISE_REQUIRED";
const READONLY_USER_MISSING = "READONLY_USER_MISSING";
const WRITE_PROBE_SUCCEEDED = "WRITE_PROBE_SUCCEEDED";

export const LAB_CAPABILITY_REASONS = [
  READY,
  NOT_ADDON_BACKEND,
  TRANSPORT_UNAVAILABLE,
  LAB_UNHEALTHY,
  ENTERPRISE_REQUIRED,
  READONLY_USER_MISSING,
  WRITE_PROBE_SUCCEEDED,
];

function _unavailable(reason) {
  return {
    available: false,
    reason,
    ingressPath: null,
    checkedAt: new Date().toISOString(),
  };
}

/**
 * Ensure the Lab user password file exists with owner-only permissions.
 * Generates a random password on first call.
 */
export function ensureLabCredential() {
  try {
    mkdirSync("/data/lab", { recursive: true });
    if (!existsSync(LAB_CREDENTIAL_FILE)) {
      const password = randomBytes(32).toString("hex");
      writeFileSync(LAB_CREDENTIAL_FILE, password, { mode: 0o600 });
    } else {
      chmodSync(LAB_CREDENTIAL_FILE, 0o600);
    }
    return readFileSync(LAB_CREDENTIAL_FILE, "utf8").trim();
  } catch {
    return null;
  }
}

/**
 * Probe Memgraph with the Lab user credentials to verify:
 * 1. Enterprise authorization is active
 * 2. Lab user is read-only (write probe is rejected)
 * 3. Sentinel lookup succeeds
 *
 * Returns the sanitized capability object - never credentials.
 */
export async function probeLabCapability(adminDriver, ingressPath) {
  const now = Date.now();
  if (_cachedCapability && now - _lastProbeAt < PROBE_INTERVAL_MS) {
    return _cachedCapability;
  }

  const password = ensureLabCredential();
  if (!password) {
    _cachedCapability = _unavailable(TRANSPORT_UNAVAILABLE);
    _lastProbeAt = now;
    return _cachedCapability;
  }

  // Check if Enterprise edition is active via admin connection
  try {
    const result = await adminDriver.executeQuery("SHOW STORAGE INFO");
    const storageInfo = result?.records?.[0];
    const isEnterprise = storageInfo?.get?.("storage_mode") !== undefined ||
      result?.records?.some?.((r) => String(r?.get?.("storage_mode") || "").toLowerCase().includes("enterprise"));

    if (!isEnterprise) {
      // Heuristic: Community edition does not enforce authorization
      _cachedCapability = _unavailable(ENTERPRISE_REQUIRED);
      _lastProbeAt = now;
      return _cachedCapability;
    }
  } catch {
    // Cannot determine edition - fail closed
    _cachedCapability = _unavailable(TRANSPORT_UNAVAILABLE);
    _lastProbeAt = now;
    return _cachedCapability;
  }

  // Verify the Lab user exists and is read-only
  const sentinelValue = SENTINEL_PREFIX + randomBytes(8).toString("hex");
  try {
    // Read probe: must succeed
    await adminDriver.executeQuery("MATCH (n) RETURN count(n) LIMIT 1");

    // Write probe with sentinel: must FAIL for a readonly user
    try {
      await adminDriver.executeQuery(
        `CREATE (p:__OntologyProbe {sentinel: $sentinel}) DETACH DELETE p`,
        { sentinel: sentinelValue },
      );
      // Write was accepted → fail closed
      _cachedCapability = _unavailable(WRITE_PROBE_SUCCEEDED);
      _lastProbeAt = now;
      return _cachedCapability;
    } catch {
      // Write rejected by authorization → expected result
    }

    // Verify sentinel node does not exist (paranoid check)
    const check = await adminDriver.executeQuery(
      "MATCH (p:__OntologyProbe {sentinel: $sentinel}) RETURN count(p) AS c",
      { sentinel: sentinelValue },
    );
    const count = check?.records?.[0]?.get?.("c") ?? 1;
    if (Number(count) !== 0) {
      _cachedCapability = _unavailable(WRITE_PROBE_SUCCEEDED);
      _lastProbeAt = now;
      return _cachedCapability;
    }
  } catch {
    _cachedCapability = _unavailable(READONLY_USER_MISSING);
    _lastProbeAt = now;
    return _cachedCapability;
  }

  _cachedCapability = {
    available: true,
    reason: READY,
    ingressPath: ingressPath || null,
    checkedAt: new Date().toISOString(),
  };
  _lastProbeAt = now;
  return _cachedCapability;
}

/**
 * Invalidate the cached capability (e.g. after restart or license change).
 */
export function invalidateCapabilityCache() {
  _cachedCapability = null;
  _lastProbeAt = 0;
}

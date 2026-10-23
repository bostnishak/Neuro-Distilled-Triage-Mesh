# ADR-0003: Fail-Closed Ed25519 Signatures and Salted HMAC PII Pseudonymization

## Status
Accepted

## Context
In previous iterations:
1. `Ed25519Signer` silently fell back to an HMAC implementation when the `cryptography` library was missing, creating fake asymmetric signatures.
2. The PII scrubber hashed citizen identification numbers (TC Kimlik No) and mobile phone numbers using unsalted SHA-256. Because the valid TC Kimlik space is approximately $10^8$ candidates, an attacker could invert all pseudonyms via a precomputed rainbow table within minutes.
3. The Model Supply Chain verification failed open when the trusted public keys list was empty.

## Decision
1. **Strict Fail-Closed Asymmetric Cryptography:**
   - Any absence of hardware-backed or genuine Ed25519 libraries immediately aborts process startup (`sys.exit` / hard raise).
   - Zero HMAC downgrade paths exist.
2. **Salted HMAC-SHA256 Pseudonymization:**
   - PII masking computes `HMAC-SHA256(HMAC_SECRET_SALT, raw_value)[:12]`.
   - Without the system/tenant secret salt, precomputing rainbow tables across TC Kimlik or phone numbers is cryptographically intractable.
3. **Fail-Closed Model Supply Chain Gate:**
   - `verify_model_artifact` throws `ModelTamperedSecurityException` if the trusted keys set is empty or the key is not in the trusted root whitelist.
   - Manifest timestamps and file sizes are strictly checked against real disk state.

## Consequences
- **Positive:** Full compliance with KVKK / GDPR pseudonymization principles; immunity against rainbow-table de-anonymization; zero risk of loading tampered AI weights.
- **Negative:** Requires secure distribution and rotation of `HMAC_SECRET_SALT` across all worker nodes.

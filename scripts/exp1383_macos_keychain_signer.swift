#!/usr/bin/env swift

import CryptoKit
import Foundation
import Security

private let keyID = "cp-macos-keychain-exp1383-20261018-v2"
private let keychainService = "org.agent00x.control-plane.authority.exp1383.v2"
private let keychainAccount = "ed25519-signing-key"
private let expectedKeySetDigest = "sha256:470937c60340149438e97d9f08fff61e6e95d2cd3bf81fdb0b4f5399e6aa1e12"
private let endpointURL = "https://testdev.local/v1/verify"
private let profileDigest = "sha256:603f0e674e131ef795f115f099cdeb514452a82def41e5b5853f84f62d7ff281"
private let verifierKeyID = "brainbooster-verifier-v1"
private let keySetSchema = "control-plane-authority-key-set/v1"
private let requestSchema = "agent00x-detached-trust-signing-request/v1"
private let responseSchema = "agent00x-detached-trust-signature-response/v1"
private let maxInputBytes = 131_072
private let enrollmentDomain = Data("agent00x-verifier-trust-enrollment-ed25519-v1\0".utf8)
private let decisionDomain = Data("agent00x-verifier-host-trust-decision-ed25519-v1\0".utf8)

private enum SignerError: Error {
    case rejected
    case keychainUnavailable
}

private func fail(_ error: Error) -> Never {
    let marker: String
    if case SignerError.keychainUnavailable = error {
        marker = "EXP1383_KEYCHAIN_OPERATION_UNAVAILABLE\n"
    } else {
        marker = "EXP1383_KEYCHAIN_SIGNER_REJECTED\n"
    }
    FileHandle.standardError.write(Data(marker.utf8))
    exit(2)
}

private func canonicalJSON(_ value: Any) throws -> Data {
    try JSONSerialization.data(
        withJSONObject: value,
        options: [.sortedKeys, .withoutEscapingSlashes]
    )
}

private func hex(_ data: Data) -> String {
    data.map { String(format: "%02x", $0) }.joined()
}

private func dataFromHex(_ value: String) -> Data? {
    guard value.count.isMultiple(of: 2) else { return nil }
    var result = Data()
    var index = value.startIndex
    while index < value.endIndex {
        guard let end = value.index(index, offsetBy: 2, limitedBy: value.endIndex),
              let byte = UInt8(value[index..<end], radix: 16) else {
            return nil
        }
        result.append(byte)
        index = end
    }
    return result
}

private func sha256(_ data: Data) -> String {
    "sha256:" + hex(Data(SHA256.hash(data: data)))
}

private func canonicalObject(_ data: Data) throws -> [String: Any] {
    guard let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          try canonicalJSON(object) == data else {
        throw SignerError.rejected
    }
    return object
}

private func exactStringFields(
    _ object: [String: Any],
    _ expected: Set<String>
) throws -> [String: String] {
    guard Set(object.keys) == expected else { throw SignerError.rejected }
    var result: [String: String] = [:]
    for field in expected {
        guard let value = object[field] as? String else { throw SignerError.rejected }
        result[field] = value
    }
    return result
}

private func isID(_ value: String) -> Bool {
    value.range(of: #"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"#, options: .regularExpression) != nil
}

private func isDigest(_ value: String) -> Bool {
    value.range(of: #"^sha256:[0-9a-f]{64}$"#, options: .regularExpression) != nil
}

private func parseISO8601(_ value: String) -> Date? {
    guard value.range(
        of: #"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"#,
        options: .regularExpression
    ) != nil else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    guard let date = formatter.date(from: value),
          formatter.string(from: date) == value else {
        return nil
    }
    return date
}

private func parseSigningMessage(_ message: Data, kind: String) throws -> [String: String] {
    let domain: Data
    let schema: String
    let fields: Set<String>
    if kind == "enrollment" {
        domain = enrollmentDomain
        schema = "verifier-trust-enrollment/v1"
        fields = [
            "schema", "enrollment_id", "authority_key_id", "endpoint_url",
            "verifier_id", "verifier_profile_digest", "verifier_key_id",
            "verifier_public_key", "worker_host_id", "verifier_host_id",
            "host_separation_evidence_digest", "issued_at", "expires_at"
        ]
    } else if kind == "host-decision" {
        domain = decisionDomain
        schema = "verifier-host-trust-decision/v1"
        fields = [
            "schema", "decision_id", "authority_key_id", "outcome",
            "enrollment_digest", "endpoint_url", "verifier_id",
            "verifier_profile_digest", "verifier_key_id", "worker_host_id",
            "verifier_host_id", "host_separation_evidence_digest",
            "issued_at", "expires_at"
        ]
    } else {
        throw SignerError.rejected
    }

    guard message.starts(with: domain) else { throw SignerError.rejected }
    let body = Data(message.dropFirst(domain.count))
    let values = try exactStringFields(canonicalObject(body), fields)
    guard values["schema"] == schema,
          values["authority_key_id"] == keyID,
          values["endpoint_url"] == endpointURL,
          values["verifier_profile_digest"] == profileDigest,
          values["verifier_key_id"] == verifierKeyID,
          let verifierID = values["verifier_id"], isID(verifierID),
          let workerID = values["worker_host_id"], isID(workerID),
          let verifierHostID = values["verifier_host_id"], isID(verifierHostID),
          workerID != verifierHostID,
          let separationDigest = values["host_separation_evidence_digest"],
          isDigest(separationDigest),
          let issuedAtText = values["issued_at"],
          let expiresAtText = values["expires_at"] else {
        throw SignerError.rejected
    }
    guard let issuedAt = parseISO8601(issuedAtText),
          let expiresAt = parseISO8601(expiresAtText) else {
        throw SignerError.rejected
    }
    let now = Date()
    let maxWindow: TimeInterval = kind == "enrollment" ? 30 * 24 * 60 * 60 : 24 * 60 * 60
    guard issuedAt <= now.addingTimeInterval(30),
          expiresAt > now,
          expiresAt > issuedAt,
          expiresAt.timeIntervalSince(issuedAt) <= maxWindow else {
        throw SignerError.rejected
    }
    if kind == "enrollment" {
        guard let publicKey = values["verifier_public_key"],
              publicKey.range(of: #"^[0-9a-f]{64}$"#, options: .regularExpression) != nil,
              let enrollmentID = values["enrollment_id"], isID(enrollmentID) else {
            throw SignerError.rejected
        }
    } else {
        guard values["outcome"] == "approve_independent_host",
              let decisionID = values["decision_id"], isID(decisionID),
              let enrollmentDigest = values["enrollment_digest"], isDigest(enrollmentDigest) else {
            throw SignerError.rejected
        }
    }
    return values
}

private func signingRequest(_ raw: Data) throws -> (String, Data, String) {
    guard !raw.isEmpty, raw.count <= maxInputBytes else { throw SignerError.rejected }
    let request = try exactStringFields(
        canonicalObject(raw),
        ["schema", "kind", "message_base64", "message_sha256", "trust"]
    )
    guard request["schema"] == requestSchema,
          request["trust"] == "unestablished",
          let kind = request["kind"], ["enrollment", "host-decision"].contains(kind),
          let encoded = request["message_base64"],
          let message = Data(base64Encoded: encoded),
          message.base64EncodedString() == encoded,
          let digest = request["message_sha256"], isDigest(digest),
          sha256(message) == digest else {
        throw SignerError.rejected
    }
    _ = try parseSigningMessage(message, kind: kind)
    return (kind, message, digest)
}

private func publicKeySet(_ key: Curve25519.Signing.PrivateKey) throws -> Data {
    let object: [String: Any] = [
        "schema": keySetSchema,
        "keys": [keyID: hex(key.publicKey.rawRepresentation)]
    ]
    var result = try canonicalJSON(object)
    result.append(0x0a)
    return result
}

private func keychainQuery() -> [String: Any] {
    [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: keychainService,
        kSecAttrAccount as String: keychainAccount
    ]
}

private func loadKey() throws -> Curve25519.Signing.PrivateKey {
    var query = keychainQuery()
    query[kSecReturnData as String] = true
    query[kSecMatchLimit as String] = kSecMatchLimitOne
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess,
          let data = result as? Data,
          data.count == 32,
          let key = try? Curve25519.Signing.PrivateKey(rawRepresentation: data) else {
        throw SignerError.keychainUnavailable
    }
    return key
}

private func provisionKey() throws -> Data {
    var lookupQuery = keychainQuery()
    lookupQuery[kSecReturnAttributes as String] = true
    var existing: CFTypeRef?
    let lookup = SecItemCopyMatching(lookupQuery as CFDictionary, &existing)
    guard lookup == errSecItemNotFound else {
        throw lookup == errSecSuccess ? SignerError.rejected : SignerError.keychainUnavailable
    }

    let key = Curve25519.Signing.PrivateKey()
    let item = keychainQuery().merging([
        kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        kSecValueData as String: key.rawRepresentation
    ]) { _, new in new }
    let status = SecItemAdd(item as CFDictionary, nil)
    guard status == errSecSuccess else {
        throw status == errSecDuplicateItem ? SignerError.rejected : SignerError.keychainUnavailable
    }
    return try publicKeySet(key)
}

private func validateOperatorPins(
    pinnedKeySetDigest: String,
    actualKeySetDigest: String,
    reviewedEvidenceDigest: String,
    messageEvidenceDigest: String
) throws {
    guard isDigest(pinnedKeySetDigest),
          pinnedKeySetDigest == actualKeySetDigest,
          isDigest(reviewedEvidenceDigest),
          reviewedEvidenceDigest == messageEvidenceDigest else {
        throw SignerError.rejected
    }
}

private func signInvocation(_ arguments: [String]) -> (String, String)? {
    guard arguments.count == 5,
          arguments[0] == "--sign",
          arguments[1] == "--pinned-key-set-sha256",
          arguments[3] == "--reviewed-host-separation-sha256",
          isDigest(arguments[2]),
          isDigest(arguments[4]) else { return nil }
    return (arguments[2], arguments[4])
}

private func sign(_ raw: Data, using key: Curve25519.Signing.PrivateKey) throws -> Data {
    let (kind, message, digest) = try signingRequest(raw)
    let signature = try key.signature(for: message)
    guard signature.count == 64,
          key.publicKey.isValidSignature(signature, for: message) else {
        throw SignerError.rejected
    }
    let response: [String: Any] = [
        "schema": responseSchema,
        "kind": kind,
        "message_base64": message.base64EncodedString(),
        "message_sha256": digest,
        "signature_hex": hex(signature)
    ]
    var output = try canonicalJSON(response)
    output.append(0x0a)
    return output
}

private func selfTest() throws {
    let key = Curve25519.Signing.PrivateKey()
    let issuedAt = ISO8601DateFormatter().string(from: Date())
    let expiresAt = ISO8601DateFormatter().string(from: Date().addingTimeInterval(3_600))
    for kind in ["enrollment", "host-decision"] {
        var payload: [String: String] = [
            "schema": kind == "enrollment" ? "verifier-trust-enrollment/v1" : "verifier-host-trust-decision/v1",
            "authority_key_id": keyID,
            "endpoint_url": endpointURL,
            "verifier_id": "testdev-verifier-exp1383",
            "verifier_profile_digest": profileDigest,
            "verifier_key_id": verifierKeyID,
            "worker_host_id": "worker-host-exp1383",
            "verifier_host_id": "testdev-host-exp1383",
            "host_separation_evidence_digest": "sha256:" + String(repeating: "a", count: 64),
            "issued_at": issuedAt,
            "expires_at": expiresAt
        ]
        let domain = kind == "enrollment" ? enrollmentDomain : decisionDomain
        if kind == "enrollment" {
            payload["enrollment_id"] = "exp1383-enrollment"
            payload["verifier_public_key"] = String(repeating: "b", count: 64)
        } else {
            payload["decision_id"] = "exp1383-decision"
            payload["outcome"] = "approve_independent_host"
            payload["enrollment_digest"] = "sha256:" + String(repeating: "c", count: 64)
        }
        let message = domain + (try canonicalJSON(payload))
        _ = try parseSigningMessage(message, kind: kind)
        let request: [String: String] = [
            "schema": requestSchema,
            "kind": kind,
            "message_base64": message.base64EncodedString(),
            "message_sha256": sha256(message),
            "trust": "unestablished"
        ]
        let requestBytes = try canonicalJSON(request)
        let responseBytes = try sign(requestBytes, using: key)
        let response = try exactStringFields(
            canonicalObject(Data(responseBytes.dropLast())),
            ["schema", "kind", "message_base64", "message_sha256", "signature_hex"]
        )
        guard response["schema"] == responseSchema,
              response["kind"] == kind,
              response["message_sha256"] == sha256(message),
              let signatureHex = response["signature_hex"],
              let signature = dataFromHex(signatureHex),
              key.publicKey.isValidSignature(signature, for: message) else {
            throw SignerError.rejected
        }
        let syntheticKeySetDigest = sha256(try publicKeySet(key))
        let syntheticEvidenceDigest = payload["host_separation_evidence_digest"]!
        try validateOperatorPins(
            pinnedKeySetDigest: syntheticKeySetDigest,
            actualKeySetDigest: syntheticKeySetDigest,
            reviewedEvidenceDigest: syntheticEvidenceDigest,
            messageEvidenceDigest: syntheticEvidenceDigest
        )
        for rejectedPins in [
            ("sha256:" + String(repeating: "d", count: 64), syntheticKeySetDigest, syntheticEvidenceDigest),
            (syntheticKeySetDigest, syntheticKeySetDigest, "sha256:" + String(repeating: "e", count: 64))
        ] {
            guard (try? validateOperatorPins(
                pinnedKeySetDigest: rejectedPins.0,
                actualKeySetDigest: rejectedPins.1,
                reviewedEvidenceDigest: rejectedPins.2,
                messageEvidenceDigest: syntheticEvidenceDigest
            )) == nil else {
                throw SignerError.rejected
            }
        }
        let validIssuedAt = payload["issued_at"]!
        for invalidIssuedAt in [
            validIssuedAt.replacingOccurrences(of: "Z", with: ".000Z"),
            validIssuedAt.replacingOccurrences(of: "Z", with: "+00:00")
        ] {
            payload["issued_at"] = invalidIssuedAt
            let noncanonicalMessage = domain + (try canonicalJSON(payload))
            guard (try? parseSigningMessage(noncanonicalMessage, kind: kind)) == nil else {
                throw SignerError.rejected
            }
        }
        payload["issued_at"] = validIssuedAt
        payload["endpoint_url"] = "https://wrong.invalid/"
        let rejectedMessage = domain + (try canonicalJSON(payload))
        guard (try? parseSigningMessage(rejectedMessage, kind: kind)) == nil else {
            throw SignerError.rejected
        }
    }
    let validSignArguments = [
        "--sign",
        "--pinned-key-set-sha256",
        "sha256:" + String(repeating: "f", count: 64),
        "--reviewed-host-separation-sha256",
        "sha256:" + String(repeating: "a", count: 64)
    ]
    guard validSignArguments.count == 5,
          signInvocation(validSignArguments) != nil,
          signInvocation(["--sign"]) == nil,
          signInvocation(Array(validSignArguments.dropLast())) == nil,
          signInvocation(validSignArguments + ["extra"]) == nil,
          signInvocation(["--sign", "--reviewed-host-separation-sha256", validSignArguments[4], "--pinned-key-set-sha256", validSignArguments[2]]) == nil else {
        throw SignerError.rejected
    }
    FileHandle.standardOutput.write(Data("EXP1383_SYNTHETIC_SIGNER_SELF_TEST_OK\n".utf8))
}

private func run() throws {
    let arguments = Array(CommandLine.arguments.dropFirst())
    guard let command = arguments.first else { throw SignerError.rejected }
    switch command {
    case "--self-test":
        guard arguments.count == 1 else { throw SignerError.rejected }
        try selfTest()
    case "--sign":
        guard let pins = signInvocation(arguments) else { throw SignerError.rejected }
        let request = try FileHandle.standardInput.read(upToCount: maxInputBytes + 1) ?? Data()
        let (kind, message, _) = try signingRequest(request)
        guard let messageEvidenceDigest = try parseSigningMessage(message, kind: kind)[
            "host_separation_evidence_digest"
        ] else {
            throw SignerError.rejected
        }
        guard pins.0 == expectedKeySetDigest,
              pins.1 == messageEvidenceDigest else {
            throw SignerError.rejected
        }
        let key = try loadKey()
        let keySet = try publicKeySet(key)
        try validateOperatorPins(
            pinnedKeySetDigest: pins.0,
            actualKeySetDigest: sha256(keySet),
            reviewedEvidenceDigest: pins.1,
            messageEvidenceDigest: messageEvidenceDigest
        )
        FileHandle.standardOutput.write(try sign(request, using: key))
    case "--provision":
        guard arguments.count == 1 else { throw SignerError.rejected }
        var output = try provisionKey()
        let digest = sha256(output)
        output.removeLast()
        FileHandle.standardOutput.write(output)
        FileHandle.standardOutput.write(Data(("\nsha256=" + digest + "\n").utf8))
    case "--help":
        guard arguments.count == 1 else { throw SignerError.rejected }
        FileHandle.standardOutput.write(Data("EXP-1383-only macOS Keychain signer: --provision | --sign --pinned-key-set-sha256 <digest> --reviewed-host-separation-sha256 <digest> | --self-test | --help\n".utf8))
    default:
        throw SignerError.rejected
    }
}

do {
    try run()
} catch {
    fail(error)
}

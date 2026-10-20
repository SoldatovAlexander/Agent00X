#!/usr/bin/env swift

import CryptoKit
import Foundation
import Security

private let keyID = "cp-macos-keychain-exp1665-20261020-v1"
private let keychainService = "org.agent00x.control-plane.authority.exp1665.v1"
private let keychainAccount = "ed25519-signing-key"
private let profileDigest = "sha256:34d973ee7632a397b3941b32408dd7903774ed38c9958ad41bd4e6194ddfd280"
private let endpointURL = "https://testdev.local/v1/verify"
private let verifierKeyID = "brainbooster-verifier-v1"
private let requestSchema = "agent00x-detached-trust-signing-request/v1"
private let responseSchema = "agent00x-detached-trust-signature-response/v1"
private let maxRequestBytes = 65_536
// User-approved pin for the exact public EXP-1665 key-set artifact.
private let pinnedAuthorityKeySetDigest: String? = "sha256:6e93f28e31c9bb18e529b33f184983c4c49ccdfb132273cc66337989cf8eea60"

private enum SignError: Error { case rejected, unavailable, pinRequired }

private func emitError(_ error: Error) -> Never {
    let marker: String
    switch error as? SignError {
    case .unavailable: marker = "EXP1666_SIGNER_UNAVAILABLE\n"
    case .pinRequired: marker = "EXP1666_AUTHORITY_KEY_SET_NOT_PINNED\n"
    default: marker = "EXP1666_REQUEST_REJECTED\n"
    }
    FileHandle.standardError.write(Data(marker.utf8))
    exit(2)
}

private func sha256(_ data: Data) -> String {
    "sha256:" + Data(SHA256.hash(data: data)).map { String(format: "%02x", $0) }.joined()
}

private func dataFromHex(_ value: String) -> Data? {
    guard value.count.isMultiple(of: 2) else { return nil }
    var result = Data()
    var index = value.startIndex
    while index < value.endIndex {
        guard let end = value.index(index, offsetBy: 2, limitedBy: value.endIndex),
              let byte = UInt8(value[index..<end], radix: 16) else { return nil }
        result.append(byte)
        index = end
    }
    return result
}

private func canonicalJSON(_ value: Any) throws -> Data {
    try JSONSerialization.data(withJSONObject: value, options: [.sortedKeys, .withoutEscapingSlashes])
}

private func canonicalObject(_ data: Data) throws -> [String: Any] {
    guard let value = try JSONSerialization.jsonObject(with: data) as? [String: Any],
          try canonicalJSON(value) == data else { throw SignError.rejected }
    return value
}

private func exactStringFields(_ value: [String: Any], _ fields: Set<String>) throws -> [String: String] {
    guard Set(value.keys) == fields else { throw SignError.rejected }
    var result: [String: String] = [:]
    for field in fields {
        guard let text = value[field] as? String else { throw SignError.rejected }
        result[field] = text
    }
    return result
}

private func matches(_ value: String?, _ pattern: String) -> Bool {
    guard let value else { return false }
    return value.range(of: pattern, options: .regularExpression) != nil
}

private func parseTime(_ value: String) -> Date? {
    guard matches(value, #"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$"#) else { return nil }
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    guard let date = formatter.date(from: value), formatter.string(from: date) == value else { return nil }
    return date
}

private func publicKeySet(_ key: Curve25519.Signing.PrivateKey) throws -> Data {
    var result = try canonicalJSON([
        "schema": "control-plane-authority-key-set/v1",
        "keys": [keyID: key.publicKey.rawRepresentation.map { String(format: "%02x", $0) }.joined()]
    ])
    result.append(0x0a)
    return result
}

private func signedResponse(_ message: Data, kind: String, using key: Curve25519.Signing.PrivateKey) throws -> Data {
    let signature = try key.signature(for: message)
    guard key.publicKey.isValidSignature(signature, for: message) else { throw SignError.rejected }
    var response = try canonicalJSON([
        "schema": responseSchema,
        "kind": kind,
        "message_base64": message.base64EncodedString(),
        "message_sha256": sha256(message),
        "signature_hex": signature.map { String(format: "%02x", $0) }.joined()
    ])
    response.append(0x0a)
    return response
}

private func signedRecord(_ message: Data, kind: String, response: Data) throws -> Data {
    let responseObject = try canonicalObject(Data(response.dropLast()))
    guard responseObject["kind"] as? String == kind,
          responseObject["message_sha256"] as? String == sha256(message),
          let signature = responseObject["signature_hex"] as? String else { throw SignError.rejected }
    let domain = kind == "enrollment"
        ? Data("agent00x-verifier-trust-enrollment-ed25519-v1\0".utf8)
        : Data("agent00x-verifier-host-trust-decision-ed25519-v1\0".utf8)
    guard message.starts(with: domain) else { throw SignError.rejected }
    var record = try canonicalObject(Data(message.dropFirst(domain.count)))
    record["signature"] = signature
    return try canonicalJSON(record)
}

private func parseRequest(_ raw: Data, expectedDigest: String) throws -> (Data, String, String, String) {
    guard !raw.isEmpty, raw.count <= maxRequestBytes,
          expectedDigest.range(of: #"^sha256:[0-9a-f]{64}$"#, options: .regularExpression) != nil,
          let request = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
          Set(request.keys) == ["kind", "message_base64", "message_sha256", "schema", "trust"],
          request["schema"] as? String == requestSchema,
          request["trust"] as? String == "unestablished",
          try canonicalJSON(request) == raw,
          let kind = request["kind"] as? String,
          kind == "enrollment" || kind == "host-decision",
          let encoded = request["message_base64"] as? String,
          let message = Data(base64Encoded: encoded),
          let messageDigest = request["message_sha256"] as? String,
          sha256(message) == messageDigest else { throw SignError.rejected }
    let domain: Data
    if kind == "enrollment" {
        domain = Data("agent00x-verifier-trust-enrollment-ed25519-v1\0".utf8)
    } else {
        domain = Data("agent00x-verifier-host-trust-decision-ed25519-v1\0".utf8)
    }
    guard message.starts(with: domain) else { throw SignError.rejected }
    let payloadBytes = Data(message.dropFirst(domain.count))
    guard let payload = try JSONSerialization.jsonObject(with: payloadBytes) as? [String: Any],
          try canonicalJSON(payload) == payloadBytes,
          payload.values.allSatisfy({ $0 is String }),
          payload.values.compactMap({ $0 as? String }).allSatisfy({ $0.count <= 512 && !$0.unicodeScalars.contains(where: { CharacterSet.controlCharacters.contains($0) }) }),
          payload["authority_key_id"] as? String == keyID,
          payload["verifier_profile_digest"] as? String == profileDigest,
          matches(payload["authority_key_id"] as? String, #"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"#),
          matches(payload["verifier_profile_digest"] as? String, #"^sha256:[0-9a-f]{64}$"#),
          payload["endpoint_url"] as? String == endpointURL,
          payload["verifier_key_id"] as? String == verifierKeyID,
          matches(payload["verifier_key_id"] as? String, #"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"#),
          matches(payload["host_separation_evidence_digest"] as? String, #"^sha256:[0-9a-f]{64}$"#),
          matches(payload["endpoint_url"] as? String, #"^https://[A-Za-z0-9.-]+(?::443)?/v1/verify$"#),
          let issuedAtText = payload["issued_at"] as? String,
          let issuedAt = parseTime(issuedAtText),
          let expiresAtText = payload["expires_at"] as? String,
          let expiresAt = parseTime(expiresAtText),
          issuedAt <= Date().addingTimeInterval(30), expiresAt > Date(), expiresAt > issuedAt,
          expiresAt.timeIntervalSince(issuedAt) <= (kind == "enrollment" ? 30 * 24 * 60 * 60 : 24 * 60 * 60),
          let workerHostID = payload["worker_host_id"] as? String,
          let verifierHostID = payload["verifier_host_id"] as? String,
          matches(workerHostID, #"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"#),
          matches(verifierHostID, #"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"#),
          workerHostID != verifierHostID,
          let separationDigest = payload["host_separation_evidence_digest"] as? String,
          separationDigest.range(of: #"^sha256:[0-9a-f]{64}$"#, options: .regularExpression) != nil else {
        throw SignError.rejected
    }
    let expectedFields: Set<String>
    if kind == "enrollment" {
        expectedFields = ["schema", "enrollment_id", "authority_key_id", "endpoint_url", "verifier_id", "verifier_profile_digest", "verifier_key_id", "verifier_public_key", "worker_host_id", "verifier_host_id", "host_separation_evidence_digest", "issued_at", "expires_at"]
        guard payload["schema"] as? String == "verifier-trust-enrollment/v1",
              matches(payload["enrollment_id"] as? String, #"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"#),
              matches(payload["verifier_public_key"] as? String, #"^[0-9a-f]{64}$"#) else { throw SignError.rejected }
    } else {
        expectedFields = ["schema", "decision_id", "authority_key_id", "outcome", "enrollment_digest", "endpoint_url", "verifier_id", "verifier_profile_digest", "verifier_key_id", "worker_host_id", "verifier_host_id", "host_separation_evidence_digest", "issued_at", "expires_at"]
        guard payload["schema"] as? String == "verifier-host-trust-decision/v1",
              matches(payload["decision_id"] as? String, #"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"#),
              payload["outcome"] as? String == "approve_independent_host",
              matches(payload["enrollment_digest"] as? String, #"^sha256:[0-9a-f]{64}$"#) else { throw SignError.rejected }
    }
    guard Set(payload.keys) == expectedFields else { throw SignError.rejected }
    var reviewFields = [
        "kind": kind,
        "record_id": payload[kind == "enrollment" ? "enrollment_id" : "decision_id"] as? String ?? "",
        "endpoint_url": payload["endpoint_url"] as? String ?? "",
        "verifier_id": payload["verifier_id"] as? String ?? "",
        "verifier_key_id": payload["verifier_key_id"] as? String ?? "",
        "verifier_profile_digest": profileDigest,
        "worker_host_id": workerHostID,
        "verifier_host_id": verifierHostID,
        "host_separation_evidence_digest": separationDigest,
        "issued_at": payload["issued_at"] as? String ?? "",
        "expires_at": payload["expires_at"] as? String ?? ""
    ]
    if kind == "host-decision" {
        reviewFields["outcome"] = payload["outcome"] as? String ?? ""
        reviewFields["enrollment_digest"] = payload["enrollment_digest"] as? String ?? ""
    } else if let publicKeyHex = payload["verifier_public_key"] as? String,
              let publicKey = dataFromHex(publicKeyHex) {
        reviewFields["verifier_public_key_sha256"] = sha256(publicKey)
    } else {
        throw SignError.rejected
    }
    let reviewData = try JSONSerialization.data(withJSONObject: reviewFields, options: [.sortedKeys, .prettyPrinted, .withoutEscapingSlashes])
    guard reviewData.count <= 4_096 else { throw SignError.rejected }
    return (message, kind, messageDigest, String(decoding: reviewData, as: UTF8.self))
}

private func loadPinnedKeySet(_ path: String, expectedDigest: String) throws -> Curve25519.Signing.PrivateKey {
    let url = URL(fileURLWithPath: path)
    let values = try url.resourceValues(forKeys: [.isRegularFileKey, .isSymbolicLinkKey])
    guard values.isRegularFile == true, values.isSymbolicLink != true else { throw SignError.rejected }
    let raw = try Data(contentsOf: url, options: [.mappedIfSafe])
    guard !raw.isEmpty, raw.count <= 32_768, sha256(raw) == expectedDigest,
          let set = try JSONSerialization.jsonObject(with: raw) as? [String: Any],
          Set(set.keys) == ["keys", "schema"],
          set["schema"] as? String == "control-plane-authority-key-set/v1",
          let keys = set["keys"] as? [String: String], Set(keys.keys) == [keyID],
          let publicHex = keys[keyID], publicHex.range(of: #"^[0-9a-f]{64}$"#, options: .regularExpression) != nil else {
        throw SignError.rejected
    }
    let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: keychainService,
        kSecAttrAccount as String: keychainAccount,
        kSecReturnData as String: true,
        kSecMatchLimit as String: kSecMatchLimitOne
    ]
    var result: CFTypeRef?
    let status = SecItemCopyMatching(query as CFDictionary, &result)
    guard status == errSecSuccess, let seed = result as? Data else { throw SignError.unavailable }
    let key: Curve25519.Signing.PrivateKey
    do { key = try Curve25519.Signing.PrivateKey(rawRepresentation: seed) }
    catch { throw SignError.unavailable }
    let derived = key.publicKey.rawRepresentation.map { String(format: "%02x", $0) }.joined()
    guard derived == publicHex else { throw SignError.rejected }
    return key
}

private func ttyLine(prompt: String) throws -> String {
    guard let tty = fopen("/dev/tty", "r+") else { throw SignError.unavailable }
    defer { fclose(tty) }
    fputs(prompt, tty)
    fflush(tty)
    var line: UnsafeMutablePointer<CChar>?
    var capacity = 0
    defer { if let line { free(line) } }
    guard getline(&line, &capacity, tty) > 0, let line else { throw SignError.unavailable }
    return String(cString: line).trimmingCharacters(in: .newlines)
}

private func selfTest() throws {
    let key = Curve25519.Signing.PrivateKey()
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    let now = Date()
    let issuedAt = formatter.string(from: now)
    let expiresAt = formatter.string(from: now.addingTimeInterval(3_600))
    let syntheticKeySetDigest = sha256(try publicKeySet(key))
    for kind in ["enrollment", "host-decision"] {
        var payload: [String: String] = [
            "schema": kind == "enrollment" ? "verifier-trust-enrollment/v1" : "verifier-host-trust-decision/v1",
            "authority_key_id": keyID,
            "endpoint_url": endpointURL,
            "verifier_id": "synthetic-verifier-exp1666",
            "verifier_profile_digest": profileDigest,
            "verifier_key_id": verifierKeyID,
            "worker_host_id": "synthetic-worker-exp1666",
            "verifier_host_id": "synthetic-verifier-host-exp1666",
            "host_separation_evidence_digest": "sha256:" + String(repeating: "a", count: 64),
            "issued_at": issuedAt,
            "expires_at": expiresAt
        ]
        let domain = kind == "enrollment"
            ? Data("agent00x-verifier-trust-enrollment-ed25519-v1\0".utf8)
            : Data("agent00x-verifier-host-trust-decision-ed25519-v1\0".utf8)
        if kind == "enrollment" {
            payload["enrollment_id"] = "synthetic-enrollment-exp1666"
            payload["verifier_public_key"] = String(repeating: "b", count: 64)
        } else {
            payload["decision_id"] = "synthetic-decision-exp1666"
            payload["outcome"] = "approve_independent_host"
            payload["enrollment_digest"] = "sha256:" + String(repeating: "c", count: 64)
        }
        let message = domain + (try canonicalJSON(payload))
        let request: [String: String] = [
            "schema": requestSchema,
            "kind": kind,
            "message_base64": message.base64EncodedString(),
            "message_sha256": sha256(message),
            "trust": "unestablished"
        ]
        let requestBytes = try canonicalJSON(request)
        let parsed = try parseRequest(requestBytes, expectedDigest: syntheticKeySetDigest)
        guard parsed.0 == message, parsed.1 == kind, parsed.2 == sha256(message), !parsed.3.isEmpty else {
            throw SignError.rejected
        }
        let responseBytes = try signedResponse(message, kind: kind, using: key)
        let response = try exactStringFields(
            canonicalObject(Data(responseBytes.dropLast())),
            ["schema", "kind", "message_base64", "message_sha256", "signature_hex"]
        )
        guard response["schema"] == responseSchema,
              response["kind"] == kind,
              response["message_base64"] == message.base64EncodedString(),
              response["message_sha256"] == sha256(message),
              let signatureHex = response["signature_hex"],
              let signature = dataFromHex(signatureHex),
              key.publicKey.isValidSignature(signature, for: message) else {
            throw SignError.rejected
        }
        var invalidPayload = payload
        invalidPayload["verifier_profile_digest"] = "sha256:" + String(repeating: "f", count: 64)
        let invalidMessage = domain + (try canonicalJSON(invalidPayload))
        var invalidRequest = request
        invalidRequest["message_base64"] = invalidMessage.base64EncodedString()
        invalidRequest["message_sha256"] = sha256(invalidMessage)
        guard (try? parseRequest(canonicalJSON(invalidRequest), expectedDigest: syntheticKeySetDigest)) == nil else {
            throw SignError.rejected
        }
    }
    FileHandle.standardOutput.write(Data("EXP1666_SELF_TEST_OK\n".utf8))
}

private func selfTestVector() throws {
    let key = Curve25519.Signing.PrivateKey()
    let formatter = ISO8601DateFormatter()
    formatter.formatOptions = [.withInternetDateTime]
    let now = Date()
    let common: [String: String] = [
        "schema": "verifier-trust-enrollment/v1",
        "authority_key_id": keyID,
        "endpoint_url": endpointURL,
        "verifier_id": "synthetic-verifier-exp1666",
        "verifier_profile_digest": profileDigest,
        "verifier_key_id": verifierKeyID,
        "worker_host_id": "synthetic-worker-exp1666",
        "verifier_host_id": "synthetic-verifier-host-exp1666",
        "host_separation_evidence_digest": "sha256:" + String(repeating: "a", count: 64),
        "issued_at": formatter.string(from: now),
        "expires_at": formatter.string(from: now.addingTimeInterval(3_600))
    ]
    var enrollmentPayload = common
    enrollmentPayload["enrollment_id"] = "synthetic-enrollment-exp1666"
    enrollmentPayload["verifier_public_key"] = String(repeating: "b", count: 64)
    let enrollmentMessage = Data("agent00x-verifier-trust-enrollment-ed25519-v1\0".utf8) + (try canonicalJSON(enrollmentPayload))
    let enrollmentRequest = try canonicalJSON([
            "schema": requestSchema,
            "kind": "enrollment",
            "message_base64": enrollmentMessage.base64EncodedString(),
            "message_sha256": sha256(enrollmentMessage),
            "trust": "unestablished"
        ])
    _ = try parseRequest(enrollmentRequest, expectedDigest: "sha256:" + String(repeating: "0", count: 64))
    let enrollmentResponse = try signedResponse(enrollmentMessage, kind: "enrollment", using: key)
    let enrollmentRecord = try signedRecord(enrollmentMessage, kind: "enrollment", response: enrollmentResponse)
    let enrollmentDigest = sha256(enrollmentRecord)

    var decisionPayload = common
    decisionPayload["schema"] = "verifier-host-trust-decision/v1"
    decisionPayload["decision_id"] = "synthetic-decision-exp1666"
    decisionPayload["outcome"] = "approve_independent_host"
    decisionPayload["enrollment_digest"] = enrollmentDigest
    let decisionMessage = Data("agent00x-verifier-host-trust-decision-ed25519-v1\0".utf8) + (try canonicalJSON(decisionPayload))
    let decisionRequest = try canonicalJSON([
        "schema": requestSchema,
        "kind": "host-decision",
        "message_base64": decisionMessage.base64EncodedString(),
        "message_sha256": sha256(decisionMessage),
        "trust": "unestablished"
    ])
    _ = try parseRequest(decisionRequest, expectedDigest: "sha256:" + String(repeating: "0", count: 64))
    let decisionResponse = try signedResponse(decisionMessage, kind: "host-decision", using: key)
    let keySet = try publicKeySet(key)
    let vector: [String: String] = [
        "schema": "agent00x-exp1666-synthetic-verification-vector/v1",
        "authority_key_set_base64": keySet.base64EncodedString(),
        "authority_key_set_digest": sha256(keySet),
        "enrollment_response_base64": enrollmentResponse.base64EncodedString(),
        "enrollment_artifact_base64": enrollmentRecord.base64EncodedString(),
        "enrollment_digest": enrollmentDigest,
        "host_decision_response_base64": decisionResponse.base64EncodedString()
    ]
    FileHandle.standardOutput.write(try canonicalJSON(vector) + Data([0x0a]))
}

let args = Array(CommandLine.arguments.dropFirst())
do {
    if args == ["--self-test"] {
        try selfTest()
        exit(0)
    }
    if args == ["--self-test-vector"] {
        try selfTestVector()
        exit(0)
    }
    guard args.count == 4, args[0] == "--key-set", args[2] == "--key-set-digest" else {
        throw SignError.rejected
    }
    let expectedDigest = args[3]
    guard let pinnedDigest = pinnedAuthorityKeySetDigest else { throw SignError.pinRequired }
    guard expectedDigest == pinnedDigest else { throw SignError.rejected }
    let rawRequest = FileHandle.standardInput.readDataToEndOfFile()
    let (message, kind, messageDigest, publicReview) = try parseRequest(rawRequest, expectedDigest: expectedDigest)
    let review = "EXP1666 REVIEW key_set=\(expectedDigest) message=\(messageDigest) bytes=\(message.count)\n\(publicReview)"
    let phrase = "SIGN EXP-1666 \(kind) \(expectedDigest) \(messageDigest)"
    guard try ttyLine(prompt: "\(review)\nType \(phrase) to continue: ") == phrase else {
        throw SignError.rejected
    }
    let key = try loadPinnedKeySet(args[1], expectedDigest: expectedDigest)
    let signature = try key.signature(for: message)
    let response: [String: String] = [
        "message_base64": message.base64EncodedString(),
        "kind": kind,
        "message_sha256": messageDigest,
        "schema": responseSchema,
        "signature_hex": signature.map { String(format: "%02x", $0) }.joined()
    ]
    let output = try canonicalJSON(response) + Data([0x0a])
    FileHandle.standardOutput.write(output)
} catch {
    emitError(error)
}

#!/usr/bin/env swift

import CryptoKit
import Foundation
import Security

private let keyID = "cp-macos-keychain-exp1665-20261020-v1"
private let keychainService = "org.agent00x.control-plane.authority.exp1665.v1"
private let keychainAccount = "ed25519-signing-key"
private let profileDigest = "sha256:34d973ee7632a397b3941b32408dd7903774ed38c9958ad41bd4e6194ddfd280"
private let keySetSchema = "control-plane-authority-key-set/v1"

private enum ProvisionError: Error {
    case rejected
    case keychainUnavailable
}

private func fail(_ error: Error) -> Never {
    let marker: String
    if case ProvisionError.keychainUnavailable = error {
        marker = "EXP1665_KEYCHAIN_OPERATION_UNAVAILABLE\n"
    } else {
        marker = "EXP1665_PROVISION_REJECTED\n"
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

private func sha256(_ data: Data) -> String {
    "sha256:" + hex(Data(SHA256.hash(data: data)))
}

private func query() -> [String: Any] {
    [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: keychainService,
        kSecAttrAccount as String: keychainAccount
    ]
}

private func publicKeySet(_ key: Curve25519.Signing.PrivateKey) throws -> Data {
    var result = try canonicalJSON([
        "schema": keySetSchema,
        "keys": [keyID: hex(key.publicKey.rawRepresentation)]
    ])
    result.append(0x0a)
    return result
}

private func selfTest() throws {
    guard profileDigest == "sha256:34d973ee7632a397b3941b32408dd7903774ed38c9958ad41bd4e6194ddfd280" else {
        throw ProvisionError.rejected
    }
    let key = Curve25519.Signing.PrivateKey()
    let bytes = try publicKeySet(key)
    guard let object = try JSONSerialization.jsonObject(with: bytes) as? [String: Any],
          object["schema"] as? String == keySetSchema,
          let keys = object["keys"] as? [String: String],
          Set(keys.keys) == [keyID],
          keys[keyID]?.count == 64,
          sha256(bytes).range(of: #"^sha256:[0-9a-f]{64}$"#, options: .regularExpression) != nil else {
        throw ProvisionError.rejected
    }
    FileHandle.standardOutput.write(Data("EXP1665_SELF_TEST_OK\n".utf8))
}

private func provision() throws {
    var lookup = query()
    lookup[kSecReturnAttributes as String] = true
    var existing: CFTypeRef?
    let lookupStatus = SecItemCopyMatching(lookup as CFDictionary, &existing)
    guard lookupStatus == errSecItemNotFound else {
        throw lookupStatus == errSecSuccess ? ProvisionError.rejected : ProvisionError.keychainUnavailable
    }

    let key = Curve25519.Signing.PrivateKey()
    let item = query().merging([
        kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
        kSecValueData as String: key.rawRepresentation
    ]) { _, new in new }
    let addStatus = SecItemAdd(item as CFDictionary, nil)
    guard addStatus == errSecSuccess else {
        throw addStatus == errSecDuplicateItem ? ProvisionError.rejected : ProvisionError.keychainUnavailable
    }

    let keySet = try publicKeySet(key)
    FileHandle.standardOutput.write(keySet)
    FileHandle.standardError.write(
        Data("EXP1665_PUBLIC_KEYSET_DIGEST|\(sha256(keySet))|profile=\(profileDigest)\n".utf8)
    )
}

let arguments = Array(CommandLine.arguments.dropFirst())
do {
    if arguments == ["--self-test"] {
        try selfTest()
    } else if arguments == ["--provision"] {
        try provision()
    } else {
        throw ProvisionError.rejected
    }
} catch {
    fail(error)
}

import Foundation
@testable import RhizeRemindersHelper
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

// Kept in a file that does NOT also `import Testing`: combining `Foundation`
// and `Testing` imports in one file pulls in the `_Testing_Foundation`
// cross-import overlay, which this toolchain's Testing.framework does not
// resolve via a plain `-F` search path. Isolating every Foundation-touching
// helper here, and every `Testing`-touching assertion in SocketServerTests.swift,
// avoids the combination entirely.

struct TestSocketError: Error {
    let message: String
}

// Returns plain `String` paths rather than `URL` — everything in this file
// is a boundary the Testing-importing test file also crosses, and `URL` is
// a Foundation type that would force this file's `import Foundation` to
// leak into that one, recreating the exact cross-import problem this split
// exists to avoid.
//
// Deliberately under `/tmp` (13 bytes as `/private/tmp`) with a short
// random suffix, NOT `NSTemporaryDirectory()` — macOS's per-user temp path
// (`/var/folders/<hash>/<hash>/T/`) is already ~46 bytes on its own, and
// `sockaddr_un.sun_path` has a hard 104-byte limit. A full UUID-named
// subdirectory under `NSTemporaryDirectory()` plus a filename reliably
// exceeds that limit and corrupts the fixed-size buffer during the fill
// loop below — this is not hypothetical, it reproduced as a crash while
// writing these tests. Production code (SocketServer.swift) guards against
// the same limit by throwing `socket_path_too_long`; the fix here is to
// keep test paths short enough that the guard is never exercised by
// accident.
func privateTempDirectory() throws -> String {
    let suffix = String(UInt32.random(in: 0...0xFFFFFFFF), radix: 16)
    let base = "/tmp/rt-\(suffix)"
    try FileManager.default.createDirectory(atPath: base, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
    return base
}

func joinPath(_ directory: String, _ component: String) -> String {
    (directory as NSString).appendingPathComponent(component)
}

func removeDirectory(atPath path: String) {
    try? FileManager.default.removeItem(atPath: path)
}

func socketFileExists(atPath path: String) -> Bool {
    FileManager.default.fileExists(atPath: path)
}

func setDirectoryPermissions(_ path: String, mode: Int) throws {
    try FileManager.default.setAttributes([.posixPermissions: mode], ofItemAtPath: path)
}

func writePlainFile(atPath path: String, contents: String) throws {
    try Data(contents.utf8).write(to: URL(fileURLWithPath: path))
}

private func fillTestSocketAddress(path: String) throws -> sockaddr_un {
    var addr = sockaddr_un()
    addr.sun_family = sa_family_t(AF_UNIX)
    let pathBytes = Array(path.utf8)
    let capacity = MemoryLayout.size(ofValue: addr.sun_path)
    // `sun_path` is a fixed 104-byte buffer — writing past it without this
    // guard silently corrupts adjacent struct fields instead of failing
    // loudly. Mirrors the guard in SocketServer.swift's production
    // `fillSocketAddress`.
    guard pathBytes.count < capacity else { throw TestSocketError(message: "test_socket_path_too_long") }
    withUnsafeMutableBytes(of: &addr.sun_path) { raw in
        let buffer = raw.bindMemory(to: UInt8.self)
        for index in buffer.indices { buffer[index] = 0 }
        for (index, byte) in pathBytes.enumerated() { buffer[index] = byte }
    }
    #if canImport(Darwin)
    addr.sun_len = UInt8(MemoryLayout<sockaddr_un>.size)
    #endif
    return addr
}

/// Leaves a socket special file on disk at `path` without anything
/// listening on it — simulates what an unclean shutdown (crash, SIGKILL)
/// of a previous helper run leaves behind, to exercise stale-socket removal.
func leaveStaleSocketFile(atPath path: String) {
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { return }
    guard var addr = try? fillTestSocketAddress(path: path) else { close(fd); return }
    _ = withUnsafePointer(to: &addr) { pointer -> Int32 in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
            bind(fd, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    close(fd)
}

/// Connects to the given Unix socket, writes one newline-terminated request
/// line, reads one newline-terminated response line, and returns it decoded.
func exchangeOverSocket(socketPath: String, requestLine: String) throws -> HelperResponse {
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { throw TestSocketError(message: "client_socket_failed") }
    defer { close(fd) }

    var addr = try fillTestSocketAddress(path: socketPath)
    let connectResult = withUnsafePointer(to: &addr) { pointer -> Int32 in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
            connect(fd, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    guard connectResult == 0 else { throw TestSocketError(message: "client_connect_failed") }

    var request = Data(requestLine.utf8)
    request.append(10)
    request.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { return }
        var offset = 0
        while offset < request.count {
            let count = write(fd, base + offset, request.count - offset)
            if count <= 0 { break }
            offset += count
        }
    }

    var response = [UInt8]()
    var chunk = [UInt8](repeating: 0, count: 4_096)
    while true {
        let count = chunk.withUnsafeMutableBytes { pointer in read(fd, pointer.baseAddress, pointer.count) }
        if count <= 0 { break }
        response.append(contentsOf: chunk[0..<count])
        if response.contains(10) { break }
    }
    guard let newlineIndex = response.firstIndex(of: 10) else { throw TestSocketError(message: "no_response_line") }
    let data = Data(response[..<newlineIndex])
    return try JSONDecoder().decode(HelperResponse.self, from: data)
}

/// Connects to the socket and sends NOTHING — simulates a half-open client
/// (finding #5). Returns `true` if the server closes its end (EOF) within
/// `timeoutSeconds`, `false` if the connection is still open when the
/// (generous, client-side) wait budget runs out. The client's OWN receive
/// timeout is set well above the server's expected deadline so a
/// regression that makes the server hang fails the assertion instead of
/// hanging the test suite.
func connectAndExpectServerCloseWithoutSending(socketPath: String, timeoutSeconds: Int) -> Bool {
    let fd = socket(AF_UNIX, SOCK_STREAM, 0)
    guard fd >= 0 else { return false }
    defer { close(fd) }
    guard var addr = try? fillTestSocketAddress(path: socketPath) else { return false }
    let connectResult = withUnsafePointer(to: &addr) { pointer -> Int32 in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
            connect(fd, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    guard connectResult == 0 else { return false }
    var clientTimeout = timeval(tv_sec: timeoutSeconds + 5, tv_usec: 0)
    setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &clientTimeout, socklen_t(MemoryLayout<timeval>.size))
    var probeByte: UInt8 = 0
    let count = read(fd, &probeByte, 1)
    return count == 0
}

/// Polls a boolean condition until it becomes true or the attempt budget is
/// exhausted, sleeping a short fixed interval between checks. Used instead
/// of a fixed sleep so tests don't race the server's accept-loop startup.
func waitUntil(attempts: Int = 100, intervalMs: UInt32 = 20, condition: () -> Bool) {
    var remaining = attempts
    while !condition(), remaining > 0 {
        usleep(intervalMs * 1_000)
        remaining -= 1
    }
}

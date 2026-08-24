import Foundation
#if canImport(Darwin)
import Darwin
#else
import Glibc
#endif

/// Errors raised by the `--serve` Unix-socket mode. Every case maps to a
/// stable, machine-readable code so a caller (tests, or a human reading
/// stderr) never has to parse free-form text.
struct SocketServeError: Error, Equatable {
    let code: String
}

/// A previous run that didn't shut down cleanly (crash, SIGKILL) can leave
/// its socket special file behind; `bind` on an existing path fails with
/// EADDRINUSE even though nothing is listening. Remove it before binding —
/// but only if it is actually a socket, never an arbitrary file, so a
/// misconfigured path can't cause us to silently delete something unrelated.
func removeStaleSocketFile(at path: String) throws {
    var info = stat()
    guard lstat(path, &info) == 0 else {
        if errno == ENOENT { return }
        throw SocketServeError(code: "stale_socket_stat_failed")
    }
    guard (info.st_mode & S_IFMT) == S_IFSOCK else {
        throw SocketServeError(code: "stale_socket_path_not_a_socket")
    }
    guard unlink(path) == 0 else {
        throw SocketServeError(code: "stale_socket_remove_failed")
    }
}

/// The installer is responsible for creating the socket's parent directory
/// as a private (0700), owner-only directory before this process ever
/// starts. Refuse to serve if that invariant doesn't hold — a
/// wrong-permission parent means either an installer bug or something else
/// got there first, and this is a local-IPC channel that hands out
/// Reminders read/write access, so failing closed is the only safe default.
func assertSocketParentDirectoryIsPrivate(_ socketPath: String) throws {
    let parent = (socketPath as NSString).deletingLastPathComponent
    guard !parent.isEmpty else { throw SocketServeError(code: "socket_path_has_no_parent") }
    var info = stat()
    guard lstat(parent, &info) == 0 else { throw SocketServeError(code: "socket_parent_missing") }
    guard (info.st_mode & S_IFMT) == S_IFDIR else { throw SocketServeError(code: "socket_parent_not_a_directory") }
    guard info.st_uid == getuid() else { throw SocketServeError(code: "socket_parent_wrong_owner") }
    guard (info.st_mode & 0o777) == 0o700 else { throw SocketServeError(code: "socket_parent_permissions_too_open") }
}

private func fillSocketAddress(path: String) throws -> sockaddr_un {
    var addr = sockaddr_un()
    addr.sun_family = sa_family_t(AF_UNIX)
    let pathBytes = Array(path.utf8)
    let capacity = MemoryLayout.size(ofValue: addr.sun_path)
    guard pathBytes.count < capacity else { throw SocketServeError(code: "socket_path_too_long") }
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

/// Identifies a filesystem entry by (device, inode) — the only reliable way
/// to ask "is this still the SAME file I created?" after the fact, since a
/// path alone can be reused by an unrelated file in between.
private struct FileIdentity: Equatable {
    let device: dev_t
    let inode: ino_t
}

private func fileIdentity(at path: String) -> FileIdentity? {
    var info = stat()
    guard lstat(path, &info) == 0 else { return nil }
    return FileIdentity(device: info.st_dev, inode: info.st_ino)
}

/// What an existing socket special file at the target path means for
/// startup. Two live `--serve` processes can overlap under launchd's
/// `KeepAlive` (a crash-restart racing the old instance's own shutdown) —
/// unconditionally unlinking on startup lets a second instance delete a
/// FIRST instance's still-live socket, bind its own, and then have the
/// first instance's (unconditional) shutdown unlink delete the SECOND
/// instance's socket out from under it. Probing before acting closes that.
private enum ExistingSocketState {
    case absent           // nothing there (ENOENT) — nothing to worry about
    case stale            // a socket file exists but nothing answers (ECONNREFUSED) — safe to remove
    case liveInstance      // something is actively listening — must NOT be touched
    case indeterminate    // present but not a socket, or the probe itself failed some other way
}

private func probeExistingSocketState(at path: String) -> ExistingSocketState {
    var info = stat()
    guard lstat(path, &info) == 0 else { return .absent }
    guard (info.st_mode & S_IFMT) == S_IFSOCK else { return .indeterminate }
    let probeFD = socket(AF_UNIX, SOCK_STREAM, 0)
    guard probeFD >= 0 else { return .indeterminate }
    defer { close(probeFD) }
    guard var addr = try? fillSocketAddress(path: path) else { return .indeterminate }
    let connectResult = withUnsafePointer(to: &addr) { pointer -> Int32 in
        pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
            connect(probeFD, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_un>.size))
        }
    }
    if connectResult == 0 { return .liveInstance }
    return errno == ECONNREFUSED ? .stale : .indeterminate
}

/// EOF is deliberately NOT treated as a frame terminator: a client that
/// connects and hangs up before sending a complete newline-terminated line
/// gets no response, rather than having whatever partial bytes it sent
/// treated as a request. `read()` returning `-1`/`EINTR` is retried;
/// any other error (including `EAGAIN`/`EWOULDBLOCK` from the receive
/// deadline set on the socket in `handleConnection`) gives up on this
/// connection instead of looping forever.
private func readOneLine(fromFD fd: Int32, maxBytes: Int = 2_000_000) -> String? {
    var buffer = [UInt8]()
    var chunk = [UInt8](repeating: 0, count: 4_096)
    while true {
        let count = chunk.withUnsafeMutableBytes { pointer in
            read(fd, pointer.baseAddress, pointer.count)
        }
        if count > 0 {
            buffer.append(contentsOf: chunk[0..<count])
            if buffer.contains(10) { break }
            if buffer.count > maxBytes { return nil }
            continue
        }
        if count == 0 { return nil }
        if errno == EINTR { continue }
        return nil
    }
    guard let newlineIndex = buffer.firstIndex(of: 10) else { return nil }
    return String(decoding: buffer[..<newlineIndex], as: UTF8.self)
}

private func writeAll(fd: Int32, data: Data) {
    data.withUnsafeBytes { raw in
        guard let base = raw.baseAddress else { return }
        var offset = 0
        while offset < data.count {
            let count = write(fd, base + offset, data.count - offset)
            if count > 0 { offset += count; continue }
            if count < 0 && errno == EINTR { continue }
            break
        }
    }
}

/// Serves the helper's NDJSON request/response protocol over a Unix domain
/// socket instead of stdin/stdout: one connection carries exactly one
/// newline-terminated JSON request and gets exactly one newline-terminated
/// JSON response before the connection is closed — the same request and
/// response bodies, and the same error codes, as the existing stdin/stdout
/// mode, so callers on either transport get identical behavior.
final class UnixSocketServer: @unchecked Sendable {
    private let socketPath: String
    private let store: EventKitStore
    /// Seconds to wait for a complete request line from a connected client
    /// before giving up on that connection. Serial accept + a blocking read
    /// with no deadline meant one half-open client (connects, never sends
    /// data) hung the entire helper forever — every later caller queues
    /// behind it indefinitely. Injectable for tests.
    private let connectionTimeoutSeconds: Int

    init(socketPath: String, store: EventKitStore, connectionTimeoutSeconds: Int = 10) {
        self.socketPath = socketPath
        self.store = store
        self.connectionTimeoutSeconds = connectionTimeoutSeconds
    }

    /// `maxConnections`, when set, stops the accept loop after that many
    /// connections have been handled — production (`nil`) serves forever;
    /// tests pass a bound so the loop terminates deterministically instead
    /// of running as a stray background task for the rest of the process.
    func run(maxConnections: Int? = nil) async throws {
        try assertSocketParentDirectoryIsPrivate(socketPath)
        switch probeExistingSocketState(at: socketPath) {
        case .absent, .stale:
            try removeStaleSocketFile(at: socketPath)
        case .liveInstance:
            // Another instance is already serving this socket (a KeepAlive
            // restart racing the outgoing instance's own shutdown, most
            // likely) — do not unlink out from under it.
            throw SocketServeError(code: "socket_already_serving")
        case .indeterminate:
            throw SocketServeError(code: "stale_socket_probe_indeterminate")
        }

        let fd = socket(AF_UNIX, SOCK_STREAM, 0)
        guard fd >= 0 else { throw SocketServeError(code: "socket_create_failed") }
        defer { close(fd) }

        var addr = try fillSocketAddress(path: socketPath)
        let bindResult = withUnsafePointer(to: &addr) { pointer -> Int32 in
            pointer.withMemoryRebound(to: sockaddr.self, capacity: 1) { sockaddrPointer in
                bind(fd, sockaddrPointer, socklen_t(MemoryLayout<sockaddr_un>.size))
            }
        }
        guard bindResult == 0 else { throw SocketServeError(code: "socket_bind_failed") }

        // Record the identity of the socket file THIS bind just created —
        // shutdown only unlinks the path if it still resolves to that same
        // (device, inode) pair. Without this, a second instance that binds
        // a fresh socket at the same path after we've already bound (however
        // unlikely now that startup probes first) would have ITS socket
        // deleted by our shutdown instead of ours.
        let boundIdentity = fileIdentity(at: socketPath)
        defer {
            if let boundIdentity, fileIdentity(at: socketPath) == boundIdentity {
                unlink(socketPath)
            }
        }

        // Defense in depth on top of the private parent directory: restrict
        // the socket file itself to the owner too.
        guard chmod(socketPath, 0o600) == 0 else { throw SocketServeError(code: "socket_chmod_failed") }
        guard listen(fd, 16) == 0 else { throw SocketServeError(code: "socket_listen_failed") }

        var served = 0
        while maxConnections == nil || served < maxConnections! {
            let clientFD = accept(fd, nil, nil)
            guard clientFD >= 0 else {
                if maxConnections != nil { break }
                continue
            }
            #if canImport(Darwin)
            // Writing to a peer that has already closed its end delivers
            // SIGPIPE by default on Darwin, which would crash the whole
            // long-lived helper process over a single misbehaving client.
            var noSigPipe: Int32 = 1
            setsockopt(clientFD, SOL_SOCKET, SO_NOSIGPIPE, &noSigPipe, socklen_t(MemoryLayout<Int32>.size))
            #endif
            var timeout = timeval(tv_sec: connectionTimeoutSeconds, tv_usec: 0)
            setsockopt(clientFD, SOL_SOCKET, SO_RCVTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
            setsockopt(clientFD, SOL_SOCKET, SO_SNDTIMEO, &timeout, socklen_t(MemoryLayout<timeval>.size))
            await handleConnection(clientFD)
            served += 1
        }
    }

    private func handleConnection(_ clientFD: Int32) async {
        defer { close(clientFD) }
        guard let line = readOneLine(fromFD: clientFD), !line.isEmpty else { return }
        let response = await processRequestLine(line, store: store)
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]
        guard var data = try? encoder.encode(response) else { return }
        data.append(10)
        writeAll(fd: clientFD, data: data)
    }
}

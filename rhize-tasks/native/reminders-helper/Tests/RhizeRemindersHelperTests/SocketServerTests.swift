import Testing
@testable import RhizeRemindersHelper

// Every test here drives `UnixSocketServer` against `FakeEventStore`
// (defined in EventKitStoreTests.swift) only. The real EventKit path
// (`SystemEventKitBackingStore`) must never execute during `swift test` —
// on an unattended Mac that would either pop a TCC prompt nothing can
// answer, or silently record a denial against the helper — so these tests
// never construct one. Foundation-touching plumbing (sockets, filesystem,
// JSON decoding) lives in SocketTestSupport.swift, which deliberately does
// NOT also `import Testing` — see the comment there for why.

@Test func serveModeHandlesOneRequestPerConnectionOverTheSocket() async throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    let socketPath = joinPath(directory, "reminders-helper.sock")

    let fake = FakeEventStore()
    let store = EventKitStore(eventStore: fake, allowedListID: "rhize")
    let server = UnixSocketServer(socketPath: socketPath, store: store)
    let serverTask = Task { try await server.run(maxConnections: 2) }

    waitUntil { socketFileExists(atPath: socketPath) }
    #expect(socketFileExists(atPath: socketPath))

    let upsertRequest = """
    {"command":"upsert","listId":"rhize","title":"Review campaigns","dueAt":null,"notes":"note","externalId":"RHIZE-1","operationKey":"op-1"}
    """
    let upsertResponse = try exchangeOverSocket(socketPath: socketPath, requestLine: upsertRequest)
    #expect(upsertResponse.ok == true)
    #expect(upsertResponse.id == "RHIZE-1")

    let listsResponse = try exchangeOverSocket(socketPath: socketPath, requestLine: #"{"command":"lists"}"#)
    #expect(listsResponse.ok == true)
    #expect(listsResponse.lists?.contains(where: { $0.id == "rhize" }) == true)

    _ = try await serverTask.value
    #expect(fake.storedReminders.count == 1)
}

@Test func serveModeRemovesAStaleSocketFileLeftFromAnUncleanShutdown() async throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    let socketPath = joinPath(directory, "reminders-helper.sock")

    leaveStaleSocketFile(atPath: socketPath)
    #expect(socketFileExists(atPath: socketPath))

    let store = EventKitStore(eventStore: FakeEventStore(), allowedListID: "rhize")
    let server = UnixSocketServer(socketPath: socketPath, store: store)
    let serverTask = Task { try await server.run(maxConnections: 1) }

    var reboundOK = false
    waitUntil {
        if (try? exchangeOverSocket(socketPath: socketPath, requestLine: #"{"command":"lists"}"#)) != nil {
            reboundOK = true
            return true
        }
        return false
    }
    #expect(reboundOK, "server must remove the stale socket file and successfully rebind")
    _ = try? await serverTask.value
}

@Test func serveModeRefusesToStartWhenTheSocketParentDirectoryIsNotPrivate() async throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    try setDirectoryPermissions(directory, mode: 0o755)
    let socketPath = joinPath(directory, "reminders-helper.sock")

    let store = EventKitStore(eventStore: FakeEventStore(), allowedListID: "rhize")
    let server = UnixSocketServer(socketPath: socketPath, store: store)
    await #expect(throws: SocketServeError(code: "socket_parent_permissions_too_open")) {
        try await server.run(maxConnections: 1)
    }
}

@Test func removeStaleSocketFileRefusesToDeleteAFileThatIsNotActuallyASocket() throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    let notASocket = joinPath(directory, "not-a-socket")
    try writePlainFile(atPath: notASocket, contents: "hello")
    #expect(throws: SocketServeError(code: "stale_socket_path_not_a_socket")) {
        try removeStaleSocketFile(at: notASocket)
    }
}

@Test func removeStaleSocketFileIsANoOpWhenNothingExistsAtThePath() throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    let missing = joinPath(directory, "does-not-exist.sock")
    try removeStaleSocketFile(at: missing)
}

// #1 (blocker) — serve mode has no process-wide list scope: each request
// must carry its own `allowedListId`, since one long-lived helper process
// now serves callers that may care about different lists over its
// lifetime (the old fixed-env-var scope only worked because stdin/stdout
// mode span up one process per call).
@Test func serveModePerRequestScopeAcceptsAMatchingListIdAndRejectsAMissingOrMismatchedOne() async throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    let socketPath = joinPath(directory, "reminders-helper.sock")

    let fake = FakeEventStore()
    let store = EventKitStore(eventStore: fake, scope: .perRequest)
    let server = UnixSocketServer(socketPath: socketPath, store: store)
    let serverTask = Task { try await server.run(maxConnections: 3) }
    waitUntil { socketFileExists(atPath: socketPath) }

    let matching = try exchangeOverSocket(
        socketPath: socketPath,
        requestLine: #"{"command":"upsert","listId":"rhize","allowedListId":"rhize","title":"Review campaigns","dueAt":null,"notes":"note","externalId":"RHIZE-1","operationKey":"op-1"}"#
    )
    #expect(matching.ok == true)
    #expect(matching.id == "RHIZE-1")

    let missingScope = try exchangeOverSocket(
        socketPath: socketPath,
        requestLine: #"{"command":"upsert","listId":"rhize","title":"Missing scope","dueAt":null,"notes":"note","externalId":"RHIZE-2","operationKey":"op-2"}"#
    )
    #expect(missingScope.ok == false)
    #expect(missingScope.error == "out_of_scope")

    let mismatchedScope = try exchangeOverSocket(
        socketPath: socketPath,
        requestLine: #"{"command":"upsert","listId":"rhize","allowedListId":"personal","title":"Mismatched scope","dueAt":null,"notes":"note","externalId":"RHIZE-3","operationKey":"op-3"}"#
    )
    #expect(mismatchedScope.ok == false)
    #expect(mismatchedScope.error == "out_of_scope")

    _ = try await serverTask.value
    #expect(fake.storedReminders.count == 1, "only the matching-scope request should have written anything")
}

// #5 (major) — a half-open client (connects, sends nothing) must not hang
// the helper forever: serial accept + a blocking read with no deadline
// meant every later caller would queue behind it indefinitely.
@Test func serveModeClosesAHalfOpenConnectionAfterItsReceiveDeadlineInsteadOfHangingForever() async throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    let socketPath = joinPath(directory, "reminders-helper.sock")

    let store = EventKitStore(eventStore: FakeEventStore(), scope: .perRequest)
    let server = UnixSocketServer(socketPath: socketPath, store: store, connectionTimeoutSeconds: 1)
    let serverTask = Task { try await server.run(maxConnections: 2) }
    waitUntil { socketFileExists(atPath: socketPath) }

    let closed = connectAndExpectServerCloseWithoutSending(socketPath: socketPath, timeoutSeconds: 1)
    #expect(closed, "the server must close a connection that never completes a request instead of holding it open forever")

    // The accept loop must have recovered, not wedged — a normal request
    // right after must still get served.
    let listsResponse = try exchangeOverSocket(socketPath: socketPath, requestLine: #"{"command":"lists"}"#)
    #expect(listsResponse.ok == true)

    _ = try await serverTask.value
}

// #4 (major) — two overlapping instances (e.g. a KeepAlive restart racing
// the outgoing instance's own shutdown) must not split-brain: the second
// instance must refuse rather than unlink the first instance's live socket.
@Test func serveModeRefusesToStartWhenAnotherInstanceIsAlreadyServingTheSameSocket() async throws {
    let directory = try privateTempDirectory()
    defer { removeDirectory(atPath: directory) }
    let socketPath = joinPath(directory, "reminders-helper.sock")

    let storeA = EventKitStore(eventStore: FakeEventStore(), scope: .perRequest)
    let serverA = UnixSocketServer(socketPath: socketPath, store: storeA, connectionTimeoutSeconds: 5)
    // maxConnections: 2 — one slot is incidentally consumed by instance B's
    // own liveness probe connection below (a successful connect() queues a
    // connection in A's accept backlog even though B sends nothing), the
    // second slot is the explicit verification request at the end.
    let serverATask = Task { try await serverA.run(maxConnections: 2) }
    waitUntil { socketFileExists(atPath: socketPath) }

    let storeB = EventKitStore(eventStore: FakeEventStore(), scope: .perRequest)
    let serverB = UnixSocketServer(socketPath: socketPath, store: storeB, connectionTimeoutSeconds: 5)
    do {
        try await serverB.run(maxConnections: 1)
        Issue.record("expected serverB.run() to throw socket_already_serving")
    } catch let error as SocketServeError {
        #expect(error == SocketServeError(code: "socket_already_serving"))
    }

    // Instance A's socket must still be intact and serving — B must not
    // have unlinked it before discovering it was live.
    let listsResponse = try exchangeOverSocket(socketPath: socketPath, requestLine: #"{"command":"lists"}"#)
    #expect(listsResponse.ok == true)

    _ = try await serverATask.value
}

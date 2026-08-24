import Foundation

/// Two run modes, same request/response protocol and same EventKit-backed
/// store either way: `--serve <socket-path>` accepts a Unix socket
/// connection per request (the LaunchAgent-driven production path); with no
/// arguments, the original stdin/stdout NDJSON loop stays exactly as it was
/// (the dev/test fallback, and what `runRemindersAccessProbe` still spawns
/// for the interactive setup access-check).
///
/// List scope differs by mode: stdin/stdout is one process per caller, so
/// `RHIZE_TASKS_REMINDERS_LIST_ID` (read once, fixed for the process's
/// whole life) was always sufficient. `--serve` is one long-lived process
/// across many callers, so each request carries its own `allowedListId`
/// instead (see `ScopeSource.perRequest` in EventKitStore.swift) — the env
/// var is not read at all in this mode.
private func runHelper() async {
    let arguments = CommandLine.arguments
    if let serveIndex = arguments.firstIndex(of: "--serve"), arguments.indices.contains(serveIndex + 1) {
        let socketPath = arguments[serveIndex + 1]
        let store = EventKitStore(eventStore: SystemEventKitBackingStore(), scope: .perRequest)
        do {
            try await UnixSocketServer(socketPath: socketPath, store: store).run()
        } catch {
            FileHandle.standardError.write("serve_failed: \(error)\n".data(using: .utf8) ?? Data())
            exit(1)
        }
        return
    }

    let allowedListID = ProcessInfo.processInfo.environment["RHIZE_TASKS_REMINDERS_LIST_ID"] ?? ""
    let store = EventKitStore(eventStore: SystemEventKitBackingStore(), allowedListID: allowedListID)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys, .withoutEscapingSlashes]

    while let line = readLine() {
        let response = await processRequestLine(line, store: store)
        if let data = try? encoder.encode(response), let output = String(data: data, encoding: .utf8) {
            print(output)
            fflush(stdout)
        }
    }
}

await runHelper()

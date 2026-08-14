import Foundation

private func runHelper() async {
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

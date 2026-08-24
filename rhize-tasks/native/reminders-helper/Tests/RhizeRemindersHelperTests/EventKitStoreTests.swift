import Testing
@testable import RhizeRemindersHelper

final class FakeEventStore: ReminderBackingStore, @unchecked Sendable {
    var authorized = true
    var storedLists = [StoredList(id: "rhize", title: "Rhize Tasks"), StoredList(id: "personal", title: "Personal")]
    var storedReminders: [StoredReminder] = []

    func requestFullAccess() async throws -> Bool { authorized }
    func lists() throws -> [StoredList] { storedLists }
    func createList(title: String) throws -> StoredList {
        let value = StoredList(id: "created-rhize", title: title)
        storedLists.append(value)
        return value
    }
    func reminders(listIDs: [String]) async throws -> [StoredReminder] {
        storedReminders.filter { listIDs.contains($0.listID) }
    }
    func save(_ reminder: StoredReminder) throws -> StoredReminder {
        if let index = storedReminders.firstIndex(where: { $0.nativeID == reminder.nativeID }) {
            storedReminders[index] = reminder
        } else {
            storedReminders.append(reminder)
        }
        return reminder
    }
    func remove(nativeID: String) throws {
        guard let index = storedReminders.firstIndex(where: { $0.nativeID == nativeID }) else {
            throw HelperFailure.reminderNotFound
        }
        storedReminders.remove(at: index)
    }
}

private func request(
    command: String = "upsert",
    listID: String? = "rhize",
    title: String? = "Review campaigns",
    externalID: String? = "RHIZE-123",
    approved: Bool? = nil,
    createList: Bool? = nil,
    redactTitles: Bool? = nil,
    allowedListId: String? = nil
) -> HelperRequest {
    HelperRequest(
        command: command,
        listId: listID,
        listIds: command == "snapshot" ? [listID].compactMap { $0 } : nil,
        title: title,
        dueAt: "2026-08-14T19:00:00Z",
        notes: "Client-safe note",
        externalId: externalID,
        id: externalID,
        operationKey: "operation-1",
        completedAt: nil,
        approved: approved,
        createList: createList,
        redactTitles: redactTitles,
        allowedListId: allowedListId
    )
}

@Test func rejectsPermissionDenial() async throws {
    let fake = FakeEventStore()
    fake.authorized = false
    let store = EventKitStore(eventStore: fake, allowedListID: "rhize")
    await #expect(throws: HelperFailure.authorizationDenied) {
        try await store.execute(request(command: "authorize"))
    }
}

@Test func rejectsWriteOutsideRhizeTasksList() async throws {
    let store = EventKitStore(eventStore: FakeEventStore(), allowedListID: "rhize")
    await #expect(throws: HelperFailure.outOfScope) {
        try await store.execute(request(listID: "personal"))
    }
}

@Test func stableMarkerMakesUpsertIdempotent() async throws {
    let fake = FakeEventStore()
    let store = EventKitStore(eventStore: fake, allowedListID: "rhize")
    let first = try await store.execute(request())
    let second = try await store.execute(request(title: "Review campaigns again"))
    #expect(first.id == "RHIZE-123")
    #expect(second.id == first.id)
    #expect(fake.storedReminders.count == 1)
    #expect(fake.storedReminders[0].notes?.contains("rhize-tasks:item:RHIZE-123") == true)
}

@Test func completeUsesStableIdentifierInsideTheAllowedList() async throws {
    let fake = FakeEventStore()
    let store = EventKitStore(eventStore: fake, allowedListID: "rhize")
    _ = try await store.execute(request())
    let result = try await store.execute(request(command: "complete", title: nil))
    #expect(result.id == "RHIZE-123")
    #expect(fake.storedReminders.count == 1)
    #expect(fake.storedReminders[0].completed == true)
}

@Test func snapshotRedactsTitlesAndNotes() async throws {
    let fake = FakeEventStore()
    fake.storedReminders = [StoredReminder(
        nativeID: "native-1", listID: "rhize", title: "Private client title", notes: "Private note",
        dueAt: nil, completed: false, stableID: "RHIZE-123", revision: "1"
    )]
    let store = EventKitStore(eventStore: fake, allowedListID: "rhize")
    let result = try await store.execute(request(command: "snapshot", redactTitles: true))
    #expect(result.items?.first?.title == "Busy")
    #expect(result.items?.first?.notes == nil)
}

@Test func listCreationRequiresExplicitApproval() async throws {
    let fake = FakeEventStore()
    fake.storedLists = []
    let store = EventKitStore(eventStore: fake, allowedListID: "")
    await #expect(throws: HelperFailure.approvalRequired) {
        try await store.execute(request(command: "authorize", approved: false, createList: true))
    }
    let result = try await store.execute(request(command: "authorize", approved: true, createList: true))
    #expect(result.lists?.first?.title == "Rhize Tasks")
}

@Test func malformedStableIdentifierIsRejected() async throws {
    let store = EventKitStore(eventStore: FakeEventStore(), allowedListID: "rhize")
    await #expect(throws: HelperFailure.invalidRequest) {
        try await store.execute(request(externalID: "bad\nidentifier"))
    }
}

@Test func malformedJsonIsNormalizedWithoutLeakingParserDetails() async throws {
    let store = EventKitStore(eventStore: FakeEventStore(), allowedListID: "rhize")
    let result = await processRequestLine("{not-json", store: store)
    #expect(result.ok == false)
    #expect(result.error == "invalid_request")
}

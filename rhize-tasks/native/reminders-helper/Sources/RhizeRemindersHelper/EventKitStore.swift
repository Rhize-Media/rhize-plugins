import EventKit
import Foundation

enum HelperFailure: Error, Equatable {
    case authorizationDenied
    case approvalRequired
    case invalidRequest
    case listNotFound
    case outOfScope
    case reminderNotFound

    var code: String {
        switch self {
        case .authorizationDenied: "authorization_denied"
        case .approvalRequired: "approval_required"
        case .invalidRequest: "invalid_request"
        case .listNotFound: "list_not_found"
        case .outOfScope: "out_of_scope"
        case .reminderNotFound: "reminder_not_found"
        }
    }
}

struct StoredList: Equatable, Sendable {
    let id: String
    let title: String
}

struct StoredReminder: Equatable, Sendable {
    let nativeID: String
    let listID: String
    var title: String
    var notes: String?
    var dueAt: Date?
    var completed: Bool
    var stableID: String?
    var revision: String
}

protocol ReminderBackingStore: Sendable {
    func requestFullAccess() async throws -> Bool
    func lists() throws -> [StoredList]
    func createList(title: String) throws -> StoredList
    func reminders(listIDs: [String]) async throws -> [StoredReminder]
    func save(_ reminder: StoredReminder) throws -> StoredReminder
    func remove(nativeID: String) throws
}

struct HelperRequest: Codable, Sendable {
    let command: String
    let listId: String?
    let listIds: [String]?
    let title: String?
    let dueAt: String?
    let notes: String?
    let externalId: String?
    let id: String?
    let operationKey: String?
    let completedAt: String?
    let approved: Bool?
    let createList: Bool?
    let redactTitles: Bool?
}

struct HelperList: Codable, Equatable, Sendable {
    let id: String
    let title: String
}

struct HelperItem: Codable, Equatable, Sendable {
    let id: String
    let listId: String
    let title: String
    let dueAt: String?
    let notes: String?
    let completed: Bool
    let revision: String
}

struct HelperResponse: Codable, Equatable, Sendable {
    var ok = true
    var authorized: Bool?
    var id: String?
    var revision: String?
    var lists: [HelperList]?
    var items: [HelperItem]?
    var error: String?
}

func processRequestLine(_ line: String, store: EventKitStore) async -> HelperResponse {
    do {
        guard let data = line.data(using: .utf8) else { throw HelperFailure.invalidRequest }
        let request = try JSONDecoder().decode(HelperRequest.self, from: data)
        return try await store.execute(request)
    } catch let failure as HelperFailure {
        return HelperResponse(ok: false, error: failure.code)
    } catch is DecodingError {
        return HelperResponse(ok: false, error: "invalid_request")
    } catch {
        return HelperResponse(ok: false, error: "eventkit_error")
    }
}

actor EventKitStore {
    static let markerPrefix = "rhize-tasks:item:"

    private let eventStore: any ReminderBackingStore
    private let allowedListID: String
    private let dateFormatter: ISO8601DateFormatter

    init(eventStore: any ReminderBackingStore, allowedListID: String) {
        self.eventStore = eventStore
        self.allowedListID = allowedListID
        self.dateFormatter = ISO8601DateFormatter()
        self.dateFormatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    }

    func execute(_ request: HelperRequest) async throws -> HelperResponse {
        switch request.command {
        case "authorize":
            let authorized = try await eventStore.requestFullAccess()
            guard authorized else { throw HelperFailure.authorizationDenied }
            if request.createList == true {
                guard request.approved == true else { throw HelperFailure.approvalRequired }
                let existing = try eventStore.lists().first { $0.title == "Rhize Tasks" }
                let list = try existing ?? eventStore.createList(title: "Rhize Tasks")
                return HelperResponse(authorized: true, lists: [HelperList(id: list.id, title: list.title)])
            }
            return HelperResponse(authorized: true)
        case "lists":
            return HelperResponse(lists: try eventStore.lists().map { HelperList(id: $0.id, title: $0.title) })
        case "snapshot":
            let requested = request.listIds ?? []
            guard !allowedListID.isEmpty, !requested.isEmpty, requested.allSatisfy({ $0 == allowedListID }) else {
                throw HelperFailure.outOfScope
            }
            let redact = request.redactTitles ?? false
            let reminders = try await eventStore.reminders(listIDs: requested)
            return HelperResponse(items: reminders.map { item in
                HelperItem(
                    id: item.stableID ?? "eventkit:\(item.nativeID)",
                    listId: item.listID,
                    title: redact ? "Busy" : item.title,
                    dueAt: item.dueAt.map(dateFormatter.string(from:)),
                    notes: redact ? nil : item.notes,
                    completed: item.completed,
                    revision: item.revision
                )
            })
        case "upsert":
            return try await upsert(request)
        case "complete":
            return try await mutate(request, delete: false)
        case "delete":
            return try await mutate(request, delete: true)
        default:
            throw HelperFailure.invalidRequest
        }
    }

    private func requireAllowedList(_ listID: String?) throws -> String {
        guard let listID, !listID.isEmpty, listID == allowedListID else { throw HelperFailure.outOfScope }
        guard try eventStore.lists().contains(where: { $0.id == listID }) else { throw HelperFailure.listNotFound }
        return listID
    }

    private func upsert(_ request: HelperRequest) async throws -> HelperResponse {
        let listID = try requireAllowedList(request.listId)
        guard let externalID = request.externalId, isSafeStableID(externalID),
              let title = request.title, !title.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            throw HelperFailure.invalidRequest
        }
        let dueAt: Date?
        if let value = request.dueAt {
            guard let parsed = Self.parseISODate(value) else { throw HelperFailure.invalidRequest }
            dueAt = parsed
        } else {
            dueAt = nil
        }
        let existing = try await eventStore.reminders(listIDs: [listID]).first { $0.stableID == externalID }
        let marker = Self.markerPrefix + externalID
        let notes = mergeMarker(notes: request.notes, marker: marker)
        let base = existing ?? StoredReminder(
            nativeID: UUID().uuidString.lowercased(),
            listID: listID,
            title: title,
            notes: notes,
            dueAt: dueAt,
            completed: false,
            stableID: externalID,
            revision: request.operationKey ?? UUID().uuidString.lowercased()
        )
        let saved = try eventStore.save(StoredReminder(
            nativeID: base.nativeID,
            listID: listID,
            title: title,
            notes: notes,
            dueAt: dueAt,
            completed: base.completed,
            stableID: externalID,
            revision: request.operationKey ?? base.revision
        ))
        return HelperResponse(id: externalID, revision: saved.revision)
    }

    private func mutate(_ request: HelperRequest, delete: Bool) async throws -> HelperResponse {
        let listID = try requireAllowedList(request.listId)
        guard let id = request.id, isSafeStableID(id) else { throw HelperFailure.invalidRequest }
        let reminders = try await eventStore.reminders(listIDs: [listID])
        guard var reminder = reminders.first(where: {
            $0.stableID == id || "eventkit:\($0.nativeID)" == id
        }) else { throw HelperFailure.reminderNotFound }
        if delete {
            try eventStore.remove(nativeID: reminder.nativeID)
        } else {
            reminder.completed = true
            reminder.revision = request.operationKey ?? reminder.revision
            let saved = try eventStore.save(reminder)
            return HelperResponse(id: id, revision: saved.revision)
        }
        return HelperResponse(id: id, revision: request.operationKey ?? reminder.revision)
    }

    private func isSafeStableID(_ value: String) -> Bool {
        !value.isEmpty && value.count <= 512 && !value.unicodeScalars.contains(where: CharacterSet.controlCharacters.contains)
    }

    private func mergeMarker(notes: String?, marker: String) -> String {
        let visible = (notes ?? "")
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.hasPrefix(Self.markerPrefix) }
            .joined(separator: "\n")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        return visible.isEmpty ? marker : "\(visible)\n\n\(marker)"
    }

    static func stableID(from notes: String?) -> String? {
        notes?.split(separator: "\n").lazy.compactMap { line -> String? in
            let value = String(line)
            guard value.hasPrefix(markerPrefix) else { return nil }
            let id = String(value.dropFirst(markerPrefix.count))
            return id.isEmpty ? nil : id
        }.first
    }

    private static func parseISODate(_ value: String) -> Date? {
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = fractional.date(from: value) { return date }
        let standard = ISO8601DateFormatter()
        return standard.date(from: value)
    }
}

final class SystemEventKitBackingStore: ReminderBackingStore, @unchecked Sendable {
    private let store = EKEventStore()

    func requestFullAccess() async throws -> Bool {
        try await store.requestFullAccessToReminders()
    }

    func lists() throws -> [StoredList] {
        store.calendars(for: .reminder).map { StoredList(id: $0.calendarIdentifier, title: $0.title) }
    }

    func createList(title: String) throws -> StoredList {
        let calendar = EKCalendar(for: .reminder, eventStore: store)
        calendar.title = title
        calendar.source = store.defaultCalendarForNewReminders()?.source ?? store.sources.first { $0.sourceType == .local }
        try store.saveCalendar(calendar, commit: true)
        return StoredList(id: calendar.calendarIdentifier, title: calendar.title)
    }

    func reminders(listIDs: [String]) async throws -> [StoredReminder] {
        let calendars = store.calendars(for: .reminder).filter { listIDs.contains($0.calendarIdentifier) }
        return try await withCheckedThrowingContinuation { continuation in
            let predicate = store.predicateForReminders(in: calendars)
            store.fetchReminders(matching: predicate) { reminders in
                continuation.resume(returning: (reminders ?? []).map(Self.storedReminder))
            }
        }
    }

    func save(_ reminder: StoredReminder) throws -> StoredReminder {
        let calendars = store.calendars(for: .reminder)
        guard let calendar = calendars.first(where: { $0.calendarIdentifier == reminder.listID }) else {
            throw HelperFailure.listNotFound
        }
        let value: EKReminder
        if let existing = store.calendarItem(withIdentifier: reminder.nativeID) as? EKReminder {
            value = existing
        } else {
            value = EKReminder(eventStore: store)
            value.calendar = calendar
        }
        value.title = reminder.title
        value.notes = reminder.notes
        value.isCompleted = reminder.completed
        if let dueAt = reminder.dueAt {
            value.dueDateComponents = Calendar(identifier: .gregorian).dateComponents(
                [.year, .month, .day, .hour, .minute, .second, .timeZone], from: dueAt
            )
        } else {
            value.dueDateComponents = nil
        }
        try store.save(value, commit: true)
        return Self.storedReminder(value)
    }

    func remove(nativeID: String) throws {
        guard let reminder = store.calendarItem(withIdentifier: nativeID) as? EKReminder else {
            throw HelperFailure.reminderNotFound
        }
        try store.remove(reminder, commit: true)
    }

    private static func storedReminder(_ reminder: EKReminder) -> StoredReminder {
        StoredReminder(
            nativeID: reminder.calendarItemIdentifier,
            listID: reminder.calendar.calendarIdentifier,
            title: reminder.title,
            notes: reminder.notes,
            dueAt: reminder.dueDateComponents.flatMap { Calendar(identifier: .gregorian).date(from: $0) },
            completed: reminder.isCompleted,
            stableID: EventKitStore.stableID(from: reminder.notes),
            revision: String(reminder.lastModifiedDate?.timeIntervalSince1970 ?? 0)
        )
    }
}

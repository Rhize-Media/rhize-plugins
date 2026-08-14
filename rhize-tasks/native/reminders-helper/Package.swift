// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "RhizeRemindersHelper",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "RhizeRemindersHelper", targets: ["RhizeRemindersHelper"])
    ],
    targets: [
        .executableTarget(name: "RhizeRemindersHelper"),
        .testTarget(
            name: "RhizeRemindersHelperTests",
            dependencies: ["RhizeRemindersHelper"]
        )
    ]
)

import AppKit
import AVFoundation
import CoreGraphics
import Foundation
import ScreenCaptureKit

struct CaptureError: Error, CustomStringConvertible {
    let description: String
}

final class RecordingDelegate: NSObject, SCRecordingOutputDelegate {
    private let lock = NSLock()
    private var completion: Result<Void, Error>?
    func recordingOutputDidStartRecording(_ output: SCRecordingOutput) {
        print("RECORDING_STARTED")
        fflush(stdout)
    }
    func recordingOutput(_ output: SCRecordingOutput, didFailWithError error: Error) {
        lock.lock(); defer { lock.unlock() }
        completion = .failure(error)
    }
    func recordingOutputDidFinishRecording(_ output: SCRecordingOutput) {
        lock.lock(); defer { lock.unlock() }
        if completion == nil { completion = .success(()) }
    }
    func result() -> Result<Void, Error>? {
        lock.lock(); defer { lock.unlock() }
        return completion
    }
}

@available(macOS 15.0, *)
@MainActor
func run() async throws {
    _ = NSApplication.shared
    let args = Array(CommandLine.arguments.dropFirst())
    guard args.count >= 2 else { throw CaptureError(description: "Expected --list <bundle-id> or --record <plan.json>") }
    guard CGPreflightScreenCaptureAccess() else {
        throw CaptureError(description: "Screen Recording permission is unavailable. Enable it for the invoking terminal/host in System Settings, then retry; no permission prompt was requested.")
    }
    let content = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: true)
    if args[0] == "--list" {
        let windows = content.windows.filter { $0.owningApplication?.bundleIdentifier == args[1] }
        let rows: [[String: Any]] = windows.map {
            ["window_id": $0.windowID, "bundle_id": args[1], "title": $0.title ?? "",
             "width": $0.frame.width, "height": $0.frame.height]
        }
        let data = try JSONSerialization.data(withJSONObject: rows, options: [.sortedKeys])
        print(String(decoding: data, as: UTF8.self))
        return
    }
    guard args[0] == "--record",
          let plan = try JSONSerialization.jsonObject(with: Data(contentsOf: URL(fileURLWithPath: args[1]))) as? [String: Any],
          let bundleID = plan["bundle_id"] as? String,
          let windowID = plan["window_id"] as? Int,
          let destination = plan["output"] as? String,
          let duration = plan["duration"] as? Double,
          let width = plan["width"] as? Int, let height = plan["height"] as? Int,
          let fps = plan["fps"] as? Int,
          plan["capture_scope"] as? String == "window", plan["include_cursor"] as? Bool == false,
          duration.isFinite, duration > 0, duration <= 3600,
          width > 0, width <= 7680, height > 0, height <= 7680, fps > 0, fps <= 60 else {
        throw CaptureError(description: "Invalid bounded window recording plan")
    }
    guard let window = content.windows.first(where: {
        Int($0.windowID) == windowID && $0.owningApplication?.bundleIdentifier == bundleID
    }) else { throw CaptureError(description: "Selected window no longer belongs to the requested application; select a current window ID") }
    guard !FileManager.default.fileExists(atPath: destination) else {
        throw CaptureError(description: "Refusing to overwrite recording")
    }
    let config = SCStreamConfiguration()
    config.width = width; config.height = height
    config.minimumFrameInterval = CMTime(value: 1, timescale: Int32(fps))
    config.showsCursor = false; config.capturesAudio = false; config.scalesToFit = true
    let delegate = RecordingDelegate()
    let outputConfig = SCRecordingOutputConfiguration()
    outputConfig.outputURL = URL(fileURLWithPath: destination)
    outputConfig.videoCodecType = .h264; outputConfig.outputFileType = .mov
    let recording = SCRecordingOutput(configuration: outputConfig, delegate: delegate)
    let stream = SCStream(filter: SCContentFilter(desktopIndependentWindow: window), configuration: config, delegate: nil)
    try stream.addRecordingOutput(recording)
    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
        stream.startCapture { error in
            if let error { continuation.resume(throwing: error) } else { continuation.resume() }
        }
    }
    try await Task.sleep(nanoseconds: UInt64(duration * 1_000_000_000))
    try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<Void, Error>) in
        stream.stopCapture { error in
            if let error { continuation.resume(throwing: error) } else { continuation.resume() }
        }
    }
    for _ in 0..<100 {
        if let result = delegate.result() { try result.get(); print("RECORDING_FINISHED"); return }
        try await Task.sleep(nanoseconds: 100_000_000)
    }
    throw CaptureError(description: "Recording did not finalize within 10 seconds")
}

do {
    if #available(macOS 15.0, *) { try await run() }
    else { throw CaptureError(description: "Native window recording requires macOS 15 or newer") }
} catch {
    FileHandle.standardError.write(Data("\(error)\n".utf8))
    exit(2)
}

//
// swiftui-headless-capture-template.swift
// Reference Blueprint for Headless macOS SwiftUI App Store Screenshot Capture
//
// Complies with:
// 1. Apple App Store 24-bit RGB (Zero-Alpha / ITMS-90111) specification
// 2. RFC #46 4-Layer Workspace Architecture:
//    - Raw outputs:  .creative/inputs/screenshots/raw/
//    - Scene cache:  .creative/.cache/raw_scenes/
// 3. Independent script execution via `swift <script-path>`
//

import SwiftUI
import AppKit

struct HeadlessCapturePipeline {
    @MainActor
    static func main() {
        let rootURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        
        // 1. Resolve RFC #46 4-Layer target directories
        let rawInputsDir = rootURL.appendingPathComponent(".creative/inputs/screenshots/raw")
        let cacheScenesDir = rootURL.appendingPathComponent(".creative/.cache/raw_scenes")
        
        try! FileManager.default.createDirectory(at: rawInputsDir, withIntermediateDirectories: true)
        try! FileManager.default.createDirectory(at: cacheScenesDir, withIntermediateDirectories: true)

        // 2. High-Fidelity 24-Bit RGB (Zero-Alpha) Image Exporter
        func export24BitRGB<V: View>(_ view: V, to urls: [URL]) {
            let renderer = ImageRenderer(content: view)
            renderer.scale = 2.0 // 1440x900 base @2x Retina = 2880x1800 exact Mac App Store resolution
            
            guard let cgImage = renderer.cgImage else {
                fatalError("ImageRenderer failed to synthesize CGImage from SwiftUI view hierarchy.")
            }
            
            let sourceRep = NSBitmapImageRep(cgImage: cgImage)
            
            // Allocate strict 24-bit RGB bitmap buffer (8 bits/sample, 3 samples/pixel, no alpha)
            guard let rgbRep = NSBitmapImageRep(
                bitmapDataPlanes: nil,
                pixelsWide: sourceRep.pixelsWide,
                pixelsHigh: sourceRep.pixelsHigh,
                bitsPerSample: 8,
                samplesPerPixel: 3,
                hasAlpha: false,
                isPlanar: false,
                colorSpaceName: .deviceRGB,
                bytesPerRow: sourceRep.pixelsWide * 3,
                bitsPerPixel: 24
            ) else {
                fatalError("Failed to allocate 24-bit RGB NSBitmapImageRep.")
            }

            NSGraphicsContext.saveGraphicsState()
            let context = NSGraphicsContext(bitmapImageRep: rgbRep)
            NSGraphicsContext.current = context

            // Draw opaque background under view pixels to prevent transparent alpha artifacts
            NSColor(calibratedRed: 0.08, green: 0.10, blue: 0.14, alpha: 1.0).setFill()
            NSRect(x: 0, y: 0, width: sourceRep.pixelsWide, height: sourceRep.pixelsHigh).fill()

            sourceRep.draw(in: NSRect(x: 0, y: 0, width: sourceRep.pixelsWide, height: sourceRep.pixelsHigh))
            NSGraphicsContext.restoreGraphicsState()

            guard let pngData = rgbRep.representation(using: .png, properties: [:]) else {
                fatalError("Failed to encode 24-bit RGB PNG representation.")
            }

            for url in urls {
                try! pngData.write(to: url)
                print("Exported: \(url.path) [\(rgbRep.pixelsWide)x\(rgbRep.pixelsHigh) 24-bit RGB]")
            }
        }

        // 3. Render Sample / Production Views
        // Replace with your real app SwiftUI views:
        let sampleHeroView = ZStack {
            Color(red: 0.10, green: 0.12, blue: 0.16)
            VStack(spacing: 24) {
                Image(systemName: "shippingbox.fill")
                    .font(.system(size: 64))
                    .foregroundStyle(.cyan)
                Text("Your App Name")
                    .font(.system(size: 36, weight: .bold))
                    .foregroundStyle(.white)
                Text("Instant inspection, trace origins, and manage system assets.")
                    .font(.headline)
                    .foregroundStyle(.secondary)
            }
        }
        .frame(width: 1440, height: 900)
        .environment(\.colorScheme, .dark)

        export24BitRGB(sampleHeroView, to: [
            rawInputsDir.appendingPathComponent("01-hero-explorer.png"),
            cacheScenesDir.appendingPathComponent("scene1.png")
        ])
    }
}

MainActor.assumeIsolated {
    HeadlessCapturePipeline.main()
}

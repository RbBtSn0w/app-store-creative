//
// swiftui-scene-compositor-template.swift
// Reference Blueprint for Commercial Video Scene Frame Composition in SwiftUI
//
// Complies with:
// 1. Apple App Store 1920x1080 30fps landscape video scene requirements
// 2. RFC #46 4-Layer Workspace Architecture:
//    - Raw captures:     .creative/inputs/screenshots/raw/
//    - Presenter assets: .creative/inputs/presenter/
//    - Output scenes:    .creative/.cache/scenes/
//

import SwiftUI
import AppKit

@main
struct VideoSceneCompositorPipeline {
    @MainActor
    static func main() {
        let rootURL = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
        let rawDir = rootURL.appendingPathComponent(".creative/inputs/screenshots/raw")
        let poseDir = rootURL.appendingPathComponent(".creative/inputs/presenter")
        let outDir = rootURL.appendingPathComponent(".creative/.cache/scenes")
        
        try! FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true, attributes: nil)

        func loadImage(from url: URL) -> NSImage? {
            return NSImage(contentsOf: url)
        }

        struct SceneSpec {
            let filename: String
            let stepBadge: String
            let headline: String
            let appWindowImage: NSImage?
            let presenterImage: NSImage?
            let subtitleText: String
            let accentColor: Color
            let soundwaveHeights: [CGFloat]
        }

        // Example scene specification
        let scenes: [SceneSpec] = [
            SceneSpec(
                filename: "scene_01.png",
                stepBadge: "01 / 04 • OVERVIEW",
                headline: "Instant Package & Receipt Inspection",
                appWindowImage: loadImage(from: rawDir.appendingPathComponent("01-hero-explorer.png")),
                presenterImage: loadImage(from: poseDir.appendingPathComponent("pose1_inspect.png")),
                subtitleText: "Inspect every receipt and bill of materials deposited on your Mac in milliseconds.",
                accentColor: Color.cyan,
                soundwaveHeights: [10, 22, 16, 26, 14, 24, 18, 12, 20]
            )
        ]

        for spec in scenes {
            let sceneView = ZStack {
                // 1. Ambient Dark Titanium / Obsidian Gradient Canvas
                LinearGradient(
                    colors: [
                        Color(red: 0.02, green: 0.04, blue: 0.08),
                        Color(red: 0.05, green: 0.10, blue: 0.22),
                        Color(red: 0.01, green: 0.16, blue: 0.38),
                        Color(red: 0.03, green: 0.06, blue: 0.14)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                // 2. Soft Ambient Accent Glows
                Circle()
                    .fill(spec.accentColor.opacity(0.18))
                    .frame(width: 760, height: 760)
                    .blur(radius: 130)
                    .offset(x: -420, y: -180)

                // 3. Top Header Bar
                VStack(spacing: 0) {
                    HStack(spacing: 16) {
                        Text("APP PREVIEW")
                            .font(.system(size: 13, weight: .bold, design: .monospaced))
                            .foregroundColor(spec.accentColor)
                            .padding(.horizontal, 14)
                            .padding(.vertical, 7)
                            .background(Color.white.opacity(0.08))
                            .cornerRadius(8)

                        Text(spec.headline)
                            .font(.system(size: 25, weight: .bold, design: .rounded))
                            .foregroundColor(.white)

                        Spacer()

                        Text(spec.stepBadge)
                            .font(.system(size: 12.5, weight: .bold, design: .monospaced))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 7)
                            .background(spec.accentColor.opacity(0.2))
                            .foregroundColor(spec.accentColor)
                            .cornerRadius(8)
                    }
                    .padding(.horizontal, 48)
                    .padding(.top, 28)

                    Spacer()
                }

                // 4. Main App Window Stage (Left-biased for balanced video hierarchy)
                if let win = spec.appWindowImage {
                    Image(nsImage: win)
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 1310)
                        .cornerRadius(14)
                        .shadow(color: Color.black.opacity(0.72), radius: 40, x: 0, y: 22)
                        .offset(x: -185, y: -42)
                }

                // 5. Presenter Avatar & Subtitle HUD (Bottom-Right)
                VStack {
                    Spacer()
                    HStack(alignment: .bottom, spacing: 20) {
                        // Glass Subtitle Panel
                        VStack(alignment: .leading, spacing: 8) {
                            HStack(spacing: 8) {
                                Circle().fill(spec.accentColor).frame(width: 8, height: 8)
                                Text("NARRATION")
                                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                                    .foregroundColor(spec.accentColor)
                                
                                ForEach(0..<spec.soundwaveHeights.count, id: \.self) { i in
                                    RoundedRectangle(cornerRadius: 1.5)
                                        .fill(spec.accentColor)
                                        .frame(width: 3, height: spec.soundwaveHeights[i])
                                }
                            }
                            Text(spec.subtitleText)
                                .font(.system(size: 15, weight: .medium))
                                .foregroundColor(.white)
                                .lineLimit(2)
                        }
                        .padding(16)
                        .frame(width: 520, alignment: .leading)
                        .background(.ultraThinMaterial)
                        .cornerRadius(12)
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(Color.white.opacity(0.12), lineWidth: 1))

                        // Presenter Avatar Squircle
                        if let avatar = spec.presenterImage {
                            Image(nsImage: avatar)
                                .resizable()
                                .aspectRatio(contentMode: .fill)
                                .frame(width: 100, height: 100)
                                .clipShape(RoundedRectangle(cornerRadius: 22))
                                .overlay(RoundedRectangle(cornerRadius: 22).stroke(spec.accentColor.opacity(0.6), lineWidth: 2))
                                .shadow(color: spec.accentColor.opacity(0.3), radius: 12)
                        }
                    }
                    .padding(.horizontal, 48)
                    .padding(.bottom, 36)
                }
            }
            .frame(width: 1920, height: 1080)
            .environment(\.colorScheme, .dark)

            // Render and export frame
            let renderer = ImageRenderer(content: sceneView)
            renderer.scale = 1.0 // 1920x1080 @ 1x = standard landscape video canvas
            guard let cgImg = renderer.cgImage else { continue }
            let rep = NSBitmapImageRep(cgImage: cgImg)
            if let data = rep.representation(using: .png, properties: [:]) {
                let dest = outDir.appendingPathComponent(spec.filename)
                try? data.write(to: dest)
                print("Composed Video Scene: \(dest.path) (1920x1080)")
            }
        }
    }
}

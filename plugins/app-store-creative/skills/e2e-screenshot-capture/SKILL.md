---
name: e2e-screenshot-capture
description: Capture deterministic, named screenshots of real product UI through an application's existing E2E or UI-test journeys. Use when an App Store creative plan needs raw screenshot inputs, capture coverage must change, or stale, mocked, nondeterministic, incorrectly sized, or visually corrupted source pixels must be diagnosed and recaptured.
---

# E2E Screenshot Capture

Resolve `<runtime-root>` as `<plugin-root>/skills/app-store-creative/runtime`.
All executable and template resources ship with the main orchestration skill.


Preserve the established contract: screenshot pixels must come from the running product UI, not a recreation, mock, Figma redraw, or generated image.

## Managed Lifecycle Binding

Read the [managed specialist contract](../app-store-creative/references/specialist-lifecycle.md) and apply it to new work. Use leased attempts and registered input/output artifacts; preserve partial failures and their reasons. A producer receipt or file does not grant approval, seal a delivery, or prove remote readiness. Standalone capture/encoding executors still require this explicit registration adapter.

## Capture

1. Read the run plan and the repository's own test instructions.
2. Start a managed capture attempt before work.
3. Use existing UI-test/E2E journeys when available. Add the narrowest deterministic journey or accessibility seam only when required.
4. Seed stable data, locale, appearance, window/device geometry, and animation state.
5. Capture named checkpoints after the UI reaches a verifiable ready state.
6. Inspect every output for stale content, permission prompts, cursors, focus rings, clipping, blank surfaces, and unexpected chrome.
7. Write a receipt listing command, environment, source revision, checkpoint-to-file mapping, dimensions, and hashes; then register the receipt and terminate the attempt.


## 24-Bit RGB (No-Alpha) Export & SwiftUI View Alignment Gate

### 1. Apple ITMS-90111 Alpha Channel Rejection Prevention
Apple App Store screenshot submission strictly enforces **24-bit RGB without transparency** (`ITMS-90111: Alpha channel found`). When capturing macOS / iOS views programmatically, strip the alpha channel using `NSBitmapImageRep` with `hasAlpha: false`:

```swift
import AppKit

extension NSImage {
    /// Export a clean 24-bit RGB PNG without an alpha channel to prevent App Store rejection.
    func representation24BitRGBPNG() -> Data? {
        guard let tiffData = self.tiffRepresentation,
              let sourceRep = NSBitmapImageRep(data: tiffData) else {
            return nil
        }

        // Allocate a 24-bit RGB bitmap (8 bits per sample, 3 samples per pixel, no alpha)
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
            return nil
        }

        NSGraphicsContext.saveGraphicsState()
        let context = NSGraphicsContext(bitmapImageRep: rgbRep)
        NSGraphicsContext.current = context

        // Draw opaque white or solid background beneath view pixels before rendering
        NSColor.white.setFill()
        NSRect(x: 0, y: 0, width: sourceRep.pixelsWide, height: sourceRep.pixelsHigh).fill()

        sourceRep.draw(in: NSRect(x: 0, y: 0, width: sourceRep.pixelsWide, height: sourceRep.pixelsHigh))
        NSGraphicsContext.restoreGraphicsState()

        return rgbRep.representation(using: .png, properties: [:])
    }
}
```

### 2. SwiftUI Source View 1:1 Alignment Gate
Before executing any capture journey, run an alignment verification to guarantee that screenshot automation renders the latest SwiftUI views:
1. Verify that capture test fixtures directly instantiate the production SwiftUI view hierarchy rather than isolated mocks or frozen mock copies.
2. Confirm that changes to typography, glass effects, layout padding, and status chrome in the application source tree immediately reflect in test renders.
3. Validate exported PNGs with `validator.py` before sealing candidates to ensure absence of alpha transparency (unless explicitly permitted by `allowAlpha`).


Do not claim success from a focused test alone when the product boundary requires a real window, device, permission, or cross-process interaction. Preserve raw captures; downstream design may frame or annotate them but must not alter their UI content.

Read [capture-contract.md](references/capture-contract.md) when defining checkpoints or receipt evidence. Read the orchestrator's [iteration contract](../app-store-creative/references/iteration-contract.md): reproduce affected checkpoints first and recapture outputs according to registered input dependencies. Use the orchestrator's [agent handoff contract](../app-store-creative/references/agent-handoff.md) for leases and completion.

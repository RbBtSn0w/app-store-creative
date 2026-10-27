#!/usr/bin/env swift
import AVFoundation
import Foundation

struct SynthesizerError: Error, CustomStringConvertible {
    let description: String
}

final class SpeechSynthesisWriter: NSObject, AVSpeechSynthesizerDelegate {
    private let synthesizer = AVSpeechSynthesizer()
    private var audioFile: AVAudioFile?
    private let lock = NSLock()
    private var error: Error?
    private var isFinished = false
    private let semaphore = DispatchSemaphore(value: 0)

    func synthesize(text: String, voice: AVSpeechSynthesisVoice, outputURL: URL, rate: Float = 1.0, pitch: Float = 1.0) throws {
        let utterance = AVSpeechUtterance(string: text)
        utterance.voice = voice
        utterance.rate = AVSpeechUtteranceDefaultSpeechRate * rate
        utterance.pitchMultiplier = pitch

        synthesizer.write(utterance) { [weak self] buffer in
            guard let self = self else { return }
            guard let pcmBuffer = buffer as? AVAudioPCMBuffer else { return }

            if pcmBuffer.frameLength == 0 {
                // End of speech buffer sequence
                self.lock.lock()
                self.isFinished = true
                self.lock.unlock()
                self.semaphore.signal()
                return
            }

            self.lock.lock()
            defer { self.lock.unlock() }

            do {
                if self.audioFile == nil {
                    // Create audio file with the native buffer format
                    self.audioFile = try AVAudioFile(
                        forWriting: outputURL,
                        settings: pcmBuffer.format.settings,
                        commonFormat: .pcmFormatFloat32,
                        interleaved: false
                    )
                }
                try self.audioFile?.write(from: pcmBuffer)
            } catch {
                self.error = error
                self.semaphore.signal()
            }
        }

        semaphore.wait()

        lock.lock()
        defer { lock.unlock() }
        if let error = error {
            throw error
        }
        guard isFinished else {
            throw SynthesizerError(description: "Speech synthesis did not complete cleanly")
        }
    }
}

func selectBestVoice(locale: String, voiceName: String? = nil) -> AVSpeechSynthesisVoice? {
    let targetLocale = locale.replacingOccurrences(of: "_", with: "-")
    let voices = AVSpeechSynthesisVoice.speechVoices()

    if let name = voiceName {
        if let match = voices.first(where: { $0.identifier == name || $0.name.lowercased() == name.lowercased() }) {
            return match
        }
    }

    let matchingLocaleVoices = voices.filter {
        $0.language.lowercased() == targetLocale.lowercased() ||
        $0.language.lowercased().starts(with: targetLocale.lowercased() + "-")
    }

    if matchingLocaleVoices.isEmpty {
        return AVSpeechSynthesisVoice(language: targetLocale)
    }

    // Tier 1 in native: Premium neural voice
    if let premium = matchingLocaleVoices.first(where: { $0.quality == .premium }) {
        return premium
    }
    // Tier 2 in native: Enhanced neural voice
    if let enhanced = matchingLocaleVoices.first(where: { $0.quality == .enhanced }) {
        return enhanced
    }
    // Tier 3 in native: Default voice
    return matchingLocaleVoices.first
}

func listVoices(filterLocale: String? = nil) {
    let target = filterLocale?.replacingOccurrences(of: "_", with: "-").lowercased()
    let voices = AVSpeechSynthesisVoice.speechVoices().sorted {
        if $0.language != $1.language { return $0.language < $1.language }
        return $0.name < $1.name
    }

    print(String(format: "%-12@ %-28@ %-12@ %@", "Locale", "Voice Name", "Quality", "Identifier"))
    print(String(repeating: "-", count: 80))

    for voice in voices {
        if let target = target, !voice.language.lowercased().contains(target) {
            continue
        }
        let qualityStr: String
        switch voice.quality {
        case .premium: qualityStr = "Premium"
        case .enhanced: qualityStr = "Enhanced"
        default: qualityStr = "Default"
        }
        print(String(format: "%-12@ %-28@ %-12@ %@", voice.language, voice.name, qualityStr, voice.identifier))
    }
}

// Testing showed +8% to +15% keeps diction clear; +24% clipped leading syllables.
let maxSpeechRate: Float = 1.15

func printUsage() {
    let usage = """
    Usage: macos_speech_synthesizer [options]

    Options:
      --text <string>        Text content to synthesize
      --input <file>         Path to UTF-8 text file to synthesize
      --output <file.wav>    Destination linear PCM audio file (WAV)
      --locale <locale>      Target language/locale (e.g. en-US, zh-CN, ja-JP; default: en-US)
      --voice <id_or_name>   Specific AVSpeechSynthesisVoice identifier or name
      --rate <float>         Speed multiplier (default: 1.0; values above 1.15 are clamped
                             because faster speech truncates short technical words)
      --pitch <float>        Pitch multiplier (default: 1.0)
      --list-voices [locale] List installed macOS neural and standard voices
      -h, --help             Show this help message
    """
    print(usage)
}

func main() {
    let args = Array(CommandLine.arguments.dropFirst())
    if args.isEmpty || args.contains("-h") || args.contains("--help") {
        printUsage()
        exit(0)
    }

    var text: String?
    var inputFile: String?
    var outputFile: String?
    var locale = "en-US"
    var voiceName: String?
    var rate: Float = 1.0
    var pitch: Float = 1.0

    var idx = 0
    while idx < args.count {
        let arg = args[idx]
        switch arg {
        case "--list-voices":
            let filter = (idx + 1 < args.count && !args[idx + 1].starts(with: "--")) ? args[idx + 1] : nil
            listVoices(filterLocale: filter)
            exit(0)
        case "--text":
            idx += 1
            guard idx < args.count else { fputs("Error: --text requires a value\n", stderr); exit(1) }
            text = args[idx]
        case "--input":
            idx += 1
            guard idx < args.count else { fputs("Error: --input requires a path\n", stderr); exit(1) }
            inputFile = args[idx]
        case "--output":
            idx += 1
            guard idx < args.count else { fputs("Error: --output requires a path\n", stderr); exit(1) }
            outputFile = args[idx]
        case "--locale":
            idx += 1
            guard idx < args.count else { fputs("Error: --locale requires a value\n", stderr); exit(1) }
            locale = args[idx]
        case "--voice":
            idx += 1
            guard idx < args.count else { fputs("Error: --voice requires a value\n", stderr); exit(1) }
            voiceName = args[idx]
        case "--rate":
            idx += 1
            guard idx < args.count, let val = Float(args[idx]) else { fputs("Error: --rate requires a float\n", stderr); exit(1) }
            if val > maxSpeechRate {
                fputs("Warning: --rate \(val) exceeds \(maxSpeechRate); clamping to keep speech intelligible\n", stderr)
            }
            rate = min(val, maxSpeechRate)
        case "--pitch":
            idx += 1
            guard idx < args.count, let val = Float(args[idx]) else { fputs("Error: --pitch requires a float\n", stderr); exit(1) }
            pitch = val
        default:
            fputs("Unknown argument: \(arg)\n", stderr)
            printUsage()
            exit(1)
        }
        idx += 1
    }

    if text == nil, let input = inputFile {
        do {
            text = try String(contentsOfFile: input, encoding: .utf8)
        } catch {
            fputs("Failed to read input file \(input): \(error)\n", stderr)
            exit(1)
        }
    }

    guard let speechText = text, !speechText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
        fputs("Error: No speech text provided (--text or --input required)\n", stderr)
        exit(1)
    }

    guard let output = outputFile else {
        fputs("Error: No output file specified (--output required)\n", stderr)
        exit(1)
    }

    guard let voice = selectBestVoice(locale: locale, voiceName: voiceName) else {
        fputs("Error: No speech voice available for locale \(locale)\n", stderr)
        exit(1)
    }

    let outputURL = URL(fileURLWithPath: output)
    let parentDir = outputURL.deletingLastPathComponent().path
    if !FileManager.default.fileExists(atPath: parentDir) {
        do {
            try FileManager.default.createDirectory(atPath: parentDir, withIntermediateDirectories: true)
        } catch {
            fputs("Error creating directory \(parentDir): \(error)\n", stderr)
            exit(1)
        }
    }

    let writer = SpeechSynthesisWriter()
    do {
        try writer.synthesize(text: speechText, voice: voice, outputURL: outputURL, rate: rate, pitch: pitch)
        fputs("Synthesized voiceover successfully using voice: \(voice.name) (\(voice.language))\n", stderr)
    } catch {
        fputs("Failed to synthesize speech: \(error)\n", stderr)
        exit(2)
    }
}

main()

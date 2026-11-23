import Foundation
import Vision

// Vision reports normalized coordinates with the origin at the lower left.
struct Match: Encodable {
    let text: String
    let x, y, width, height: CGFloat
}

let image = URL(fileURLWithPath: CommandLine.arguments[1])
let phrase = CommandLine.arguments[2]
let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.automaticallyDetectsLanguage = true
do {
    try VNImageRequestHandler(url: image).perform([request])
    let matches = (request.results ?? []).compactMap { observation -> Match? in
        guard let text = observation.topCandidates(1).first?.string,
              text.localizedCaseInsensitiveContains(phrase) else { return nil }
        let box = observation.boundingBox
        return Match(text: text, x: box.minX, y: 1 - box.maxY, width: box.width, height: box.height)
    }
    FileHandle.standardOutput.write(try JSONEncoder().encode(matches))
} catch {
    FileHandle.standardError.write(Data(error.localizedDescription.utf8))
    exit(1)
}

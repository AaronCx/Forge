#!/usr/bin/env swift
// ocr-helper.swift — Extract text from an image using Apple Vision framework.
// Usage: ocr-helper <image-path> [--json]
// Outputs recognized text lines, or JSON array with bounding boxes if --json is passed.

import Foundation
import Vision
import AppKit

guard CommandLine.arguments.count >= 2 else {
    fputs("Usage: ocr-helper <image-path> [--json]\n", stderr)
    exit(1)
}

let imagePath = CommandLine.arguments[1]
let jsonMode = CommandLine.arguments.contains("--json")

guard let image = NSImage(contentsOfFile: imagePath),
      let cgImage = image.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    fputs("Error: could not load image at \(imagePath)\n", stderr)
    exit(1)
}

let imageWidth = CGFloat(cgImage.width)
let imageHeight = CGFloat(cgImage.height)

let request = VNRecognizeTextRequest()
request.recognitionLevel = .accurate
request.usesLanguageCorrection = true

let handler = VNImageRequestHandler(cgImage: cgImage, options: [:])
do {
    try handler.perform([request])
} catch {
    fputs("Error: OCR failed: \(error)\n", stderr)
    exit(1)
}

guard let observations = request.results else {
    print(jsonMode ? "[]" : "")
    exit(0)
}

if jsonMode {
    var elements: [[String: Any]] = []
    for obs in observations {
        guard let candidate = obs.topCandidates(1).first else { continue }
        let box = obs.boundingBox
        // Convert from normalized (bottom-left origin) to pixel coords (top-left origin)
        let x = Int(box.origin.x * imageWidth)
        let y = Int((1 - box.origin.y - box.height) * imageHeight)
        let w = Int(box.width * imageWidth)
        let h = Int(box.height * imageHeight)
        elements.append([
            "text": candidate.string,
            "confidence": candidate.confidence,
            "x": x,
            "y": y,
            "width": w,
            "height": h,
        ])
    }
    if let data = try? JSONSerialization.data(withJSONObject: elements, options: [.sortedKeys]),
       let str = String(data: data, encoding: .utf8) {
        print(str)
    }
} else {
    for obs in observations {
        if let candidate = obs.topCandidates(1).first {
            print(candidate.string)
        }
    }
}

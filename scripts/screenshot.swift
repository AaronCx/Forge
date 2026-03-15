#!/usr/bin/env swift
// screenshot.swift — Capture screen via ScreenCaptureKit (works over SSH on macOS 15+).
// Usage: screenshot <output-path>

import Foundation
import ScreenCaptureKit
import CoreGraphics
import ImageIO
import UniformTypeIdentifiers

guard CommandLine.arguments.count >= 2 else {
    fputs("Usage: screenshot <output-path>\n", stderr)
    exit(1)
}

let outputPath = CommandLine.arguments[1]

let semaphore = DispatchSemaphore(value: 0)
var capturedImage: CGImage?
var captureError: Error?

Task {
    do {
        let content = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: false)
        guard let display = content.displays.first else {
            fputs("Error: no displays found\n", stderr)
            exit(1)
        }

        let filter = SCContentFilter(display: display, excludingWindows: [])
        let config = SCStreamConfiguration()
        config.width = display.width
        config.height = display.height
        config.pixelFormat = kCVPixelFormatType_32BGRA
        config.showsCursor = false

        capturedImage = try await SCScreenshotManager.captureImage(
            contentFilter: filter,
            configuration: config
        )
    } catch {
        captureError = error
    }
    semaphore.signal()
}

semaphore.wait()

if let error = captureError {
    fputs("Error: \(error.localizedDescription)\n", stderr)
    exit(1)
}

guard let image = capturedImage else {
    fputs("Error: no image captured\n", stderr)
    exit(1)
}

let url = URL(fileURLWithPath: outputPath) as CFURL
guard let dest = CGImageDestinationCreateWithURL(url, UTType.png.identifier as CFString, 1, nil) else {
    fputs("Error: could not create image destination\n", stderr)
    exit(1)
}

CGImageDestinationAddImage(dest, image, nil)
guard CGImageDestinationFinalize(dest) else {
    fputs("Error: could not write image\n", stderr)
    exit(1)
}

print("{\"success\":true,\"width\":\(image.width),\"height\":\(image.height),\"path\":\"\(outputPath)\"}")

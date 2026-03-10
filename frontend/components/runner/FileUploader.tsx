"use client";

import { useRef } from "react";
import { Button } from "@/components/ui/button";

interface FileUploaderProps {
  onFileSelect: (file: File) => void;
  selectedFile: File | null;
}

export function FileUploader({ onFileSelect, selectedFile }: FileUploaderProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt,.csv,.json"
        className="hidden"
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelect(file);
        }}
      />
      <Button
        type="button"
        variant="outline"
        size="sm"
        onClick={() => inputRef.current?.click()}
      >
        {selectedFile ? selectedFile.name : "Upload File"}
      </Button>
      {selectedFile && (
        <p className="mt-1 text-xs text-muted-foreground">
          {(selectedFile.size / 1024).toFixed(1)} KB
        </p>
      )}
    </div>
  );
}

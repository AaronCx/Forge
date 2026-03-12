"use client";

import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import { api, KnowledgeCollection, KnowledgeDocument, SearchResult } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { isDemoMode } from "@/lib/demo-data";

const STATUS_COLORS: Record<string, string> = {
  pending: "bg-yellow-500",
  processing: "bg-blue-500",
  ready: "bg-green-500",
  error: "bg-red-500",
};

export default function KnowledgePage() {
  const [collections, setCollections] = useState<KnowledgeCollection[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCollection, setSelectedCollection] = useState<string>("");
  const [documents, setDocuments] = useState<KnowledgeDocument[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<SearchResult[]>([]);
  const [searching, setSearching] = useState(false);

  // Create collection form
  const [showCreate, setShowCreate] = useState(false);
  const [newName, setNewName] = useState("");
  const [newDesc, setNewDesc] = useState("");

  // Add document form
  const [showAddDoc, setShowAddDoc] = useState(false);
  const [docFilename, setDocFilename] = useState("");
  const [docText, setDocText] = useState("");

  useEffect(() => {
    if (isDemoMode()) {
      setCollections([]);
      setLoading(false);
      return;
    }
    loadCollections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedCollection) {
      loadDocuments(selectedCollection);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCollection]);

  async function loadCollections() {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      const list = await api.knowledge.collections(data.session.access_token);
      setCollections(list);
      if (list.length > 0 && !selectedCollection) {
        setSelectedCollection(list[0].id);
      }
    } catch {
      // ignore
    } finally {
      setLoading(false);
    }
  }

  async function loadDocuments(collectionId: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      const docs = await api.knowledge.documents(collectionId, data.session.access_token);
      setDocuments(docs);
    } catch {
      setDocuments([]);
    }
  }

  async function handleCreateCollection() {
    if (!newName.trim()) return;
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      await api.knowledge.createCollection(
        { name: newName, description: newDesc },
        data.session.access_token,
      );
      setNewName("");
      setNewDesc("");
      setShowCreate(false);
      await loadCollections();
    } catch {
      // ignore
    }
  }

  async function handleDeleteCollection(id: string) {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      await api.knowledge.deleteCollection(id, data.session.access_token);
      if (selectedCollection === id) setSelectedCollection("");
      await loadCollections();
    } catch {
      // ignore
    }
  }

  async function handleAddDocument() {
    if (!docFilename.trim() || !docText.trim()) return;
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    try {
      await api.knowledge.addDocument(
        selectedCollection,
        { filename: docFilename, raw_text: docText },
        data.session.access_token,
      );
      setDocFilename("");
      setDocText("");
      setShowAddDoc(false);
      await loadDocuments(selectedCollection);
      await loadCollections();
    } catch {
      // ignore
    }
  }

  async function handleSearch() {
    if (!searchQuery.trim() || !selectedCollection) return;
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    setSearching(true);
    try {
      const results = await api.knowledge.search(
        selectedCollection,
        { query: searchQuery, top_k: 5 },
        data.session.access_token,
      );
      setSearchResults(results);
    } catch {
      setSearchResults([]);
    } finally {
      setSearching(false);
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Knowledge Base</h1>
          <p className="mt-1 text-muted-foreground">
            Upload documents, generate embeddings, and search with RAG
          </p>
        </div>
        <Button size="sm" onClick={() => setShowCreate(!showCreate)}>
          {showCreate ? "Cancel" : "New Collection"}
        </Button>
      </div>

      {/* Create collection form */}
      {showCreate && (
        <Card className="mt-4">
          <CardContent className="p-4 space-y-3">
            <Input
              placeholder="Collection name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <Input
              placeholder="Description (optional)"
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
            />
            <Button size="sm" onClick={handleCreateCollection}>
              Create Collection
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Collections list */}
        <div className="space-y-2">
          <h2 className="text-sm font-medium text-muted-foreground">Collections</h2>
          {loading ? (
            <div className="space-y-2">
              {[1, 2].map((i) => (
                <div key={i} className="h-16 animate-pulse rounded-lg bg-muted" />
              ))}
            </div>
          ) : collections.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No collections yet. Create one to get started.
            </p>
          ) : (
            collections.map((col) => (
              <Card
                key={col.id}
                className={`cursor-pointer transition-colors hover:border-primary/50 ${
                  selectedCollection === col.id ? "border-primary" : ""
                }`}
                onClick={() => {
                  setSelectedCollection(col.id);
                  setSearchResults([]);
                }}
              >
                <CardContent className="p-3">
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{col.name}</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      className="h-6 w-6 p-0 text-muted-foreground"
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteCollection(col.id);
                      }}
                    >
                      x
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground mt-1">
                    {col.document_count} docs, {col.chunk_count} chunks
                  </p>
                </CardContent>
              </Card>
            ))
          )}
        </div>

        {/* Documents + Search */}
        <div className="lg:col-span-2 space-y-4">
          {selectedCollection ? (
            <>
              {/* Search */}
              <div className="flex gap-2">
                <Input
                  placeholder="Search knowledge base..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleSearch()}
                  className="flex-1"
                />
                <Button onClick={handleSearch} disabled={searching}>
                  {searching ? "Searching..." : "Search"}
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setShowAddDoc(!showAddDoc)}
                >
                  {showAddDoc ? "Cancel" : "Add Doc"}
                </Button>
              </div>

              {/* Add document form */}
              {showAddDoc && (
                <Card>
                  <CardContent className="p-4 space-y-3">
                    <Input
                      placeholder="Filename (e.g., guide.txt)"
                      value={docFilename}
                      onChange={(e) => setDocFilename(e.target.value)}
                    />
                    <textarea
                      placeholder="Paste document text here..."
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm min-h-[120px]"
                      value={docText}
                      onChange={(e) => setDocText(e.target.value)}
                    />
                    <Button size="sm" onClick={handleAddDocument}>
                      Add Document
                    </Button>
                  </CardContent>
                </Card>
              )}

              {/* Search results */}
              {searchResults.length > 0 && (
                <div className="space-y-2">
                  <h3 className="text-sm font-medium text-muted-foreground">
                    Search Results ({searchResults.length})
                  </h3>
                  {searchResults.map((result) => (
                    <Card key={result.chunk_id}>
                      <CardContent className="p-3">
                        <div className="flex items-center gap-2 mb-1">
                          <Badge variant="outline" className="text-xs">
                            {(result.similarity * 100).toFixed(1)}% match
                          </Badge>
                          <span className="text-xs text-muted-foreground font-mono">
                            chunk #{result.chunk_index}
                          </span>
                        </div>
                        <p className="text-sm whitespace-pre-wrap line-clamp-4">
                          {result.content}
                        </p>
                      </CardContent>
                    </Card>
                  ))}
                </div>
              )}

              {/* Documents list */}
              <div className="space-y-2">
                <h3 className="text-sm font-medium text-muted-foreground">
                  Documents ({documents.length})
                </h3>
                {documents.length === 0 ? (
                  <p className="text-sm text-muted-foreground">
                    No documents yet. Click &quot;Add Doc&quot; to upload text.
                  </p>
                ) : (
                  documents.map((doc) => (
                    <Card key={doc.id}>
                      <CardContent className="flex items-center gap-3 py-3">
                        <div
                          className={`h-2.5 w-2.5 rounded-full ${STATUS_COLORS[doc.status] || "bg-gray-500"}`}
                        />
                        <span className="text-sm font-medium flex-1">
                          {doc.filename}
                        </span>
                        <Badge variant="outline" className="text-xs">
                          {doc.status}
                        </Badge>
                        <span className="text-xs text-muted-foreground">
                          {doc.chunk_count} chunks
                        </span>
                        <span className="text-xs text-muted-foreground">
                          {(doc.file_size / 1024).toFixed(1)}KB
                        </span>
                      </CardContent>
                    </Card>
                  ))
                )}
              </div>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">
              Select a collection to view documents and search.
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
